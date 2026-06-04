from __future__ import annotations

import pandas as pd
import pytest

from matb_integration.analysis.stats.rmcorr import rm_corr, rm_corr_level_adjusted

# Bland & Altman (1995) intra-subject pH/PaCO2 data, 8 subjects, 47 obs —
# the canonical rmcorr example in Bakdash & Marusich (2017), Front. Psychol.
_SUBJ = [1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4,
         5, 5, 5, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 7, 7, 7, 8, 8, 8, 8, 8, 8, 8, 8]
_PH = [6.68, 6.53, 6.43, 6.33, 6.85, 7.06, 7.13, 7.17, 7.4, 7.42, 7.41, 7.37,
       7.34, 7.35, 7.28, 7.3, 7.34, 7.36, 7.33, 7.29, 7.3, 7.35, 7.35, 7.3,
       7.3, 7.37, 7.27, 7.28, 7.32, 7.32, 7.38, 7.3, 7.29, 7.33, 7.31, 7.33,
       6.86, 6.94, 6.92, 7.19, 7.29, 7.21, 7.25, 7.2, 7.19, 6.77, 6.82]
_PACO2 = [3.97, 4.12, 4.09, 3.97, 5.27, 5.37, 5.41, 5.44, 5.67, 3.64, 4.32,
          4.73, 4.96, 5.04, 5.22, 4.82, 5.07, 5.67, 5.1, 5.53, 4.75, 5.51,
          4.28, 4.44, 4.32, 3.23, 4.46, 4.72, 4.75, 4.99, 4.78, 4.73, 5.12,
          4.93, 5.03, 4.93, 6.85, 6.44, 6.52, 5.28, 4.56, 4.34, 4.32, 4.41,
          3.69, 6.09, 5.58]


def _bland_altman_pairs() -> pd.DataFrame:
    return pd.DataFrame({"participant_id": [str(s) for s in _SUBJ],
                         "x": _PH, "y": _PACO2})


def test_rm_corr_matches_pingouin_oracle():
    out = rm_corr(_bland_altman_pairs())
    assert out["status"] == "ok"
    # pingouin 0.6.1: r=-0.5067697422, dof=38, p=0.0008471081091, CI95 [-0.71, -0.23]
    assert out["r"] == pytest.approx(-0.5067697422, abs=1e-9)
    assert out["dof"] == 38
    assert out["p"] == pytest.approx(0.0008471081091, rel=1e-6)
    assert out["ci95"][0] == pytest.approx(-0.71, abs=0.02)
    assert out["ci95"][1] == pytest.approx(-0.23, abs=0.02)
    assert out["n_pairs"] == 47 and out["n_participants"] == 8


def test_rm_corr_insufficient_data():
    pairs = _bland_altman_pairs().head(6)  # 2 subjects
    assert rm_corr(pairs)["status"] == "insufficient_data"


def test_rm_corr_level_adjusted_runs():
    pairs = _bland_altman_pairs()
    # synthetic level labels purely to exercise the residualization path
    pairs["workload_level"] = (["LOW", "MEDIUM", "HIGH"] * 16)[: len(pairs)]
    out = rm_corr_level_adjusted(pairs)
    assert out["status"] == "ok"
    assert "sensitivity" in out["method"]
    assert -1.0 <= out["r"] <= 0.0  # same direction as canonical


def test_rm_corr_degenerate_constant_input_is_not_estimable():
    # constant x and y previously fabricated r=1.0 with p~1e-244
    pairs = pd.DataFrame({
        "participant_id": [f"P{p}" for p in range(4) for _ in range(5)],
        "x": [1.0] * 20, "y": [2.0] * 20,
    })
    out = rm_corr(pairs)
    assert out["status"] == "not_estimable"
    assert "variance" in out["detail"]
    # constant x with varying y is equally unidentifiable
    pairs2 = pairs.assign(y=list(range(20)))
    assert rm_corr(pairs2)["status"] == "not_estimable"


def test_rm_corr_level_adjusted_degenerate_is_not_estimable():
    # OLS residuals of constant input carry float jitter (~1e-16) that must
    # not bypass the variance guard
    pairs = pd.DataFrame({
        "participant_id": [f"P{p}" for p in range(4) for _ in range(5)],
        "x": [1.0] * 20, "y": [2.0] * 20,
        "workload_level": (["LOW", "MEDIUM", "HIGH"] * 7)[:20],
    })
    out = rm_corr_level_adjusted(pairs)
    assert out["status"] == "not_estimable"
    assert "variance" in out["detail"]
