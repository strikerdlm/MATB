"""
matb_integration/log_converter.py

Parse an OpenMATB v1.4.5 session CSV and convert it to a structured dict
(one JSONL record per block/session).

CSV columns: logtime, scenario_time, type, module, address, value

Row types this converter consumes:

    performance | sysmon          | signal_detection  | HIT / MISS / FA
    performance | sysmon          | response_time     | <float ms or nan>
    performance | sysmon          | name              | <indicator e.g. F5>
    performance | genericscales   | Workload          | <float 1.0–5.0>  (ISA probe)
    performance | genericscales   | <subscale title>  | <float 0.0–10.0> (NASA-TLX)
    performance | communications  | sdt_value         | HIT / MISS / FA / CR
    performance | communications  | response_time     | <float ms or nan>
    performance | communications  | response_was_needed | 0 / 1
    event       | genericscales   | self              | start  (probe fires)
    event       | sysmon          | *-failure         | 1      (failure event)
"""

from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any

NASA_TLX_SUBSCALES: tuple[str, ...] = (
    "Mental demand",
    "Physical demand",
    "Time pressure",
    "Performance",
    "Effort",
    "Frustration",
)

ISA_TITLE: str = "Workload"
BEDFORD_TITLE: str = "Bedford"
SYSMON_N_INDICATORS: int = 6   # 2 lights + 4 scales (OpenMATB default)
SYSMON_ALERTTIMEOUT_SEC: float = 10.0   # OpenMATB default alerttimeout


def _norm_ppf(p: float) -> float:
    """Probit function — inverse standard normal CDF.

    Rational approximation by Peter Acklam (max error < 1.15e-9).
    No external dependencies.
    """
    p = max(1e-9, min(1 - 1e-9, p))

    a = (-3.969683028665376e+01,  2.209460984245205e+02,
         -2.759285104469687e+02,  1.383577518672690e+02,
         -3.066479806614716e+01,  2.506628277459239e+00)
    b = (-5.447609879822406e+01,  1.615858368580409e+02,
         -1.556989798598866e+02,  6.680131188771972e+01,
         -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01,
         -2.400758277161838e+00, -2.549732539343734e+00,
          4.374664141464968e+00,  2.938163982698783e+00)
    d = ( 7.784695709041462e-03,  3.224671290700398e-01,
          2.445134137142996e+00,  3.754408661907416e+00)

    p_low, p_high = 0.02425, 1 - 0.02425

    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    elif p <= p_high:
        q = p - 0.5
        r = q * q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    else:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def _d_prime(n_hits: int, n_misses: int, n_fa: int, n_cr: int) -> float | None:
    """d' with Hautus (2004) log-linear correction. Returns None when undefined."""
    n_signals = n_hits + n_misses
    n_noise = n_fa + n_cr
    if n_signals == 0 or n_noise == 0:
        return None
    # Hautus: add 0.5 / add 1 to avoid boundary rates
    h = (n_hits + 0.5) / (n_signals + 1)
    f = (n_fa + 0.5) / (n_noise + 1)
    return round(_norm_ppf(h) - _norm_ppf(f), 4)


def _parse_csv(csv_path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with open(csv_path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({k.strip(): v.strip() for k, v in row.items()})
    return rows


def _float_or_none(s: str) -> float | None:
    try:
        v = float(s)
        return None if math.isnan(v) else v
    except (ValueError, TypeError):
        return None


def _sysmon_metrics(
    rows: list[dict[str, str]],
    alerttimeout_sec: float = SYSMON_ALERTTIMEOUT_SEC,
    n_indicators: int = SYSMON_N_INDICATORS,
    scenario_duration_sec: float | None = None,
) -> dict[str, Any]:
    perf = [r for r in rows
            if r.get("type") == "performance" and r.get("module") == "sysmon"]

    det = [r for r in perf if r.get("address") == "signal_detection"]
    rt_rows = [r for r in perf if r.get("address") == "response_time"]

    n_hits  = sum(1 for r in det if r.get("value", "").upper() == "HIT")
    n_misses = sum(1 for r in det if r.get("value", "").upper() == "MISS")
    n_fa    = sum(1 for r in det if r.get("value", "").upper() == "FA")
    n_signals = n_hits + n_misses

    hit_rate = (n_hits / n_signals) if n_signals > 0 else None

    rt_values = [v for r in rt_rows if (v := _float_or_none(r.get("value", ""))) is not None]
    mean_rt = round(statistics.mean(rt_values), 2) if rt_values else None

    # Correct rejections: estimated from scenario duration and alerttimeout
    d_prime: float | None = None
    n_cr: int | None = None
    if scenario_duration_sec is not None and scenario_duration_sec > 0:
        n_noise_intervals = math.floor(
            scenario_duration_sec * n_indicators / alerttimeout_sec
        ) - n_signals
        n_cr = max(0, n_noise_intervals - n_fa)
        d_prime = _d_prime(n_hits, n_misses, n_fa, n_cr)

    return {
        "n_hits": n_hits,
        "n_misses": n_misses,
        "n_false_alarms": n_fa,
        "n_signals": n_signals,
        "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
        "d_prime": d_prime,
        "n_correct_rejections": n_cr,
        "mean_rt_ms": mean_rt,
    }


def _isa_metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    isa_rows = [
        r for r in rows
        if r.get("type") == "performance"
        and r.get("module") == "genericscales"
        and r.get("address") == ISA_TITLE
    ]

    probes: list[dict[str, Any]] = []
    for r in isa_rows:
        t = _float_or_none(r.get("scenario_time", ""))
        v = _float_or_none(r.get("value", ""))
        if v is not None:
            probes.append({"scenario_time": round(t, 3) if t is not None else None, "value": round(v, 2)})

    values = [p["value"] for p in probes]
    return {
        "n_probes_completed": len(values),
        "probes": probes,
        "mean": round(statistics.mean(values), 4) if values else None,
        "sd": round(statistics.stdev(values), 4) if len(values) > 1 else None,
    }


def _nasatlx_metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    tlx_rows = [
        r for r in rows
        if r.get("type") == "performance"
        and r.get("module") == "genericscales"
        and r.get("address") in NASA_TLX_SUBSCALES
    ]

    subscales: dict[str, float | None] = {s: None for s in NASA_TLX_SUBSCALES}
    for r in tlx_rows:
        v = _float_or_none(r.get("value", ""))
        if v is not None:
            subscales[r["address"]] = round(v, 2)

    filled = [v for v in subscales.values() if v is not None]
    raw_tlx = round(sum(filled), 4) if filled else None

    return {
        **{k.lower().replace(" ", "_"): v for k, v in subscales.items()},
        "raw_tlx": raw_tlx,
        "n_subscales_completed": len(filled),
    }


def _bedford_metric(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Extract Bedford workload rating (1–10, post-block).

    The genericscales slider stores a float in [1, 10]; round to nearest integer
    for the standard Bedford scale value.
    """
    bedford_rows = [
        r for r in rows
        if r.get("type") == "performance"
        and r.get("module") == "genericscales"
        and r.get("address") == BEDFORD_TITLE
    ]

    if not bedford_rows:
        return {"value": None, "value_raw": None}

    # Take the last row if multiple (shouldn't happen, but defensive)
    r = bedford_rows[-1]
    raw = _float_or_none(r.get("value", ""))
    return {
        "value": round(raw) if raw is not None else None,
        "value_raw": round(raw, 2) if raw is not None else None,
    }


def _comm_metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    perf = [r for r in rows
            if r.get("type") == "performance" and r.get("module") == "communications"]

    sdt_rows = [r for r in perf if r.get("address") == "sdt_value"]
    rt_rows  = [r for r in perf if r.get("address") == "response_time"]

    n_hits   = sum(1 for r in sdt_rows if r.get("value", "").upper() == "HIT")
    n_misses = sum(1 for r in sdt_rows if r.get("value", "").upper() == "MISS")
    n_fa     = sum(1 for r in sdt_rows if r.get("value", "").upper() == "FA")
    n_cr     = sum(1 for r in sdt_rows if r.get("value", "").upper() == "CR")
    n_signals = n_hits + n_misses
    n_noise   = n_fa + n_cr

    hit_rate = (n_hits / n_signals) if n_signals > 0 else None
    fa_rate  = (n_fa / n_noise) if n_noise > 0 else None

    rt_values = [v for r in rt_rows if (v := _float_or_none(r.get("value", ""))) is not None]
    mean_rt = round(statistics.mean(rt_values), 2) if rt_values else None

    return {
        "n_hits": n_hits,
        "n_misses": n_misses,
        "n_false_alarms": n_fa,
        "n_correct_rejections": n_cr,
        "n_signals": n_signals,
        "n_noise_trials": n_noise,
        "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
        "fa_rate": round(fa_rate, 4) if fa_rate is not None else None,
        "d_prime": _d_prime(n_hits, n_misses, n_fa, n_cr),
        "mean_rt_ms": mean_rt,
    }


def convert_session(
    csv_path: Path,
    participant_id: str = "unknown",
    block_name: str = "block_0",
    workload_level: str = "UNKNOWN",
    alerttimeout_sec: float = SYSMON_ALERTTIMEOUT_SEC,
    sysmon_n_indicators: int = SYSMON_N_INDICATORS,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert one OpenMATB session CSV to a structured dict (one JSONL record).

    Args:
        csv_path: Path to OpenMATB session CSV.
        participant_id: Participant identifier (e.g. "P01").
        block_name: Block label (e.g. "low_workload").
        workload_level: LOW / MEDIUM / HIGH / UNKNOWN.
        alerttimeout_sec: SYSMON alerttimeout in seconds (used for d' estimation).
        sysmon_n_indicators: Number of SYSMON indicators (lights + scales, default 6).
        extra_metadata: Additional fields merged into the top-level output dict.

    Returns:
        Dict suitable for json.dumps() as one JSONL line.
    """
    rows = parse_csv(csv_path)

    scenario_times: list[float] = [
        v for r in rows
        if (v := _float_or_none(r.get("scenario_time", ""))) is not None
    ]
    t_min = round(min(scenario_times), 3) if scenario_times else None
    t_max = round(max(scenario_times), 3) if scenario_times else None
    duration = (t_max - (t_min or 0.0)) if t_max is not None else None

    record: dict[str, Any] = {
        "participant_id": participant_id,
        "block_name": block_name,
        "workload_level": workload_level,
        "csv_path": str(csv_path),
        "n_rows": len(rows),
        "scenario_time_min_s": t_min,
        "scenario_time_max_s": t_max,
        "sysmon": _sysmon_metrics(rows, alerttimeout_sec, sysmon_n_indicators, duration),
        "isa": _isa_metrics(rows),
        "nasatlx": _nasatlx_metrics(rows),
        "bedford": _bedford_metric(rows),
        "comm": _comm_metrics(rows),
    }

    if extra_metadata:
        record.update(extra_metadata)

    return record


# Public alias consistent with tests
parse_csv = _parse_csv


def convert_to_jsonl(
    csv_path: Path,
    output_path: Path | None = None,
    **kwargs: Any,
) -> str:
    """Convert one session CSV to a JSONL line. Optionally appends to a file.

    Args:
        csv_path: OpenMATB session CSV.
        output_path: If provided, append the JSONL record to this file.
        **kwargs: Forwarded to convert_session().

    Returns:
        The JSON string (one line, no trailing newline).
    """
    record = convert_session(csv_path, **kwargs)
    line = json.dumps(record, ensure_ascii=False)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    return line


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert an OpenMATB session CSV to a structured JSONL record."
    )
    parser.add_argument("csv", type=Path, help="OpenMATB session CSV file")
    parser.add_argument("--participant", default="P00", metavar="ID", help="Participant ID")
    parser.add_argument("--block", default="block_0", help="Block name")
    parser.add_argument(
        "--level", default="UNKNOWN", choices=["LOW", "MEDIUM", "HIGH", "UNKNOWN"],
        help="Workload level"
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Append output to this JSONL file"
    )
    parser.add_argument(
        "--alerttimeout", type=float, default=SYSMON_ALERTTIMEOUT_SEC,
        help=f"SYSMON alerttimeout in seconds (default: {SYSMON_ALERTTIMEOUT_SEC})"
    )
    args = parser.parse_args()

    line = convert_to_jsonl(
        csv_path=args.csv,
        output_path=args.output,
        participant_id=args.participant,
        block_name=args.block,
        workload_level=args.level,
        alerttimeout_sec=args.alerttimeout,
    )
    print(line)
