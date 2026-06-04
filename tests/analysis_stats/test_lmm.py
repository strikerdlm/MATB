from __future__ import annotations

import pytest

from matb_integration.analysis.stats.data import fits_frame, metrics_frame
from matb_integration.analysis.stats.lmm import fit_q1, fit_q2, fit_q4

from .conftest import simulate_metric_rows


@pytest.fixture
def df42():
    return metrics_frame(simulate_metric_rows("sysmon_d_prime", seed=42))


def test_q1_recovers_level_effects_and_omnibus(df42):
    out = fit_q1(df42)
    assert out["status"] == "ok"
    coefs = {c["name"]: c for c in out["coefs"]}
    # truth: MEDIUM-LOW = 0.8, HIGH-LOW = 1.6
    assert coefs["MEDIUM-LOW"]["coef"] == pytest.approx(0.8, abs=0.15)
    assert coefs["HIGH-LOW"]["coef"] == pytest.approx(1.6, abs=0.15)
    assert out["omnibus"]["df"] == 2 and out["omnibus"]["p"] < 1e-6
    lo, hi = coefs["HIGH-LOW"]["ci95"]
    assert lo < 1.6 < hi
    assert coefs["HIGH-LOW"]["standardizer"] == "sqrt(re_var + resid_var)"
    # std effect = coef / sqrt(re_var + resid_var)
    import math
    expected = coefs["HIGH-LOW"]["coef"] / math.sqrt(out["re_var"] + out["resid_var"])
    assert coefs["HIGH-LOW"]["std_effect"] == pytest.approx(expected)


def test_q1_contrasts_include_high_vs_medium(df42):
    out = fit_q1(df42)
    names = [c["name"] for c in out["contrasts"]]
    assert names == ["MEDIUM-LOW", "HIGH-LOW", "HIGH-MEDIUM"]
    hm = out["contrasts"][2]
    assert hm["coef"] == pytest.approx(0.8, abs=0.15)
    assert 0 < hm["p"] < 1e-4
    assert hm["ci95"][0] < hm["coef"] < hm["ci95"][1]


def test_q2_recovers_visit_slope(df42):
    out = fit_q2(df42)
    assert out["status"] == "ok"
    # primary slope comes from the ADDITIVE model (level-adjusted common slope)
    assert "visit_c:" not in out["formula"]
    slope = {c["name"]: c for c in out["coefs"]}["visit_c"]
    assert slope["coef"] == pytest.approx(-0.05, abs=0.04)
    # interaction terms come from a separate exploratory fit
    assert any(":" in c["name"] for c in out["interactions"])


def test_q2_primary_slope_is_common_not_low_only():
    """If learning happens ONLY at HIGH, the confirmatory slope must still see it."""
    import numpy as np
    rng = np.random.default_rng(7)
    rows = []
    for p in range(12):
        u = rng.normal(0, 0.5)
        for v in range(1, 7):
            for li, lvl in enumerate(["LOW", "MEDIUM", "HIGH"]):
                slope = -0.3 if lvl == "HIGH" else 0.0   # marginal avg = -0.1
                y = 2.0 + 0.8 * li + slope * (v - 3.5) + u + rng.normal(0, 0.3)
                rows.append({"participant_id": f"P{p:02d}", "visit_ordinal": v,
                             "workload_level": lvl, "metric": "sysmon_d_prime",
                             "value": float(y)})
    out = fit_q2(metrics_frame(rows))
    slope = {c["name"]: c for c in out["coefs"]}["visit_c"]
    # the LOW-only slope is 0; the level-adjusted common slope is ~ -0.1
    assert slope["coef"] == pytest.approx(-0.1, abs=0.05)
    assert slope["p"] < 0.05


def test_insufficient_data_status():
    df = metrics_frame(simulate_metric_rows("bedford", seed=7, n_participants=2))
    assert fit_q1(df)["status"] == "insufficient_data"
    assert fit_q2(df)["status"] == "insufficient_data"


def test_not_estimable_on_degenerate_input():
    # constant response -> singular fit must yield a status, never raise
    rows = simulate_metric_rows("bedford", seed=7)
    for r in rows:
        r["value"] = 5.0
    out = fit_q1(metrics_frame(rows))
    assert out["status"] in ("ok", "not_estimable")  # never an exception
    if out["status"] == "not_estimable":
        assert out["detail"]


def test_q4_recovers_g0_drift(sim_fits):
    out = fit_q4(fits_frame(sim_fits), "g0")
    assert out["status"] == "ok"
    slope = {c["name"]: c for c in out["coefs"]}["visit_c"]
    assert slope["coef"] == pytest.approx(0.5, abs=0.1)


def test_q4_insufficient(sim_fits):
    one_visit = [r for r in sim_fits if r["visit_ordinal"] == 1]
    assert fit_q4(fits_frame(one_visit), "g0")["status"] == "insufficient_data"
