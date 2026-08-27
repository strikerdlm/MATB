from __future__ import annotations

from matb_integration.physiology.timing import (
    HostClockMapper,
    NotificationRRBatch,
    estimate_segment_beat_times,
)


def test_clock_mapper_detects_wall_clock_jump_without_changing_monotonic_time() -> None:
    monotonic_values = iter([100, 104, 200, 204])
    wall_values = iter([1_102, 1_402])
    mapper = HostClockMapper(
        monotonic_ns=lambda: next(monotonic_values),
        wall_ns=lambda: next(wall_values),
        jump_threshold_ns=100,
    )

    first = mapper.capture_anchor("connect")
    second = mapper.capture_anchor("periodic")

    assert first.monotonic_midpoint_ns == 102
    assert first.utc_minus_monotonic_offset_ns == 1_000
    assert first.discontinuity_detected is False
    assert second.clock_epoch == 1
    assert second.discontinuity_detected is True


def test_segment_timing_uses_all_rr_values_and_robust_notification_offset() -> None:
    batches = [
        NotificationRRBatch(
            notification_index=1,
            received_monotonic_ns=2_100_000_000,
            rr_ticks_1024=(1024,),
        ),
        NotificationRRBatch(
            notification_index=2,
            received_monotonic_ns=4_100_000_000,
            rr_ticks_1024=(1024, 1024),
        ),
    ]

    beats = estimate_segment_beat_times("segment-1", batches)

    assert [beat.notification_index for beat in beats] == [1, 2, 2]
    assert [beat.rr_index_in_notification for beat in beats] == [0, 0, 1]
    assert [beat.estimated_beat_monotonic_ns for beat in beats] == [
        2_100_000_000,
        3_100_000_000,
        4_100_000_000,
    ]
    assert all(beat.fit_residual_ns == 0 for beat in beats)


def test_segment_timing_does_not_bridge_connection_segments() -> None:
    batch = NotificationRRBatch(
        notification_index=8,
        received_monotonic_ns=9_000_000_000,
        rr_ticks_1024=(512,),
    )

    beat = estimate_segment_beat_times("reconnected", [batch])[0]

    assert beat.segment_id == "reconnected"
    assert beat.estimated_beat_monotonic_ns == 9_000_000_000
