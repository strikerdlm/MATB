"""Machine-readable scientific metric definitions and schema helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

METRICS_SPEC_PATH = Path(__file__).with_name("metrics_spec.json")


def load_metrics_spec(path: Path = METRICS_SPEC_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("metrics"), dict):
        raise ValueError("metrics specification must contain a metrics object")
    if str(payload.get("schema_version") or "") != "2.0":
        raise ValueError("unsupported metrics schema version")
    return payload


METRICS_SPEC = load_metrics_spec()
METRICS_SCHEMA_VERSION = str(METRICS_SPEC["schema_version"])

# Public long-format API key -> canonical registry identifier. Compatibility
# aliases intentionally resolve to the definition whose historical semantics
# they preserve.
LONG_METRIC_IDS: dict[str, str] = {
    "sysmon_dprime_observed_v2": "sysmon.dprime_observed_v2",
    "sysmon_dprime_estimated_v1": "sysmon.dprime_estimated_v1",
    "sysmon_d_prime": "sysmon.dprime_estimated_v1",
    "sysmon_hit_rate": "sysmon.hit_rate",
    "sysmon_mean_rt_ms": "sysmon.mean_rt_ms",
    "track_rmse_deviation": "track.rmse_deviation",
    "track_percent_time_in_target": "track.percent_time_in_target",
    "resman_mean_absolute_deviation": "resman.mean_absolute_deviation",
    "resman_percent_time_in_tolerance": "resman.percent_time_in_tolerance",
    "comm_d_prime": "communications.d_prime",
    "nasatlx_rtlx_mean_0_100": "nasatlx.rtlx_mean_0_100",
    "nasatlx_legacy_sum_0_60": "nasatlx.legacy_subscale_sum_0_60",
    "nasatlx_raw_tlx": "nasatlx.legacy_subscale_sum_0_60",
    "bedford": "bedford.value",
    "isa_mean": "isa.mean",
}


def metric_definition(metric_id: str) -> dict[str, Any]:
    try:
        return dict(METRICS_SPEC["metrics"][metric_id])
    except KeyError as exc:
        raise KeyError(f"unknown scientific metric: {metric_id}") from exc


def long_metric_definition(metric_key: str) -> dict[str, Any]:
    try:
        metric_id = LONG_METRIC_IDS[metric_key]
    except KeyError as exc:
        raise KeyError(f"unknown long-format metric: {metric_key}") from exc
    definition = metric_definition(metric_id)
    definition["metric_id"] = metric_id
    return definition
