from __future__ import annotations

from matb_integration.scientific_data.quality import assess_timing_quality
from matb_integration.scientific_data.sampling import DeadlineSampler


def test_thirty_minute_twenty_hz_schedule_has_no_cumulative_drift() -> None:
    sampler = DeadlineSampler(sample_hz=20.0, start_monotonic_ns=1_000_000_000)
    observations = [
        sampler.observe(1_000_000_000 + index * 50_000_000 + (index % 7) * 100_000)
        for index in range(1, 36_001)
    ]
    emitted = [observation for observation in observations if observation is not None]

    assert len(emitted) == 36_000
    assert emitted[-1].scheduled_monotonic_ns == 1_801_000_000_000
    assert sum(observation.missed_ticks for observation in emitted) == 0
    quality = assess_timing_quality(
        sample_hz=20.0,
        observed_intervals_ms=[
            (right.observed_monotonic_ns - left.observed_monotonic_ns) / 1_000_000
            for left, right in zip(emitted, emitted[1:])
        ],
        lateness_ms=[observation.lateness_ms for observation in emitted],
        missed_ticks=0,
        observed_samples=len(emitted),
        non_monotonic_timestamps=0,
    )
    assert quality["status"] == "ok"
    assert quality["completeness"] == 1.0
