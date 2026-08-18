from __future__ import annotations

import hashlib
import json

import pytest

from app.hrv_task_client import HrvTaskTemporaryError
from tests.test_liftoff_endpoints import (
    FakeHrvClient,
    create_payload,
    finish_phases,
    polar_metadata,
    prepared_session,
    valid_hrv_response,
)


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


@pytest.mark.anyio
async def test_hrv_outage_leaves_retryable_pending_link(liftoff_client):
    client, manager = liftoff_client
    session, lease = await prepared_session(liftoff_client)
    await finish_phases(client, session["id"], lease)
    rr_content = "\n".join(["800"] * 1900)
    manager.hrv_client = FakeHrvClient(error=HrvTaskTemporaryError("hrv_unavailable"))
    files = {
        "rr_file": ("polar.txt", rr_content.encode(), "text/plain"),
        "metadata_file": ("polar.metadata.json", json.dumps(polar_metadata(session["id"], rr_content)).encode(), "application/json"),
    }

    response = await client.post(
        f"/liftoff/sessions/{session['id']}/physiology-link",
        files=files,
        headers={"X-Liftoff-Controller": lease},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    pending = manager._active[session["id"]].recorder.run_dir / "pending-hrv-request.json"
    assert pending.is_file()
    manager.hrv_client = FakeHrvClient(valid_hrv_response(session["id"], "hrv-retry"))
    retry = await client.post(
        f"/liftoff/sessions/{session['id']}/physiology-link/retry",
        json={},
        headers={"X-Liftoff-Controller": lease},
    )
    assert retry.status_code == 200
    assert retry.json()["hrv_measurement_id"] == "hrv-retry"
    assert not pending.exists()
