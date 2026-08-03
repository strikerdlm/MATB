from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.models import Participant, Visit
from app.simulation_persistence import InMemorySimulationPersistence
from app.simulation_runtime import InvalidLease, SimulationConflict, SimulationManager
from app.simulation_schemas import CommandRequest, CreateSimulationSession


@pytest.fixture
def runtime_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    import app.models  # noqa: F401
    import app.simulation_models  # noqa: F401
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        db.add(Visit(participant_id="P01", visit_ordinal=1, scheduled_day=0))
        db.commit()
    return engine


@pytest.fixture
def manager(tmp_path: Path):
    return SimulationManager(
        scenario_root=Path(__file__).resolve().parents[3] / "scenarios" / "suas",
        artifact_root=tmp_path / "exports",
        persistence=InMemorySimulationPersistence(),
        run_background_tasks=False,
    )


def request() -> CreateSimulationSession:
    return CreateSimulationSession(participant_id="P01", visit_ordinal=1, scenario_id="reference_area_search", locale="en")


@pytest.mark.anyio
async def test_prepare_start_tick_snapshot_and_lease(manager, runtime_db):
    with Session(runtime_db) as db:
        prepared = await manager.prepare(request(), db)
    assert prepared.controller_lease
    assert prepared.lifecycle == "PREPARED"
    with pytest.raises(InvalidLease):
        await manager.start(prepared.id, "PRACTICE", "wrong")
    await manager.start(prepared.id, "PRACTICE", prepared.controller_lease)
    await manager.tick_once()
    await manager.tick_once()
    state = await manager.state(prepared.id)
    assert state["simulation_time_ms"] == 200
    first = await manager.snapshot_once()
    second = await manager.snapshot_once()
    assert first["state_version"] == second["state_version"]
    await manager.shutdown()


@pytest.mark.anyio
async def test_only_one_active_session(manager, runtime_db):
    with Session(runtime_db) as db:
        first = await manager.prepare(request(), db)
        with pytest.raises(SimulationConflict):
            await manager.prepare(request(), db)
    await manager.shutdown()


@pytest.mark.anyio
async def test_submit_is_queued_until_tick(manager, runtime_db):
    with Session(runtime_db) as db:
        prepared = await manager.prepare(request(), db)
    await manager.start(prepared.id, "PRACTICE", prepared.controller_lease)
    task = asyncio.create_task(manager.submit(prepared.id, prepared.controller_lease, CommandRequest(
        command_id="11111111-1111-1111-1111-111111111111", expected_state_version=0,
        kind="HOLD", payload={"aircraft_id": "UAS-01"},
    )))
    await asyncio.sleep(0)
    await manager.tick_once()
    result = await task
    assert result.status.value in {"accepted", "rejected"}
    await manager.shutdown()


@pytest.mark.anyio
async def test_stale_controller_disconnect_does_not_pause_replacement_stream(manager, runtime_db):
    with Session(runtime_db) as db:
        prepared = await manager.prepare(request(), db)
    await manager.start(prepared.id, "PRACTICE", prepared.controller_lease)

    replacement = await manager.hub.subscribe(prepared.id, role="controller")
    await manager.controller_disconnected(prepared.id, prepared.controller_lease)
    assert manager.active is not None
    assert manager.active.lifecycle == "RUNNING"

    await manager.hub.unsubscribe(replacement)
    await manager.controller_disconnected(prepared.id, prepared.controller_lease)
    assert manager.active.lifecycle == "PAUSED"
    await manager.shutdown()


@pytest.mark.anyio
async def test_pending_controller_handoff_defers_disconnect_pause(manager, runtime_db):
    with Session(runtime_db) as db:
        prepared = await manager.prepare(request(), db)
    await manager.start(prepared.id, "PRACTICE", prepared.controller_lease)

    await manager.controller_connected(prepared.id, prepared.controller_lease)
    await manager.controller_disconnected(prepared.id, prepared.controller_lease)
    assert manager.active is not None and manager.active.lifecycle == "RUNNING"

    await manager.controller_stream_established(prepared.id, prepared.controller_lease)
    await manager.controller_disconnected(prepared.id, prepared.controller_lease)
    assert manager.active.lifecycle == "PAUSED"
    await manager.shutdown()


@pytest.mark.anyio
async def test_protocol_probe_pauses_and_redacts_operational_state(manager, runtime_db):
    with Session(runtime_db) as db:
        prepared = await manager.prepare(request(), db)
    await manager.start(prepared.id, "PRACTICE", prepared.controller_lease)

    # Practice ISA is scheduled at 150 s. One-shot ticks keep the test fully
    # deterministic and avoid depending on wall-clock scheduling.
    while manager.active is not None and manager.active.protocol is not None and manager.active.protocol.active_probe is None:
        await manager.tick_once()
    assert manager.active is not None and manager.active.protocol is not None
    assert manager.active.protocol.phase.value == "ISA_ACTIVE"
    isa = manager.active.protocol.active_probe
    assert isa is not None and isa.probe_id
    isa_result = await manager.submit(
        prepared.id,
        prepared.controller_lease,
        CommandRequest(
            command_id=uuid4(), expected_state_version=manager.active.engine.snapshot()["state_version"],
            kind="SUBMIT_ISA", payload={"probe_id": isa.probe_id, "rating": 5},
        ),
    )
    assert isa_result.status.value == "accepted"

    while manager.active.protocol.active_probe is None:
        await manager.tick_once()
    sagat = manager.active.protocol.active_probe
    assert sagat is not None and sagat.kind == "SAGAT"
    state = await manager.state(prepared.id)
    assert "aircraft" not in state
    assert "truth" not in str(state)
    assert "correct_answer" not in str(sagat.public_payload)

    while manager.active.protocol.active_probe is not None:
        current = manager.active.protocol.active_probe
        assert current.probe_id
        result = await manager.submit(
            prepared.id,
            prepared.controller_lease,
            CommandRequest(
                command_id=uuid4(), expected_state_version=manager.active.engine.snapshot()["state_version"],
                kind="SUBMIT_SAGAT", payload={"probe_id": current.probe_id, "answer": "Unknown"},
            ),
        )
        assert result.status.value == "accepted"
    assert manager.active.lifecycle == "RUNNING"
    await manager.shutdown()


@pytest.mark.anyio
async def test_repeated_pause_reconnect_and_checkpoint_recovery_cycles(manager, runtime_db):
    """Repeated operator/controller failures do not leak tasks or state."""

    with Session(runtime_db) as db:
        prepared = await manager.prepare(request(), db)
    await manager.start(prepared.id, "PRACTICE", prepared.controller_lease)

    for _ in range(25):
        # One checkpoint is emitted at each 5-second simulation boundary.
        for _ in range(50):
            await manager.tick_once()
        handle = manager.active
        assert handle is not None
        checkpoint_paths = sorted(handle.recorder.checkpoints_dir.glob("checkpoint-*.json.gz"))
        assert checkpoint_paths
        checkpoint_version = int(checkpoint_paths[-1].name.split("-")[-1].split(".")[0])

        await manager.pause(prepared.id, prepared.controller_lease, reason="cycle_pause")
        await manager.resume(prepared.id, prepared.controller_lease)
        await manager.controller_connected(prepared.id, prepared.controller_lease)
        await manager.controller_stream_established(prepared.id, prepared.controller_lease)
        await manager.controller_disconnected(prepared.id, prepared.controller_lease)
        assert manager.active.lifecycle == "PAUSED"

        await manager._interrupt(handle, "cycle_interruption", {"reason": "cycle"})  # noqa: SLF001
        recovered = await manager.recover(
            prepared.id, prepared.controller_lease, checkpoint_version,
        )
        assert recovered.lifecycle == "PAUSED"
        await manager.resume(prepared.id, prepared.controller_lease)
        assert manager.active.lifecycle == "RUNNING"

    await manager.finish(prepared.id, prepared.controller_lease, "abort")
    await manager.shutdown()
