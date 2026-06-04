"""MixedLM fits for Q1 (level), Q2 (trajectory), Q4 (DEPDF drift).

Random intercepts only (n=12 participants; spec section 2). REML estimates;
Wald inference (small-sample caveat carried in the artifact).
"""
from __future__ import annotations

import math
import warnings
from typing import Any

import pandas as pd
from scipy.stats import norm

from . import gates

LEVEL_TERM = "C(workload_level, Treatment('LOW'))"
MED = f"{LEVEL_TERM}[T.MEDIUM]"
HIGH = f"{LEVEL_TERM}[T.HIGH]"
STANDARDIZER = "sqrt(re_var + resid_var)"
_Z = float(norm.ppf(0.975))


def _fit(formula: str, df: pd.DataFrame):
    import statsmodels.formula.api as smf

    model = smf.mixedlm(formula, df, groups=df["participant_id"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return model.fit(reml=True)


def _coef(res, name: str, label: str, denom: float) -> dict[str, Any]:
    ci = res.conf_int().loc[name]
    coef = float(res.params[name])
    return {
        "name": label, "coef": coef,
        "ci95": [float(ci.iloc[0]), float(ci.iloc[1])],
        "p": float(res.pvalues[name]),
        "std_effect": coef / denom, "standardizer": STANDARDIZER,
    }


def _variances(res) -> tuple[float, float]:
    re_var = float(res.cov_re.iloc[0, 0])
    resid_var = float(res.scale)
    return re_var, resid_var


def _contrasts(res, denom: float) -> list[dict[str, Any]]:
    out = [_coef(res, MED, "MEDIUM-LOW", denom), _coef(res, HIGH, "HIGH-LOW", denom)]
    est = float(res.params[HIGH] - res.params[MED])
    V = res.cov_params()
    se = math.sqrt(float(V.loc[HIGH, HIGH] + V.loc[MED, MED] - 2 * V.loc[HIGH, MED]))
    w = res.wald_test(f"{HIGH} - {MED} = 0", scalar=True)
    out.append({
        "name": "HIGH-MEDIUM", "coef": est,
        "ci95": [est - _Z * se, est + _Z * se], "p": float(w.pvalue),
        "std_effect": est / denom, "standardizer": STANDARDIZER,
    })
    return out


def _meta(res, df: pd.DataFrame) -> dict[str, Any]:
    re_var, resid_var = _variances(res)
    return {"n_obs": int(res.nobs),
            "n_participants": int(df["participant_id"].nunique()),
            "re_var": re_var, "resid_var": resid_var}


def fit_q1(df: pd.DataFrame) -> dict[str, Any]:
    reason = gates.gate_q1(df)
    if reason:
        return {"status": "insufficient_data", "detail": reason}
    try:
        res = _fit(f"value ~ {LEVEL_TERM} + visit_c", df)
        if not res.converged:
            return {"status": "not_estimable", "detail": "MixedLM did not converge"}
        re_var, resid_var = _variances(res)
        denom = math.sqrt(re_var + resid_var)
        w = res.wald_test(f"{MED} = 0, {HIGH} = 0", scalar=True)
        return {
            "status": "ok", **_meta(res, df),
            "formula": f"value ~ {LEVEL_TERM} + visit_c",
            "omnibus": {"statistic": float(w.statistic), "df": 2,
                        "p": float(w.pvalue), "test": "Wald chi2 (REML)"},
            "coefs": [_coef(res, MED, "MEDIUM-LOW", denom),
                      _coef(res, HIGH, "HIGH-LOW", denom),
                      _coef(res, "visit_c", "visit_c", denom)],
            "contrasts": _contrasts(res, denom),
        }
    except Exception as e:  # noqa: BLE001 — statuses are first-class (spec section 4)
        return {"status": "not_estimable", "detail": f"{type(e).__name__}: {e}"}


def fit_q2(df: pd.DataFrame) -> dict[str, Any]:
    """Primary trajectory = ADDITIVE model: under treatment coding with an
    interaction present, visit_c would be the LOW-only slope; the additive
    model makes it the level-adjusted common slope (spec section 2). The
    interaction model is a second, exploratory fit."""
    reason = gates.gate_q2(df)
    if reason:
        return {"status": "insufficient_data", "detail": reason}
    formula = f"value ~ visit_c + {LEVEL_TERM}"
    try:
        res = _fit(formula, df)
        if not res.converged:
            return {"status": "not_estimable", "detail": "MixedLM did not converge"}
        re_var, resid_var = _variances(res)
        denom = math.sqrt(re_var + resid_var)
        out = {
            "status": "ok", **_meta(res, df), "formula": formula,
            "coefs": [_coef(res, "visit_c", "visit_c", denom),
                      _coef(res, MED, "MEDIUM-LOW", denom),
                      _coef(res, HIGH, "HIGH-LOW", denom)],
            "interactions": [],
        }
    except Exception as e:  # noqa: BLE001
        return {"status": "not_estimable", "detail": f"{type(e).__name__}: {e}"}
    # exploratory: do slopes differ by level? Failure here must not take down
    # the primary result — interactions just stay empty.
    try:
        res_i = _fit(f"value ~ visit_c + {LEVEL_TERM} + visit_c:{LEVEL_TERM}", df)
        if res_i.converged:
            re_v, rs_v = _variances(res_i)
            d_i = math.sqrt(re_v + rs_v)
            inter = [n for n in res_i.params.index if n.startswith("visit_c:")]
            out["interactions"] = [_coef(res_i, n, n, d_i) for n in inter]
    except Exception:  # noqa: BLE001,S110 — secondary fit is best-effort
        pass
    return out


def fit_q4(fits: pd.DataFrame, param: str) -> dict[str, Any]:
    reason = gates.gate_q4(fits)
    if reason:
        return {"status": "insufficient_data", "detail": reason}
    df = fits.rename(columns={param: "value"})
    try:
        res = _fit("value ~ visit_c", df)
        if not res.converged:
            return {"status": "not_estimable", "detail": "MixedLM did not converge"}
        re_var, resid_var = _variances(res)
        denom = math.sqrt(re_var + resid_var)
        return {"status": "ok", **_meta(res, df), "formula": f"{param} ~ visit_c",
                "coefs": [_coef(res, "visit_c", "visit_c", denom)]}
    except Exception as e:  # noqa: BLE001
        return {"status": "not_estimable", "detail": f"{type(e).__name__}: {e}"}
