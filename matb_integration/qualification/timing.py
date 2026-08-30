"""Analyze independently captured MATB timing records.

The input is a tidy CSV produced after event matching.  It must retain one row
per planned event and must not silently omit unmatched or ambiguous events.
"""

from __future__ import annotations

import csv
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import evaluate_timing_qualification

REQUIRED_COLUMNS = {"event_id", "modality", "device_id", "run_id"}
SUPPORTED_MODALITIES = {"visual", "audio", "input"}


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    data = list(values)
    if not data:
        return {key: None for key in ("median", "q1", "q3", "p95", "p99", "max", "min")} | {"n": 0}
    return {
        "n": len(data),
        "median": round(statistics.median(data), 6),
        "q1": round(_percentile(data, 0.25), 6),
        "q3": round(_percentile(data, 0.75), 6),
        "p95": round(_percentile(data, 0.95), 6),
        "p99": round(_percentile(data, 0.99), 6),
        "max": round(max(data), 6),
        "min": round(min(data), 6),
    }


def read_timing_csv(path: Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or ())
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(f"timing CSV missing columns: {', '.join(sorted(missing))}")
        return [{str(key): str(value or "").strip() for key, value in row.items()} for row in reader]


def _latencies(row: Mapping[str, Any]) -> dict[str, float]:
    modality = str(row.get("modality") or "")
    dispatch = _number(row.get("dispatch_s"))
    physical = _number(row.get("physical_s"))
    lsl = _number(row.get("lsl_s"))
    physical_input = _number(row.get("physical_input_s"))
    response = _number(row.get("response_s"))
    values: dict[str, float] = {}
    if modality in {"visual", "audio"} and dispatch is not None and physical is not None:
        values["dispatch_to_physical_ms"] = (physical - dispatch) * 1000.0
    if modality in {"visual", "audio"} and physical is not None and lsl is not None:
        values["physical_to_lsl_ms"] = (lsl - physical) * 1000.0
    if modality == "input" and physical_input is not None and response is not None:
        values["physical_input_to_response_ms"] = (response - physical_input) * 1000.0
    return values


def _limits_pass(statistics_by_metric: Mapping[str, Mapping[str, Any]], limits: Mapping[str, Any]) -> bool:
    if not limits:
        return False
    for metric, rules in limits.items():
        observed = statistics_by_metric.get(metric)
        if not isinstance(rules, Mapping) or not isinstance(observed, Mapping):
            return False
        for rule, threshold in rules.items():
            if rule not in {"max_abs_median_ms", "max_p95_ms", "max_p99_ms", "max_ms"}:
                return False
            if not isinstance(threshold, (int, float)) or threshold < 0:
                return False
            statistic = {
                "max_abs_median_ms": "median",
                "max_p95_ms": "p95",
                "max_p99_ms": "p99",
                "max_ms": "max",
            }[rule]
            value = observed.get(statistic)
            if not isinstance(value, (int, float)):
                return False
            compared = abs(value) if rule == "max_abs_median_ms" else value
            if compared > threshold:
                return False
    return True


def analyze_timing_records(
    rows: list[Mapping[str, Any]],
    *,
    rig: Mapping[str, Any],
    use_tier: str,
    preregistered_limits: Mapping[str, Any],
    representative_full_block_recorded: bool,
    source_commit: str,
) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        modality = str(row.get("modality") or "")
        if modality not in SUPPORTED_MODALITIES:
            raise ValueError(f"unsupported timing modality: {modality or '<missing>'}")
        grouped[modality].append(row)

    summaries: list[dict[str, Any]] = []
    physical_measured = False
    for modality in sorted(SUPPORTED_MODALITIES):
        subset = grouped.get(modality, [])
        counts = Counter(str(row.get("event_id") or "") for row in subset)
        duplicate_ids = sorted(event_id for event_id, count in counts.items() if event_id and count > 1)
        metrics: dict[str, list[float]] = defaultdict(list)
        unmatched = 0
        for row in subset:
            values = _latencies(row)
            required_metric = (
                "physical_input_to_response_ms" if modality == "input" else "dispatch_to_physical_ms"
            )
            if not str(row.get("event_id") or "") or counts[str(row.get("event_id") or "")] > 1 or required_metric not in values:
                unmatched += 1
                continue
            physical_measured = True
            for key, value in values.items():
                metrics[key].append(value)
        stats = {key: distribution(values) for key, values in sorted(metrics.items())}
        modality_limits = preregistered_limits.get(modality)
        if not isinstance(modality_limits, Mapping):
            modality_limits = {}
        summaries.append(
            {
                "modality": modality,
                "device_id": sorted({str(row.get("device_id") or "") for row in subset}),
                "n": len(subset) - unmatched,
                "planned_n": len(subset),
                "run_count": len({str(row.get("run_id") or "") for row in subset if row.get("run_id")}),
                "unmatched_count": unmatched,
                "duplicate_event_ids": duplicate_ids,
                "statistics_ms": stats,
                "preregistered_limits": dict(modality_limits),
                "limits_passed": _limits_pass(stats, modality_limits),
            }
        )

    return evaluate_timing_qualification(
        {
            "use_tier": use_tier,
            "source_commit": source_commit,
            "rig": dict(rig),
            "physical_measurement": {"measured": physical_measured},
            "measurement_summaries": summaries,
            "representative_full_block_recorded": representative_full_block_recorded,
        }
    )


def analyze_timing_csv(path: Path, **kwargs: Any) -> dict[str, Any]:
    return analyze_timing_records(read_timing_csv(path), **kwargs)
