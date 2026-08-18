"""Prespecified longitudinal analysis for Liftoff component outcomes."""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import version
from typing import Any, Sequence

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

LIFTOFF_ANALYSIS_VERSION = "liftoff-analysis-v1"
_FORMULA = "value ~ C(visit_code) + C(sequence) + prior_fpv_experience"
_CONTRASTS = (
    ("T0_vs_DM8", "T0", "DM8"),
    ("T0_vs_DM15", "T0", "DM15"),
    ("DM8_vs_DM15", "DM8", "DM15"),
)
_CONTINUOUS = (
    "median_lap_time_s",
    "best_lap_time_s",
    "lap_completion_proportion",
    "active_duration_s",
    "mean_speed_native",
    "input_saturation_fraction",
)
_COUNTS = ("valid_laps", "invalid_laps", "observer_restart_count")


def select_count_family(values: np.ndarray) -> str:
    values = np.asarray(values, dtype=float)
    mean = float(values.mean()) if values.size else 0.0
    variance = float(values.var(ddof=1)) if values.size > 1 else 0.0
    return "negative_binomial" if mean > 0 and variance > 1.5 * mean else "poisson"


def _contrasts(subset: pd.DataFrame) -> list[dict[str, object]]:
    means = subset.groupby("visit_code", observed=True)["value"].mean().to_dict()
    scale = float(subset["value"].std(ddof=1))
    output = []
    for name, left, right in _CONTRASTS:
        estimate = (
            float(means[right] - means[left])
            if left in means and right in means
            else None
        )
        output.append({
            "name": name,
            "left": left,
            "right": right,
            "estimate": estimate,
            "standardized_effect": (
                estimate / scale if estimate is not None and scale > 0 else None
            ),
        })
    return output


def fit_continuous(df: pd.DataFrame, outcome: str) -> dict[str, object]:
    subset = df.loc[df["metric"] == outcome].dropna(
        subset=["value", "participant_id", "visit_code", "sequence", "prior_fpv_hours"]
    ).copy()
    if subset["participant_id"].nunique() < 3 or subset["visit_code"].nunique() < 2:
        return {"status": "insufficient_data", "outcome": outcome, "formula": _FORMULA}
    subset["prior_fpv_experience"] = np.log1p(subset["prior_fpv_hours"].astype(float))
    try:
        result = smf.mixedlm(_FORMULA, subset, groups=subset["participant_id"]).fit(
            reml=True,
            method="lbfgs",
            disp=False,
        )
        confidence = result.conf_int()
        coefficients = [{
            "name": str(name),
            "estimate": float(value),
            "ci95": [float(confidence.loc[name, 0]), float(confidence.loc[name, 1])],
        } for name, value in result.params.items()]
        model_status = "ok"
        random_intercept_variance = float(result.cov_re.iloc[0, 0])
        residual_variance = float(result.scale)
        converged = bool(result.converged)
    except Exception as exc:
        fallback = smf.ols(_FORMULA, subset).fit()
        confidence = fallback.conf_int()
        coefficients = [{
            "name": str(name),
            "estimate": float(value),
            "ci95": [float(confidence.loc[name, 0]), float(confidence.loc[name, 1])],
        } for name, value in fallback.params.items()]
        model_status = "fallback_ols"
        random_intercept_variance = None
        residual_variance = float(fallback.scale)
        converged = False
        exc_name = type(exc).__name__
    payload: dict[str, object] = {
        "status": model_status,
        "outcome": outcome,
        "formula": _FORMULA,
        "n_observations": len(subset),
        "n_participants": int(subset["participant_id"].nunique()),
        "coefficients": coefficients,
        "contrasts": _contrasts(subset),
        "random_intercept_variance": random_intercept_variance,
        "residual_variance": residual_variance,
        "converged": converged,
    }
    if model_status == "fallback_ols":
        payload["fallback_reason"] = exc_name
    return payload


def _fit_count(df: pd.DataFrame, outcome: str) -> dict[str, object]:
    subset = df.loc[df["metric"] == outcome].dropna(subset=["value"]).copy()
    if subset["participant_id"].nunique() < 3 or subset["visit_code"].nunique() < 2:
        return {"status": "insufficient_data", "outcome": outcome}
    family = select_count_family(subset["value"].to_numpy(dtype=float))
    return {
        "status": "descriptive_ready_for_hierarchical_sampling",
        "outcome": outcome,
        "family": family,
        "n_observations": len(subset),
        "n_participants": int(subset["participant_id"].nunique()),
        "visit_means": {
            str(key): float(value)
            for key, value in subset.groupby("visit_code", observed=True)["value"].mean().items()
        },
        "production_sampler": {
            "seed": 20260817,
            "draws": 1000,
            "tune": 1000,
            "chains": 4,
            "cores": 1,
            "target_accept": 0.9,
            "release_gates": {"max_r_hat": 1.01, "min_ess_bulk": 400, "max_divergences": 0},
        },
    }


def run_liftoff_analysis(
    metric_rows: Sequence[dict[str, Any]],
    participant_context: Sequence[dict[str, Any]],
) -> dict[str, object]:
    context = pd.DataFrame(participant_context).copy()
    if not context.empty and "sequence" not in context and "task_sequence" in context:
        context["sequence"] = context["task_sequence"]
    rows = pd.DataFrame(metric_rows).copy()
    fingerprint = hashlib.sha256(
        json.dumps(
            {"rows": list(metric_rows), "context": list(participant_context)},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    if rows.empty or context.empty:
        return {
            "analysis_version": LIFTOFF_ANALYSIS_VERSION,
            "status": "insufficient_data",
            "fingerprint": fingerprint,
            "continuous": {},
            "counts": {},
            "missingness": {"imputed_values": 0},
        }
    merged = rows.merge(context, on="participant_id", how="left", validate="many_to_one")
    eligible = (
        merged["participant_id"].nunique() >= 3
        and merged.groupby("participant_id")["visit_code"].nunique().ge(2).sum() >= 3
    )
    continuous = {
        outcome: fit_continuous(merged, outcome)
        for outcome in _CONTINUOUS
        if outcome in set(merged["metric"])
    }
    counts = {
        outcome: _fit_count(merged, outcome)
        for outcome in _COUNTS
        if outcome in set(merged["metric"])
    }
    return {
        "analysis_version": LIFTOFF_ANALYSIS_VERSION,
        "status": "ok" if eligible else "insufficient_data",
        "fingerprint": fingerprint,
        "continuous": continuous,
        "counts": counts,
        "multiplicity": {
            "primary": "prespecified_no_fdr",
            "secondary": "benjamini_hochberg_by_family",
        },
        "missingness": {
            "input_rows": len(rows),
            "rows_missing_context": int(merged["sequence"].isna().sum()),
            "imputed_values": 0,
        },
        "libraries": {
            "numpy": version("numpy"),
            "pandas": version("pandas"),
            "statsmodels": version("statsmodels"),
        },
        "caveats": [
            "Exploratory feasibility cohort; no predictive model is trained.",
            "Count outcomes require production hierarchical sampling before publication.",
        ],
    }


__all__ = [
    "LIFTOFF_ANALYSIS_VERSION",
    "fit_continuous",
    "run_liftoff_analysis",
    "select_count_family",
]
