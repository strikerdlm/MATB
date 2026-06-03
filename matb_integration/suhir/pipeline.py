"""End-to-end per-participant DEPDF fit.

Consumes block records (from log_converter.convert_session) plus their raw rows
(from log_converter.parse_csv), one each for LOW/MEDIUM/HIGH. Produces a fitted
parameter dict suitable for json.dump.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from matb_integration.suhir import hcf
from matb_integration.suhir.calibration import estimate_p0, estimate_tau0, solve_g0
from matb_integration.suhir.failure_events import failure_metrics, sysmon_failure_times
from matb_integration.suhir.mwl import absolute_mwl

_CRITERIA_PATH = Path(__file__).with_name("failure_criteria.yaml")


def _criteria_version() -> int:
    with open(_CRITERIA_PATH, encoding="utf-8") as fh:
        return int(yaml.safe_load(fh)["version"])


def fit_participant(
    participant_id: str,
    blocks: dict[str, tuple[dict[str, Any], list[dict[str, str]]]],
    source: str = "raw_tlx",
    hcf_store: dict[str, hcf.HCFEstimate] | None = None,
) -> dict[str, Any]:
    """Fit G0, P0, tau0 for one participant from LOW/MEDIUM/HIGH blocks.

    Args:
        participant_id: e.g. "P01".
        blocks: maps level name -> (record, raw_rows).
        source: MWL instrument for the calibration levels.
        hcf_store: optional external HCF estimates; absent -> F0 default.
    """
    levels: list[tuple[float, float]] = []
    per_level: dict[str, Any] = {}
    for name, (record, rows) in blocks.items():
        g = absolute_mwl(record, source)
        duration = float(record.get("scenario_time_max_s") or 0.0)
        metrics = failure_metrics(sysmon_failure_times(rows), duration)
        per_level[name] = {"mwl": g, **metrics}
        if metrics["mttf_s"] is not None:
            levels.append((g, metrics["mttf_s"]))

    if len(levels) < 3:
        raise ValueError(
            f"need 3 MWL levels with observed failures to fit; got {len(levels)}"
        )
    levels.sort(key=lambda x: x[0])
    g0 = solve_g0(levels)  # consumes all three levels internally
    (g1, t1), (g2, t2) = levels[0], levels[1]
    p0 = estimate_p0(g1, g2, t1, t2, g0=g0)
    tau0 = estimate_tau0(g1, t1, g0=g0, p0=p0)
    hcf_est = hcf.resolve(participant_id, store=hcf_store)

    return {
        "participant_id": participant_id,
        "mwl_source": source,
        "criteria_version": _criteria_version(),
        "g0": g0,
        "p0": p0,
        "tau0": tau0,
        "hcf_value": hcf_est.value,
        "hcf_source": hcf_est.source,
        "per_level": per_level,
    }
