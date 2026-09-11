"""Bayesian sensitivity re-fits for Q2/Q4 (spec section 7, Phase 3B).

NUTS via PyMC with pinned weakly-informative priors: coefficients
Normal(0, 2.5*sd(y)); group and residual SDs HalfNormal(sd(y)). Intervals are
95% equal-tailed (ETI; arviz 1.x). Convergence: max R-hat <= 1.01 AND zero
divergences. cores=1 always — the console runs this inside a worker thread.

This artifact is SEPARATE from the frequentist engine artifact and carries its
own BAYES_VERSION; bump it on any model/prior/schema change.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from . import gates
from .data import (CONFIRMATORY_METRICS, confirmatory_eligibility_summary,
                   fingerprint, fits_frame, metrics_frame)

BAYES_VERSION = "2.2.1"
SPEC = "docs/research/scientific-foundation-v2.md"
DEFAULT_SEED = 20260604
RHAT_MAX = 1.01
PRIORS = {
    "coefficients": "Normal(0, 2.5*sd(y))",
    "sds": "HalfNormal(sd(y)) for sigma_u (participant) and sigma_e (residual)",
}
CAVEATS = [
    "Only v2 confirmatory metrics are fitted; legacy TLX sums and estimated SYSMON d-prime are excluded.",
    "Bayesian sensitivity re-fit of Q2/Q4 only; the frequentist artifact is primary.",
    "95% intervals are equal-tailed (ETI), not HDI.",
    "'not converged' (R-hat > 1.01 or any divergence) means the posterior summary "
    "is unreliable and must not be reported.",
]


def _finite_float(value: Any, *, field: str) -> float:
    observed = float(value)
    if not np.isfinite(observed):
        raise ValueError(f"Bayesian diagnostic {field} is non-finite")
    return observed


def _fit_one(df: pd.DataFrame, *, include_levels: bool, seed: int, draws: int,
             tune: int, chains: int) -> dict[str, Any]:
    """One hierarchical fit: y ~ b0 + b_visit*visit_c (+ level indicators)
    + u[participant] + eps. df needs columns participant_id, visit_c, value
    (+ workload_level when include_levels)."""
    import arviz as az
    import pymc as pm

    pid_codes, uniques = pd.factorize(df["participant_id"])
    y = df["value"].to_numpy(dtype=float)
    x = df["visit_c"].to_numpy(dtype=float)
    sd_y = float(np.std(y)) or 1.0
    var_names = ["b0", "b_visit"]
    with pm.Model():
        # Initialize the intercept at observed location without changing its prior.
        # Jitter of order one is unstable for narrow-scale outcomes far from zero.
        b0 = pm.Normal("b0", 0.0, 2.5 * sd_y, initval=float(np.mean(y)))
        b_visit = pm.Normal("b_visit", 0.0, 2.5 * sd_y)
        mu = b0 + b_visit * x
        if include_levels:
            med = (df["workload_level"] == "MEDIUM").to_numpy(dtype=float)
            high = (df["workload_level"] == "HIGH").to_numpy(dtype=float)
            b_med = pm.Normal("b_med", 0.0, 2.5 * sd_y)
            b_high = pm.Normal("b_high", 0.0, 2.5 * sd_y)
            mu = mu + b_med * med + b_high * high
            var_names += ["b_med", "b_high"]
        sigma_u = pm.HalfNormal("sigma_u", sd_y)
        sigma_e = pm.HalfNormal("sigma_e", sd_y)
        u = pm.Normal("u", 0.0, sigma_u, shape=len(uniques))
        pm.Normal("y", mu + u[pid_codes], sigma_e, observed=y)
        idata = pm.sample(draws=draws, tune=tune, chains=chains, cores=1,
                          random_seed=seed, progressbar=False,
                          compute_convergence_checks=False, init="adapt_diag")
    var_names += ["sigma_u", "sigma_e"]
    # Participant effects are not scientific coefficients exposed by this
    # artifact, but they are sampled parameters and must participate in the
    # convergence gate.  Excluding ``u`` could label a model converged while
    # one or more participant effects still mix poorly.
    summ = az.summary(idata, var_names=[*var_names, "u"], ci_prob=0.95)
    divergences = int(idata.sample_stats["diverging"].sum())
    coefs: dict[str, Any] = {}
    for name in var_names:
        row = summ.loc[name]
        coefs[name] = {
            "mean": _finite_float(row["mean"], field=f"{name}.mean"),
            "sd": _finite_float(row["sd"], field=f"{name}.sd"),
            "eti95": [
                _finite_float(row["eti95_lb"], field=f"{name}.eti95_lb"),
                _finite_float(row["eti95_ub"], field=f"{name}.eti95_ub"),
            ],
            "r_hat": _finite_float(row["r_hat"], field=f"{name}.r_hat"),
            "ess_bulk": _finite_float(row["ess_bulk"], field=f"{name}.ess_bulk"),
            "ess_tail": _finite_float(row["ess_tail"], field=f"{name}.ess_tail"),
        }
    max_r_hat = _finite_float(summ["r_hat"].max(), field="max_r_hat")
    return {
        "status": "ok",
        "n_obs": int(len(df)), "n_participants": int(len(uniques)),
        "coefs": coefs,
        "diagnostics": {"max_r_hat": max_r_hat,
                        "min_ess_bulk": _finite_float(
                            summ["ess_bulk"].min(), field="min_ess_bulk"
                        ),
                        "divergences": divergences},
        "converged": bool(max_r_hat <= RHAT_MAX and divergences == 0),
    }


def _guarded(df: pd.DataFrame, gate_reason: str | None, **kw) -> dict[str, Any]:
    if gate_reason:
        return {"status": "insufficient_data", "detail": gate_reason}
    try:
        return _fit_one(df, **kw)
    except Exception as e:  # noqa: BLE001 — statuses are first-class
        return {"status": "not_estimable", "detail": f"{type(e).__name__}: {e}"}


def _convergence_summary(
    results: list[dict[str, Any]],
) -> tuple[bool, dict[str, int]]:
    """Summarize the complete preregistered Bayesian model family.

    ``all_converged`` is deliberately stronger than "all models that happened
    to fit converged": every planned Q2/Q4 model must be fitted and pass the
    diagnostic gate.
    """

    fitted = [result for result in results if result.get("status") == "ok"]
    converged = [result for result in fitted if result.get("converged") is True]
    not_converged = len(fitted) - len(converged)
    summary = {
        "models_planned": len(results),
        "models_fitted": len(fitted),
        "models_converged": len(converged),
        "models_not_converged": not_converged,
        "models_not_fitted": len(results) - len(fitted),
    }
    return len(results) > 0 and len(converged) == len(results), summary


def run_bayes(metrics_rows: list[dict[str, Any]], fits_rows: list[dict[str, Any]],
              *, seed: int = DEFAULT_SEED, draws: int = 1000, tune: int = 1000,
              chains: int = 4, created_utc: str | None = None) -> dict[str, Any]:
    if isinstance(chains, bool) or not isinstance(chains, int) or chains < 2:
        raise ValueError("Bayesian convergence diagnostics require at least two chains")
    metrics_rows, fits_rows = list(metrics_rows), list(fits_rows)
    mdf, fdf = metrics_frame(metrics_rows), fits_frame(fits_rows)
    eligible_mdf = mdf[mdf["confirmatory_eligible"]] if not mdf.empty else mdf
    kw = {"seed": seed, "draws": draws, "tune": tune, "chains": chains}

    q2 = {}
    for m in CONFIRMATORY_METRICS:
        d = eligible_mdf[eligible_mdf["metric"] == m]
        q2[m] = _guarded(d, gates.gate_q2(d), include_levels=True, **kw)
    q4 = {}
    for param in ("g0", "p0", "tau0"):
        d = fdf.rename(columns={param: "value"})
        q4[param] = _guarded(d, gates.gate_q4(fdf), include_levels=False, **kw)

    all_converged, convergence_summary = _convergence_summary(
        list(q2.values()) + list(q4.values())
    )
    return {
        "bayes_version": BAYES_VERSION, "spec": SPEC,
        "sampler": {"seed": seed, "chains": chains, "draws": draws, "tune": tune,
                    "nuts": "pymc", "cores": 1, "interval": "95% ETI",
                    "initialization": "adapt_diag; b0=observed_mean; remaining prior defaults",
                    "priors": dict(PRIORS)},
        "provenance": {
            "fingerprint": fingerprint(metrics_rows, fits_rows),
            "n_metric_rows": len(metrics_rows), "n_fit_rows": len(fits_rows),
            "libraries": _libraries(), "created_utc": created_utc,
        },
        "q2": q2, "q4": q4,
        "confirmatory_eligibility": confirmatory_eligibility_summary(mdf),
        "all_converged": all_converged,
        "convergence_summary": convergence_summary,
        "caveats": list(CAVEATS),
    }


def _libraries() -> dict[str, str]:
    import arviz
    import numpy
    import pymc
    return {"pymc": pymc.__version__, "arviz": arviz.__version__,
            "numpy": numpy.__version__, "pandas": pd.__version__}
