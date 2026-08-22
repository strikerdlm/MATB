from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from matb_integration.liftoff.protocol import decode_packet
from matb_integration.liftoff.quality import assess_quality
from matb_integration.liftoff.receiver import ReceiverHealth
from matb_integration.liftoff.records import TelemetryRecord
from tests.liftoff.test_protocol import valid_payload


def records_at(times: list[float]) -> list[TelemetryRecord]:
    packet = decode_packet(valid_payload())
    started = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)
    return [
        TelemetryRecord(
            session_id="12345678-1234-5678-1234-567812345678",
            sequence=index,
            received_monotonic_ns=index * 10_000_000,
            received_utc=(started + timedelta(milliseconds=index * 10)).isoformat().replace("+00:00", "Z"),
            packet=replace(packet, simulator_time=simulator_time),
        )
        for index, simulator_time in enumerate(times, start=1)
    ]


@pytest.mark.parametrize(
    ("count", "validity", "reason"),
    [
        (100, "valid", None),
        (96, "partial", "packet_loss_partial"),
        (94, "invalid", "packet_loss_invalid"),
    ],
)
def test_quality_applies_prespecified_packet_loss_thresholds(count, validity, reason):
    times = [index / (count - 1) for index in range(count)]

    report = assess_quality(records_at(times), ReceiverHealth(), expected_rate_hz=100.0)

    assert report.expected_packet_count == 100
    assert report.validity == validity
    assert (reason in report.reason_codes) if reason else not report.reason_codes


def test_quality_reports_ordering_receiver_and_clock_failures():
    health = ReceiverHealth(overflow_count=2, invalid_value_count=1, clock_step_detected=True)

    report = assess_quality(
        records_at([0.0, 0.02, 0.01, 0.03]),
        health,
        expected_rate_hz=100.0,
    )

    assert report.nonmonotonic_count == 1
    assert report.invalid_packet_count == 1
    assert report.overflow_count == 2
    assert report.maximum_gap_s == pytest.approx(0.02)
    assert {
        "receiver_overflow",
        "simulator_time_nonmonotonic",
        "host_clock_step",
    } <= set(report.reason_codes)


def test_quality_marks_silent_stream_invalid():
    report = assess_quality([], ReceiverHealth(), expected_rate_hz=100.0)

    assert report.validity == "invalid"
    assert report.reason_codes == ("no_telemetry",)
