from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

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
