from __future__ import annotations

import numpy as np
import pytest

# Known ground truth for the simulated study (used by recovery assertions)
TRUE_LEVEL_STEP = 0.8     # per level index LOW=0, MEDIUM=1, HIGH=2
TRUE_VISIT_SLOPE = -0.05  # per centered visit
RE_SD, NOISE_SD = 0.5, 0.3


def simulate_metric_rows(metric: str, seed: int, n_participants: int = 12,
                         base: float = 2.0) -> list[dict]:
    """12x6x3 rows for one metric with known fixed effects + random intercepts."""
    rng = np.random.default_rng(seed)
    rows = []
    for p in range(n_participants):
        u = rng.normal(0, RE_SD)
        for v in range(1, 7):
            for li, lvl in enumerate(["LOW", "MEDIUM", "HIGH"]):
                y = (base + TRUE_LEVEL_STEP * li
                     + TRUE_VISIT_SLOPE * (v - 3.5) + u + rng.normal(0, NOISE_SD))
                rows.append({"participant_id": f"P{p:02d}", "visit_ordinal": v,
                             "workload_level": lvl, "metric": metric,
                             "value": float(y)})
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
        for v in range(1, 7):
            rows.append({"participant_id": f"P{p:02d}", "visit_ordinal": v,
                         "g0": float(40.0 + 0.5 * (v - 3.5) + rng.normal(0, 0.3)),
                         "p0": float(np.clip(0.99 + rng.normal(0, 0.002), 0, 1)),
                         "tau0": float(12.0 + rng.normal(0, 0.5))})
    return rows
