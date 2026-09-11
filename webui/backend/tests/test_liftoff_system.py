from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import struct

import pytest

from matb_integration.liftoff.protocol import decode_packet
from matb_integration.liftoff.session import LIFTOFF_PROFILE
from matb_integration.recording.artifacts import verify_checksum_file
from tests.test_liftoff_endpoints import (
    FakeHrvClient,
    create_payload,
    finish_phases,
    polar_metadata,
    prepared_session,
    valid_hrv_response,
)


def valid_payload(*, simulator_time: float) -> bytes:
    values = [float(index) for index in range(20)]
    values[0] = simulator_time
    return struct.pack("<20fB4f", *values, 4, 1000.0, 1001.0, 1002.0, 1003.0)


@pytest.mark.anyio
async def test_full_liftoff_collection_round_trip(liftoff_client):
    client, manager = liftoff_client
    session, lease = await prepared_session(liftoff_client)
    active = manager._active[session["id"]]
    started = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)
    for index in range(600):
        active.recorder.append_packet(
            valid_payload(simulator_time=index / 60.0),
            received_monotonic_ns=1_000_000_000 + index * 16_666_667,
            received_utc=started + timedelta(seconds=index / 60.0),
        )
    await finish_phases(client, session["id"], lease)
    screenshot = b"\x89PNG\r\n\x1a\nsynthetic"
    import hashlib
    results = await client.post(
        f"/liftoff/sessions/{session['id']}/results",
        data={"metadata": json.dumps({
            "valid_lap_times_s": [61.2, 63.0, 60.8],
            "invalid_laps": 1,
            "observer_restart_count": 0,
            "screenshot_sha256": hashlib.sha256(screenshot).hexdigest(),
        })},
        files={"screenshot": ("result.png", screenshot, "image/png")},
        headers={"X-Liftoff-Controller": lease},
    )
    assert results.status_code == 201
    assert (await client.post(
        f"/liftoff/sessions/{session['id']}/questionnaires",
        json={
            "kss": 4, "mental_demand": 50, "physical_demand": 20,
            "temporal_demand": 50, "performance": 40, "effort": 55,
            "frustration": 20,
        },
        headers={"X-Liftoff-Controller": lease},
    )).status_code == 201
    closed = await client.post('/station/close', json={'actor': 'Dr Fixture', 'reason': 'All assigned collection and ratings complete; import post-visit physiology'})
    assert closed.status_code == 200, closed.text
    rr_content = "\n".join(["800"] * 1900)
    manager.hrv_client = FakeHrvClient(valid_hrv_response(session["id"], session["id"]))
    assert (await client.post(
        f"/liftoff/sessions/{session['id']}/physiology-link",
        files={
            "rr_file": ("polar.txt", rr_content.encode(), "text/plain"),
            "metadata_file": ("polar.metadata.json", json.dumps(polar_metadata(session["id"], rr_content)).encode(), "application/json"),
        },
        headers={"X-Liftoff-Controller": lease},
    )).status_code == 200
    sealed = await client.post(
        f"/liftoff/sessions/{session['id']}/seal",
        json={},
        headers={"X-Liftoff-Controller": lease},
    )
    assert sealed.status_code == 200, sealed.text
    assert sealed.json()["validity"] == "valid"
    row = manager.persistence.load_session(session["id"])
    assert row is not None
    run_dir = Path(row.artifact_root)
    assert verify_checksum_file(run_dir, profile=LIFTOFF_PROFILE) == ()

    raw = (run_dir / "telemetry.raw").read_bytes()
    canonical = [json.loads(line) for line in (run_dir / "telemetry.jsonl").read_text().splitlines()]
    offset = 0
    decoded_times = []
    header = struct.Struct("<4sQQqH")
    while offset < len(raw):
        magic, sequence, _monotonic, _utc_ns, size = header.unpack_from(raw, offset)
        offset += header.size
        payload = raw[offset:offset + size]
        offset += size
        assert magic == b"LFT1"
        assert sequence == len(decoded_times) + 1
        decoded_times.append(decode_packet(payload).simulator_time)
    assert decoded_times == [row["simulator_time"] for row in canonical]
