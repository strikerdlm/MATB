from __future__ import annotations

import asyncio
from datetime import date

import httpx
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.main import app
from app.models import Participant
from app.physiology_models import PolarCaptureRecord  # noqa: F401
from app.physiology_runtime import PolarCaptureManager
from matb_integration.physiology.transport import SimulatedPolarTransport


def test_polar_http_workflow_uses_tokens_leases_and_no_address(tmp_path) -> None:
    async def exercise() -> None:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        SQLModel.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(Participant(id="P01", enrollment_date=date(2026, 9, 3)))
            db.commit()
        simulated = SimulatedPolarTransport()
        manager = PolarCaptureManager(engine=engine, artifact_root=tmp_path, transport=simulated)
        await manager.startup()
        app.state.polar_manager = manager
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        try:
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                headers={"Origin": "http://localhost:3100"},
            ) as client:
                scanned = await client.post(
                    "/physiology/polar-h10/v1/scan", json={"timeout_seconds": 0.25}
                )
                assert scanned.status_code == 200
                assert "address" not in scanned.text.casefold()
                token = scanned.json()[0]["device_token"]
                connected = await client.post(
                    "/physiology/polar-h10/v1/connect", json={"device_token": token}
                )
                assert connected.status_code == 200
                prepared = await client.post("/physiology/polar-h10/v1/captures", json={
                    "participant_pseudonym": "P01", "matb_session_kind": "generic",
                    "matb_session_id": "api-test", "settings": {
                        "ecg_sample_rate_hz": 130, "ecg_resolution_bits": 14,
                        "acc_sample_rate_hz": 50, "acc_resolution_bits": 16,
                        "acc_range_g": 2,
                    },
                })
                assert prepared.status_code == 201
                capture_id = prepared.json()["capture"]["capture_id"]
                lease = prepared.json()["controller_lease"]
                denied = await client.post(
                    f"/physiology/polar-h10/v1/captures/{capture_id}/start", json={}
                )
                assert denied.status_code == 403
                started = await client.post(
                    f"/physiology/polar-h10/v1/captures/{capture_id}/start", json={},
                    headers={"X-Polar-Controller": lease},
                )
                assert started.status_code == 200
                simulated.emit_hr(bytes.fromhex("16 3c 00 04"))
                await asyncio.sleep(0.03)
                stopped = await client.post(
                    f"/physiology/polar-h10/v1/captures/{capture_id}/stop", json={},
                    headers={"X-Polar-Controller": lease},
                )
                assert stopped.status_code == 200
                inventory = await client.get(
                    f"/physiology/polar-h10/v1/captures/{capture_id}/artifacts",
                    headers={"X-Polar-Controller": lease},
                )
                assert inventory.json()["state"] == "finalized"
                gate = await client.get("/physiology/polar-h10/v1/internal-recordings/status")
                assert gate.status_code == 501
                assert gate.json()["detail"]["code"] == "polar_internal_recording_not_qualified"
        finally:
            await manager.shutdown()
            del app.state.polar_manager

    asyncio.run(exercise())
