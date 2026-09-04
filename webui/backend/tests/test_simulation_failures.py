from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from types import MethodType
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.models import Participant, PvtAssessment, Visit
from app.simulation_persistence import InMemorySimulationPersistence, SQLModelSimulationPersistence
from app.simulation_runtime import SimulationManager
from app.simulation_schemas import CommandRequest, CreateSimulationSession, CreateTechnicalSimulationSession
from matb_integration.suas.recording.records import RecordingError


async def _running(manager: SimulationManager, engine) -> tuple[object, str]:
    with Session(engine) as db:
        db.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        db.add(Visit(participant_id="P01", visit_ordinal=1, scheduled_day=0))
        db.commit()
        db.add(PvtAssessment(participant_id="P01", visit_id=1, kss_score=3,
            administered_at="2026-06-01T12:00:00Z", duration_ms=600000, pvt_version=2,
            protocol_valid=True, raw_trials_json="[]", metrics_json="{}"))
        db.commit()
        prepared = await manager.prepare(
            CreateSimulationSession(
                participant_id="P01", visit_ordinal=1,
                scenario_id="reference_area_search", locale="en",
            ),
            db,
        )
    await manager.start(prepared.id, "PRACTICE", prepared.controller_lease)
    return prepared, prepared.controller_lease


@pytest.mark.anyio
async def test_recording_error_interrupts_without_advancing(engine, tmp_path, monkeypatch) -> None:
    persistence = InMemorySimulationPersistence()
    manager = SimulationManager(
        scenario_root=Path(__file__).resolve().parents[3] / "scenarios" / "suas",
        artifact_root=tmp_path,
        persistence=persistence,
        run_background_tasks=False,
    )
    prepared, lease = await _running(manager, engine)
    for _ in range(10):
        await manager.tick_once()
    before = (await manager.state(prepared.id))["state_version"]

    def fail(_record) -> None:
        raise RecordingError("disk full")

    monkeypatch.setattr(manager.active.recorder, "append", fail)
    command_task = asyncio.create_task(manager.submit(
        prepared.id,
        lease,
        CommandRequest(
            command_id=uuid4(), expected_state_version=before,
            kind="HOLD", payload={"aircraft_id": "UAS-01"},
        ),
    ))
    await asyncio.sleep(0)
    await manager.tick_once()
    with pytest.raises(RecordingError):
        await command_task
    assert (await manager.view(prepared.id)).lifecycle == "INTERRUPTED"
    assert (await manager.state(prepared.id))["state_version"] == before
    assert persistence.deviations[-1]["code"] == "recording_failure"


@pytest.mark.anyio
async def test_explicit_recovery_restores_checkpoint_and_marks_deviation(engine, tmp_path, monkeypatch) -> None:
    persistence = InMemorySimulationPersistence()
    manager = SimulationManager(
        scenario_root=Path(__file__).resolve().parents[3] / "scenarios" / "suas",
        artifact_root=tmp_path,
        persistence=persistence,
        run_background_tasks=False,
    )
    prepared, lease = await _running(manager, engine)
    for _ in range(50):
        await manager.tick_once()
    before_failure = (await manager.state(prepared.id))["simulation_time_ms"]

    def fail(_record) -> None:
        raise RecordingError("disk full")

    monkeypatch.setattr(manager.active.recorder, "append", fail)
    command_task = asyncio.create_task(manager.submit(
        prepared.id, lease,
        CommandRequest(
            command_id=uuid4(), expected_state_version=50,
            kind="HOLD", payload={"aircraft_id": "UAS-01"},
        ),
    ))
    await asyncio.sleep(0)
    await manager.tick_once()
    with pytest.raises(RecordingError):
        await command_task
    monkeypatch.setattr(manager.active.recorder, "append", MethodType(type(manager.active.recorder).append, manager.active.recorder))
    recovered = await manager.recover(prepared.id, lease, checkpoint_version=1)
    assert recovered.lifecycle == "PAUSED"
    assert recovered.validity == "valid_with_deviation"
    assert (await manager.state(prepared.id))["simulation_time_ms"] == before_failure
    assert persistence.deviations[-1]["code"] == "checkpoint_recovery"


@pytest.mark.anyio
async def test_recovery_requires_existing_lease(engine, tmp_path) -> None:
    manager = SimulationManager(
        scenario_root=Path(__file__).resolve().parents[3] / "scenarios" / "suas",
        artifact_root=tmp_path,
        persistence=InMemorySimulationPersistence(),
        run_background_tasks=False,
    )
    prepared, _lease = await _running(manager, engine)
    manager.active.lifecycle = "INTERRUPTED"
    with pytest.raises(Exception):
        await manager.recover(prepared.id, None, checkpoint_version=1)


@pytest.mark.anyio
async def test_process_restart_recovery_preserves_technical_classification(engine, tmp_path) -> None:
    scenario_root = Path(__file__).resolve().parents[3] / "scenarios" / "suas"
    artifact_root = tmp_path / "exports"
    persistence = SQLModelSimulationPersistence(engine)
    original = SimulationManager(
        scenario_root=scenario_root,
        artifact_root=artifact_root,
        persistence=persistence,
        run_background_tasks=False,
    )
    with Session(engine) as db:
        prepared = await original.prepare_technical(
            CreateTechnicalSimulationSession(
                scenario_id="reference_area_search",
                block_id="HIGH",
                locale="en",
            ),
            db,
        )
    await original.start(prepared.id, "HIGH", prepared.controller_lease)
    for _ in range(50):
        await original.tick_once()
    await original.shutdown()
    original.active.recorder.close()

    recovered_manager = SimulationManager(
        scenario_root=scenario_root,
        artifact_root=artifact_root,
        persistence=persistence,
        run_background_tasks=False,
    )
    recovered = await recovered_manager.recover(
        prepared.id,
        None,
        checkpoint_version=1,
        confirm_process_restart=True,
    )
    assert recovered.session_mode == "interactive_technical"
    assert recovered.record_class == "technical_only"
    assert recovered.selected_block_id == "HIGH"
    assert recovered.block_order == ["HIGH"]
    assert recovered.participant_id is None
    assert recovered.visit_id is None
    assert recovered.validity == "technical_only_with_deviation"
    await recovered_manager.shutdown()
