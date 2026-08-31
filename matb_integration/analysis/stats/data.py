"""Tidy long-format frames + input fingerprint for the stats engine.

Input row shapes are exactly what the console serves: /metrics/long rows
(participant_id, visit_ordinal, workload_level, metric, value) and /fits rows
(participant_id, visit_ordinal, g0, p0, tau0; extra keys ignored).
"""
from __future__ import annotations

import hashlib
import json
import math
from numbers import Real
from typing import Any, Iterable

import pandas as pd

from matb_integration.metrics_schema import (
    LONG_METRIC_IDS,
    METRICS_SCHEMA_VERSION,
    long_metric_definition,
)

ALL_METRICS: tuple[str, ...] = tuple(LONG_METRIC_IDS)
CONFIRMATORY_METRICS: tuple[str, ...] = (
    "sysmon_hit_rate", "nasatlx_rtlx_mean_0_100", "bedford",
)
LEVELS: tuple[str, ...] = ("LOW", "MEDIUM", "HIGH")
VISIT_CENTER = 3.5  # mean of visit ordinals 1..6

_METRIC_COLS = (
    "participant_id", "visit_ordinal", "workload_level", "metric", "value",
    "metrics_schema_version", "metric_version", "confirmatory_eligible",
)
_FINGERPRINT_METRIC_COLS = _METRIC_COLS
_FIT_COLS = ("participant_id", "visit_ordinal", "g0", "p0", "tau0")

_METRIC_BOUNDS: dict[str, tuple[float | None, float | None]] = {
    "sysmon_hit_rate": (0.0, 1.0),
    "sysmon_mean_rt_ms": (0.0, None),
    "track_rmse_deviation": (0.0, None),
    "track_percent_time_in_target": (0.0, 100.0),
    "resman_mean_absolute_deviation": (0.0, None),
    "resman_percent_time_in_tolerance": (0.0, 100.0),
    "nasatlx_rtlx_mean_0_100": (0.0, 100.0),
    "nasatlx_legacy_sum_0_60": (0.0, 60.0),
    "nasatlx_raw_tlx": (0.0, 60.0),
    "bedford": (1.0, 10.0),
    "isa_mean": (1.0, 10.0),
}


def _participant_id(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("participant_id must be a non-empty trimmed string")
    return value


def _visit_ordinal(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("visit_ordinal must be an exact positive integer")
    return value


def _finite_number(value: Any, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field_name} must be a finite number, not a boolean")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def _validate_metric_domain(metric: str, value: float) -> None:
    minimum, maximum = _METRIC_BOUNDS.get(metric, (None, None))
    if minimum is not None and value < minimum:
        raise ValueError(f"value for {metric} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"value for {metric} must be <= {maximum}")


def _frame(rows: Iterable[dict[str, Any]], cols: tuple[str, ...]) -> pd.DataFrame:
    df = pd.DataFrame(list(rows), columns=list(cols))
    if df.empty:
        df = pd.DataFrame({c: pd.Series(dtype="object") for c in cols})
    return df


def metrics_frame(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    supplied = list(rows)
    schema_versions = {
        str(row.get("metrics_schema_version") or "1.0")
        for row in supplied
    }
    if len(schema_versions) > 1:
        raise ValueError(
            "mixed metrics_schema_version values require an explicit migration: "
            f"{sorted(schema_versions)}"
        )
    normalized: list[dict[str, Any]] = []
    identities: set[tuple[str, int, str, str]] = set()
    for row in supplied:
        participant_id = _participant_id(row.get("participant_id"))
        visit_ordinal = _visit_ordinal(row.get("visit_ordinal"))
        metric = str(row.get("metric") or "")
        if metric not in ALL_METRICS:
            raise ValueError(f"unknown metric keys: {[metric]}")
        schema_version = str(row.get("metrics_schema_version") or "1.0")
        if schema_version not in {"1.0", METRICS_SCHEMA_VERSION}:
            raise ValueError(
                f"unsupported metrics_schema_version: {schema_version!r}"
            )
        eligible_value = row.get("confirmatory_eligible", False)
        metric_version_value = row.get("metric_version")
        if schema_version == METRICS_SCHEMA_VERSION:
            if "confirmatory_eligible" not in row:
                raise ValueError(
                    "metrics schema 2.0 requires confirmatory_eligible on every row"
                )
            if not isinstance(eligible_value, bool):
                raise ValueError("confirmatory_eligible must be a boolean")
            if metric_version_value is None:
                raise ValueError("metrics schema 2.0 requires metric_version on every row")
            expected_version = str(long_metric_definition(metric)["metric_version"])
            if metric in {"sysmon_d_prime", "nasatlx_raw_tlx"}:
                expected_version = "1-legacy-alias"
            if str(metric_version_value) != expected_version:
                raise ValueError(
                    f"metric_version mismatch for {metric}: expected "
                    f"{expected_version!r}, observed {metric_version_value!r}"
                )
            if eligible_value and not bool(
                long_metric_definition(metric)["confirmatory_eligible"]
            ):
                raise ValueError(
                    f"metric {metric} is not confirmatory-eligible in schema 2.0"
                )
        else:
            if eligible_value is True:
                raise ValueError(
                    "legacy metrics schema rows cannot claim confirmatory eligibility"
                )
            eligible_value = False
            metric_version_value = (
                "unknown" if metric_version_value is None else str(metric_version_value)
            )
        workload_level = row.get("workload_level")
        if not isinstance(workload_level, str) or workload_level not in LEVELS:
            raise ValueError(f"unknown workload_level values: {[workload_level]}")
        identity = (participant_id, visit_ordinal, workload_level, metric)
        if identity in identities:
            raise ValueError(
                "duplicate participant×visit×workload×metric row: "
                f"{identity!r}"
            )
        identities.add(identity)
        raw_value = row.get("value")
        value = None
        if raw_value is not None:
            value = _finite_number(raw_value, field_name=f"value for {metric}")
            _validate_metric_domain(metric, value)
        normalized.append({
            **row,
            "participant_id": participant_id,
            "visit_ordinal": visit_ordinal,
            "workload_level": workload_level,
            "metric": metric,
            "value": value,
            "metrics_schema_version": schema_version,
            "metric_version": str(metric_version_value),
            "confirmatory_eligible": eligible_value,
        })

    df = _frame(normalized, _METRIC_COLS)
    df = df[df["value"].notna()].copy()
    if not df.empty:
        df["visit_ordinal"] = df["visit_ordinal"].astype("int64")
        df["value"] = df["value"].astype("float64")
        df["confirmatory_eligible"] = df["confirmatory_eligible"].astype("bool")
    df["visit_c"] = pd.to_numeric(df["visit_ordinal"], errors="coerce") - VISIT_CENTER
    return df.reset_index(drop=True)


def confirmatory_eligibility_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Describe fail-closed row filtering for the planned confirmatory family."""
    if df.empty:
        return {
            "rows_in_scope": 0,
            "rows_eligible": 0,
            "rows_excluded": 0,
            "excluded_by_reason": {},
            "by_metric": {
                metric: {"in_scope": 0, "eligible": 0, "excluded": 0}
                for metric in CONFIRMATORY_METRICS
            },
        }
    scope = df[df["metric"].isin(CONFIRMATORY_METRICS)]
    eligible = scope["confirmatory_eligible"].astype(bool)
    by_metric: dict[str, dict[str, int]] = {}
    for metric in CONFIRMATORY_METRICS:
        metric_rows = scope[scope["metric"] == metric]
        metric_eligible = int(metric_rows["confirmatory_eligible"].astype(bool).sum())
        by_metric[metric] = {
            "in_scope": int(len(metric_rows)),
            "eligible": metric_eligible,
            "excluded": int(len(metric_rows) - metric_eligible),
        }
    excluded = int((~eligible).sum())
    return {
        "rows_in_scope": int(len(scope)),
        "rows_eligible": int(eligible.sum()),
        "rows_excluded": excluded,
        "excluded_by_reason": (
            {"confirmatory_eligible_false": excluded} if excluded else {}
        ),
        "by_metric": by_metric,
    }


def fits_frame(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    normalized: list[dict[str, Any]] = []
    identities: set[tuple[str, int]] = set()
    for row in rows:
        participant_id = _participant_id(row.get("participant_id"))
        visit_ordinal = _visit_ordinal(row.get("visit_ordinal"))
        identity = (participant_id, visit_ordinal)
        if identity in identities:
            raise ValueError(f"duplicate participant×visit fit row: {identity!r}")
        identities.add(identity)
        g0 = _finite_number(row.get("g0"), field_name="g0")
        p0 = _finite_number(row.get("p0"), field_name="p0")
        tau0 = _finite_number(row.get("tau0"), field_name="tau0")
        # These are parameter domains, not merely numerical conveniences.
        # G0 is a positive workload scale, P0 is a probability, and tau0 is a
        # positive time scale.  Letting invalid fits reach Q4 would give a
        # statistically polished result for a physically impossible model.
        if g0 <= 0.0:
            raise ValueError("g0 must be in the registered domain (0, +inf)")
        if not 0.0 <= p0 <= 1.0:
            raise ValueError("p0 must be in the probability domain [0, 1]")
        if tau0 <= 0.0:
            raise ValueError("tau0 must be in the registered domain (0, +inf)")
        normalized.append({
            "participant_id": participant_id,
            "visit_ordinal": visit_ordinal,
            "g0": g0,
            "p0": p0,
            "tau0": tau0,
        })
    df = _frame(normalized, _FIT_COLS)
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
        {"metrics": canon(metrics_rows, _FINGERPRINT_METRIC_COLS),
         "fits": canon(fits_rows, _FIT_COLS)},
        separators=(",", ":"), default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()
