from __future__ import annotations

import pytest

from app.websocket.simulation import StreamEnvelope, StreamKind


def test_stream_envelope_is_strict_and_json_safe() -> None:
    envelope = StreamEnvelope(
        session_id="sim-20260801-00000000",
        sequence=1,
        simulation_time_ms=0,
        wall_time_utc="2026-08-01T12:00:00Z",
        state_version=0,
        kind=StreamKind.SNAPSHOT,
        payload={"resynchronizes_after_sequence": 0},
    )
    assert envelope.as_json()["kind"] == "snapshot"
    with pytest.raises(ValueError):
        StreamEnvelope(
            session_id="sim-1",
            sequence=0,
            simulation_time_ms=0,
            wall_time_utc="2026-08-01T12:00:00Z",
            state_version=0,
            kind=StreamKind.SNAPSHOT,
            payload={},
            unexpected=True,
        )
