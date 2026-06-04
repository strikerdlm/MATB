"""Engine orchestration: Q1-Q4 + multiplicity -> one JSON-serializable artifact.

Multiplicity (spec section 3): BH-FDR at q=.05 over exactly the 6-test
confirmatory family ({d', raw TLX, Bedford} x {Q1 omnibus, Q2 visit slope});
pairwise Q1 contrasts only for FDR survivors, Holm-corrected within metric.
Everything else is exploratory. If some planned tests are not estimable, the
FDR correction runs over the available tests and both planned and actual
family sizes are recorded.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .data import (ALL_METRICS, CONFIRMATORY_METRICS, fingerprint,
                   fits_frame, metrics_frame)
from .lmm import fit_q1, fit_q2, fit_q4
from .multiplicity import bh_fdr, holm
from .rmanova import rm_anova_q1
from .rmcorr import rm_corr, rm_corr_level_adjusted

ENGINE_VERSION = "1.0.0"
SPEC = "docs/superpowers/specs/2026-06-03-webui-phase3-statistics-design.md"
FDR_Q = 0.05
# Pre-specified exploratory coupling pairs (x = subjective workload, y = performance)
Q3_PAIRS: tuple[tuple[str, str], ...] = tuple(
    (x, y)
    for x in ("nasatlx_raw_tlx", "bedford", "isa_mean")
    for y in ("sysmon_d_prime", "sysmon_mean_rt_ms", "comm_d_prime")
)
CAVEATS = [
    "Wald inference on REML fits; small-sample (n=12) p-values are approximate.",
    "Random intercepts only; random slopes not estimable at this n.",
    "Q2 primary slope is the level-adjusted common slope (additive model); "
    "level-specific slopes are exploratory (interaction fit).",
    "rmANOVA is complete-case and visit-averaged; descriptive sensitivity only.",
    "Q3/Q4 and non-confirmatory metrics are exploratory (no error-rate control).",
    "Q4 on p0: near-boundary [0,1] probability; the linear-LMM slope is "
    "descriptive only and may be not_estimable.",
]


def _pairs_frame(mdf: pd.DataFrame, x_metric: str, y_metric: str) -> pd.DataFrame:
    cols = ["participant_id", "visit_ordinal", "workload_level"]
    empty = pd.DataFrame(columns=cols + ["x", "y"])
    if mdf.empty:
        return empty
    wide = mdf.pivot_table(index=cols, columns="metric", values="value",
                           aggfunc="first").reset_index()
    if x_metric not in wide.columns or y_metric not in wide.columns:
        return empty
    out = wide[cols + [x_metric, y_metric]].dropna()
    return out.rename(columns={x_metric: "x", y_metric: "y"})


def _libraries() -> dict[str, str]:
    import numpy
    import scipy
    import statsmodels
    return {"pandas": pd.__version__, "statsmodels": statsmodels.__version__,
            "scipy": scipy.__version__, "numpy": numpy.__version__}


def run_analysis(metrics_rows: list[dict[str, Any]], fits_rows: list[dict[str, Any]],
                 created_utc: str | None = None) -> dict[str, Any]:
    metrics_rows, fits_rows = list(metrics_rows), list(fits_rows)
    mdf, fdf = metrics_frame(metrics_rows), fits_frame(fits_rows)

    per_metric = {m: mdf[mdf["metric"] == m] for m in ALL_METRICS}
    q1 = {m: fit_q1(d) for m, d in per_metric.items()}
    q2 = {m: fit_q2(d) for m, d in per_metric.items()}

    # --- confirmatory family: BH-FDR over the available planned tests ---
    planned: list[tuple[str, str, float | None]] = []
    for m in CONFIRMATORY_METRICS:
        p1 = q1[m]["omnibus"]["p"] if q1[m]["status"] == "ok" else None
        slope = next((c for c in q2[m].get("coefs", []) if c["name"] == "visit_c"), None)
        p2 = slope["p"] if q2[m]["status"] == "ok" and slope else None
        planned.append((m, "Q1_omnibus", p1))
        planned.append((m, "Q2_visit_slope", p2))
    avail = [(m, q, p) for m, q, p in planned if p is not None]
    p_adj, reject = bh_fdr([p for _, _, p in avail], q=FDR_Q)
    adj_map = {(m, q): (pa, rj) for (m, q, _), pa, rj in zip(avail, p_adj, reject)}
    tests = []
    for m, qname, p in planned:
        pa, rj = adj_map.get((m, qname), (None, None))
        tests.append({"metric": m, "test": qname, "p": p, "p_fdr": pa, "reject": rj})
    confirmatory = {"family_size_planned": len(planned),
                    "family_size_actual": len(avail),
                    "fdr_q": FDR_Q, "tests": tests}

    # --- Q1 contrasts: only for FDR-surviving confirmatory omnibus tests ---
    survivors = {m for m, qname, _ in planned
                 if qname == "Q1_omnibus" and adj_map.get((m, qname), (None, False))[1]}
    for m, res in q1.items():
        res["exploratory"] = m not in CONFIRMATORY_METRICS
        contrasts = res.pop("contrasts", None)
        if m in survivors and contrasts:
            p_holm, rej = holm([c["p"] for c in contrasts])
            for c, ph, rj in zip(contrasts, p_holm, rej):
                c["p_holm"], c["reject_holm"] = ph, rj
            res["contrasts"] = contrasts
        else:
            res["contrasts"] = None  # suppressed: gated on the FDR family (spec section 3)
    for m, res in q2.items():
        res["exploratory"] = m not in CONFIRMATORY_METRICS

    # --- Q3 (exploratory): canonical rmcorr + level-adjusted sensitivity ---
    q3 = []
    for x_metric, y_metric in Q3_PAIRS:
        pairs = _pairs_frame(mdf, x_metric, y_metric)
        entry: dict[str, Any] = {"x": x_metric, "y": y_metric,
                                 "canonical": rm_corr(pairs[["participant_id", "x", "y"]])}
        if entry["canonical"]["status"] == "ok":
            entry["sensitivity"] = rm_corr_level_adjusted(pairs)
        q3.append(entry)

    # --- Q4 (exploratory): DEPDF parameter drift ---
    q4 = {param: fit_q4(fdf, param) for param in ("g0", "p0", "tau0")}

    rmanova = {m: rm_anova_q1(per_metric[m]) for m in CONFIRMATORY_METRICS}

    return {
        "engine_version": ENGINE_VERSION, "spec": SPEC,
        "provenance": {
            "fingerprint": fingerprint(metrics_rows, fits_rows),
            "n_metric_rows": len(metrics_rows), "n_fit_rows": len(fits_rows),
            "n_participants": int(mdf["participant_id"].nunique()) if not mdf.empty else 0,
            "libraries": _libraries(), "created_utc": created_utc,
        },
        "confirmatory": confirmatory,
        "q1": q1, "q2": q2, "q3": q3, "q4": q4, "rmanova": rmanova,
        "caveats": list(CAVEATS),
    }
