"""Tidy long-format metric extraction from stored block records.

The long format (participant, visit, level, metric, value) is the shape the
Phase-2 charts and the Phase-3 statistics engine both consume. Only observed
(non-null numeric) values are emitted.
"""

from __future__ import annotations

from typing import Any

# metric key -> (section, field) inside the log_converter record
_PATHS: dict[str, tuple[str, str]] = {
    "sysmon_d_prime": ("sysmon", "d_prime"),
    "sysmon_hit_rate": ("sysmon", "hit_rate"),
    "sysmon_mean_rt_ms": ("sysmon", "mean_rt_ms"),
    "comm_d_prime": ("comm", "d_prime"),
    "nasatlx_raw_tlx": ("nasatlx", "raw_tlx"),
    "bedford": ("bedford", "value"),
    "isa_mean": ("isa", "mean"),
}

METRIC_KEYS: tuple[str, ...] = tuple(_PATHS)


def extract_long_metrics(record: dict[str, Any]) -> list[tuple[str, float]]:
    """(metric, value) pairs for observed metrics; nulls/missing omitted."""
    out: list[tuple[str, float]] = []
    for key, (section, field) in _PATHS.items():
        value = (record.get(section) or {}).get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out.append((key, float(value)))
    return out
