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
import io
import json
import math
import statistics
import re
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

# Spanish equivalents (Rolo-González et al., 2010; INSST NTP-544)
NASA_TLX_SUBSCALES_ES: tuple[str, ...] = (
    "Demanda mental",
    "Demanda física",
    "Demanda temporal",
    "Rendimiento",
    "Esfuerzo",
    "Frustración",
)

_ALL_NASA_TLX_SUBSCALES: frozenset[str] = frozenset(NASA_TLX_SUBSCALES + NASA_TLX_SUBSCALES_ES)

ISA_TITLE: str = "Workload"
ISA_TITLE_ES: str = "Carga de trabajo"
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


def _parse_csv_with_recovery(csv_path: Path) -> tuple[list[dict[str, str]], int]:
    raw_text = Path(csv_path).read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(raw_text, newline=""), strict=True)
    fieldnames = reader.fieldnames
    if (
        not fieldnames
        or any(name is None or not name.strip() for name in fieldnames)
        or len(set(fieldnames)) != len(fieldnames)
    ):
        raise ValueError("malformed_csv_header")
    rows: list[dict[str, str]] = []
    parsed_rows: list[tuple[dict[str | None, str | list[str] | None], int]] = []
    incomplete_final_rows = 0
    final_append_unterminated = bool(
        raw_text and not raw_text.endswith(("\n", "\r"))
    )
    physical_line_count = len(raw_text.splitlines())
    while True:
        record_start_line = reader.line_num + 1
        try:
            row = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            if (
                final_append_unterminated
                and record_start_line == physical_line_count
            ):
                incomplete_final_rows = 1
                break
            raise ValueError("malformed_csv_row") from exc
        parsed_rows.append((row, record_start_line))

    for index, (row, record_start_line) in enumerate(parsed_rows):
        malformed = any(key is None or value is None for key, value in row.items())
        if malformed:
            if (
                final_append_unterminated
                and index == len(parsed_rows) - 1
                and record_start_line == physical_line_count
            ):
                incomplete_final_rows = 1
                continue
            raise ValueError("malformed_csv_row")
        rows.append({str(key).strip(): str(value).strip() for key, value in row.items()})
    return rows, incomplete_final_rows


def _parse_csv(csv_path: Path) -> list[dict[str, str]]:
    rows, _incomplete_final_rows = _parse_csv_with_recovery(csv_path)
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
        and r.get("address") in (ISA_TITLE, ISA_TITLE_ES)
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
        and r.get("address") in _ALL_NASA_TLX_SUBSCALES
    ]

    # Accept both English and Spanish titles; normalise to English keys
    _ES_TO_EN: dict[str, str] = dict(zip(NASA_TLX_SUBSCALES_ES, NASA_TLX_SUBSCALES))
    subscales: dict[str, float | None] = {s: None for s in NASA_TLX_SUBSCALES}
    for r in tlx_rows:
        addr = r["address"]
        key = _ES_TO_EN.get(addr, addr)   # pass English through unchanged
        v = _float_or_none(r.get("value", ""))
        if v is not None and key in subscales:
            subscales[key] = round(v, 2)

    filled = [v for v in subscales.values() if v is not None]
    complete = len(filled) == len(NASA_TLX_SUBSCALES)
    raw_tlx = round(statistics.mean(filled), 4) if complete else None
    unweighted_sum = round(sum(filled), 4) if complete else None

    return {
        **{k.lower().replace(" ", "_"): v for k, v in subscales.items()},
        "raw_tlx": raw_tlx,
        "raw_tlx_method": "unweighted_mean_of_six_0_to_10",
        "unweighted_sum_0_60": unweighted_sum,
        "n_subscales_completed": len(filled),
        "complete": complete,
        "reason_code": None if complete else "incomplete_nasa_tlx",
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


def _sagat_metric(rows: list[dict], manifest_path: Path | None) -> dict:
    """Aggregate SAGAT probe rows into per-block JSONL output.

    rows: full row stream from one OpenMATB CSV session (post-block filtering done upstream).
    manifest_path: optional path to {participant}_block{N}_sagat_manifest.json. When
        present, freezes listed in the manifest but absent from the CSV are emitted
        with executed=False.
    """
    sagat_rows = [r for r in rows if r.get("module") == "sagat"]

    # Group consecutive 10-row probe blocks by freeze_id then probe order.
    # Each probe is exactly 10 rows: probe_id, sa_level, domain, question_text,
    # options_text, given_answer, correct_answer, is_correct, latency_sec, freeze_id.
    PROBE_FIELDS = (
        "probe_id", "sa_level", "domain", "question_text", "options_text",
        "given_answer", "correct_answer", "is_correct", "latency_sec", "freeze_id",
    )

    # Snapshot rows live alongside probe rows but use addresses starting "snapshot_".
    snapshot_by_freeze: dict[str, dict[str, str]] = {}
    pending_snapshot: dict[str, str] = {}

    probes_by_freeze: dict[str, list[dict]] = {}
    current_probe: dict[str, str] = {}
    for r in sagat_rows:
        addr = r["address"]
        val = r["value"]
        if addr.startswith("snapshot_"):
            pending_snapshot[addr[len("snapshot_"):]] = val
            continue
        if addr in PROBE_FIELDS:
            current_probe[addr] = val
            if addr == "freeze_id":  # last field — stash and reset
                freeze_id = val
                probes_by_freeze.setdefault(freeze_id, []).append(current_probe)
                if pending_snapshot and freeze_id not in snapshot_by_freeze:
                    snapshot_by_freeze[freeze_id] = pending_snapshot
                    pending_snapshot = {}
                current_probe = {}

    # Per-level counters
    level_counts = {1: [0, 0], 2: [0, 0], 3: [0, 0]}  # [correct, total]
    latencies: list[float] = []
    n_answered = 0
    n_timeout = 0
    freeze_details: list[dict] = []

    for freeze_id, probes in probes_by_freeze.items():
        detail_probes: list[dict] = []
        for p in probes:
            lvl = int(p["sa_level"])
            correct = p["is_correct"] == "True"
            given = p["given_answer"]
            timed_out = given == "TIMEOUT"
            try:
                latency = float(p["latency_sec"])
            except (KeyError, ValueError):
                latency = 0.0
            latencies.append(latency)
            if lvl not in level_counts:
                level_counts[lvl] = [0, 0]
            level_counts[lvl][1] += 1
            if correct:
                level_counts[lvl][0] += 1
            if timed_out:
                n_timeout += 1
            else:
                n_answered += 1
            detail_probes.append({
                "probe_id": p["probe_id"],
                "sa_level": lvl,
                "domain": p["domain"],
                "question": p["question_text"],
                "options": [o.strip() for o in p["options_text"].split("|")],
                "given_answer": given,
                "correct_answer": p["correct_answer"],
                "is_correct": correct,
                "latency_sec": latency,
            })
        freeze_details.append({
            "freeze_id": freeze_id,
            "executed": True,
            "snapshot": snapshot_by_freeze.get(freeze_id, {}),
            "probes": detail_probes,
        })

    # Manifest cross-check
    n_freezes_planned = len(freeze_details)
    if manifest_path is not None and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        planned_ids = [f["freeze_id"] for f in manifest["freezes"]]
        executed_ids = {f["freeze_id"] for f in freeze_details}
        # Re-emit in manifest order, marking missing ones as executed=False
        ordered: list[dict] = []
        executed_lookup = {f["freeze_id"]: f for f in freeze_details}
        for planned_freeze in manifest["freezes"]:
            fid = planned_freeze["freeze_id"]
            if fid in executed_ids:
                d = executed_lookup[fid]
                d["scenario_time_sec"] = planned_freeze["scenario_time_sec"]
                ordered.append(d)
            else:
                ordered.append({
                    "freeze_id": fid,
                    "scenario_time_sec": planned_freeze["scenario_time_sec"],
                    "executed": False,
                    "snapshot": {},
                    "probes": [],
                })
        freeze_details = ordered
        n_freezes_planned = len(planned_ids)
    n_freezes_executed = sum(1 for d in freeze_details if d.get("executed"))

    def _pct(lvl: int) -> float:
        correct, total = level_counts.get(lvl, [0, 0])
        return round(100.0 * correct / total, 1) if total else 0.0

    n_total = sum(t for c, t in level_counts.values())
    total_correct = sum(c for c, t in level_counts.values())

    return {
        "n_freezes_planned": n_freezes_planned,
        "n_freezes_executed": n_freezes_executed,
        "n_probes_total": n_total,
        "n_probes_answered": n_answered,
        "n_probes_timeout": n_timeout,
        "sa_score_level_1_pct": _pct(1),
        "sa_score_level_2_pct": _pct(2),
        "sa_score_level_3_pct": _pct(3),
        "sa_score_overall_pct": round(100.0 * total_correct / n_total, 1) if n_total else 0.0,
        "mean_latency_sec": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "freeze_details": freeze_details,
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


def _bool_or_none(value: str) -> bool | None:
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "1.0"}:
        return True
    if normalized in {"false", "0", "0.0"}:
        return False
    return None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _tracking_metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Aggregate OpenMATB pursuit-tracking performance samples."""

    performance = [
        row
        for row in rows
        if row.get("type") == "performance" and row.get("module") == "track"
    ]
    target_samples = [
        value
        for row in performance
        if row.get("address") == "cursor_in_target"
        and (value := _bool_or_none(row.get("value", ""))) is not None
    ]
    deviations = [
        abs(value)
        for row in performance
        if row.get("address") == "center_deviation"
        and (value := _float_or_none(row.get("value", ""))) is not None
    ]
    recoveries = [
        value
        for row in performance
        if row.get("address") == "response_time"
        and (value := _float_or_none(row.get("value", ""))) is not None
    ]
    in_target = sum(target_samples)
    return {
        "n_samples": len(target_samples),
        "in_target_count": in_target,
        "in_target_pct": 100.0 * in_target / len(target_samples)
        if target_samples
        else None,
        "n_deviation_samples": len(deviations),
        "mean_center_deviation": statistics.mean(deviations)
        if deviations
        else None,
        "rms_center_deviation": math.sqrt(
            statistics.mean(value * value for value in deviations)
        )
        if deviations
        else None,
        "p95_center_deviation": _percentile(deviations, 0.95)
        if deviations
        else None,
        "n_recoveries": len(recoveries),
        "mean_recovery_rt_ms": round(statistics.mean(recoveries), 2)
        if recoveries
        else None,
    }


_RESMAN_ADDRESS = re.compile(r"^([a-z])_(in_tolerance|deviation|response_time)$")


def _resman_metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Aggregate target-tank tolerance, deviation, and recovery measures."""

    by_tank: dict[str, dict[str, list[Any]]] = {}
    for row in rows:
        if row.get("type") != "performance" or row.get("module") != "resman":
            continue
        match = _RESMAN_ADDRESS.fullmatch(row.get("address", ""))
        if match is None:
            continue
        tank, measure = match.groups()
        values = by_tank.setdefault(
            tank,
            {"in_tolerance": [], "deviation": [], "response_time": []},
        )
        if measure == "in_tolerance":
            parsed: Any = _bool_or_none(row.get("value", ""))
        else:
            parsed = _float_or_none(row.get("value", ""))
        if parsed is not None:
            values[measure].append(parsed)

    tank_metrics: dict[str, dict[str, Any]] = {}
    all_tolerance: list[bool] = []
    all_deviations: list[float] = []
    all_recoveries: list[float] = []
    for tank in sorted(by_tank):
        values = by_tank[tank]
        tolerance = [bool(value) for value in values["in_tolerance"]]
        deviations = [abs(float(value)) for value in values["deviation"]]
        recoveries = [float(value) for value in values["response_time"]]
        all_tolerance.extend(tolerance)
        all_deviations.extend(deviations)
        all_recoveries.extend(recoveries)
        tank_metrics[tank] = {
            "n_tolerance_samples": len(tolerance),
            "in_tolerance_pct": 100.0 * sum(tolerance) / len(tolerance)
            if tolerance
            else None,
            "n_deviation_samples": len(deviations),
            "mean_abs_deviation": statistics.mean(deviations)
            if deviations
            else None,
            "rms_deviation": math.sqrt(
                statistics.mean(value * value for value in deviations)
            )
            if deviations
            else None,
            "max_abs_deviation": max(deviations) if deviations else None,
            "n_recoveries": len(recoveries),
            "mean_recovery_rt_ms": round(statistics.mean(recoveries), 2)
            if recoveries
            else None,
        }

    combined = {
        "n_tolerance_samples": len(all_tolerance),
        "in_tolerance_pct": 100.0 * sum(all_tolerance) / len(all_tolerance)
        if all_tolerance
        else None,
        "n_deviation_samples": len(all_deviations),
        "mean_abs_deviation": statistics.mean(all_deviations)
        if all_deviations
        else None,
        "rms_deviation": math.sqrt(
            statistics.mean(value * value for value in all_deviations)
        )
        if all_deviations
        else None,
        "max_abs_deviation": max(all_deviations)
        if all_deviations
        else None,
        "n_recoveries": len(all_recoveries),
        "mean_recovery_rt_ms": round(statistics.mean(all_recoveries), 2)
        if all_recoveries
        else None,
    }
    return {"tanks": tank_metrics, "combined": combined}


def _activity_metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Count preserved task activity without inventing a composite score."""

    def counts(row_type: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for row in rows:
            if row.get("type") != row_type:
                continue
            module = row.get("module", "") or "unknown"
            result[module] = result.get(module, 0) + 1
        return dict(sorted(result.items()))

    return {
        "total_rows": len(rows),
        "event_count": sum(row.get("type") == "event" for row in rows),
        "input_count": sum(row.get("type") == "input" for row in rows),
        "performance_row_count": sum(
            row.get("type") == "performance" for row in rows
        ),
        "state_row_count": sum(row.get("type") == "state" for row in rows),
        "events_by_module": counts("event"),
        "inputs_by_module": counts("input"),
    }


def convert_session(
    csv_path: Path,
    participant_id: str = "unknown",
    block_name: str = "block_0",
    workload_level: str = "UNKNOWN",
    alerttimeout_sec: float = SYSMON_ALERTTIMEOUT_SEC,
    sysmon_n_indicators: int = SYSMON_N_INDICATORS,
    extra_metadata: dict[str, Any] | None = None,
    sagat_manifest_dir: Path | None = None,
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
        sagat_manifest_dir: Optional directory to search for the SAGAT manifest JSON.
            When set, searched first. Falls back to csv_path.parent, then to the
            repo-owned questionnaire asset directory used by generated fixtures.

    Returns:
        Dict suitable for json.dumps() as one JSONL line.
    """
    rows, incomplete_final_rows = _parse_csv_with_recovery(csv_path)

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
        "csv_path": Path(csv_path).name,
        "source_recovery": {
            "incomplete_final_csv_rows_ignored": incomplete_final_rows,
            "warning_codes": (
                ["incomplete_final_csv_row_ignored"] if incomplete_final_rows else []
            ),
        },
        "n_rows": len(rows),
        "scenario_time_min_s": t_min,
        "scenario_time_max_s": t_max,
        "sysmon": _sysmon_metrics(rows, alerttimeout_sec, sysmon_n_indicators, duration),
        "isa": _isa_metrics(rows),
        "nasatlx": _nasatlx_metrics(rows),
        "bedford": _bedford_metric(rows),
        "comm": _comm_metrics(rows),
        "tracking": _tracking_metrics(rows),
        "resource_management": _resman_metrics(rows),
        "activity": _activity_metrics(rows),
    }

    # Locate optional SAGAT manifest. Search order:
    #   1. Explicit sagat_manifest_dir parameter, if given.
    #   2. csv_path.parent (e.g. when manifest is co-located with the CSV).
    #   3. Repo-owned questionnaire assets directory (for generated fixtures).
    sagat_manifest_path: Path | None = None
    search_dirs: list[Path] = []
    if sagat_manifest_dir is not None:
        search_dirs.append(Path(sagat_manifest_dir))
    if hasattr(csv_path, "parent"):
        search_dirs.append(csv_path.parent)
    repo_root = Path(__file__).resolve().parents[1]
    search_dirs.append(repo_root / "matb_integration" / "questionnaires")
    for d in search_dirs:
        candidates = list(d.glob("*_sagat_manifest.json"))
        if candidates:
            sagat_manifest_path = candidates[0]
            break
    record["sagat"] = _sagat_metric(rows, manifest_path=sagat_manifest_path)

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
