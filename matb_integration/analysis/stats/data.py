"""Tidy long-format frames + input fingerprint for the stats engine.

Input row shapes are exactly what the console serves: /metrics/long rows
(participant_id, visit_ordinal, workload_level, metric, value) and /fits rows
(participant_id, visit_ordinal, g0, p0, tau0; extra keys ignored).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

import pandas as pd

ALL_METRICS: tuple[str, ...] = (
    "sysmon_d_prime", "sysmon_hit_rate", "sysmon_mean_rt_ms",
    "comm_d_prime", "nasatlx_raw_tlx", "bedford", "isa_mean",
)
CONFIRMATORY_METRICS: tuple[str, ...] = ("sysmon_d_prime", "nasatlx_raw_tlx", "bedford")
LEVELS: tuple[str, ...] = ("LOW", "MEDIUM", "HIGH")
VISIT_CENTER = 3.5  # mean of visit ordinals 1..6

_METRIC_COLS = ("participant_id", "visit_ordinal", "workload_level", "metric", "value")
_FIT_COLS = ("participant_id", "visit_ordinal", "g0", "p0", "tau0")


def _frame(rows: Iterable[dict[str, Any]], cols: tuple[str, ...]) -> pd.DataFrame:
    df = pd.DataFrame(list(rows), columns=list(cols))
    if df.empty:
        df = pd.DataFrame({c: pd.Series(dtype="object") for c in cols})
    return df


def metrics_frame(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    df = _frame(rows, _METRIC_COLS)
    df = df[df["value"].notna()].copy()
    if not df.empty:
        bad_lvl = set(df["workload_level"]) - set(LEVELS)
        if bad_lvl:
            raise ValueError(f"unknown workload_level values: {sorted(bad_lvl)}")
        bad_metric = set(df["metric"]) - set(ALL_METRICS)
        if bad_metric:
            raise ValueError(f"unknown metric keys: {sorted(bad_metric)}")
        df["visit_ordinal"] = df["visit_ordinal"].astype("int64")
        df["value"] = df["value"].astype("float64")
    df["visit_c"] = pd.to_numeric(df["visit_ordinal"], errors="coerce") - VISIT_CENTER
    return df.reset_index(drop=True)


def fits_frame(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    df = _frame(rows, _FIT_COLS)
    if not df.empty:
        df["visit_ordinal"] = df["visit_ordinal"].astype("int64")
        for c in ("g0", "p0", "tau0"):
            df[c] = df[c].astype("float64")
    df["visit_c"] = pd.to_numeric(df["visit_ordinal"], errors="coerce") - VISIT_CENTER
    return df.reset_index(drop=True)


def fingerprint(metrics_rows: Iterable[dict[str, Any]],
                fits_rows: Iterable[dict[str, Any]]) -> str:
    """sha256 over canonicalized (sorted, column-restricted) input rows."""
    def canon(rows: Iterable[dict[str, Any]], cols: tuple[str, ...]) -> list[list[Any]]:
        recs = [[r.get(c) for c in cols] for r in rows]
        return sorted(recs, key=lambda rec: json.dumps(rec, default=str))
    payload = json.dumps(
        {"metrics": canon(metrics_rows, _METRIC_COLS),
         "fits": canon(fits_rows, _FIT_COLS)},
        separators=(",", ":"), default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()
