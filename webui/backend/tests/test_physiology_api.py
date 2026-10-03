from __future__ import annotations

import asyncio
from datetime import date

import httpx
import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.main import app
from app.models import Participant
from app.physiology_models import PolarCaptureRecord  # noqa: F401
from app.physiology_runtime import PolarCaptureManager
from matb_integration.physiology.transport import SimulatedPolarTransport


@pytest.mark.parametrize("purpose", ["study", "practice"])
def test_polar_http_workflow_uses_tokens_leases_and_no_address(tmp_path, purpose) -> None:
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
                unregistered = await client.post("/physiology/polar-h10/v1/captures", json={
                    "execution_purpose": purpose, "participant_pseudonym": "P99", "matb_session_kind": "generic",
                })
                assert unregistered.status_code == 404
                assert unregistered.json()["detail"]["code"] == "participant_not_found"
                assert (await client.get("/physiology/polar-h10/v1/captures/active")).json() is None
                arguments = {}
                session_context = 'api-test'
                if purpose == 'study':
                    from tests.study_fixtures import h10_arguments
                    from app.physiology_schemas import CaptureSettings
                    selected = h10_arguments(engine, participant_id='P01', session_kind='generic', session_id='api-test', settings=CaptureSettings().model_dump())
                    arguments = {'attempt_id': selected['attempt_id']}
                    session_context = selected['session_id']
                prepared = await client.post("/physiology/polar-h10/v1/captures", json={
                    **arguments, "execution_purpose": purpose,
                    "participant_pseudonym": "P01", "matb_session_kind": "generic",
                    "settings": {
                        "ecg_sample_rate_hz": 130, "ecg_resolution_bits": 14,
                        "acc_sample_rate_hz": 50, "acc_resolution_bits": 16,
                        "acc_range_g": 2,
                    },
                })
                assert prepared.status_code == 201
                capture_id = prepared.json()["capture"]["capture_id"]
                assert prepared.json()["capture"]["matb_session_id"] == (session_context if purpose == "study" else capture_id)
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
                prefix = f"/physiology/polar-h10/v1/captures/{capture_id}"
                assert (await client.get(prefix + "/rr-export")).status_code == 403
                assert (await client.get(prefix + "/rr-export", headers={"X-Polar-Controller": lease})).status_code == 409
                active = await client.get("/physiology/polar-h10/v1/captures/active")
                assert active.json()["capture_id"] == capture_id
                control = f"/physiology/polar-h10/v1/captures/{capture_id}/control"
                assert (await client.get(control)).status_code == 403
                assert (await client.get(control, headers={"X-Polar-Controller": "wrong"})).status_code == 403
                assert (await client.get(control, headers={"X-Polar-Controller": lease})).json()["capture_id"] == capture_id
                blocked = await client.post(f"/physiology/polar-h10/v1/captures/{capture_id}/start", json={}, headers={"X-Polar-Controller": lease})
                assert blocked.status_code == 409
                assert blocked.json()["detail"]["code"] == "polar_capture_already_active"
                denied_stop = await client.post(f"/physiology/polar-h10/v1/captures/{capture_id}/stop", json={})
                assert denied_stop.status_code == 403
                assert (await client.get("/physiology/polar-h10/v1/captures/active")).json()["capture_id"] == capture_id
                simulated.emit_hr(bytes.fromhex("16 3c 00 04"))
                await asyncio.sleep(0.03)
                stopped = await client.post(
                    f"/physiology/polar-h10/v1/captures/{capture_id}/stop", json={},
                    headers={"X-Polar-Controller": lease},
                )
                assert stopped.status_code == 200
                exports = await client.get(prefix + "/rr-export", headers={"X-Polar-Controller": lease})
                assert exports.status_code == 200, exports.text
                assert exports.json()["rr_count"] == 1
                assert exports.json()["execution_purpose"] == purpose
                filename = exports.json()["segments"][0]["txt_filename"]
                downloaded = await client.get(prefix + "/rr-export/files/" + filename, headers={"X-Polar-Controller": lease})
                assert downloaded.status_code == 200 and downloaded.text == "1000\n"
                assert "attachment" in downloaded.headers["content-disposition"]
                assert (await client.get(prefix + "/rr-export/files/manifest.json", headers={"X-Polar-Controller": lease})).status_code == 404
                assert (await client.get(prefix + "/review")).status_code == 403
                reviewed = await client.get(prefix + "/review", headers={"X-Polar-Controller": lease})
                assert reviewed.status_code == 200, reviewed.text
                assert reviewed.json()["respiration"]["respiratory_rate_bpm"] is None
                context = await client.get(prefix + '/rr-export/files/capture_context.json', headers={"X-Polar-Controller": lease})
                assert context.status_code == 200
                assert context.json()['participant_pseudonym'] == 'P01'
                assert context.json()['execution_purpose'] == purpose
                assert context.json()['alias_is_persistent_device_id'] is False
                assert (await client.get("/physiology/polar-h10/v1/captures/active")).json() is None
                inventory = await client.get(
                    f"/physiology/polar-h10/v1/captures/{capture_id}/artifacts",
                    headers={"X-Polar-Controller": lease},
                )
                assert inventory.json()["state"] == "finalized"
                bundle = await client.get(
                    f"/physiology/polar-h10/v1/captures/{capture_id}/bundle",
                    headers={"X-Polar-Controller": lease},
                )
                assert bundle.status_code == (409 if purpose == "practice" else 200)
                missing = await client.get("/physiology/polar-h10/v1/captures/unknown-capture/bundle")
                assert missing.status_code == 404
                gate = await client.get("/physiology/polar-h10/v1/internal-recordings/status")
                assert gate.status_code == 501
                assert gate.json()["detail"]["code"] == "polar_internal_recording_not_qualified"
        finally:
            await manager.shutdown()
            del app.state.polar_manager

    asyncio.run(exercise())
