"""Canonical repeated-measures correlation (Bakdash & Marusich 2017).

ANCOVA y ~ x + C(participant); r from the covariate partial SS with
df = N - k - 1 (N pairs, k participants). Fisher-z 95% CI on the error df.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from . import gates

METHOD = "Bakdash & Marusich (2017) ANCOVA rmcorr"
_Z = float(norm.ppf(0.975))


def rm_corr(pairs: pd.DataFrame) -> dict[str, Any]:
    """pairs: columns participant_id, x, y (complete pairs only)."""
    reason = gates.gate_rmcorr(pairs)
    if reason:
        return {"status": "insufficient_data", "detail": reason}
    try:
        import statsmodels.api as sm
        from statsmodels.formula.api import ols

        model = ols("y ~ x + C(participant_id)", data=pairs).fit()
        table = sm.stats.anova_lm(model, typ=3)
        ss_x = float(table.loc["x", "sum_sq"])
        ss_err = float(table.loc["Residual", "sum_sq"])
        dof = int(table.loc["Residual", "df"])
        r = float(np.sign(model.params["x"]) * np.sqrt(ss_x / (ss_x + ss_err)))
        z, se = np.arctanh(r), 1.0 / np.sqrt(dof - 1)
        return {
            "status": "ok", "r": r, "dof": dof,
            "p": float(table.loc["x", "PR(>F)"]),
            "ci95": [float(np.tanh(z - _Z * se)), float(np.tanh(z + _Z * se))],
            "ci_method": "Fisher z, se = 1/sqrt(dof - 1)",
            "n_pairs": int(len(pairs)),
            "n_participants": int(pairs["participant_id"].nunique()),
            "method": METHOD,
        }
    except Exception as e:  # noqa: BLE001 — statuses are first-class
        return {"status": "not_estimable", "detail": f"{type(e).__name__}: {e}"}


def rm_corr_level_adjusted(pairs: pd.DataFrame) -> dict[str, Any]:
    """Sensitivity: residualize x and y on workload level first (spec section 2)."""
    try:
        from statsmodels.formula.api import ols

        adj = pairs.copy()
        for col in ("x", "y"):
            adj[col] = ols(f"{col} ~ C(workload_level)", data=adj).fit().resid
    except Exception as e:  # noqa: BLE001
        return {"status": "not_estimable", "detail": f"{type(e).__name__}: {e}"}
    out = rm_corr(adj[["participant_id", "x", "y"]])
    out["method"] = "rmcorr on level-adjusted residuals (sensitivity)"
    return out
