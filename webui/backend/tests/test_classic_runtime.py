from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import pytest
from sqlmodel import Session, select

from app import classic_runtime as classic_runtime_module
from app.classic_models import ClassicSessionArtifact, ClassicSessionSelection
from app.classic_persistence import ClassicPersistenceError, SQLModelClassicPersistence
from app.classic_runtime import (
    TASK_DURATION_SECONDS,
    ClassicManager,
    ClassicRuntimeError,
)
from app.classic_schemas import CreateClassicSession
from app.models import Participant, Visit
from matb_integration.physiology.acquisition import (
    PolarConnectionManager,
    PolarSessionRecorder,
)
from matb_integration.physiology.backend import PolarBackendError, SimulatedPolarBackend
from matb_integration.physiology.openmatb_process import OpenMATBProcessResult
from matb_integration.physiology.reporting import build_session_bundle


def _seed(engine) -> None:
    with Session(engine) as db:
        db.add(Participant(id="P30", enrollment_date=date(2026, 8, 23)))
        db.add(Visit(participant_id="P30", visit_ordinal=1, scheduled_day=0))
        db.commit()


def _event_lines(session_id: str, *event_names: str) -> str:
    start_monotonic = time.monotonic_ns()
    start_utc = time.time_ns()
    records: list[str] = []
    for sequence, event_name in enumerate(event_names, start=1):
        at_task_end = event_name != "scenario_started"
        offset_ns = 900_000_000_000 if at_task_end else 0
        records.append(
            json.dumps(
                {
                    "schema_version": "openmatb-synchronized-event-v1",
                    "session_id": session_id,
                    "sequence": sequence,
                    "received_monotonic_ns": start_monotonic + offset_ns,
                    "received_utc_ns": start_utc + offset_ns,
                    "scenario_time": 900.0 if at_task_end else 0.0,
                    "event": event_name,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
    return "".join(records)


class FakeLauncher:
    def __init__(self, backend: SimulatedPolarBackend) -> None:
        self.backend = backend
        self.emit_rr = True
        self.scenario_bytes = b"frozen military aviation scenario\n"
        self.application_bytes = b"frozen OpenMATB application source\n"
        self.run_called = False

    def available_scenarios(self) -> tuple[str, ...]:
        return (
            "military_aviation/low_workload.txt",
            "military_aviation/medium_workload.txt",
            "military_aviation/high_workload.txt",
        )

    def scenario_sha256(self, scenario_name: str) -> str:
        assert scenario_name in self.available_scenarios()
        return hashlib.sha256(self.scenario_bytes).hexdigest()

    def application_sha256(self) -> str:
        return hashlib.sha256(self.application_bytes).hexdigest()

    async def run(self, *, scenario_name: str, session_id: str, output_dir: Path):
        del scenario_name
        self.run_called = True
        if self.emit_rr:
            for _ in range(5):
                await self.backend.emit_rr_ticks((1024,))
        output_dir.mkdir(parents=True, exist_ok=True)
        source = output_dir / "openmatb-session.csv"
        source.write_text(
            "logtime,scenario_time,type,module,address,value\n"
            "1.0,0.0,performance,track,cursor_in_target,True\n"
            "901.0,900.0,state,track,cursor_x,0.1\n",
            encoding="utf-8",
        )
        events = output_dir / "openmatb-events.jsonl"
        events.write_text(
            _event_lines(
                session_id,
                "scenario_started",
                "task_window_completed",
                "scenario_completed",
                "scenario_finished",
            ),
            encoding="utf-8",
        )
        now = datetime.now(timezone.utc)
        return OpenMATBProcessResult(
            exit_code=0,
            source_csv=source,
            synchronized_events=events,
            stdout_log=output_dir / "stdout.log",
            stderr_log=output_dir / "stderr.log",
            started_at=now,
            finished_at=now,
        )

    async def abort(self, *, timeout_seconds: float = 5.0) -> None:
        del timeout_seconds


@pytest.mark.anyio
async def test_runtime_runs_baseline_task_recovery_and_seals_bundle(engine, tmp_path) -> None:
    _seed(engine)
    backend = SimulatedPolarBackend()
    connection = PolarConnectionManager(backend)
    candidate = (await connection.scan(0.01))[0]
    await connection.connect(candidate.device_token)
    preflight = asyncio.create_task(connection.preflight(timeout_seconds=1.0))
    await asyncio.sleep(0)
    await backend.emit_rr_ticks((1024,))
    await preflight

    async def phase_sleep(_seconds: float) -> None:
        for _ in range(5):
            await backend.emit_rr_ticks((1024,))

    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=SQLModelClassicPersistence(engine),
        polar=connection,
        launcher=FakeLauncher(backend),
        sleep=phase_sleep,
    )
    prepared = await manager.prepare_session(
        CreateClassicSession(
            participant_id="P30",
            visit_ordinal=1,
            workload_level="LOW",
            scenario_name="military_aviation/low_workload.txt",
        )
    )

    await manager.start_session(prepared.id, prepared.controller_lease)
    final = await manager.wait_until_finished(prepared.id)

    assert final.status == "COMPLETE", final.failure_reason_code
    assert final.task_validity == "valid"
    assert final.physiology_quality in {
        "excellent",
        "good",
        "acceptable",
        "poor",
        "unusable",
        "insufficient_data",
    }
    run_dir = tmp_path / "classic" / prepared.id
    assert (run_dir / ".capture" / "polar-rr-journal.jsonl").is_file()
    assert (run_dir / "report.en.md").is_file()
    assert (run_dir / "report.es.md").is_file()
    session_document = json.loads(
        (run_dir / "session.json").read_text(encoding="utf-8")
    )
    assert session_document["session"]["session_id"] == prepared.id
    assert session_document["session"]["polar_backend"] == "simulated"
    assert session_document["session"]["acquisition_mode"] == "polar_h10_rr"
    assert session_document["session"]["scenario_sha256"] == prepared.scenario_sha256
    assert session_document["session"]["openmatb_source_sha256"] == prepared.openmatb_source_sha256
    assert session_document["session"]["test_mode"] is False
    assert session_document["session"]["wall_time_scale"] == 1.0
    assert session_document["session"]["provenance"]["hrv_analysis_version"]
    assert session_document["session"]["provenance"]["device_model"] == "Polar H10"
    assert "connected_device_name" not in session_document["session"]["provenance"]
    assert "device_identifier_sha256" not in session_document["session"]["provenance"]
    connected_name = connection.status.connected_device_name
    assert connected_name is not None
    assert connected_name not in json.dumps(session_document)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["provenance"]["polar_backend"] == "simulated"
    with Session(engine) as db:
        assert len(db.exec(select(ClassicSessionArtifact)).all()) == 12
        assert db.exec(select(ClassicSessionSelection)).one().attempt_id == prepared.id

    (run_dir / "report.es.md").unlink()
    with pytest.raises(
        ClassicRuntimeError,
        match="classic_registered_bundle_(missing|integrity_failed)",
    ):
        manager.recover_orphaned_attempts()


@pytest.mark.anyio
async def test_start_rechecks_sensor_readiness_after_prepare(engine, tmp_path) -> None:
    _seed(engine)
    backend = SimulatedPolarBackend()
    connection = PolarConnectionManager(backend)
    candidate = (await connection.scan(0.01))[0]
    await connection.connect(candidate.device_token)
    preflight = asyncio.create_task(connection.preflight(timeout_seconds=1.0))
    await asyncio.sleep(0)
    await backend.emit_rr_ticks((1024,))
    await preflight
    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=SQLModelClassicPersistence(engine),
        polar=connection,
        launcher=FakeLauncher(backend),
        sleep=lambda _seconds: None,
    )
    prepared = await manager.prepare_session(
        CreateClassicSession(
            participant_id="P30",
            visit_ordinal=1,
            workload_level="LOW",
            scenario_name="military_aviation/low_workload.txt",
        )
    )
    await connection.disconnect()

    with pytest.raises(ClassicRuntimeError, match="polar_preflight_required"):
        await manager.start_session(prepared.id, prepared.controller_lease)

    assert manager.session_view(prepared.id).status == "PREPARED"


@pytest.mark.anyio
async def test_scenario_digest_is_frozen_at_prepare_and_rechecked_before_launch(
    engine,
    tmp_path,
) -> None:
    _seed(engine)
    backend = SimulatedPolarBackend()
    launcher = FakeLauncher(backend)
    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=SQLModelClassicPersistence(engine),
        polar=PolarConnectionManager(backend),
        launcher=launcher,
        sleep=lambda _seconds: None,
    )
    prepared = await manager.prepare_session(
        CreateClassicSession(
            participant_id="P30",
            visit_ordinal=1,
            workload_level="LOW",
            scenario_name="military_aviation/low_workload.txt",
            performance_only_override=True,
            override_reason_code="sensor_unavailable",
        )
    )
    original_digest = hashlib.sha256(launcher.scenario_bytes).hexdigest()
    assert prepared.scenario_sha256 == original_digest
    launcher.scenario_bytes = b"scenario changed after operator preparation\n"

    await manager.start_session(prepared.id, prepared.controller_lease)
    final = await manager.wait_until_finished(prepared.id)

    assert launcher.run_called is False
    assert final.status == "INTERRUPTED"
    assert final.failure_reason_code == "openmatb_scenario_changed_after_prepare"
    assert final.scenario_sha256 == original_digest
    document = json.loads(
        (tmp_path / "classic" / prepared.id / "session.json").read_text(encoding="utf-8")
    )
    assert document["session"]["scenario_sha256"] == original_digest


@pytest.mark.anyio
async def test_test_mode_attempt_is_provenanced_invalid_and_never_selectable(
    engine,
    tmp_path,
) -> None:
    _seed(engine)
    backend = SimulatedPolarBackend()
    launcher = FakeLauncher(backend)
    launcher.emit_rr = False
    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=SQLModelClassicPersistence(engine),
        polar=PolarConnectionManager(backend),
        launcher=launcher,
        sleep=lambda _seconds: None,
        test_mode=True,
        wall_time_scale=0.001,
    )
    prepared = await manager.prepare_session(
        CreateClassicSession(
            participant_id="P30",
            visit_ordinal=1,
            workload_level="MEDIUM",
            scenario_name="military_aviation/medium_workload.txt",
            performance_only_override=True,
            override_reason_code="sensor_unavailable",
        )
    )

    await manager.start_session(prepared.id, prepared.controller_lease)
    final = await manager.wait_until_finished(prepared.id)

    assert prepared.test_mode is True
    assert prepared.wall_time_scale == 0.001
    assert final.status == "COMPLETE"
    assert final.task_validity == "invalid"
    assert final.failure_reason_code == "test_mode_attempt"
    with Session(engine) as db:
        assert db.exec(select(ClassicSessionSelection)).first() is None
    document = json.loads(
        (tmp_path / "classic" / prepared.id / "session.json").read_text(encoding="utf-8")
    )
    assert document["session"]["test_mode"] is True
    assert document["session"]["wall_time_scale"] == 0.001
    assert "test_mode | True" in (
        tmp_path / "classic" / prepared.id / "report.en.md"
    ).read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_early_window_close_is_invalid_and_never_auto_selected(engine, tmp_path) -> None:
    _seed(engine)
    backend = SimulatedPolarBackend()
    candidate = (await backend.scan(0.01))[0]
    await backend.connect(candidate.device_token)

    class EarlyCloseLauncher(FakeLauncher):
        def __init__(self, backend):
            super().__init__(backend)
            self.emit_rr = False

        async def run(self, **kwargs):
            result = await super().run(**kwargs)
            result.synchronized_events.write_text(
                _event_lines(
                    kwargs["session_id"],
                    "scenario_started",
                    "scenario_finished",
                ),
                encoding="utf-8",
            )
            return result

    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=SQLModelClassicPersistence(engine),
        polar=PolarConnectionManager(backend),
        launcher=EarlyCloseLauncher(backend),
        sleep=lambda _seconds: None,
    )
    prepared = await manager.prepare_session(
        CreateClassicSession(
            participant_id="P30",
            visit_ordinal=1,
            workload_level="HIGH",
            scenario_name="military_aviation/high_workload.txt",
            performance_only_override=True,
            override_reason_code="sensor_unavailable",
        )
    )

    await manager.start_session(prepared.id, prepared.controller_lease)
    final = await manager.wait_until_finished(prepared.id)

    assert final.status == "COMPLETE", final.failure_reason_code
    assert final.task_validity == "invalid"
    assert final.failure_reason_code == "openmatb_task_incomplete"
    document = json.loads(
        (tmp_path / "classic" / prepared.id / "session.json").read_text(
            encoding="utf-8"
        )
    )
    assert document["session"]["failure_reason_code"] == "openmatb_task_incomplete"
    with Session(engine) as db:
        assert db.exec(select(ClassicSessionSelection)).first() is None


@pytest.mark.anyio
async def test_completed_marker_before_task_duration_is_invalid(engine, tmp_path) -> None:
    _seed(engine)
    backend = SimulatedPolarBackend()

    class ShortCompletedLauncher(FakeLauncher):
        def __init__(self, backend):
            super().__init__(backend)
            self.emit_rr = False

        async def run(self, **kwargs):
            result = await super().run(**kwargs)
            result.source_csv.write_text(
                "logtime,scenario_time,type,module,address,value\n"
                "1.0,0.0,performance,track,cursor_in_target,True\n"
                "2.0,1.0,state,track,cursor_x,0.1\n",
                encoding="utf-8",
            )
            return result

    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=SQLModelClassicPersistence(engine),
        polar=PolarConnectionManager(backend),
        launcher=ShortCompletedLauncher(backend),
        sleep=lambda _seconds: None,
    )
    prepared = await manager.prepare_session(
        CreateClassicSession(
            participant_id="P30",
            visit_ordinal=1,
            workload_level="MEDIUM",
            scenario_name="military_aviation/medium_workload.txt",
            performance_only_override=True,
            override_reason_code="sensor_unavailable",
        )
    )

    await manager.start_session(prepared.id, prepared.controller_lease)
    final = await manager.wait_until_finished(prepared.id)

    assert final.status == "COMPLETE", final.failure_reason_code
    assert final.task_validity == "invalid"
    assert final.failure_reason_code == "openmatb_task_too_short"
    session_document = json.loads(
        (tmp_path / "classic" / prepared.id / "session.json").read_text(
            encoding="utf-8"
        )
    )
    assert session_document["session"]["openmatb_max_scenario_time_s"] == 1.0
    with Session(engine) as db:
        assert db.exec(select(ClassicSessionSelection)).first() is None


@pytest.mark.anyio
async def test_task_physiology_window_ends_before_post_task_questionnaire(engine, tmp_path) -> None:
    _seed(engine)
    backend = SimulatedPolarBackend()
    boundary_release = asyncio.Event()
    boundary_written = asyncio.Event()
    questionnaire_release = asyncio.Event()
    launcher_started = asyncio.Event()

    class QuestionnaireLauncher(FakeLauncher):
        def __init__(self, backend):
            super().__init__(backend)
            self.emit_rr = False

        async def run(self, **kwargs):
            session_id = kwargs["session_id"]
            output_dir = kwargs["output_dir"]
            output_dir.mkdir(parents=True, exist_ok=True)
            source = output_dir / "openmatb-session.csv"
            source.write_text(
                "logtime,scenario_time,type,module,address,value\n"
                "1.0,900.0,performance,track,cursor_in_target,True\n",
                encoding="utf-8",
            )
            events = output_dir / "openmatb-events.jsonl"
            start_line = _event_lines(session_id, "scenario_started")
            events.write_text(start_line, encoding="utf-8")
            launcher_started.set()
            await boundary_release.wait()
            with events.open("a", encoding="utf-8") as stream:
                boundary = json.loads(
                    _event_lines(
                        session_id,
                        "scenario_started",
                        "task_window_completed",
                    ).splitlines()[1]
                )
                boundary["sequence"] = 2
                stream.write(json.dumps(boundary, separators=(",", ":")) + "\n")
                stream.flush()
            boundary_written.set()
            await questionnaire_release.wait()
            with events.open("a", encoding="utf-8") as stream:
                terminal = [
                    json.loads(line)
                    for line in _event_lines(
                        session_id,
                        "scenario_started",
                        "task_window_completed",
                        "scenario_completed",
                        "scenario_finished",
                    ).splitlines()[2:]
                ]
                for sequence, record in enumerate(terminal, start=3):
                    record["sequence"] = sequence
                    stream.write(json.dumps(record, separators=(",", ":")) + "\n")
            now = datetime.now(timezone.utc)
            return OpenMATBProcessResult(
                exit_code=0,
                source_csv=source,
                synchronized_events=events,
                stdout_log=output_dir / "stdout.log",
                stderr_log=output_dir / "stderr.log",
                started_at=now,
                finished_at=now,
            )

    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=SQLModelClassicPersistence(engine),
        polar=PolarConnectionManager(backend),
        launcher=QuestionnaireLauncher(backend),
        sleep=lambda _seconds: None,
    )
    prepared = await manager.prepare_session(
        CreateClassicSession(
            participant_id="P30",
            visit_ordinal=1,
            workload_level="MEDIUM",
            scenario_name="military_aviation/medium_workload.txt",
            performance_only_override=True,
            override_reason_code="sensor_unavailable",
        )
    )
    await manager.start_session(prepared.id, prepared.controller_lease)
    await launcher_started.wait()
    try:
        for _ in range(10):
            await asyncio.sleep(0)
        assert manager.session_view(prepared.id).task_finished_at is None

        boundary_release.set()
        await boundary_written.wait()
        during_questionnaire = manager.session_view(prepared.id)
        for _ in range(100):
            if during_questionnaire.task_finished_at is not None:
                break
            await asyncio.sleep(0.01)
            during_questionnaire = manager.session_view(prepared.id)
        assert during_questionnaire.task_finished_at is not None
        assert during_questionnaire.status == "POST_TASK"
        assert during_questionnaire.post_task_timeout_seconds == 600.0
    finally:
        boundary_release.set()
        questionnaire_release.set()
        await manager.wait_until_finished(prepared.id)


@pytest.mark.anyio
async def test_post_task_questionnaire_timeout_interrupts_and_seals_attempt(
    engine,
    tmp_path,
    monkeypatch,
) -> None:
    _seed(engine)
    backend = SimulatedPolarBackend()
    questionnaire_started = asyncio.Event()

    class HungQuestionnaireLauncher(FakeLauncher):
        def __init__(self, backend):
            super().__init__(backend)
            self.emit_rr = False

        async def run(self, **kwargs):
            session_id = kwargs["session_id"]
            output_dir = kwargs["output_dir"]
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "openmatb-session.csv").write_text(
                "logtime,scenario_time,type,module,address,value\n"
                "1.0,900.0,performance,track,cursor_in_target,True\n",
                encoding="utf-8",
            )
            (output_dir / "openmatb-events.jsonl").write_text(
                _event_lines(
                    session_id,
                    "scenario_started",
                    "task_window_completed",
                ),
                encoding="utf-8",
            )
            questionnaire_started.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(
        "app.classic_runtime.POST_TASK_QUESTIONNAIRE_TIMEOUT_SECONDS",
        0.05,
    )
    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=SQLModelClassicPersistence(engine),
        polar=PolarConnectionManager(backend),
        launcher=HungQuestionnaireLauncher(backend),
        sleep=lambda _seconds: None,
    )
    prepared = await manager.prepare_session(
        CreateClassicSession(
            participant_id="P30",
            visit_ordinal=1,
            workload_level="MEDIUM",
            scenario_name="military_aviation/medium_workload.txt",
            performance_only_override=True,
            override_reason_code="sensor_unavailable",
        )
    )

    await manager.start_session(prepared.id, prepared.controller_lease)
    await questionnaire_started.wait()
    for _ in range(100):
        if manager.session_view(prepared.id).status == "POST_TASK":
            break
        await asyncio.sleep(0.005)
    assert manager.session_view(prepared.id).status == "POST_TASK"

    final = await manager.wait_until_finished(prepared.id)

    assert final.status == "INTERRUPTED"
    assert final.failure_reason_code == "openmatb_post_task_timeout"
    assert len(manager.artifacts(prepared.id)) == 12


@pytest.mark.anyio
async def test_backend_restart_recovers_fsynced_rr_and_seals_interrupted_bundle(
    engine,
    tmp_path,
) -> None:
    _seed(engine)
    persistence = SQLModelClassicPersistence(engine)
    session_id = "de4ad40d-7cbb-4b2a-a4c6-9f839a086c4e"
    persistence.create_attempt(
        participant_id="P30",
        visit_ordinal=1,
        workload_level="LOW",
        scenario_name="military_aviation/low_workload.txt",
        artifact_root=session_id,
        session_id=session_id,
        controller_lease_hash="0" * 64,
    )
    persistence.update_attempt_state(
        session_id,
        status="BASELINE",
        baseline_started_at=datetime.now(timezone.utc),
    )
    run_dir = tmp_path / "classic" / session_id
    journal = run_dir / ".capture" / "polar-rr-journal.jsonl"
    backend = SimulatedPolarBackend()
    candidate = (await backend.scan(0.01))[0]
    await backend.connect(candidate.device_token)
    recorder = PolarSessionRecorder(backend)
    await recorder.start(session_id, journal_path=journal)
    recorder.begin_phase("baseline", nominal_duration_s=300.0)
    await backend.emit_rr_ticks((1024, 900))
    recorder.end_phase("baseline")
    await recorder.stop()
    # Simulate a power loss after the first visible artifact but before the
    # checksums commit marker was published.
    (run_dir / "session.json").write_text("{}\n", encoding="utf-8")

    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=persistence,
        polar=PolarConnectionManager(SimulatedPolarBackend()),
        launcher=FakeLauncher(backend),
        sleep=lambda _seconds: None,
    )

    assert manager.recover_orphaned_attempts() == 1
    recovered = manager.session_view(session_id)
    assert recovered.status == "INTERRUPTED"
    assert recovered.failure_reason_code == "backend_process_restart"
    assert len(manager.artifacts(session_id)) == 12
    assert "1024" in (run_dir / "rr-intervals.csv").read_text(encoding="utf-8")
    assert manager.debrief(session_id).hrv["phases"]["baseline"]["raw_rr_count"] == 2


def test_backend_restart_reports_a_corrupt_rr_journal(engine, tmp_path) -> None:
    _seed(engine)
    persistence = SQLModelClassicPersistence(engine)
    session_id = "f850cab2-adb0-4fe0-8e8e-28f1ac24aebd"
    persistence.create_attempt(
        participant_id="P30",
        visit_ordinal=1,
        workload_level="LOW",
        scenario_name="military_aviation/low_workload.txt",
        artifact_root=session_id,
        session_id=session_id,
        controller_lease_hash="9" * 64,
    )
    persistence.update_attempt_state(session_id, status="BASELINE")
    capture = tmp_path / "classic" / session_id / ".capture"
    capture.mkdir(parents=True)
    (capture / "polar-rr-journal.jsonl").write_text(
        '{"schema_version":"polar-rr-journal-v1","kind":"session_started",'
        f'"session_id":"{session_id}"}}\n'
        "corrupt-middle-record\n",
        encoding="utf-8",
    )
    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=persistence,
        polar=PolarConnectionManager(SimulatedPolarBackend()),
        launcher=FakeLauncher(SimulatedPolarBackend()),
        sleep=lambda _seconds: None,
    )

    assert manager.recover_orphaned_attempts() == 1
    recovered = manager.session_view(session_id)
    assert recovered.status == "INTERRUPTED"
    assert (
        recovered.failure_reason_code
        == "backend_process_restart_acquisition_journal_invalid"
    )


def test_backend_restart_commits_a_published_bundle_left_before_database_commit(
    engine,
    tmp_path,
) -> None:
    _seed(engine)
    persistence = SQLModelClassicPersistence(engine)
    session_id = "81aa0a6d-b7f0-48d0-9ac3-0087f5b5d13d"
    persistence.create_attempt(
        participant_id="P30",
        visit_ordinal=1,
        workload_level="HIGH",
        scenario_name="military_aviation/high_workload.txt",
        artifact_root=session_id,
        session_id=session_id,
        controller_lease_hash="1" * 64,
        performance_only_override=True,
        override_reason_code="sensor_unavailable",
    )
    run_dir = tmp_path / "classic" / session_id
    capture = run_dir / ".capture"
    capture.mkdir(parents=True)
    source = capture / "openmatb-session.csv"
    source.write_text(
        "logtime,scenario_time,type,module,address,value\n"
        "1.0,900.0,performance,track,cursor_in_target,True\n",
        encoding="utf-8",
    )
    events = capture / "openmatb-events.jsonl"
    events.write_text('{"event":"scenario_completed"}\n', encoding="utf-8")
    metrics = {
        "n_rows": 1,
        "tracking": {"in_target_pct": 100.0},
    }
    phase_results = {}
    build_session_bundle(
        run_dir,
        session={
            "session_id": session_id,
            "participant_id": "P30",
            "visit_ordinal": 1,
            "workload_level": "HIGH",
            "scenario_name": "military_aviation/high_workload.txt",
            "status": "COMPLETE",
            "task_validity": "valid",
            "physiology_quality": "missing_performance_only",
            "failure_reason_code": None,
        },
        matb_metrics=metrics,
        phase_results=phase_results,
        rr_records=[],
        clock_anchors=[],
        openmatb_csv=source,
        synchronized_events=events,
    )
    backend = SimulatedPolarBackend()
    launcher = FakeLauncher(backend)
    launcher.emit_rr = False
    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=persistence,
        polar=PolarConnectionManager(backend),
        launcher=launcher,
        sleep=lambda _seconds: None,
    )

    assert manager.recover_orphaned_attempts() == 1
    recovered = manager.session_view(session_id)
    assert recovered.status == "COMPLETE"
    assert recovered.task_validity == "valid"
    assert len(manager.artifacts(session_id)) == 12
    with Session(engine) as db:
        assert db.exec(select(ClassicSessionSelection)).one().attempt_id == session_id


def test_backend_restart_reconciles_published_bundle_after_fallback_termination(
    engine,
    tmp_path,
) -> None:
    _seed(engine)
    persistence = SQLModelClassicPersistence(engine)
    session_id = "44634f2b-ab17-43e8-8a09-bb8b2ec003e4"
    persistence.create_attempt(
        participant_id="P30",
        visit_ordinal=1,
        workload_level="MEDIUM",
        scenario_name="military_aviation/medium_workload.txt",
        artifact_root=session_id,
        session_id=session_id,
        controller_lease_hash="2" * 64,
        performance_only_override=True,
        override_reason_code="sensor_unavailable",
    )
    run_dir = tmp_path / "classic" / session_id
    capture = run_dir / ".capture"
    capture.mkdir(parents=True)
    source = capture / "openmatb-session.csv"
    source.write_text(
        "logtime,scenario_time,type,module,address,value\n"
        "1.0,900.0,performance,track,cursor_in_target,True\n",
        encoding="utf-8",
    )
    events = capture / "openmatb-events.jsonl"
    events.write_text('{"event":"scenario_completed"}\n', encoding="utf-8")
    build_session_bundle(
        run_dir,
        session={
            "session_id": session_id,
            "participant_id": "P30",
            "visit_ordinal": 1,
            "workload_level": "MEDIUM",
            "scenario_name": "military_aviation/medium_workload.txt",
            "status": "COMPLETE",
            "task_validity": "valid",
            "physiology_quality": "missing_performance_only",
            "failure_reason_code": None,
        },
        matb_metrics={"n_rows": 1},
        phase_results={},
        rr_records=[],
        clock_anchors=[],
        openmatb_csv=source,
        synchronized_events=events,
    )
    # Reproduce the former fallback path: filesystem publication succeeded,
    # then the failed database commit was replaced by a bare terminal row.
    persistence.terminate_attempt(
        session_id,
        status="INTERRUPTED",
        reason_code="injected_finalize_failure",
    )
    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=persistence,
        polar=PolarConnectionManager(SimulatedPolarBackend()),
        launcher=FakeLauncher(SimulatedPolarBackend()),
        sleep=lambda _seconds: None,
    )

    assert manager.recover_orphaned_attempts() == 1
    recovered = manager.session_view(session_id)
    assert recovered.status == "COMPLETE"
    assert recovered.task_validity == "valid"
    assert len(manager.artifacts(session_id)) == 12


@pytest.mark.anyio
async def test_terminal_bundle_failure_persists_intent_and_recovers_on_restart(
    engine,
    tmp_path,
    monkeypatch,
) -> None:
    _seed(engine)
    persistence = SQLModelClassicPersistence(engine)
    backend = SimulatedPolarBackend()
    launcher = FakeLauncher(backend)
    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=persistence,
        polar=PolarConnectionManager(backend),
        launcher=launcher,
        sleep=lambda _seconds: None,
    )
    prepared = await manager.prepare_session(
        CreateClassicSession(
            participant_id="P30",
            visit_ordinal=1,
            workload_level="LOW",
            scenario_name="military_aviation/low_workload.txt",
            performance_only_override=True,
            override_reason_code="sensor_unavailable",
        )
    )
    real_builder = classic_runtime_module.build_session_bundle

    def fail_bundle(*_args, **_kwargs):
        raise OSError("injected_bundle_publication_failure")

    monkeypatch.setattr(classic_runtime_module, "build_session_bundle", fail_bundle)
    pending = await manager.abort(
        prepared.id,
        prepared.controller_lease,
        "participant_requested_stop",
    )

    stored = persistence.get_attempt(prepared.id)
    assert pending.status == "FINALIZING"
    assert stored.terminal_intent_status == "ABORTED"
    assert stored.terminal_intent_reason_code == "participant_requested_stop"
    assert manager.artifacts(prepared.id) == []

    monkeypatch.setattr(classic_runtime_module, "build_session_bundle", real_builder)
    restarted = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=persistence,
        polar=PolarConnectionManager(SimulatedPolarBackend()),
        launcher=FakeLauncher(SimulatedPolarBackend()),
        sleep=lambda _seconds: None,
    )

    assert restarted.recover_orphaned_attempts() == 1
    recovered = restarted.session_view(prepared.id)
    assert recovered.status == "ABORTED"
    assert recovered.failure_reason_code == "participant_requested_stop"
    assert len(restarted.artifacts(prepared.id)) == 12


def test_backend_restart_repairs_a_legacy_terminal_row_without_artifacts(
    engine,
    tmp_path,
) -> None:
    _seed(engine)
    persistence = SQLModelClassicPersistence(engine)
    session_id = "89ad4d1f-a029-4c50-afbe-3e27bbdb9925"
    persistence.create_attempt(
        participant_id="P30",
        visit_ordinal=1,
        workload_level="MEDIUM",
        scenario_name="military_aviation/medium_workload.txt",
        artifact_root=session_id,
        session_id=session_id,
        controller_lease_hash="3" * 64,
        performance_only_override=True,
        override_reason_code="sensor_unavailable",
    )
    persistence.terminate_attempt(
        session_id,
        status="INTERRUPTED",
        reason_code="legacy_terminal_without_bundle",
    )
    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=persistence,
        polar=PolarConnectionManager(SimulatedPolarBackend()),
        launcher=FakeLauncher(SimulatedPolarBackend()),
        sleep=lambda _seconds: None,
    )

    assert manager.recover_orphaned_attempts() == 1
    repaired = manager.session_view(session_id)
    assert repaired.status == "INTERRUPTED"
    assert repaired.failure_reason_code == "legacy_terminal_without_bundle"
    assert len(manager.artifacts(session_id)) == 12


def test_synthetic_capture_text_is_atomically_published_and_directory_synced(
    tmp_path,
    monkeypatch,
) -> None:
    target = tmp_path / "capture" / "openmatb-events.jsonl"
    replacements: list[tuple[Path, Path]] = []
    synced: list[Path] = []
    real_replace = classic_runtime_module.os.replace

    def tracking_replace(source, destination) -> None:
        replacements.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(classic_runtime_module.os, "replace", tracking_replace)
    monkeypatch.setattr(
        classic_runtime_module,
        "_fsync_directory",
        lambda path: synced.append(Path(path)),
    )

    classic_runtime_module._publish_private_text(target, "evidence\n")

    assert target.read_text(encoding="utf-8") == "evidence\n"
    assert replacements[-1][1] == target
    assert target.parent in synced
    assert not replacements[-1][0].exists()


@pytest.mark.anyio
async def test_runtime_blocks_missing_polar_unless_override_is_explicit(engine, tmp_path) -> None:
    _seed(engine)
    backend = SimulatedPolarBackend()
    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=SQLModelClassicPersistence(engine),
        polar=PolarConnectionManager(backend),
        launcher=FakeLauncher(backend),
        sleep=lambda _seconds: None,
    )
    request = CreateClassicSession(
        participant_id="P30",
        visit_ordinal=1,
        workload_level="MEDIUM",
        scenario_name="military_aviation/medium_workload.txt",
    )

    with pytest.raises(ClassicRuntimeError, match="polar_preflight_required"):
        await manager.prepare_session(request)

    overridden = await manager.prepare_session(
        request.model_copy(
            update={
                "performance_only_override": True,
                "override_reason_code": "participant_declined_sensor",
            }
        )
    )
    assert overridden.performance_only_override is True


@pytest.mark.anyio
async def test_aborted_attempt_still_seals_partial_research_bundle(engine, tmp_path) -> None:
    _seed(engine)
    backend = SimulatedPolarBackend()
    connection = PolarConnectionManager(backend)
    candidate = (await connection.scan(0.01))[0]
    await connection.connect(candidate.device_token)
    preflight = asyncio.create_task(connection.preflight(timeout_seconds=1.0))
    await asyncio.sleep(0)
    await backend.emit_rr_ticks((1024,))
    await preflight
    phase_gate = asyncio.Event()

    async def blocked_sleep(_seconds: float) -> None:
        await backend.emit_rr_ticks((1024,))
        await phase_gate.wait()

    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=SQLModelClassicPersistence(engine),
        polar=connection,
        launcher=FakeLauncher(backend),
        sleep=blocked_sleep,
    )
    prepared = await manager.prepare_session(
        CreateClassicSession(
            participant_id="P30",
            visit_ordinal=1,
            workload_level="HIGH",
            scenario_name="military_aviation/high_workload.txt",
        )
    )
    await manager.start_session(prepared.id, prepared.controller_lease)
    for _ in range(20):
        if manager.session_view(prepared.id).status == "BASELINE":
            break
        await asyncio.sleep(0)

    aborted = await manager.abort(
        prepared.id,
        prepared.controller_lease,
        "participant_requested_stop",
    )

    assert aborted.status == "ABORTED"
    assert aborted.failure_reason_code == "participant_requested_stop"
    assert len(manager.artifacts(prepared.id)) == 12
    assert (tmp_path / "classic" / prepared.id / "session.json").is_file()
    assert manager.debrief(prepared.id).session.status == "ABORTED"


@pytest.mark.anyio
async def test_immediate_abort_after_start_seals_bundle_and_releases_active_slot(
    engine,
    tmp_path,
) -> None:
    _seed(engine)
    backend = SimulatedPolarBackend()
    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=SQLModelClassicPersistence(engine),
        polar=PolarConnectionManager(backend),
        launcher=FakeLauncher(backend),
        sleep=lambda _seconds: None,
    )
    request = CreateClassicSession(
        participant_id="P30",
        visit_ordinal=1,
        workload_level="LOW",
        scenario_name="military_aviation/low_workload.txt",
        performance_only_override=True,
        override_reason_code="sensor_unavailable",
    )
    prepared = await manager.prepare_session(request)

    await manager.start_session(prepared.id, prepared.controller_lease)
    aborted = await manager.abort(
        prepared.id,
        prepared.controller_lease,
        "participant_requested_stop",
    )

    assert aborted.status == "ABORTED"
    assert len(manager.artifacts(prepared.id)) == 12
    assert manager.debrief(prepared.id).session.status == "ABORTED"
    replacement = await manager.prepare_session(
        request.model_copy(update={"workload_level": "MEDIUM"})
    )
    assert replacement.status == "PREPARED"


@pytest.mark.anyio
async def test_shutdown_of_prepared_attempt_seals_interrupted_bundle(engine, tmp_path) -> None:
    _seed(engine)
    backend = SimulatedPolarBackend()
    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=SQLModelClassicPersistence(engine),
        polar=PolarConnectionManager(backend),
        launcher=FakeLauncher(backend),
        sleep=lambda _seconds: None,
    )
    prepared = await manager.prepare_session(
        CreateClassicSession(
            participant_id="P30",
            visit_ordinal=1,
            workload_level="MEDIUM",
            scenario_name="military_aviation/medium_workload.txt",
            performance_only_override=True,
            override_reason_code="sensor_unavailable",
        )
    )

    await manager.shutdown()

    interrupted = manager.session_view(prepared.id)
    assert interrupted.status == "INTERRUPTED"
    assert interrupted.failure_reason_code == "backend_shutdown"
    assert len(manager.artifacts(prepared.id)) == 12
    assert manager.debrief(prepared.id).session.status == "INTERRUPTED"


@pytest.mark.anyio
async def test_shutdown_of_running_attempt_is_interrupted_not_operator_aborted(
    engine,
    tmp_path,
) -> None:
    _seed(engine)
    backend = SimulatedPolarBackend()
    phase_started = asyncio.Event()

    async def blocking_phase(_seconds: float) -> None:
        phase_started.set()
        await asyncio.Event().wait()

    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=SQLModelClassicPersistence(engine),
        polar=PolarConnectionManager(backend),
        launcher=FakeLauncher(backend),
        sleep=blocking_phase,
    )
    prepared = await manager.prepare_session(
        CreateClassicSession(
            participant_id="P30",
            visit_ordinal=1,
            workload_level="MEDIUM",
            scenario_name="military_aviation/medium_workload.txt",
            performance_only_override=True,
            override_reason_code="sensor_unavailable",
        )
    )
    await manager.start_session(prepared.id, prepared.controller_lease)
    await phase_started.wait()

    await manager.shutdown()

    interrupted = manager.session_view(prepared.id)
    assert interrupted.status == "INTERRUPTED"
    assert interrupted.failure_reason_code == "backend_shutdown"
    assert len(manager.artifacts(prepared.id)) == 12


@pytest.mark.anyio
async def test_stop_notification_failure_exports_all_fsynced_rr_records(
    engine,
    tmp_path,
) -> None:
    _seed(engine)

    class StopFailureBackend(SimulatedPolarBackend):
        fail_stop = False

        async def stop_notifications(self) -> None:
            await super().stop_notifications()
            if self.fail_stop:
                raise RuntimeError("injected stop failure")

    backend = StopFailureBackend()
    connection = PolarConnectionManager(backend)
    candidate = (await connection.scan(0.01))[0]
    await connection.connect(candidate.device_token)
    preflight = asyncio.create_task(connection.preflight(timeout_seconds=1.0))
    await asyncio.sleep(0)
    await backend.emit_rr_ticks((1024,))
    await preflight

    async def phase_sleep(_seconds: float) -> None:
        await backend.emit_rr_ticks((1024,))

    backend.fail_stop = True
    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=SQLModelClassicPersistence(engine),
        polar=connection,
        launcher=FakeLauncher(backend),
        sleep=phase_sleep,
    )
    prepared = await manager.prepare_session(
        CreateClassicSession(
            participant_id="P30",
            visit_ordinal=1,
            workload_level="HIGH",
            scenario_name="military_aviation/high_workload.txt",
        )
    )

    await manager.start_session(prepared.id, prepared.controller_lease)
    interrupted = await manager.wait_until_finished(prepared.id)

    assert interrupted.status == "INTERRUPTED"
    rr_csv = tmp_path / "classic" / prepared.id / "rr-intervals.csv"
    assert len(rr_csv.read_text(encoding="utf-8").splitlines()) > 1
    phase_results = manager.debrief(prepared.id).hrv["phases"]
    assert sum(result["raw_rr_count"] for result in phase_results.values()) >= 4


@pytest.mark.anyio
async def test_notification_start_failure_exports_rr_already_fsynced_to_journal(
    engine,
    tmp_path,
) -> None:
    _seed(engine)

    class EmitThenFailBackend(SimulatedPolarBackend):
        fail_start = False

        async def start_notifications(self, callback) -> None:
            if self.fail_start:
                await callback(bytes((0x10, 60, 0x00, 0x04)))
                raise PolarBackendError("notification_start_failed")
            await super().start_notifications(callback)

    backend = EmitThenFailBackend()
    connection = PolarConnectionManager(backend)
    candidate = (await connection.scan(0.01))[0]
    await connection.connect(candidate.device_token)
    preflight = asyncio.create_task(connection.preflight(timeout_seconds=1.0))
    await asyncio.sleep(0)
    await backend.emit_rr_ticks((1024,))
    await preflight
    backend.fail_start = True
    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=SQLModelClassicPersistence(engine),
        polar=connection,
        launcher=FakeLauncher(backend),
        sleep=lambda _seconds: None,
    )
    prepared = await manager.prepare_session(
        CreateClassicSession(
            participant_id="P30",
            visit_ordinal=1,
            workload_level="LOW",
            scenario_name="military_aviation/low_workload.txt",
        )
    )

    await manager.start_session(prepared.id, prepared.controller_lease)
    interrupted = await manager.wait_until_finished(prepared.id)

    assert interrupted.status == "INTERRUPTED"
    rr_lines = (
        tmp_path / "classic" / prepared.id / "rr-intervals.csv"
    ).read_text(encoding="utf-8").splitlines()
    assert len(rr_lines) == 2
    assert "1024" in rr_lines[1]


@pytest.mark.anyio
async def test_first_database_finalize_failure_recovers_published_bundle(
    engine,
    tmp_path,
) -> None:
    _seed(engine)
    persistence = SQLModelClassicPersistence(engine)
    real_finalize = persistence.finalize_attempt_with_artifacts
    call_count = 0

    def fail_first_finalize(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ClassicPersistenceError("injected_finalize_failure")
        return real_finalize(*args, **kwargs)

    persistence.finalize_attempt_with_artifacts = fail_first_finalize  # type: ignore[method-assign]
    backend = SimulatedPolarBackend()
    launcher = FakeLauncher(backend)
    launcher.emit_rr = False
    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=persistence,
        polar=PolarConnectionManager(backend),
        launcher=launcher,
        sleep=lambda _seconds: None,
    )
    prepared = await manager.prepare_session(
        CreateClassicSession(
            participant_id="P30",
            visit_ordinal=1,
            workload_level="LOW",
            scenario_name="military_aviation/low_workload.txt",
            performance_only_override=True,
            override_reason_code="sensor_unavailable",
        )
    )

    await manager.start_session(prepared.id, prepared.controller_lease)
    recovered = await manager.wait_until_finished(prepared.id)

    assert call_count >= 2
    assert recovered.status == "COMPLETE"
    assert len(manager.artifacts(prepared.id)) == 12
    session_document = json.loads(
        (tmp_path / "classic" / prepared.id / "session.json").read_text(encoding="utf-8")
    )
    assert manager.debrief(prepared.id).hrv["summary"] == session_document["session"][
        "hrv_summary"
    ]
