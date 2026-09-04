from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

import pytest
from sqlmodel import Session

from app.models import Participant, Visit
from app.openmatb_runtime import OpenMatbManager, OpenMatbRuntimeError
from app.openmatb_schemas import ClonePresetRequest, CreateOpenMatbSession, UpdatePresetRequest


def _manager(engine, tmp_path: Path) -> OpenMatbManager:
    return OpenMatbManager(
        engine=engine,
        repo_root=Path(__file__).resolve().parents[3],
        artifact_root=tmp_path / "controlled",
        python_executable=Path(__file__),
    )


def _seed_visit(engine) -> None:
    with Session(engine) as db:
        db.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        db.add(Visit(participant_id="P01", visit_ordinal=1, scheduled_day=0))
        db.commit()


def test_create_session_generates_versioned_spanish_counterbalanced_suite(engine, tmp_path):
    _seed_visit(engine)
    manager = _manager(engine, tmp_path)

    prepared = asyncio.run(manager.create_session(CreateOpenMatbSession(participant_id="P01", visit_ordinal=1)))

    assert prepared.session.lifecycle == "INSTRUCTIONS"
    assert prepared.session.visual_theme == "classic"
    assert prepared.session.block_order[0] == "PRACTICE"
    assert set(prepared.session.block_order[1:]) == {"LOW", "MEDIUM", "HIGH"}
    run_root = Path(manager.artifact_root) / prepared.session.id
    scenarios = sorted((run_root / "scenarios").glob("*.txt"))
    assert len(scenarios) == 4
    for scenario in scenarios:
        assert ";genericscales;filename;isa_es.txt" in scenario.read_text(encoding="utf-8")
        manifest = json.loads(Path(f"{scenario}.manifest.json").read_text(encoding="utf-8"))
        assert manifest["questionnaires"]["isa"] == "isa_es.txt"
        expected_profile = scenario.stem.split("_", 1)[1]
        assert manifest["parameters"]["suite_profile_name"] == expected_profile
        assert manifest["parameters"]["difficulty"] >= 0
    assert prepared.controller_lease not in (run_root / "scenarios" / "0_PRACTICE.txt").read_text(encoding="utf-8")


def test_cockpit_theme_is_frozen_in_session_and_scenario_provenance(engine, tmp_path):
    _seed_visit(engine)
    manager = _manager(engine, tmp_path)

    prepared = asyncio.run(manager.create_session(CreateOpenMatbSession(
        participant_id="P01", visit_ordinal=1, visual_theme="cockpit",
    )))

    assert prepared.session.visual_theme == "cockpit"
    run_root = Path(manager.artifact_root) / prepared.session.id
    for manifest_path in sorted((run_root / "scenarios").glob("*.manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["parameters"]["visual_theme"] == "cockpit"


def test_published_preset_is_immutable_and_clone_is_editable(engine, tmp_path):
    manager = _manager(engine, tmp_path)
    published = manager.list_presets()[0]

    with pytest.raises(OpenMatbRuntimeError, match="published_configuration_immutable"):
        manager.update_preset(published.preset_id, published.version, UpdatePresetRequest(profiles=published.profiles))

    draft = manager.clone_preset(
        published.preset_id,
        published.version,
        ClonePresetRequest(preset_id="matb-fac-study", version="1.0.1", label_es="Estudio uno"),
    )
    assert draft.status == "draft"


def test_participant_token_is_required_for_acknowledgement(engine, tmp_path):
    _seed_visit(engine)
    manager = _manager(engine, tmp_path)
    prepared = asyncio.run(manager.create_session(CreateOpenMatbSession(participant_id="P01", visit_ordinal=1)))

    with pytest.raises(OpenMatbRuntimeError, match="openmatb_invalid_participant_token"):
        manager.acknowledge_instructions(prepared.session.id, "wrong-token")
    ready = manager.acknowledge_instructions(prepared.session.id, prepared.participant_token)
    assert ready.lifecycle == "READY"


def test_native_process_exit_before_ready_is_reported_immediately(engine, tmp_path, monkeypatch):
    _seed_visit(engine)
    manager = _manager(engine, tmp_path)

    class FailedProcess:
        def __init__(self) -> None:
            self.pid = 12345
            self.returncode = 1
            self.stdin = None
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self.stdout.feed_eof()
            self.stderr.feed_data(b"ModuleNotFoundError: No module named 'rstr'\n")
            self.stderr.feed_eof()

        async def wait(self) -> int:
            return self.returncode

        def terminate(self) -> None:
            self.returncode = 1

        def kill(self) -> None:
            self.returncode = 1

    captured_command = []

    async def create_failed_process(*args, **_kwargs):
        captured_command.extend(args)
        return FailedProcess()

    monkeypatch.setattr("app.openmatb_runtime.asyncio.create_subprocess_exec", create_failed_process)
    monkeypatch.setattr("app.openmatb_runtime._WindowsJob", lambda _pid: None)

    async def run() -> str:
        prepared = await manager.create_session(
            CreateOpenMatbSession(participant_id="P01", visit_ordinal=1),
        )
        manager.acknowledge_instructions(prepared.session.id, prepared.participant_token)
        with pytest.raises(OpenMatbRuntimeError, match="openmatb_dependency_missing"):
            await manager.start_block(prepared.session.id, prepared.controller_lease)
        return prepared.session.id

    session_id = asyncio.run(run())
    failed = manager.session_view(session_id)
    assert failed.lifecycle == "FAILED"
    assert failed.last_error == "openmatb_dependency_missing"
    assert captured_command[captured_command.index("--visual-theme") + 1] == "classic"
