"""Complete-case repeated-measures ANOVA — descriptive Q1 sensitivity only."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

MIN_COMPLETE_CASE = 3


def rm_anova_q1(df: pd.DataFrame) -> dict[str, Any]:
    have = df.groupby("participant_id")["workload_level"].nunique()
    keep = have[have == 3].index
    cc = df[df["participant_id"].isin(keep)]
    n_cc = int(cc["participant_id"].nunique())
    if n_cc < MIN_COMPLETE_CASE:
        return {"status": "insufficient_data",
                "detail": f"only {n_cc} complete-case participants (< {MIN_COMPLETE_CASE})"}
    try:
        from statsmodels.stats.anova import AnovaRM

        res = AnovaRM(cc, depvar="value", subject="participant_id",
                      within=["workload_level"], aggregate_func="mean").fit()
        row = res.anova_table.iloc[0]
        f, df1, df2 = float(row["F Value"]), float(row["Num DF"]), float(row["Den DF"])
        if not np.isfinite(f) or f < 0:
            return {"status": "not_estimable",
                    "detail": "non-finite or negative F (degenerate within-subject variance)"}
        return {"status": "ok", "F": f, "df": [df1, df2],
                "p": float(row["Pr > F"]),
                "partial_eta_sq": f * df1 / (f * df1 + df2),
                "complete_case_n": n_cc,
                "note": "complete-case, visit-averaged; descriptive sensitivity only"}
    except Exception as e:  # noqa: BLE001 — statuses are first-class
        return {"status": "not_estimable", "detail": f"{type(e).__name__}: {e}"}
