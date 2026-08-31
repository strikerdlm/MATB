# Copyright 2023-2026, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

"""Clock-domain observations for scientific event timing.

The scenario clock and the host monotonic clock answer different questions.  This
module deliberately records both and refuses regressions so downstream code cannot
silently substitute one clock domain for the other.
"""

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter_ns


@dataclass(frozen=True, slots=True)
class ClockReading:
    """One linked observation of experiment and host-monotonic time."""

    experiment_time_ns: int
    host_monotonic_ns: int


class ExperimentClock:
    """Observe experiment time against a monotonic host clock.

    Equal experiment times are valid because multiple events may be dispatched in
    one scenario tick.  Regressions are rejected because they would make scientific
    event ordering ambiguous.
    """

    def __init__(self, monotonic_ns: Callable[[], int] = perf_counter_ns) -> None:
        self._monotonic_ns = monotonic_ns
        self._last_experiment_time_ns: int | None = None
        self._last_host_monotonic_ns: int | None = None

    def observe(self, experiment_time_ns: int) -> ClockReading:
        if isinstance(experiment_time_ns, bool) or not isinstance(experiment_time_ns, int):
            raise TypeError("experiment time must be an integer number of nanoseconds")
        if experiment_time_ns < 0:
            raise ValueError("experiment time must be non-negative")
        if (
            self._last_experiment_time_ns is not None
            and experiment_time_ns < self._last_experiment_time_ns
        ):
            raise ValueError("experiment time regressed")

        host_monotonic_ns = self._monotonic_ns()
        if isinstance(host_monotonic_ns, bool) or not isinstance(host_monotonic_ns, int):
            raise TypeError("host monotonic clock must return integer nanoseconds")
        if (
            self._last_host_monotonic_ns is not None
            and host_monotonic_ns < self._last_host_monotonic_ns
        ):
            raise RuntimeError("host monotonic clock regressed")

        self._last_experiment_time_ns = experiment_time_ns
        self._last_host_monotonic_ns = host_monotonic_ns
        return ClockReading(
            experiment_time_ns=experiment_time_ns,
            host_monotonic_ns=host_monotonic_ns,
        )
