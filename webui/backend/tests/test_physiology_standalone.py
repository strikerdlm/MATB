"""Standalone recordings retain raw data without requiring a test or study."""
import asyncio
from datetime import date

import httpx
import pyarrow.parquet as pq
import pytest
from fastapi import HTTPException
from sqlmodel import Session

from app.main import app
from app.models import Participant
from app.physiology_runtime import PolarCaptureManager
from app.station_resources import admit, finish, snapshot
from matb_integration.physiology.transport import SimulatedPolarTransport


@pytest.mark.parametrize("foreground_first", [True, False])
@pytest.mark.parametrize("stop_first", ["foreground", "physiology"])
def test_standalone_recording_and_practice_task_keep_separate_ownership(
    engine, tmp_path, monkeypatch, foreground_first, stop_first,
):
    async def exercise():
        with Session(engine) as db:
            db.add(Participant(id="P01", enrollment_date=date(2026, 10, 2)))
            db.commit()
        transport = SimulatedPolarTransport()
        manager = PolarCaptureManager(engine=engine, artifact_root=tmp_path, transport=transport)
        await manager.startup()
        monkeypatch.setattr(app.state, "polar_manager", manager, raising=False)
        device, _ = (await manager.scan(0.25))[0]
        await manager.connect(device)

        def start_foreground():
            with Session(engine) as db:
                admit(db, "simulation:practice", instrument="suas", owner="standalone:practice")
                db.commit()

        def finish_foreground():
            with Session(engine) as db:
                finish(db, "simulation:practice")
                db.commit()

        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver",
                headers={"Origin": "http://localhost:3100"},
            ) as client:
                body = dict(execution_purpose="practice", participant_pseudonym="P01", matb_session_kind="generic")
                prepared = await client.post("/physiology/polar-h10/v1/captures", json=body)
                assert prepared.status_code == 201, prepared.text
                payload = prepared.json()
                identity = payload["capture"]["capture_id"]
                assert payload["capture"]["matb_session_id"] == identity
                headers = {"X-Polar-Controller": payload["controller_lease"]}
                if foreground_first:
                    start_foreground()
                response = await client.post(f"/physiology/polar-h10/v1/captures/{identity}/start", json={}, headers=headers)
                assert response.status_code == 200, response.text
                if not foreground_first:
                    start_foreground()
                with Session(engine) as db:
                    state = snapshot(db)
                    assert len(state["acquisitions"]) == 2
                    assert state["acquisitions"][f"polar_capture:{identity}"]["independent_physiology"]
                    with pytest.raises(HTTPException):
                        admit(db, "second-task", instrument="pvt", owner="standalone:second")
                    db.rollback()
                transport.emit_hr(bytes.fromhex("16 3c 00 04"))
                transport.emit_ecg(10_000_000_000, (-100, 0, 100))
                transport.emit_acc(10_000_000_000, ((0, 0, 1000), (10, 0, 999)))
                if stop_first == "foreground":
                    finish_foreground()
                    with Session(engine) as db:
                        state = snapshot(db)
                        assert len(state["acquisitions"]) == 1
                        assert state["reservation"]["owner"] == f"standalone:polar_capture:{identity}"
                stopped = await client.post(f"/physiology/polar-h10/v1/captures/{identity}/stop", json={}, headers=headers)
                assert stopped.status_code == 200, stopped.text
                assert stopped.json()["artifact_state"] == "finalized"
                if stop_first == "physiology":
                    with Session(engine) as db:
                        state = snapshot(db)
                        assert list(state["acquisitions"]) == ["simulation:practice"]
                        assert state["reservation"]["owner"] == "standalone:practice"
                    finish_foreground()
                for stream, count in [("rr", 1), ("ecg", 3), ("acc", 2)]:
                    assert pq.read_table(tmp_path / identity / f"{stream}.parquet").num_rows == count
                assert (tmp_path / identity / "manifest.json").is_file()
                with Session(engine) as db:
                    assert snapshot(db)["reservation"] is None
                    assert snapshot(db)["acquisitions"] == {}
                second = await client.post("/physiology/polar-h10/v1/captures", json=body)
                assert second.status_code == 201
                assert second.json()["capture"]["matb_session_id"] != payload["capture"]["matb_session_id"]
                for change in ({"matb_session_kind": "openmatb"}, {"execution_purpose": "study"}):
                    rejected = await client.post("/physiology/polar-h10/v1/captures", json={**body, **change})
                    assert rejected.status_code == (422 if change.get("matb_session_kind") == "openmatb" else 409)
                rejected = await client.post("/physiology/polar-h10/v1/captures", json={
                    **body, "execution_purpose": "study", "matb_session_id": "unassigned",
                })
                assert rejected.status_code == 409
                assert rejected.json()["detail"]["code"] == "study_assignment_required"
        finally:
            await manager.shutdown()

    asyncio.run(exercise())


@pytest.mark.parametrize("blocker", ["assignment", "maintenance", "another_h10", "uncertain"])
def test_independent_recording_preserves_station_protection(engine, blocker):
    from app.station_resources import StationState
    with Session(engine) as db:
        if blocker == "assignment":
            admit(db, "study", instrument="pvt", owner="assignment:study", participant="P01", visit=1)
        else:
            admit(db, "other", instrument="physiology" if blocker == "another_h10" else "suas",
                  owner="standalone:other", independent_physiology=blocker == "another_h10")
            if blocker == "maintenance":
                finish(db, "other")
                state = db.get(StationState, 1)
                state.maintenance = True
                db.add(state)
            elif blocker == "uncertain":
                finish(db, "other", uncertain=True)
        db.commit()
        original = snapshot(db)
        with pytest.raises(HTTPException):
            admit(db, "h10", instrument="physiology", owner="standalone:h10", independent_physiology=True)
        db.rollback()
        assert snapshot(db) == original
