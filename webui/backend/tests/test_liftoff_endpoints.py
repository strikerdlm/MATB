from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest


def create_payload(*, polar_recording_confirmed: bool = True) -> dict[str, object]:
    return {
        "participant_id": "P01",
        "execution_purpose": "study",
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


async def finish_phases(client, session_id: str, lease: str) -> None:
    for action in (
        "baseline/start",
        "baseline/finish",
        "task/start",
        "task/finish",
        "recovery/start",
        "recovery/finish",
    ):
        response = await transition(client, session_id, action, lease)
        assert response.status_code == 200, response.text


def polar_metadata(session_id: str, rr_content: str) -> dict[str, object]:
    return {
        "schema_version": "polar-task-capture-v1",
        "recorder_version": "polar-h10-recorder-v1",
        "capture_id": "11111111-2222-4333-8444-555555555555",
        "external_session_id": session_id,
        "participant_id": "P01",
        "recording_start_utc": "2026-08-17T14:00:00Z",
        "recording_end_utc": "2026-08-17T14:25:20Z",
        "start_monotonic_ns": 1_000_000_000,
        "end_monotonic_ns": 1_521_000_000_000,
        "first_rr_received_monotonic_ns": 1_800_000_000,
        "last_rr_received_monotonic_ns": 1_520_200_000_000,
        "device_identifier_hash": "a" * 64,
        "rr_count": 1900,
        "rr_file_sha256": hashlib.sha256(rr_content.encode()).hexdigest(),
    }


def valid_hrv_response(session_id: str, measurement_id: str = "hrv-123") -> dict[str, object]:
    phase = {
        "mean_hr_bpm": 75.0,
        "rmssd_ms": 40.0,
        "lnrmssd": 3.688879,
        "artifact_percentage": 0.0,
        "usable_coverage_pct": 100.0,
    }
    return {
        "contract_version": "task-session-hrv-v1",
        "external_session_id": session_id,
        "participant_id": "P01",
        "measurement_id": measurement_id,
        "rr_file_sha256": "placeholder",
        "rr_count": 1900,
        "recording_start_utc": "2026-08-17T14:00:00Z",
        "segment_indices": [
            {"label": "baseline", "start_idx": 0, "end_idx": 374},
            {"label": "task", "start_idx": 375, "end_idx": 1499},
            {"label": "recovery", "start_idx": 1500, "end_idx": 1874},
        ],
        "phase_metrics": {"baseline": phase, "task": phase, "recovery": phase},
        "delta_lnrmssd_baseline_task": 0.0,
        "delta_lnrmssd_task_recovery": 0.0,
        "quality": {"status": "good", "artifact_percentage": 0.0, "usable_rr_count": 1900, "reason_codes": []},
    }


class FakeHrvClient:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.requests = []

    async def analyze(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        payload = dict(self.response)
        payload["rr_file_sha256"] = request.rr_file_sha256
        from app.hrv_task_client import TaskSessionHrvResponse
        return TaskSessionHrvResponse.model_validate(payload)


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
async def test_practice_export_is_denied_and_missing_export_is_not_found(liftoff_client):
    client, manager = liftoff_client
    manager.receiver.inject_valid_packets(20)
    response = await client.post("/liftoff/sessions", json={
        **create_payload(), "execution_purpose": "practice",
    })
    assert response.status_code == 201, response.text
    session_id = response.json()["id"]
    denied = await client.get(f"/liftoff/sessions/{session_id}/bundle")
    assert denied.status_code == 409
    assert denied.json()["detail"]["code"] == "practice_not_research_export"
    missing = await client.get("/liftoff/sessions/unknown-session/bundle")
    assert missing.status_code == 404


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


@pytest.mark.anyio
async def test_hrv_link_persists_authoritative_response(liftoff_client):
    client, manager = liftoff_client
    session, lease = await prepared_session(liftoff_client)
    await finish_phases(client, session["id"], lease)
    rr_content = "\n".join(["800"] * 1900)
    manager.hrv_client = FakeHrvClient(valid_hrv_response(session["id"]))

    response = await client.post(
        f"/liftoff/sessions/{session['id']}/physiology-link",
        files={
            "rr_file": ("polar.txt", rr_content.encode(), "text/plain"),
            "metadata_file": ("polar.metadata.json", json.dumps(polar_metadata(session["id"], rr_content)).encode(), "application/json"),
        },
        headers={"X-Liftoff-Controller": lease},
    )

    assert response.status_code == 200, response.text
    assert response.json()["hrv_measurement_id"] == "hrv-123"
    assert response.json()["sync_quality"] == "good"
    assert (manager._active[session["id"]].recorder.run_dir / "physiology-link.json").is_file()
