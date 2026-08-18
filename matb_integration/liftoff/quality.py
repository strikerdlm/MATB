"""Deterministic telemetry completeness and ordering audit."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from .protocol import LiftoffPacket
from .receiver import ReceiverHealth
from .records import TelemetryRecord


@dataclass(frozen=True, slots=True)
class TelemetryQualityReport:
    packet_count: int
    expected_packet_count: int
    loss_pct: float
    observed_rate_hz: float
    maximum_gap_s: float
    invalid_packet_count: int
    overflow_count: int
    nonmonotonic_count: int
    clock_step_detected: bool
    validity: str
    reason_codes: tuple[str, ...]


def _simulator_time(record: TelemetryRecord | LiftoffPacket) -> float:
    return record.packet.simulator_time if isinstance(record, TelemetryRecord) else record.simulator_time


def assess_quality(
    records: Sequence[TelemetryRecord | LiftoffPacket],
    health: ReceiverHealth,
    *,
    expected_rate_hz: float,
) -> TelemetryQualityReport:
    if (
        isinstance(expected_rate_hz, bool)
        or not isinstance(expected_rate_hz, (int, float))
        or not math.isfinite(expected_rate_hz)
        or expected_rate_hz <= 0
    ):
        raise ValueError("expected_rate_hz must be positive and finite")
    if not records:
        return TelemetryQualityReport(
            packet_count=0,
            expected_packet_count=0,
            loss_pct=100.0,
            observed_rate_hz=0.0,
            maximum_gap_s=0.0,
            invalid_packet_count=health.invalid_packet_count,
            overflow_count=health.overflow_count,
            nonmonotonic_count=health.duplicate_time_count + health.out_of_order_count,
            clock_step_detected=health.clock_step_detected,
            validity="invalid",
            reason_codes=("no_telemetry",),
        )

    times = [_simulator_time(record) for record in records]
    if not all(math.isfinite(value) for value in times):
        raise ValueError("records contain nonfinite simulator time")
    duration = max(times[-1] - times[0], 0.0)
    expected = max(1, round(duration * expected_rate_hz))
    loss_pct = max(0.0, 100.0 * (expected - len(records)) / expected)
    if loss_pct >= 5.0:
        validity = "invalid"
    elif loss_pct >= 1.0:
        validity = "partial"
    else:
        validity = "valid"
    gaps = [current - previous for previous, current in zip(times, times[1:])]
    gap_nonmonotonic = sum(gap <= 0 for gap in gaps)
    nonmonotonic = (
        gap_nonmonotonic
        + health.duplicate_time_count
        + health.out_of_order_count
    )
    reason_codes = tuple(
        code
        for condition, code in (
            (loss_pct >= 5.0, "packet_loss_invalid"),
            (1.0 <= loss_pct < 5.0, "packet_loss_partial"),
            (health.overflow_count > 0, "receiver_overflow"),
            (nonmonotonic > 0, "simulator_time_nonmonotonic"),
            (health.clock_step_detected, "host_clock_step"),
        )
        if condition
    )
    return TelemetryQualityReport(
        packet_count=len(records),
        expected_packet_count=expected,
        loss_pct=loss_pct,
        observed_rate_hz=(len(records) / duration) if duration > 0 else 0.0,
        maximum_gap_s=max((0.0, *gaps)),
        invalid_packet_count=health.invalid_packet_count,
        overflow_count=health.overflow_count,
        nonmonotonic_count=nonmonotonic,
        clock_step_detected=health.clock_step_detected,
        validity=validity,
        reason_codes=reason_codes,
    )


__all__ = ["TelemetryQualityReport", "assess_quality"]
