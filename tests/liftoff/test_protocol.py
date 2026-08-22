from __future__ import annotations

import math
from pathlib import Path
import struct

import pytest

from matb_integration.liftoff.protocol import (
    LIFTOFF_ALL_V1,
    PACKET_SIZE,
    PacketDecodeError,
    decode_packet,
)
from matb_integration.liftoff.records import MarkerRecord, TelemetryRecord


def valid_payload(*, motor_count: int = 4, replacement: tuple[int, float] | None = None) -> bytes:
    values = [float(index) for index in range(20)]
    if replacement is not None:
        values[replacement[0]] = replacement[1]
    return struct.pack("<20fB4f", *values, motor_count, 1000.0, 1001.0, 1002.0, 1003.0)


def test_decode_all_profile():
    packet = decode_packet(valid_payload())

    assert LIFTOFF_ALL_V1 == "liftoff-telemetry-all-v1"
    assert PACKET_SIZE == 97
    assert packet.simulator_time == 0.0
    assert packet.position_native == (1.0, 2.0, 3.0)
    assert packet.attitude_native == (4.0, 5.0, 6.0, 7.0)
    assert packet.processed_input == (14.0, 15.0, 16.0, 17.0)
    assert packet.motor_count == 4
    assert packet.motor_rpm == (1000.0, 1001.0, 1002.0, 1003.0)


@pytest.mark.parametrize("payload", [b"", b"x" * 96, b"x" * 98])
def test_wrong_size_rejected(payload):
    with pytest.raises(PacketDecodeError, match="packet_size"):
        decode_packet(payload)


def test_nonfinite_packet_value_rejected():
    with pytest.raises(PacketDecodeError, match="packet_values"):
        decode_packet(valid_payload(replacement=(5, math.nan)))


def test_unsupported_motor_count_rejected():
    with pytest.raises(PacketDecodeError, match="motor_count"):
        decode_packet(valid_payload(motor_count=6))


def test_synthetic_fixture_matches_preliminary_profile():
    payload = Path("tests/liftoff/fixtures/everything_v1_synthetic.bin").read_bytes()

    assert payload == valid_payload()
    assert decode_packet(payload).charge_percent == 19.0


def test_telemetry_record_is_flat_and_strict():
    record = TelemetryRecord(
        session_id="12345678-1234-5678-1234-567812345678",
        sequence=1,
        received_monotonic_ns=10,
        received_utc="2026-08-17T14:00:00.000000Z",
        packet=decode_packet(valid_payload()),
    )

    payload = record.as_dict()
    assert payload["schema_version"] == "liftoff-telemetry-v1"
    assert payload["position_native"] == [1.0, 2.0, 3.0]
    assert payload["motor_rpm"] == [1000.0, 1001.0, 1002.0, 1003.0]
    assert "packet" not in payload
    with pytest.raises(ValueError, match="sequence"):
        TelemetryRecord(
            session_id=record.session_id,
            sequence=0,
            received_monotonic_ns=10,
            received_utc=record.received_utc,
            packet=record.packet,
        )


def test_marker_record_accepts_only_declared_kinds_and_valid_amendments():
    base = {
        "session_id": "12345678-1234-5678-1234-567812345678",
        "sequence": 2,
        "received_monotonic_ns": 20,
        "received_utc": "2026-08-17T14:00:01Z",
        "phase": "baseline",
        "source": "operator",
    }
    marker = MarkerRecord(kind="baseline_started", **base)
    amendment = MarkerRecord(kind="amendment", amendment_of_sequence=1, **base)

    assert marker.as_dict()["kind"] == "baseline_started"
    assert amendment.as_dict()["amendment_of_sequence"] == 1
    with pytest.raises(ValueError, match="kind"):
        MarkerRecord(kind="unknown", **base)
    with pytest.raises(ValueError, match="amendment_of_sequence"):
        MarkerRecord(kind="amendment", amendment_of_sequence=2, **base)
