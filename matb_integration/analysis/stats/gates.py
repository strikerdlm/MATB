"""Pre-registered data gates (spec section 4). None = pass; str = failure reason."""
from __future__ import annotations

import pandas as pd

MIN_PARTICIPANTS_LMM = 6
MIN_ROWS_LMM = 24
MIN_PARTICIPANTS_RMCORR = 4
MIN_ERROR_DF_RMCORR = 8
MIN_PARTICIPANTS_Q4 = 4


def gate_q1(df: pd.DataFrame) -> str | None:
    if len(df) < MIN_ROWS_LMM:
        return f"only {len(df)} rows (< {MIN_ROWS_LMM})"
    n = int((df.groupby("participant_id")["workload_level"].nunique() >= 2).sum())
    if n < MIN_PARTICIPANTS_LMM:
        return f"only {n} participants with >=2 levels (< {MIN_PARTICIPANTS_LMM})"
    return None


def gate_q2(df: pd.DataFrame) -> str | None:
    if len(df) < MIN_ROWS_LMM:
        return f"only {len(df)} rows (< {MIN_ROWS_LMM})"
    n = int((df.groupby("participant_id")["visit_ordinal"].nunique() >= 2).sum())
    if n < MIN_PARTICIPANTS_LMM:
        return f"only {n} participants with >=2 visits (< {MIN_PARTICIPANTS_LMM})"
    return None


def gate_rmcorr(pairs: pd.DataFrame) -> str | None:
    n_ok = int((pairs.groupby("participant_id").size() >= 2).sum())
    if n_ok < MIN_PARTICIPANTS_RMCORR:
        return f"only {n_ok} participants with >=2 pairs (< {MIN_PARTICIPANTS_RMCORR})"
    n, k = len(pairs), int(pairs["participant_id"].nunique())
    err_df = n - k - 1
    if err_df < MIN_ERROR_DF_RMCORR:
        return f"error df {err_df} (< {MIN_ERROR_DF_RMCORR})"
    return None


def gate_q4(fits: pd.DataFrame) -> str | None:
    n = int((fits.groupby("participant_id")["visit_ordinal"].nunique() >= 2).sum())
    if n < MIN_PARTICIPANTS_Q4:
        return f"only {n} participants with >=2 fitted visits (< {MIN_PARTICIPANTS_Q4})"
    return None
