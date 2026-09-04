"""Cohort-z composite -> HCF ratio F/F0 (spec section 3; exploratory).

F/F0 = 1 + K*mean(z) clamped to CLAMP, where z are per-subtest cohort
z-scores sign-aligned so higher = better capacity. Pre-registered gates:
>= MIN_COHORT screened participants; a metric enters the cohort z only with
>= 2 valid values (sample SD, ddof=1; SD == 0 -> z = 0).

There is no validated external standard for this mapping (Suhir section 5.9's
FOM approach is itself heuristic) — every consumer labels the result
exploratory.
"""
from __future__ import annotations

import statistics
from typing import Any

from matb_integration.suhir.hcf import HCFEstimate

SCREEN_VERSION = 2
K = 0.05
CLAMP = (0.85, 1.15)
MIN_COHORT = 3
MIN_METRIC_N = 2

# metric key -> (subtest, score field, sign): sign +1 means higher raw = better
METRICS: dict[str, tuple[str, str, int]] = {
    "simple_rt": ("simple_rt", "median_ms", -1),
    "choice_rt": ("choice_rt", "median_ms", -1),
    "nback": ("nback", "d_prime", +1),
    "tracking": ("tracking", "rms_norm", -1),
}


def _metric_values(scores_by_pid: dict[str, dict], subtest: str, field: str
                   ) -> dict[str, float]:
    vals: dict[str, float] = {}
    for pid, scores in scores_by_pid.items():
        s = scores.get(subtest) or {}
        if s.get("valid") and s.get(field) is not None:
            vals[pid] = float(s[field])
    return vals


def compute_cohort_hcf(scores_by_pid: dict[str, dict[str, Any]]
                       ) -> dict[str, HCFEstimate]:
    """Map every screened participant's scores to an HCFEstimate.

    Returns {} when the cohort gate (>= MIN_COHORT screens) fails.
    """
    if len(scores_by_pid) < MIN_COHORT:
        return {}
    z_by_pid: dict[str, dict[str, float]] = {pid: {} for pid in scores_by_pid}
    for metric, (subtest, field, sign) in METRICS.items():
        vals = _metric_values(scores_by_pid, subtest, field)
        if len(vals) < MIN_METRIC_N:
            continue  # excluded cohort-wide
        mean = statistics.fmean(vals.values())
        sd = statistics.stdev(vals.values()) if len(vals) > 1 else 0.0
        for pid, v in vals.items():
            z_by_pid[pid][metric] = sign * ((v - mean) / sd) if sd > 0 else 0.0

    store: dict[str, HCFEstimate] = {}
    for pid, zs in z_by_pid.items():
        if not zs:
            continue  # no valid metrics survived -> no screen estimate
        composite = statistics.fmean(zs.values())
        f = min(max(1.0 + K * composite, CLAMP[0]), CLAMP[1])
        store[pid] = HCFEstimate(
            participant_id=pid, value=f, source="screen",
            components={**zs, "composite_z": composite,
                        "screen_version": SCREEN_VERSION},
        )
    return store
