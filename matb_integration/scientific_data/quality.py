"""Timing-quality metrics and non-destructive engineering warnings."""

from __future__ import annotations

import math
from typing import Iterable


def _percentile(values: Iterable[float], percentile: float) -> float | None:
    ordered = sorted(float(value) for value in values if math.isfinite(value))
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def assess_timing_quality(
    *,
    sample_hz: float,
    observed_intervals_ms: Iterable[float],
    lateness_ms: Iterable[float],
    missed_ticks: int,
    observed_samples: int,
    non_monotonic_timestamps: int,
) -> dict[str, object]:
    intervals = list(observed_intervals_ms)
    lateness = list(lateness_ms)
    expected = observed_samples + missed_ticks
    completeness = observed_samples / expected if expected else None
    p95_lateness = _percentile(lateness, 0.95)
    max_gap = max(intervals) if intervals else None
    issues: list[dict[str, object]] = []
    if non_monotonic_timestamps:
        issues.append({
            "severity": "error",
            "code": "non_monotonic_timestamp",
            "observed": non_monotonic_timestamps,
        })
    if completeness is not None and completeness < 0.99:
        issues.append({
            "severity": "warning",
            "code": "sample_completeness",
            "expected_minimum": 0.99,
            "observed": completeness,
        })
    if p95_lateness is not None and p95_lateness > 10.0:
        issues.append({
            "severity": "warning",
            "code": "timing_lateness_p95",
            "expected_maximum_ms": 10.0,
            "observed_ms": p95_lateness,
        })
    if max_gap is not None and max_gap > 250.0:
        issues.append({
            "severity": "warning",
            "code": "timing_gap_max",
            "expected_maximum_ms": 250.0,
            "observed_ms": max_gap,
        })
    status = "error" if any(issue["severity"] == "error" for issue in issues) else "warning" if issues else "ok"
    return {
        "status": status,
        "sample_hz": sample_hz,
        "expected_samples": expected,
        "observed_samples": observed_samples,
        "missed_ticks": missed_ticks,
        "completeness": completeness,
        "interval_ms_p50": _percentile(intervals, 0.50),
        "interval_ms_p95": _percentile(intervals, 0.95),
        "interval_ms_p99": _percentile(intervals, 0.99),
        "interval_ms_max": max_gap,
        "lateness_ms_p95": p95_lateness,
        "non_monotonic_timestamps": non_monotonic_timestamps,
        "issues": issues,
    }


__all__ = ["assess_timing_quality"]
