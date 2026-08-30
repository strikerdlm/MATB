"""MWL normalization from log_converter records.

G0 is anchored within-participant to their LOW block (Suhir's comparative,
not absolute, framing). `source` selects which workload instrument supplies G,
enabling the normalization sensitivity analysis (spec §10).
"""

from __future__ import annotations

from typing import Any

DEFAULT_MWL_SOURCE = "rtlx_mean_0_100"

_SOURCES = {
    "rtlx_mean_0_100": lambda rec: rec["nasatlx"]["rtlx_mean_0_100"],
    # Compatibility-only v1 source: sum of available native 0-10 subscales.
    # It is not the standard Raw TLX and may be based on an incomplete form.
    "raw_tlx": lambda rec: rec["nasatlx"]["raw_tlx"],
    "isa_mean": lambda rec: rec["isa"]["mean"],
    "bedford": lambda rec: rec["bedford"]["value"],
}


def absolute_mwl(record: dict[str, Any], source: str = DEFAULT_MWL_SOURCE) -> float:
    """Scalar absolute MWL G from one block record for the chosen instrument."""
    if source not in _SOURCES:
        raise ValueError(f"unknown MWL source {source!r}; choose from {sorted(_SOURCES)}")
    value = _SOURCES[source](record)
    if value is None:
        raise ValueError(f"MWL source {source!r} is missing/None in record")
    return float(value)


def mwl_ratio(
    record: dict[str, Any],
    baseline: dict[str, Any],
    source: str = DEFAULT_MWL_SOURCE,
) -> float:
    """Dimensionless G/G0, anchored to the participant's baseline (LOW) block."""
    g = absolute_mwl(record, source)
    g0 = absolute_mwl(baseline, source)
    if g0 <= 0:
        raise ValueError("baseline MWL must be positive to form a ratio")
    return g / g0


def isa_timeseries(record: dict[str, Any]) -> list[tuple[float, float]]:
    """Time-resolved MWL G(t) from ISA probes, sorted by scenario time."""
    probes = record.get("isa", {}).get("probes", []) or []
    pairs = [
        (float(p["scenario_time"]), float(p["value"]))
        for p in probes
        if p.get("scenario_time") is not None and p.get("value") is not None
    ]
    return sorted(pairs, key=lambda x: x[0])
