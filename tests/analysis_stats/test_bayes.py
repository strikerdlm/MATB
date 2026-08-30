# tests/analysis_stats/test_bayes.py
from __future__ import annotations

import json

import pytest

pytest.importorskip("pymc")  # Phase-3B-only dependency (webui/backend/requirements.txt)

from matb_integration.analysis.stats.bayes import BAYES_VERSION, run_bayes  # noqa: E402

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
    # truth: visit slope -0.05, MEDIUM-LOW 0.8, HIGH-LOW 1.6 (posterior means)
    assert q2["coefs"]["b_visit"]["mean"] == pytest.approx(-0.05, abs=0.05)
    assert q2["coefs"]["b_med"]["mean"] == pytest.approx(0.8, abs=0.2)
    assert q2["coefs"]["b_high"]["mean"] == pytest.approx(1.6, abs=0.25)
    lo, hi = q2["coefs"]["b_visit"]["eti95"]
    assert lo < q2["coefs"]["b_visit"]["mean"] < hi
    d = q2["diagnostics"]
    assert set(d) == {"max_r_hat", "min_ess_bulk", "divergences"}
    assert isinstance(q2["converged"], bool)
    # Q4 on the drifting-g0 fixture
    q4 = art["q4"]["g0"]
    assert q4["status"] == "ok"
    assert q4["coefs"]["b_visit"]["mean"] == pytest.approx(0.5, abs=0.15)
    # sampler config + provenance persisted (spec section 7)
    s = art["sampler"]
    assert s["seed"] == 20260604 and s["chains"] == 2 and s["draws"] == 300 and s["tune"] == 300
    assert s["interval"] == "95% ETI"
    assert "Normal(0, 2.5*sd(y))" in s["priors"]["coefficients"]
    assert "HalfNormal(sd(y))" in s["priors"]["sds"]
    assert {"pymc", "arviz", "numpy", "pandas"} <= set(art["provenance"]["libraries"])
    assert len(art["provenance"]["fingerprint"]) == 64
    json.dumps(art)  # JSON-serializable


def test_bayes_insufficient_and_empty():
    rows = simulate_metric_rows("bedford", seed=7, n_participants=2)
    art = run_bayes(rows, [], **FAST)
    assert art["q2"]["bedford"]["status"] == "insufficient_data"
    assert all(v["status"] == "insufficient_data" for v in art["q4"].values())
    empty = run_bayes([], [], **FAST)
    assert all(v["status"] == "insufficient_data" for v in empty["q2"].values())


def test_bayes_seed_reproducibility(sim_fits):
    rows = simulate_metric_rows("nasatlx_rtlx_mean_0_100", seed=43)
    a = run_bayes(rows, [], seed=11, draws=200, tune=200, chains=2)
    b = run_bayes(rows, [], seed=11, draws=200, tune=200, chains=2)
    assert a["q2"]["nasatlx_rtlx_mean_0_100"]["coefs"]["b_visit"]["mean"] == \
        b["q2"]["nasatlx_rtlx_mean_0_100"]["coefs"]["b_visit"]["mean"]
