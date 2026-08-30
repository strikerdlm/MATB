"""Tidy long-format metric extraction from stored block records.

The long format (participant, visit, level, metric, value) is the shape the
Phase-2 charts and the Phase-3 statistics engine both consume. Only observed
(non-null numeric) values are emitted.
"""

from __future__ import annotations

from typing import Any

from matb_integration.metrics_schema import long_metric_definition

# metric key -> (section, field) inside the log_converter record
_PATHS: dict[str, tuple[str, str]] = {
    "sysmon_dprime_observed_v2": ("sysmon", "dprime_observed_v2"),
    "sysmon_dprime_estimated_v1": ("sysmon", "dprime_estimated_v1"),
    "sysmon_d_prime": ("sysmon", "d_prime"),
    "sysmon_hit_rate": ("sysmon", "hit_rate"),
    "sysmon_mean_rt_ms": ("sysmon", "mean_rt_ms"),
    "track_rmse_deviation": ("track", "rmse_deviation"),
    "track_percent_time_in_target": ("track", "percent_time_in_target"),
    "resman_mean_absolute_deviation": ("resman", "mean_absolute_deviation"),
    "resman_percent_time_in_tolerance": ("resman", "percent_time_in_tolerance"),
    "comm_d_prime": ("comm", "d_prime"),
    "nasatlx_rtlx_mean_0_100": ("nasatlx", "rtlx_mean_0_100"),
    "nasatlx_legacy_sum_0_60": ("nasatlx", "legacy_subscale_sum_0_60"),
    "nasatlx_raw_tlx": ("nasatlx", "raw_tlx"),
    "bedford": ("bedford", "value"),
    "isa_mean": ("isa", "mean"),
}

METRIC_KEYS: tuple[str, ...] = tuple(_PATHS)

_LEGACY_ALIAS_VERSIONS = {
    "sysmon_d_prime": "1-legacy-alias",
    "nasatlx_raw_tlx": "1-legacy-alias",
}
_METADATA: dict[str, dict[str, Any]] = {}
for _metric_key in _PATHS:
    _definition = long_metric_definition(_metric_key)
    _METADATA[_metric_key] = {
        "metric_version": _LEGACY_ALIAS_VERSIONS.get(
            _metric_key, str(_definition["metric_version"])
        ),
        "confirmatory_eligible": bool(_definition["confirmatory_eligible"]),
    }


def extract_long_metrics(record: dict[str, Any]) -> list[tuple[str, float]]:
    """(metric, value) pairs for observed metrics; nulls/missing omitted."""
    out: list[tuple[str, float]] = []
    for key, (section, field) in _PATHS.items():
        value = (record.get(section) or {}).get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out.append((key, float(value)))
    return out


def metric_metadata(metric: str, record: dict[str, Any]) -> dict[str, Any]:
    """Return explicit version/eligibility provenance for a long metric."""
    metadata = dict(_METADATA[metric])
    if metric == "sysmon_dprime_observed_v2":
        metadata["confirmatory_eligible"] = bool(
            (record.get("sysmon") or {}).get("observed_confirmatory_eligible")
        )
    elif metric == "nasatlx_rtlx_mean_0_100":
        metadata["confirmatory_eligible"] = bool(
            (record.get("nasatlx") or {}).get("confirmatory_eligible")
        )
    metadata["metrics_schema_version"] = str(record.get("metrics_schema_version") or "1.0")
    return metadata
