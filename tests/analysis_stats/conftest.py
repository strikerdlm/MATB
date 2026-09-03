from __future__ import annotations

import numpy as np
import pytest

from matb_integration.metrics_schema import (
    METRICS_SCHEMA_VERSION,
    long_metric_definition,
)

# Known ground truth for the simulated study (used by recovery assertions)
TRUE_LEVEL_STEP = 0.8     # per level index LOW=0, MEDIUM=1, HIGH=2
TRUE_VISIT_SLOPE = -0.05  # per centered visit
RE_SD, NOISE_SD = 0.5, 0.3


def simulate_metric_rows(metric: str, seed: int, n_participants: int = 12,
                         base: float = 2.0) -> list[dict]:
    """12x6x3 rows for one metric with known fixed effects + random intercepts."""
    profiles = {
        # Keep confirmatory fixtures inside their registered measurement
        # domains.  The legacy unbounded d-prime fixture retains the original
        # coefficients used by the LMM recovery tests.
        "sysmon_hit_rate": {
            "base": 0.80, "step": -0.12, "slope": 0.01,
            "re_sd": 0.025, "noise_sd": 0.015, "bounds": (0.0, 1.0),
        },
        "nasatlx_rtlx_mean_0_100": {
            "base": 35.0, "step": 15.0, "slope": -1.0,
            "re_sd": 4.0, "noise_sd": 2.0, "bounds": (0.0, 100.0),
        },
        "bedford": {
            "base": 3.0, "step": 2.0, "slope": -0.10,
            "re_sd": 0.35, "noise_sd": 0.20, "bounds": (1.0, 10.0),
        },
    }
    profile = profiles.get(metric, {
        "base": base, "step": TRUE_LEVEL_STEP, "slope": TRUE_VISIT_SLOPE,
        "re_sd": RE_SD, "noise_sd": NOISE_SD, "bounds": (None, None),
    })
    rng = np.random.default_rng(seed)
    rows = []
    for p in range(n_participants):
        u = rng.normal(0, profile["re_sd"])
        for v in range(1, 7):
            for li, lvl in enumerate(["LOW", "MEDIUM", "HIGH"]):
                y = (profile["base"] + profile["step"] * li
                     + profile["slope"] * (v - 3.5) + u
                     + rng.normal(0, profile["noise_sd"]))
                lower, upper = profile["bounds"]
                if lower is not None:
                    y = max(lower, y)
                if upper is not None:
                    y = min(upper, y)
                rows.append({"participant_id": f"P{p:02d}", "visit_ordinal": v,
                             "workload_level": lvl, "metric": metric,
                             "value": float(y),
                             "metrics_schema_version": METRICS_SCHEMA_VERSION,
                             "metric_version": (
                                 "1-legacy-alias"
                                 if metric in {"sysmon_d_prime", "nasatlx_raw_tlx"}
                                 else str(long_metric_definition(metric)["metric_version"])
                             ),
                             "confirmatory_eligible": bool(
                                 long_metric_definition(metric)["confirmatory_eligible"]
                             )})
    return rows


@pytest.fixture
def sim_study():
    """Three confirmatory metrics with the same known structure, distinct seeds."""
    rows = []
    for seed, metric in (
        (42, "sysmon_hit_rate"),
        (43, "nasatlx_rtlx_mean_0_100"),
        (44, "bedford"),
    ):
        rows.extend(simulate_metric_rows(metric, seed))
    return rows


@pytest.fixture
def sim_fits():
    """Per-visit DEPDF fits with a known g0 drift (+0.5/visit) for 6 participants."""
    rng = np.random.default_rng(99)
    rows = []
    for p in range(6):
        participant_intercept = rng.normal(0, 1.0)
        for v in range(1, 7):
            rows.append({"participant_id": f"P{p:02d}", "visit_ordinal": v,
                         "g0": float(40.0 + participant_intercept
                                     + 0.5 * (v - 3.5) + rng.normal(0, 0.3)),
                         "p0": float(np.clip(0.99 + rng.normal(0, 0.002), 0, 1)),
                         "tau0": float(12.0 + rng.normal(0, 0.5))})
    return rows
