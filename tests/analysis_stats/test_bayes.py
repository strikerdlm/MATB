# tests/analysis_stats/test_bayes.py
from __future__ import annotations

import json

import pytest

pytest.importorskip("pymc")  # Phase-3B-only dependency (webui/backend/requirements.txt)

from matb_integration.analysis.stats.bayes import (  # noqa: E402
    BAYES_VERSION,
    _convergence_summary,
    run_bayes,
)

from .conftest import simulate_metric_rows

# Small but real sampling: keep draws low so the suite stays fast (seeded).
FAST = {"draws": 300, "tune": 300, "chains": 2}


def test_bayes_q2_recovers_known_effects(sim_fits):
    rows = simulate_metric_rows("sysmon_hit_rate", seed=42)
    art = run_bayes(rows, sim_fits, seed=20260604, **FAST,
                    created_utc="2026-06-04T00:00:00+00:00")
    assert art["bayes_version"] == BAYES_VERSION
    q2 = art["q2"]["sysmon_hit_rate"]
    assert q2["status"] == "ok"
    # Registered hit-rate-domain truth: learning +.01/visit and workload
    # decrements of -.12/-.24 for MEDIUM/HIGH.
    assert q2["coefs"]["b_visit"]["mean"] == pytest.approx(0.01, abs=0.02)
    assert q2["coefs"]["b_med"]["mean"] == pytest.approx(-0.12, abs=0.04)
    assert q2["coefs"]["b_high"]["mean"] == pytest.approx(-0.24, abs=0.05)
    lo, hi = q2["coefs"]["b_visit"]["eti95"]
    assert lo < q2["coefs"]["b_visit"]["mean"] < hi
    d = q2["diagnostics"]
    assert set(d) == {"max_r_hat", "min_ess_bulk", "divergences"}
    assert isinstance(q2["converged"], bool)
    # Q4 on the drifting-g0 fixture
    q4 = art["q4"]["g0"]
    assert q4["status"] == "ok"
    assert q4["coefs"]["b_visit"]["mean"] == pytest.approx(0.5, abs=0.15)
    assert all(result["status"] == "ok" for result in art["q4"].values())
    # sampler config + provenance persisted (spec section 7)
    s = art["sampler"]
    assert s["seed"] == 20260604 and s["chains"] == 2 and s["draws"] == 300 and s["tune"] == 300
    assert s["interval"] == "95% ETI"
    assert s["initialization"] == "adapt_diag; b0=observed_mean; remaining prior defaults"
    assert "Normal(0, 2.5*sd(y))" in s["priors"]["coefficients"]
    assert "HalfNormal(sd(y))" in s["priors"]["sds"]
    assert {"pymc", "arviz", "numpy", "pandas"} <= set(art["provenance"]["libraries"])
    assert len(art["provenance"]["fingerprint"]) == 64
    json.dumps(art, allow_nan=False)  # strict JSON-serializable


def test_bayes_rejects_one_chain_because_rhat_is_undefined():
    with pytest.raises(ValueError, match="at least two chains"):
        run_bayes([], [], draws=50, tune=50, chains=1)


def test_bayes_insufficient_and_empty():
    rows = simulate_metric_rows("bedford", seed=7, n_participants=2)
    art = run_bayes(rows, [], **FAST)
    assert art["q2"]["bedford"]["status"] == "insufficient_data"
    assert all(v["status"] == "insufficient_data" for v in art["q4"].values())
    empty = run_bayes([], [], **FAST)
    assert all(v["status"] == "insufficient_data" for v in empty["q2"].values())
    assert empty["all_converged"] is False
    assert empty["convergence_summary"] == {
        "models_planned": 6,
        "models_fitted": 0,
        "models_converged": 0,
        "models_not_converged": 0,
        "models_not_fitted": 6,
    }


def test_all_converged_requires_every_planned_model_to_fit_and_converge():
    complete = [{"status": "ok", "converged": True} for _ in range(6)]
    partial = complete[:5] + [{"status": "insufficient_data"}]
    failed = complete[:5] + [{"status": "ok", "converged": False}]

    assert _convergence_summary(complete)[0] is True
    assert _convergence_summary(partial)[0] is False
    assert _convergence_summary(failed)[0] is False
    assert _convergence_summary(failed)[1]["models_not_converged"] == 1


def test_bayes_seed_reproducibility(sim_fits):
    rows = simulate_metric_rows("nasatlx_rtlx_mean_0_100", seed=43)
    a = run_bayes(rows, [], seed=11, draws=200, tune=200, chains=2)
    b = run_bayes(rows, [], seed=11, draws=200, tune=200, chains=2)
    assert a["q2"]["nasatlx_rtlx_mean_0_100"]["coefs"]["b_visit"]["mean"] == \
        b["q2"]["nasatlx_rtlx_mean_0_100"]["coefs"]["b_visit"]["mean"]


def test_bayes_excludes_ineligible_confirmatory_rows():
    rows = [
        dict(row, confirmatory_eligible=False)
        for row in simulate_metric_rows("sysmon_hit_rate", seed=42)
    ]
    art = run_bayes(rows, [], **FAST)

    assert art["q2"]["sysmon_hit_rate"]["status"] == "insufficient_data"
    assert art["confirmatory_eligibility"]["rows_excluded"] == len(rows)
    assert art["confirmatory_eligibility"]["rows_eligible"] == 0
