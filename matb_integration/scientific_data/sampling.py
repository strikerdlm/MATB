"""Fixed-deadline sampling without invented catch-up observations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SampleTiming:
    sample_index: int
    scheduled_monotonic_ns: int
    observed_monotonic_ns: int
    lateness_ms: float
    missed_ticks: int


class DeadlineSampler:
    def __init__(self, *, sample_hz: float, start_monotonic_ns: int) -> None:
        if not 0 < sample_hz <= 1_000:
            raise ValueError("sample_hz must be in (0, 1000]")
        self.sample_hz = float(sample_hz)
        self.period_ns = round(1_000_000_000 / self.sample_hz)
        self.next_deadline_ns = int(start_monotonic_ns) + self.period_ns
        self.sample_index = 0

    def observe(self, monotonic_ns: int) -> SampleTiming | None:
        now = int(monotonic_ns)
        if now < self.next_deadline_ns:
            return None
        elapsed_deadlines = (now - self.next_deadline_ns) // self.period_ns
        scheduled = self.next_deadline_ns + elapsed_deadlines * self.period_ns
        timing = SampleTiming(
            sample_index=self.sample_index,
            scheduled_monotonic_ns=scheduled,
            observed_monotonic_ns=now,
            lateness_ms=(now - scheduled) / 1_000_000,
            missed_ticks=int(elapsed_deadlines),
        )
        self.sample_index += 1
        self.next_deadline_ns = scheduled + self.period_ns
        return timing


__all__ = ["DeadlineSampler", "SampleTiming"]
