"""Helper data structures for the operator capacity plugin."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional, Sequence, Tuple


@dataclass(slots=True)
class CapacityReport:
    """Snapshot describing how a workload role compares against its limit."""

    role: str
    count: int
    limit: int
    exceeded: bool
    assignments: Tuple[str, ...] = ()


@dataclass(slots=True)
class CapacityModel:
    """Encapsulates the workload/limit relationship for active and supervisory control."""

    active_limit: int
    supervisory_limit: int
    overlap_low_threshold: float
    overlap_high_threshold: float
    overlap_window: int
    overlap_samples: Deque[float] = field(init=False)
    active_assignments: Tuple[str, ...] = field(default_factory=tuple)
    supervisory_assignments: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        window = max(1, self.overlap_window)
        self.overlap_window = window
        self.overlap_samples = deque(maxlen=window)

    def update_config(
        self,
        *,
        active_limit: Optional[int] = None,
        supervisory_limit: Optional[int] = None,
        overlap_low_threshold: Optional[float] = None,
        overlap_high_threshold: Optional[float] = None,
        overlap_window: Optional[int] = None,
    ) -> None:
        """Refresh bounds from plugin parameters."""
        if active_limit is not None:
            self.active_limit = max(1, active_limit)
        if supervisory_limit is not None:
            self.supervisory_limit = max(self.active_limit, supervisory_limit)
        if overlap_low_threshold is not None:
            self.overlap_low_threshold = self._clamp_ratio(overlap_low_threshold)
        if overlap_high_threshold is not None:
            self.overlap_high_threshold = self._clamp_ratio(overlap_high_threshold)
        if overlap_window is not None:
            window = max(1, overlap_window)
            if window != self.overlap_samples.maxlen:
                self.overlap_window = window
                self.overlap_samples = deque(self.overlap_samples, maxlen=window)

    def update_assignments(
        self,
        role: str,
        assignments: Optional[Sequence[str]],
        explicit_count: Optional[int],
    ) -> CapacityReport:
        """Store the latest assignment snapshot for the requested role."""
        role_key = 'active' if role == 'active' else 'supervisory'
        cleaned = tuple(self._normalise_name(name) for name in assignments) if assignments else tuple()
        count = explicit_count if explicit_count is not None else len(cleaned)
        count = max(0, count)

        if role_key == 'active':
            self.active_assignments = cleaned
            limit = self.active_limit
        else:
            self.supervisory_assignments = cleaned
            limit = self.effective_supervisory_limit()

        exceeded = count > limit
        return CapacityReport(role_key, count, limit, exceeded, cleaned)

    def record_overlap(self, ratio: float) -> float:
        """Append a new overlap measurement (0-1)."""
        clamped = self._clamp_ratio(ratio)
        self.overlap_samples.append(clamped)
        return clamped

    def average_overlap(self) -> Optional[float]:
        """Return the running mean overlap if we have measurements."""
        if not self.overlap_samples:
            return None
        return sum(self.overlap_samples) / len(self.overlap_samples)

    def effective_supervisory_limit(self) -> int:
        """Compute the current supervisory cap based on overlap statistics."""
        avg = self.average_overlap()
        if avg is None:
            return self.supervisory_limit
        if avg >= self.overlap_high_threshold:
            return self.supervisory_limit
        if avg <= self.overlap_low_threshold:
            return max(self.active_limit, self.supervisory_limit - 2)
        return max(self.active_limit, self.supervisory_limit - 1)

    @staticmethod
    def _normalise_name(name: str) -> str:
        return name.strip()

    @staticmethod
    def _clamp_ratio(value: float) -> float:
        return min(max(float(value), 0.0), 1.0)

