from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest


def create_payload(*, polar_recording_confirmed: bool = True) -> dict[str, object]:
    return {
        "participant_id": "P01",
        "visit_ordinal": 1,
        "configuration": {
            "liftoff_build": "1.6.0-test",
            "track_id": "astra-neutral-time-trial-v1",
            "drone_id": "astra-standard-quad-v1",
            "flight_mode": "acro",
            "camera_angle_deg": 25,
            "fov_deg": 110,
            "rates_profile": "astra-v1",
            "controller_model": "research-rc",
            "controller_firmware": "1.0.0",
            "resolution": "1920x1080",
            "refresh_rate_hz": 120,
            "graphics_preset": "medium",
            "damage_enabled": False,
            "battery_enabled": False,
            "telemetry_profile": "liftoff-telemetry-all-v1",
        },
        "polar_recording_confirmed": polar_recording_confirmed,
        "performance_only_reason": None if polar_recording_confirmed else "polar_unavailable",
    }


async def prepared_session(liftoff_client):
    client, manager = liftoff_client
    manager.receiver.inject_valid_packets(20)
    response = await client.post("/liftoff/sessions", json=create_payload())
    assert response.status_code == 201, response.text
    return response.json(), response.json()["controller_lease"]


async def transition(client, session_id: str, action: str, lease: str):
    return await client.post(
        f"/liftoff/sessions/{session_id}/{action}",
        json={},
        headers={"X-Liftoff-Controller": lease},
    )


@pytest.mark.anyio
async def test_create_session_returns_one_time_lease(liftoff_client):
    client, manager = liftoff_client
    manager.receiver.inject_valid_packets(20)

    response = await client.post("/liftoff/sessions", json=create_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PREPARED"
    assert body["controller_lease"]
    fetched = await client.get(f"/liftoff/sessions/{body['id']}")
    assert fetched.status_code == 200
    assert "controller_lease" not in fetched.json()
    assert "artifact_root" not in fetched.json()


@pytest.mark.anyio
async def test_task_cannot_start_before_baseline_finishes(liftoff_client):
    client, _manager = liftoff_client
    session, lease = await prepared_session(liftoff_client)

    response = await transition(client, session["id"], "task/start", lease)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "liftoff_phase_order"


@pytest.mark.anyio
async def test_prepare_through_seal_exposes_verified_artifacts_and_bundle(liftoff_client):
    client, _manager = liftoff_client
    session, lease = await prepared_session(liftoff_client)
    headers = {"X-Liftoff-Controller": lease}
    for action in (
        "baseline/start",
        "baseline/finish",
        "task/start",
        "task/finish",
        "recovery/start",
        "recovery/finish",
    ):
        response = await transition(client, session["id"], action, lease)
        assert response.status_code == 200, response.text

    screenshot = b"\x89PNG\r\n\x1a\nsynthetic"
    result_payload = {
        "valid_lap_times_s": [61.2, 63.0, 60.8],
        "invalid_laps": 1,
        "observer_restart_count": 0,
        "screenshot_sha256": hashlib.sha256(screenshot).hexdigest(),
    }
    results = await client.post(
        f"/liftoff/sessions/{session['id']}/results",
        data={"metadata": json.dumps(result_payload)},
        files={"screenshot": ("ignored-name.png", screenshot, "image/png")},
        headers=headers,
    )
    assert results.status_code == 201, results.text
    questionnaires = await client.post(
        f"/liftoff/sessions/{session['id']}/questionnaires",
        json={
            "kss": 4,
            "mental_demand": 55,
            "physical_demand": 15,
            "temporal_demand": 50,
            "performance": 30,
            "effort": 60,
            "frustration": 20,
        },
        headers=headers,
    )
    assert questionnaires.status_code == 201, questionnaires.text
    sealed = await client.post(
        f"/liftoff/sessions/{session['id']}/seal",
        json={},
        headers=headers,
    )
    assert sealed.status_code == 200, sealed.text
    assert sealed.json()["status"] == "FINISHED"
    assert sealed.json()["quality"]["validity"] == "invalid"

    artifacts = await client.get(f"/liftoff/sessions/{session['id']}/artifacts")
    assert artifacts.status_code == 200
    assert all("/tmp/" not in row["relative_path"] for row in artifacts.json())
    assert any(row["relative_path"] == "checksums.sha256" for row in artifacts.json())
    bundle = await client.get(f"/liftoff/sessions/{session['id']}/bundle")
    assert bundle.status_code == 200
    assert bundle.headers["cache-control"] == "no-store"
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        assert "checksums.sha256" in archive.namelist()
        assert "debrief.json" in archive.namelist()
