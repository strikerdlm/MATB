from __future__ import annotations

from matb_integration.analysis.stats.data import metrics_frame
from matb_integration.analysis.stats.rmanova import rm_anova_q1

from .conftest import simulate_metric_rows


def test_rm_anova_detects_level_effect():
    df = metrics_frame(simulate_metric_rows("bedford", seed=42))
    out = rm_anova_q1(df)
    assert out["status"] == "ok"
    assert out["p"] < 1e-6
    assert 0.5 < out["partial_eta_sq"] <= 1.0
    assert out["complete_case_n"] == 12
    assert "sensitivity" in out["note"]


def test_rm_anova_complete_case_only():
    rows = simulate_metric_rows("bedford", seed=42)
    # drop ALL HIGH rows for P00/P01 -> those participants are not complete-case
    rows = [r for r in rows
            if not (r["participant_id"] in ("P00", "P01")
                    and r["workload_level"] == "HIGH")]
    out = rm_anova_q1(metrics_frame(rows))
    assert out["status"] == "ok" and out["complete_case_n"] == 10


def test_rm_anova_insufficient():
    rows = simulate_metric_rows("bedford", seed=42, n_participants=2)
    assert rm_anova_q1(metrics_frame(rows))["status"] == "insufficient_data"


def test_rm_anova_degenerate_constant_input_is_not_estimable():
    rows = simulate_metric_rows("bedford", seed=42)
    for r in rows:
        r["value"] = 5.0
    out = rm_anova_q1(metrics_frame(rows))
    assert out["status"] == "not_estimable"
