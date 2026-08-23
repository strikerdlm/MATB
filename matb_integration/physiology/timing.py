"""Host-clock anchoring and RR-derived beat-time estimation.

The Bluetooth Heart Rate Service has no measurement timestamp.  Receipt times
are therefore preserved verbatim and beat times are explicitly labelled as
estimates derived from the native RR sequence.
"""

from __future__ import annotations

from dataclasses import dataclass
import statistics
import time
from collections.abc import Callable, Sequence
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class ClockAnchor:
    anchor_id: str
    anchor_index: int
    clock_epoch: int
    monotonic_midpoint_ns: int
    utc_ns: int
    host_clock_uncertainty_ns: int
    utc_minus_monotonic_offset_ns: int
    reason: str
    discontinuity_detected: bool


class HostClockMapper:
    """Capture monotonic/UTC anchors without hiding wall-clock changes."""

    def __init__(
        self,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
        wall_ns: Callable[[], int] = time.time_ns,
        *,
        jump_threshold_ns: int = 100_000_000,
    ) -> None:
        if jump_threshold_ns < 0:
            raise ValueError("jump_threshold_ns_must_be_non_negative")
        self._monotonic_ns = monotonic_ns
        self._wall_ns = wall_ns
        self._jump_threshold_ns = jump_threshold_ns
        self._anchors: list[ClockAnchor] = []
        self._clock_epoch = 0

    @property
    def anchors(self) -> tuple[ClockAnchor, ...]:
        return tuple(self._anchors)

    @property
    def clock_epoch(self) -> int:
        return self._clock_epoch

    def capture_anchor(self, reason: str) -> ClockAnchor:
        before = int(self._monotonic_ns())
        utc_ns = int(self._wall_ns())
        after = int(self._monotonic_ns())
        if after < before:
            raise RuntimeError("monotonic_clock_reversed")
        midpoint = (before + after) // 2
        uncertainty = (after - before) // 2
        offset = utc_ns - midpoint
        discontinuity = False
        if self._anchors:
            previous_offset = self._anchors[-1].utc_minus_monotonic_offset_ns
            if abs(offset - previous_offset) > self._jump_threshold_ns:
                self._clock_epoch += 1
                discontinuity = True
        anchor = ClockAnchor(
            anchor_id=str(uuid4()),
            anchor_index=len(self._anchors),
            clock_epoch=self._clock_epoch,
            monotonic_midpoint_ns=midpoint,
            utc_ns=utc_ns,
            host_clock_uncertainty_ns=uncertainty,
            utc_minus_monotonic_offset_ns=offset,
            reason=reason,
            discontinuity_detected=discontinuity,
        )
        self._anchors.append(anchor)
        return anchor


@dataclass(frozen=True, slots=True)
class NotificationRRBatch:
    notification_index: int
    received_monotonic_ns: int
    rr_ticks_1024: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class EstimatedBeatTime:
    segment_id: str
    notification_index: int
    rr_index_in_notification: int
    rr_count_in_notification: int
    estimated_beat_monotonic_ns: int
    notification_received_monotonic_ns: int
    fit_residual_ns: int
    fit_uncertainty_ns: int
    timestamp_source: str = "host_rr_robust_offset_v1"


def estimate_segment_beat_times(
    segment_id: str,
    batches: Sequence[NotificationRRBatch],
) -> tuple[EstimatedBeatTime, ...]:
    """Fit one host-time offset to a chronological RR sequence.

    Each notification constrains the endpoint of its final RR interval to the
    host receipt time.  The median constraint offset avoids making notification
    scheduling jitter part of the RR series.  Callers invoke this separately for
    every BLE connection segment, so disconnects are never bridged.
    """

    cumulative_ns = 0
    endpoints: list[tuple[NotificationRRBatch, tuple[int, ...]]] = []
    offsets: list[int] = []
    for batch in batches:
        batch_endpoints: list[int] = []
        for ticks in batch.rr_ticks_1024:
            if ticks <= 0:
                continue
            cumulative_ns += round(ticks * 1_000_000_000 / 1024)
            batch_endpoints.append(cumulative_ns)
        if not batch_endpoints:
            continue
        endpoint_tuple = tuple(batch_endpoints)
        endpoints.append((batch, endpoint_tuple))
        offsets.append(batch.received_monotonic_ns - endpoint_tuple[-1])

    if not offsets:
        return ()
    fitted_offset = round(statistics.median(offsets))
    residuals = [offset - fitted_offset for offset in offsets]
    uncertainty = round(statistics.median(abs(value) for value in residuals))

    beats: list[EstimatedBeatTime] = []
    for (batch, batch_endpoints), residual in zip(endpoints, residuals, strict=True):
        count = len(batch_endpoints)
        for rr_index, endpoint_ns in enumerate(batch_endpoints):
            beats.append(
                EstimatedBeatTime(
                    segment_id=segment_id,
                    notification_index=batch.notification_index,
                    rr_index_in_notification=rr_index,
                    rr_count_in_notification=count,
                    estimated_beat_monotonic_ns=fitted_offset + endpoint_ns,
                    notification_received_monotonic_ns=batch.received_monotonic_ns,
                    fit_residual_ns=residual,
                    fit_uncertainty_ns=uncertainty,
                )
            )
    return tuple(beats)


__all__ = [
    "ClockAnchor",
    "EstimatedBeatTime",
    "HostClockMapper",
    "NotificationRRBatch",
    "estimate_segment_beat_times",
]
