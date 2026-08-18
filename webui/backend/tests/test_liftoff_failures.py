from __future__ import annotations

import hashlib
import json

import pytest

from tests.test_liftoff_endpoints import create_payload, prepared_session


@pytest.mark.anyio
async def test_create_requires_telemetry_readiness(liftoff_client):
    client, _manager = liftoff_client

    response = await client.post("/liftoff/sessions", json=create_payload())

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "liftoff_telemetry_not_ready"


@pytest.mark.anyio
async def test_performance_only_collection_requires_bounded_reason(liftoff_client):
    client, manager = liftoff_client
    manager.receiver.inject_valid_packets(20)
    payload = create_payload(polar_recording_confirmed=False)
    payload["performance_only_reason"] = None

    response = await client.post("/liftoff/sessions", json=payload)

    assert response.status_code == 422


@pytest.mark.anyio
async def test_transition_requires_exact_controller_lease(liftoff_client):
    client, _manager = liftoff_client
    session, _lease = await prepared_session(liftoff_client)

    response = await client.post(
        f"/liftoff/sessions/{session['id']}/baseline/start",
        json={},
        headers={"X-Liftoff-Controller": "wrong"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "liftoff_invalid_lease"


@pytest.mark.anyio
async def test_result_upload_rejects_magic_and_hash_mismatch(liftoff_client):
    client, _manager = liftoff_client
    session, lease = await prepared_session(liftoff_client)
    screenshot = b"not-an-image"
    metadata = {
        "valid_lap_times_s": [60.0],
        "invalid_laps": 0,
        "observer_restart_count": 0,
        "screenshot_sha256": hashlib.sha256(b"different").hexdigest(),
    }

    response = await client.post(
        f"/liftoff/sessions/{session['id']}/results",
        data={"metadata": json.dumps(metadata)},
        files={"screenshot": ("result.png", screenshot, "image/png")},
        headers={"X-Liftoff-Controller": lease},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] in {
        "liftoff_screenshot_type",
        "liftoff_screenshot_hash",
    }
