"""Discrete failure-event extraction from raw OpenMATB rows.

A "failure" is a discrete per-task error event (Suhir's "error = failure").
Raw rows are dicts as produced by matb_integration.log_converter.parse_csv.
"""

from __future__ import annotations

import math
import statistics
from typing import Any


def _to_float(s: Any) -> float | None:
    """Parse a string to float, rejecting non-finite values (nan/inf)."""
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def sysmon_failure_times(rows: list[dict[str, str]]) -> list[float]:
    """Sorted scenario times of SYSMON MISS events."""
    times = [
        t
        for r in rows
        if r.get("type") == "performance"
        and r.get("module") == "sysmon"
        and r.get("address") == "signal_detection"
        and r.get("value", "").upper() == "MISS"
        and (t := _to_float(r.get("scenario_time"))) is not None
    ]
    return sorted(times)


def threshold_excursions(
    samples: list[tuple[float, float]], lo: float, hi: float, min_dur: float
) -> list[float]:
    """Start times of breaches outside [lo, hi] sustained for >= min_dur seconds.

    Breach duration is measured as the span between the FIRST and LAST
    out-of-band samples of the breach (last_out_of_band - first_out_of_band).
    Consequence: a breach represented by a single out-of-band sample has
    duration 0 and is excluded. This is the pre-registered Phase-1 semantic;
    it never over-counts on sparse/irregular sampling. An alternative
    "breach_start -> recovery sample" semantic is deferred to Phase 2 when
    TRACK/RESMAN are wired into the fit pipeline (currently only SYSMON
    discrete events feed it). See design spec / plan.

    Args:
        samples: (time, value) pairs, assumed time-ordered.
        lo, hi: inclusive in-band limits.
        min_dur: minimum sustained breach duration to count as one failure.
    """
    samples = sorted(samples, key=lambda s: s[0])
    out: list[float] = []
    breach_start: float | None = None
    last_t = None
    for t, v in samples:
        outside = v < lo or v > hi
        if outside and breach_start is None:
            breach_start = t
        elif not outside and breach_start is not None:
            if last_t is not None and (last_t - breach_start) >= min_dur:
                out.append(breach_start)
            breach_start = None
        last_t = t
    if breach_start is not None and last_t is not None and (last_t - breach_start) >= min_dur:
        out.append(breach_start)
    return out


def failure_metrics(failure_times: list[float], duration_s: float) -> dict[str, Any]:
    """MTTF, failure rate, and count from discrete failure times.

    MTTF is the mean inter-failure interval, counting time-to-first-failure
    from t=0. With no failures the block is right-censored: mttf undefined,
    rate 0. `duration_s` is retained for the Phase-2 censoring extension
    (post-last-failure time is intentionally excluded from the Phase-1
    inter-failure MTTF).
    """
    times = sorted(failure_times)
    n = len(times)
    if n == 0:
        return {"n_failures": 0, "mttf_s": None, "lambda_per_s": 0.0}
    intervals = [times[0]] + [times[i] - times[i - 1] for i in range(1, n)]
    mttf = statistics.mean(intervals)
    return {
        "n_failures": n,
        "mttf_s": mttf,
        "lambda_per_s": (1.0 / mttf) if mttf > 0 else 0.0,
    }
