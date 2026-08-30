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

from matb_integration.metrics_schema import METRICS_SCHEMA_VERSION

NASA_TLX_SUBSCALES: tuple[str, ...] = (
    "Mental demand",
    "Physical demand",
    "Time pressure",
    "Performance",
    "Effort",
    "Frustration",
)

# OpenMATB's tracked full questionnaire uses "Time pressure", while the
# integration/short forms use the standard dimension label "Temporal demand".
# Keep the historical output key (`time_pressure`) but accept both source labels.
NASA_TLX_SUBSCALE_ALIASES: dict[str, str] = {
    "Temporal demand": "Time pressure",
}

# Spanish equivalents (Rolo-González et al., 2010; INSST NTP-544)
NASA_TLX_SUBSCALES_ES: tuple[str, ...] = (
    "Demanda mental",
    "Demanda física",
    "Demanda temporal",
    "Rendimiento",
    "Esfuerzo",
    "Frustración",
)

_ALL_NASA_TLX_SUBSCALES: frozenset[str] = frozenset(
    NASA_TLX_SUBSCALES + NASA_TLX_SUBSCALES_ES + tuple(NASA_TLX_SUBSCALE_ALIASES)
)

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


def _parse_csv(csv_path: Path) -> list[dict[str, str]]:
    raw = Path(csv_path).read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Historical Windows/OpenMATB exports and investigator-created fixtures
        # may use the active ANSI code page.  cp1252 is deliberately the only
        # fallback: it is deterministic and covers the Spanish questionnaire
        # labels used by this project.  Other encodings fail rather than being
        # guessed silently.
        text = raw.decode("cp1252")
    rows: list[dict[str, str]] = []
    reader = csv.DictReader(text.splitlines())
    for row in reader:
        rows.append({k.strip(): v.strip() for k, v in row.items()})
    return rows


def _float_or_none(s: str) -> float | None:
    try:
        v = float(s)
        return None if math.isnan(v) else v
    except (ValueError, TypeError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    return None


def _summary(values: list[float]) -> dict[str, float | int | None]:
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 4) if values else None,
        "median": round(statistics.median(values), 4) if values else None,
        "sd": round(statistics.stdev(values), 4) if len(values) > 1 else None,
    }


def _track_metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    perf = [r for r in rows if r.get("type") == "performance" and r.get("module") == "track"]
    deviations = [
        value for row in perf
        if row.get("address") == "center_deviation"
        and (value := _float_or_none(row.get("value", ""))) is not None
    ]
    target_states = [
        value for row in perf
        if row.get("address") == "cursor_in_target"
        and (value := _bool_or_none(row.get("value"))) is not None
    ]
    recovery_times = [
        value for row in perf
        if row.get("address") == "response_time"
        and (value := _float_or_none(row.get("value", ""))) is not None
    ]
    return {
        "n_samples": len(deviations),
        "mean_absolute_deviation": round(statistics.mean(abs(v) for v in deviations), 4) if deviations else None,
        "rmse_deviation": round(math.sqrt(statistics.mean(v * v for v in deviations)), 4) if deviations else None,
        "percent_time_in_target": round(100 * sum(target_states) / len(target_states), 4) if target_states else None,
        "recovery_time_ms": _summary(recovery_times),
        "measurement_basis": "observed_runtime_samples",
        "confirmatory_eligible": bool(deviations and target_states),
    }


def _resman_metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    perf = [r for r in rows if r.get("type") == "performance" and r.get("module") == "resman"]
    deviations: list[float] = []
    tolerance_states: list[bool] = []
    recovery_times: list[float] = []
    by_tank_values: dict[str, dict[str, list[Any]]] = {}
    for row in perf:
        address = row.get("address", "")
        tank = address.split("_", 1)[0] if "_" in address else "unknown"
        bucket = by_tank_values.setdefault(tank, {"deviations": [], "tolerance": [], "recovery": []})
        if address.endswith("_deviation"):
            value = _float_or_none(row.get("value", ""))
            if value is not None:
                deviations.append(value)
                bucket["deviations"].append(value)
        elif address.endswith("_in_tolerance"):
            state = _bool_or_none(row.get("value"))
            if state is not None:
                tolerance_states.append(state)
                bucket["tolerance"].append(state)
        elif address.endswith("_response_time"):
            value = _float_or_none(row.get("value", ""))
            if value is not None:
                recovery_times.append(value)
                bucket["recovery"].append(value)

    by_tank: dict[str, Any] = {}
    for tank, values in by_tank_values.items():
        tank_deviations = values["deviations"]
        tank_tolerance = values["tolerance"]
        by_tank[tank] = {
            "n_samples": len(tank_deviations),
            "mean_absolute_deviation": round(statistics.mean(abs(v) for v in tank_deviations), 4)
            if tank_deviations else None,
            "percent_time_in_tolerance": round(100 * sum(tank_tolerance) / len(tank_tolerance), 4)
            if tank_tolerance else None,
            "recovery_time_ms": _summary(values["recovery"]),
        }
    return {
        "n_samples": len(deviations),
        "mean_absolute_deviation": round(statistics.mean(abs(v) for v in deviations), 4) if deviations else None,
        "rmse_deviation": round(math.sqrt(statistics.mean(v * v for v in deviations)), 4) if deviations else None,
        "percent_time_in_tolerance": round(100 * sum(tolerance_states) / len(tolerance_states), 4)
        if tolerance_states else None,
        "recovery_time_ms": _summary(recovery_times),
        "by_tank": by_tank,
        "measurement_basis": "observed_runtime_samples",
        "confirmatory_eligible": bool(deviations and tolerance_states),
    }


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

    # Legacy estimate retained verbatim for historical reproducibility. It is
    # not confirmatory-eligible because non-target opportunities were not
    # observed by the v1 runtime.
    d_prime_estimated: float | None = None
    n_cr_estimated: int | None = None
    if scenario_duration_sec is not None and scenario_duration_sec > 0:
        n_noise_intervals = math.floor(
            scenario_duration_sec * n_indicators / alerttimeout_sec
        ) - n_signals
        n_cr_estimated = max(0, n_noise_intervals - n_fa)
        d_prime_estimated = _d_prime(n_hits, n_misses, n_fa, n_cr_estimated)

    observed_outcomes: dict[str, tuple[bool, str]] = {}
    opportunity_issues: list[str] = []
    for row in perf:
        if row.get("address") != "opportunity":
            continue
        try:
            payload = json.loads(row.get("value", ""))
        except (json.JSONDecodeError, TypeError):
            opportunity_issues.append("invalid_json")
            continue
        if not isinstance(payload, dict) or payload.get("phase") != "closed":
            continue
        opportunity_id = str(payload.get("opportunity_id") or "").strip()
        target = payload.get("target")
        outcome = str(payload.get("outcome") or "").upper()
        if not opportunity_id or not isinstance(target, bool):
            opportunity_issues.append("missing_id_or_target")
            continue
        allowed = {"HIT", "MISS"} if target else {"FA", "CR"}
        if outcome not in allowed:
            opportunity_issues.append(f"invalid_outcome:{opportunity_id}")
            continue
        if opportunity_id in observed_outcomes:
            opportunity_issues.append(f"duplicate_outcome:{opportunity_id}")
            continue
        observed_outcomes[opportunity_id] = (target, outcome)

    observed_hits = sum(1 for target, outcome in observed_outcomes.values() if target and outcome == "HIT")
    observed_misses = sum(1 for target, outcome in observed_outcomes.values() if target and outcome == "MISS")
    observed_fa = sum(1 for target, outcome in observed_outcomes.values() if not target and outcome == "FA")
    observed_cr = sum(1 for target, outcome in observed_outcomes.values() if not target and outcome == "CR")
    observed_targets = observed_hits + observed_misses
    observed_nontargets = observed_fa + observed_cr
    if opportunity_issues:
        observed_status = "invalid"
        dprime_observed = None
    elif not observed_outcomes:
        observed_status = "unavailable"
        dprime_observed = None
    elif observed_targets == 0 or observed_nontargets == 0:
        observed_status = "insufficient_classes"
        dprime_observed = None
    else:
        observed_status = "complete"
        dprime_observed = _d_prime(observed_hits, observed_misses, observed_fa, observed_cr)

    return {
        "n_hits": n_hits,
        "n_misses": n_misses,
        "n_false_alarms": n_fa,
        "n_signals": n_signals,
        "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
        "d_prime": d_prime_estimated,
        "dprime_estimated_v1": d_prime_estimated,
        "n_correct_rejections": n_cr_estimated,
        "n_correct_rejections_estimated": n_cr_estimated,
        "estimated_measurement_basis": "estimated_duration_windows",
        "estimated_confirmatory_eligible": False,
        "dprime_observed_v2": dprime_observed,
        "observed_n_hits": observed_hits,
        "observed_n_misses": observed_misses,
        "observed_n_false_alarms": observed_fa,
        "observed_n_correct_rejections": observed_cr,
        "n_observed_target_opportunities": observed_targets,
        "n_observed_nontarget_opportunities": observed_nontargets,
        "observed_opportunity_status": observed_status,
        "observed_opportunity_issues": opportunity_issues,
        "observed_measurement_basis": "observed_protocol_defined_opportunities",
        "observed_confirmatory_eligible": observed_status == "complete",
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
        key = _ES_TO_EN.get(addr, NASA_TLX_SUBSCALE_ALIASES.get(addr, addr))
        v = _float_or_none(r.get("value", ""))
        if v is not None and key in subscales:
            subscales[key] = round(v, 2)

    filled = [v for v in subscales.values() if v is not None]
    legacy_sum = round(sum(filled), 4) if filled else None
    invalid_subscales = [
        key.lower().replace(" ", "_")
        for key, value in subscales.items()
        if value is not None and not 0 <= value <= 10
    ]
    complete = len(filled) == len(NASA_TLX_SUBSCALES) and not invalid_subscales
    rtlx_mean_0_10 = round(statistics.mean(filled), 4) if complete else None
    rtlx_mean_0_100 = round(rtlx_mean_0_10 * 10, 4) if rtlx_mean_0_10 is not None else None

    return {
        **{k.lower().replace(" ", "_"): v for k, v in subscales.items()},
        # Deprecated compatibility field. Its v1 semantics remain unchanged.
        "raw_tlx": legacy_sum,
        "legacy_subscale_sum_0_60": legacy_sum,
        "rtlx_mean_0_10": rtlx_mean_0_10,
        "rtlx_mean_0_100": rtlx_mean_0_100,
        "weighted_tlx_0_100": None,
        "weighted_tlx_available": False,
        "complete": complete,
        "invalid_subscales": invalid_subscales,
        "measurement_basis": "observed_complete_questionnaire" if complete else "incomplete_or_invalid_questionnaire",
        "confirmatory_eligible": complete,
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
    rows = parse_csv(csv_path)

    scenario_times: list[float] = [
        v for r in rows
        if (v := _float_or_none(r.get("scenario_time", ""))) is not None
    ]
    t_min = round(min(scenario_times), 3) if scenario_times else None
    t_max = round(max(scenario_times), 3) if scenario_times else None
    duration = (t_max - (t_min or 0.0)) if t_max is not None else None

    record: dict[str, Any] = {
        "metrics_schema_version": METRICS_SCHEMA_VERSION,
        "metric_deprecations": {
            "nasatlx.raw_tlx": "use nasatlx.rtlx_mean_0_100; raw_tlx preserves the legacy partial sum",
            "sysmon.d_prime": "use sysmon.dprime_observed_v2 when complete observed opportunities exist",
        },
        "participant_id": participant_id,
        "block_name": block_name,
        "workload_level": workload_level,
        "csv_path": str(csv_path),
        "n_rows": len(rows),
        "scenario_time_min_s": t_min,
        "scenario_time_max_s": t_max,
        "sysmon": _sysmon_metrics(rows, alerttimeout_sec, sysmon_n_indicators, duration),
        "track": _track_metrics(rows),
        "resman": _resman_metrics(rows),
        "isa": _isa_metrics(rows),
        "nasatlx": _nasatlx_metrics(rows),
        "bedford": _bedford_metric(rows),
        "comm": _comm_metrics(rows),
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
