from __future__ import annotations

import asyncio
import json
import os
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest
from app.models import Participant, Visit
from app.openmatb_runtime import OpenMatbManager, OpenMatbRuntimeError
from app.openmatb_schemas import (
    ClonePresetRequest,
    CloneVisualProfileRequest,
    CreateOpenMatbSession,
    ImportVisualProfileRequest,
    PublishVisualProfileRequest,
    UpdatePresetRequest,
    UpdateVisualProfileRequest,
    VisualProfilePreviewRequest,
)
from sqlmodel import Session


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


def test_english_practice_has_one_block_and_preserves_locale(engine, tmp_path):
    _seed_visit(engine)
    manager = _manager(engine, tmp_path)
    prepared = asyncio.run(manager.create_session(CreateOpenMatbSession(
        participant_id="P01", visit_ordinal=1, execution_purpose="practice",
        instruction_protocol_id="matb-fac-en", instruction_version="1.0.0")))
    assert prepared.session.locale == "en"
    assert prepared.session.execution_purpose == "practice"
    assert prepared.session.block_order == ["PRACTICE"]
    assert prepared.session.instruction_protocol.locale == "en"
    assert "practice" in prepared.session.visit_instruction.lower()
    scenario = next((Path(manager.artifact_root) / prepared.session.id / "scenarios").glob("*.txt"))
    assert ";genericscales;filename;isa_en.txt" in scenario.read_text(encoding="utf-8")


def test_create_session_generates_versioned_spanish_counterbalanced_suite(engine, tmp_path):
    _seed_visit(engine)
    manager = _manager(engine, tmp_path)

    prepared = asyncio.run(manager.create_session(CreateOpenMatbSession(participant_id="P01", visit_ordinal=1)))

    assert prepared.session.lifecycle == "INSTRUCTIONS"
    assert prepared.session.visual_theme == "fac_modern"
    assert prepared.session.visual_profile_id == "matb-fac-modern"
    assert prepared.session.visual_profile_version == "1.0.0"
    assert prepared.session.visual_profile_schema_version == "openmatb-visual-profile-v1"
    assert prepared.session.visual_profile_sha256
    assert prepared.session.block_order[0] == "PRACTICE"
    assert set(prepared.session.block_order[1:]) == {"LOW", "MEDIUM", "HIGH"}
    run_root = Path(manager.artifact_root) / prepared.session.id
    frozen_profile = json.loads((run_root / "visual-profile.json").read_text(encoding="utf-8"))
    assert frozen_profile["profile_id"] == "matb-fac-modern"
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
    assert prepared.session.visual_profile_id == "cockpit"
    run_root = Path(manager.artifact_root) / prepared.session.id
    for manifest_path in sorted((run_root / "scenarios").glob("*.manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["parameters"]["visual_theme"] == "cockpit"
        assert manifest["parameters"]["visual_profile_id"] == "cockpit"
        assert manifest["parameters"]["visual_profile_sha256"] == prepared.session.visual_profile_sha256


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
    from types import SimpleNamespace
    monkeypatch.setattr(manager, "readiness", lambda: SimpleNamespace(ready=True))

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
    assert "--visual-theme" not in captured_command
    profile_path = Path(captured_command[captured_command.index("--theme-file") + 1])
    assert profile_path.name == "visual-profile.json"
    assert profile_path.is_file()


def test_visual_profile_clone_edit_validate_publish_and_immutability(engine, tmp_path):
    manager = _manager(engine, tmp_path)
    bundled = next(row for row in manager.list_visual_profiles() if row.profile_id == "matb-fac-modern")
    assert bundled.status == "published"
    assert bundled.bundled

    draft = manager.clone_visual_profile(
        bundled.profile_id,
        bundled.version,
        CloneVisualProfileRequest(
            profile_id="matb-fac-study",
            version="1.0.1",
            label="MATB-FAC study draft",
        ),
    )
    payload = deepcopy(draft.payload.model_dump(mode="json"))
    payload["palette"]["accent"] = "#1557B0"
    updated = manager.update_visual_profile(
        draft.profile_id,
        draft.version,
        UpdateVisualProfileRequest(payload=payload),
    )
    assert updated.sha256 != draft.sha256
    assert manager.validate_saved_visual_profile(draft.profile_id, draft.version).validation.valid

    with pytest.raises(OpenMatbRuntimeError, match="visual_profile_warning_acknowledgement_required"):
        manager.publish_visual_profile(
            draft.profile_id,
            draft.version,
            PublishVisualProfileRequest(),
        )
    warning_codes = [issue.code for issue in updated.validation.warnings]
    published = manager.publish_visual_profile(
        draft.profile_id,
        draft.version,
        PublishVisualProfileRequest(warning_acknowledgements=warning_codes),
    )
    assert published.status == "published"
    assert published.validation.publishable
    with pytest.raises(OpenMatbRuntimeError, match="published_configuration_immutable"):
        manager.update_visual_profile(
            published.profile_id,
            published.version,
            UpdateVisualProfileRequest(payload=published.payload),
        )


def test_visual_profile_publish_blocks_essential_contrast_failure(engine, tmp_path):
    manager = _manager(engine, tmp_path)
    source = next(row for row in manager.list_visual_profiles() if row.profile_id == "matb-fac-modern")
    draft = manager.clone_visual_profile(
        source.profile_id,
        source.version,
        CloneVisualProfileRequest(profile_id="invalid-contrast", version="1.0.0", label="Invalid contrast"),
    )
    payload = draft.payload.model_dump(mode="json")
    payload["palette"]["text"] = payload["palette"]["panel_background"]
    invalid = manager.update_visual_profile(
        draft.profile_id,
        draft.version,
        UpdateVisualProfileRequest(payload=payload),
    )
    assert not invalid.validation.valid
    with pytest.raises(OpenMatbRuntimeError, match="visual_profile_accessibility_errors"):
        manager.publish_visual_profile(
            invalid.profile_id,
            invalid.version,
            PublishVisualProfileRequest(
                warning_acknowledgements=[issue.code for issue in invalid.validation.warnings]
            ),
        )


def test_visual_profile_import_is_draft_idempotent_and_collision_safe(engine, tmp_path):
    manager = _manager(engine, tmp_path)
    source = next(row for row in manager.list_visual_profiles() if row.profile_id == "matb-fac-modern")
    payload = source.payload.model_dump(mode="json")
    payload.update(profile_id="imported-profile", version="2.0.0", label="Imported profile")
    request = ImportVisualProfileRequest(payload=payload)
    imported = manager.import_visual_profile(request)
    repeated = manager.import_visual_profile(request)
    assert imported.status == "draft"
    assert repeated.sha256 == imported.sha256

    conflicting = deepcopy(payload)
    conflicting["palette"]["accent"] = "#123456"
    with pytest.raises(OpenMatbRuntimeError, match="visual_profile_import_collision"):
        manager.import_visual_profile(ImportVisualProfileRequest(payload=conflicting))


def test_frozen_visual_profile_tampering_fails_closed_before_launch(engine, tmp_path, monkeypatch):
    _seed_visit(engine)
    manager = _manager(engine, tmp_path)
    from types import SimpleNamespace
    monkeypatch.setattr(manager, "readiness", lambda: SimpleNamespace(ready=True))
    prepared = asyncio.run(
        manager.create_session(CreateOpenMatbSession(participant_id="P01", visit_ordinal=1))
    )
    manager.acknowledge_instructions(prepared.session.id, prepared.participant_token)
    profile_path = Path(manager.artifact_root) / prepared.session.id / "visual-profile.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    payload["palette"]["accent"] = "#123456"
    profile_path.write_text(json.dumps(payload), encoding="utf-8")

    called = False

    async def unexpected_spawn(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("app.openmatb_runtime.asyncio.create_subprocess_exec", unexpected_spawn)
    with pytest.raises(OpenMatbRuntimeError, match="openmatb_visual_profile_tampered"):
        asyncio.run(manager.start_block(prepared.session.id, prepared.controller_lease))
    assert not called


def test_draft_visual_preview_is_isolated_and_abortable(engine, tmp_path, monkeypatch):
    manager = _manager(engine, tmp_path)
    source = next(row for row in manager.list_visual_profiles() if row.profile_id == "matb-fac-modern")
    draft = manager.clone_visual_profile(
        source.profile_id,
        source.version,
        CloneVisualProfileRequest(profile_id="preview-draft", version="1.0.0", label="Preview draft"),
    )
    captured_command: list[str] = []

    class ReadyProcess:
        def __init__(self) -> None:
            self.pid = 24680
            self.returncode = None
            self.stdin = None
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self._done = asyncio.Event()
            self.stdout.feed_data(b'{"event":"ready"}\n')

        async def wait(self) -> int:
            await self._done.wait()
            return int(self.returncode or 0)

        def terminate(self) -> None:
            self.returncode = 0
            self.stdout.feed_eof()
            self.stderr.feed_eof()
            self._done.set()

        def kill(self) -> None:
            self.terminate()

    async def create_ready_process(*args, **_kwargs):
        captured_command.extend(args)
        process = ReadyProcess()
        # POSIX termination addresses the child's process group. Keep that
        # signal inside the fake process, just like terminate() on Windows.
        if hasattr(os, "killpg"):
            monkeypatch.setattr("app.openmatb_runtime.os.killpg", lambda *_: process.terminate())
        return process

    monkeypatch.setattr("app.openmatb_runtime.asyncio.create_subprocess_exec", create_ready_process)
    monkeypatch.setattr("app.openmatb_runtime._WindowsJob", lambda _pid: None)

    async def run_preview():
        running = await manager.start_visual_profile_preview(
            draft.profile_id,
            draft.version,
            VisualProfilePreviewRequest(display_index=0, windowed=True),
        )
        assert running.lifecycle == "RUNNING"
        assert running.pid == 24680
        assert running.artifact_root
        assert "openmatb-preview" in Path(running.artifact_root).parts
        assert manager.visual_profile_preview_status().lifecycle == "RUNNING"
        stopped = await manager.abort_visual_profile_preview()
        assert stopped.lifecycle == "IDLE"

    asyncio.run(run_preview())
    assert "--theme-file" in captured_command
    assert "--windowed" in captured_command
    assert "--control-stdio" in captured_command
    assert "--visual-theme" not in captured_command
    assert not any("participant" in part.lower() for part in captured_command)
