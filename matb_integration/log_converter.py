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
import re
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

LEGACY_CSV_SOURCE_STATUS = (
    "legacy_csv_derived_not_reconciled_to_authoritative_event_stream"
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
CSV_COLUMNS: tuple[str, ...] = (
    "logtime",
    "scenario_time",
    "type",
    "module",
    "address",
    "value",
)


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
    try:
        reader = csv.DictReader(io.StringIO(text), strict=True)
        raw_headers = reader.fieldnames
        if raw_headers is None:
            raise ValueError("CSV header is missing")
        headers = tuple(header.strip() for header in raw_headers)
        if len(headers) != len(set(headers)) or headers != CSV_COLUMNS:
            raise ValueError(
                "CSV header must contain exactly, in order: "
                + ", ".join(CSV_COLUMNS)
            )
        reader.fieldnames = list(headers)
        for row in reader:
            if (
                len(row) != len(CSV_COLUMNS)
                or None in row
                or any(value is None for value in row.values())
            ):
                raise ValueError(
                    f"CSV row {reader.line_num} does not contain exactly "
                    f"{len(CSV_COLUMNS)} fields"
                )
            rows.append({key.strip(): value.strip() for key, value in row.items()})
    except csv.Error as exc:
        raise ValueError(f"malformed CSV near row {getattr(reader, 'line_num', 1)}") from exc
    return rows


def _float_or_none(s: str) -> float | None:
    try:
        v = float(s)
        return v if math.isfinite(v) else None
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
    expected_target_opportunities: int | None = None,
    expected_nontarget_opportunities: int | None = None,
) -> dict[str, Any]:
    perf = [r for r in rows
            if r.get("type") == "performance" and r.get("module") == "sysmon"]

    det = [r for r in perf if r.get("address") == "signal_detection"]
    rt_rows = [r for r in perf if r.get("address") == "response_time"]

    n_hits  = sum(1 for r in det if r.get("value", "").upper() == "HIT")
    n_misses = sum(1 for r in det if r.get("value", "").upper() == "MISS")
    n_fa    = sum(1 for r in det if r.get("value", "").upper() == "FA")
    n_signals = n_hits + n_misses

    legacy_hit_rate = (n_hits / n_signals) if n_signals > 0 else None

    rt_values = [v for r in rt_rows if (v := _float_or_none(r.get("value", ""))) is not None]
    mean_rt_legacy = round(statistics.mean(rt_values), 2) if rt_values else None

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

    opened_opportunities: dict[str, dict[str, Any]] = {}
    observed_outcomes: dict[str, tuple[bool, str, str, bool, float | None]] = {}
    opportunity_issues: list[str] = []
    incomplete_opportunity_evidence = False
    invalid_opportunity_evidence = False
    for row in perf:
        if row.get("address") != "opportunity":
            continue
        try:
            payload = json.loads(row.get("value", ""))
        except (json.JSONDecodeError, TypeError):
            opportunity_issues.append("invalid_json")
            invalid_opportunity_evidence = True
            continue
        if not isinstance(payload, dict):
            opportunity_issues.append("invalid_payload")
            invalid_opportunity_evidence = True
            continue
        phase = payload.get("phase")
        opportunity_id = str(payload.get("opportunity_id") or "").strip()
        target = payload.get("target")
        if not opportunity_id or not isinstance(target, bool):
            opportunity_issues.append("missing_id_or_target")
            invalid_opportunity_evidence = True
            continue
        if phase == "opened":
            if opportunity_id in opened_opportunities or opportunity_id in observed_outcomes:
                opportunity_issues.append(f"duplicate_open:{opportunity_id}")
                invalid_opportunity_evidence = True
                continue
            actor = payload.get(
                "allocation_actor",
                payload.get("response_actor", "participant"),
            )
            automation_active = payload.get(
                "automation_active", actor == "automation"
            )
            if (
                actor not in {"participant", "automation"}
                or type(automation_active) is not bool
                or (actor == "automation") != automation_active
            ):
                opportunity_issues.append(f"invalid_actor:{opportunity_id}")
                invalid_opportunity_evidence = True
                continue
            opened_opportunities[opportunity_id] = {
                "target": target,
                "allocation_actor": actor,
                "automation_active": automation_active,
                "opened_scenario_time_s": payload.get("opened_scenario_time_s"),
                "deadline_s": payload.get("deadline_s"),
            }
            continue
        if phase != "closed":
            opportunity_issues.append(f"invalid_phase:{opportunity_id}")
            invalid_opportunity_evidence = True
            continue
        outcome = str(payload.get("outcome") or "").upper()
        allowed = {"HIT", "MISS"} if target else {"FA", "CR"}
        if outcome not in allowed:
            opportunity_issues.append(f"invalid_outcome:{opportunity_id}")
            invalid_opportunity_evidence = True
            continue
        if opportunity_id in observed_outcomes:
            opportunity_issues.append(f"duplicate_outcome:{opportunity_id}")
            invalid_opportunity_evidence = True
            continue
        if opportunity_id not in opened_opportunities:
            opportunity_issues.append(f"close_without_open:{opportunity_id}")
            incomplete_opportunity_evidence = True
            continue
        opened = opened_opportunities[opportunity_id]
        if opened["target"] != target:
            opportunity_issues.append(f"target_mismatch:{opportunity_id}")
            invalid_opportunity_evidence = True
            continue
        actor = payload.get("response_actor", opened["allocation_actor"])
        automation_active = payload.get(
            "automation_active", opened["automation_active"]
        )
        if (
            actor not in {"participant", "automation"}
            or type(automation_active) is not bool
            or automation_active != opened["automation_active"]
            or (not automation_active and actor != "participant")
        ):
            opportunity_issues.append(f"actor_mismatch:{opportunity_id}")
            invalid_opportunity_evidence = True
            continue
        opened_time = opened.get("opened_scenario_time_s")
        closed_opened_time = payload.get("opened_scenario_time_s")
        if (
            opened_time is not None
            and closed_opened_time is not None
            and opened_time != closed_opened_time
        ):
            opportunity_issues.append(f"opened_time_mismatch:{opportunity_id}")
            invalid_opportunity_evidence = True
            continue
        opened_deadline = opened.get("deadline_s")
        closed_deadline = payload.get("scheduled_deadline_s")
        if (
            opened_deadline is not None
            and closed_deadline is not None
            and opened_deadline != closed_deadline
        ):
            opportunity_issues.append(f"deadline_mismatch:{opportunity_id}")
            invalid_opportunity_evidence = True
            continue
        raw_response_time = payload.get("response_time_ms")
        response_time_ms = (
            None if raw_response_time is None else _float_or_none(raw_response_time)
        )
        if (
            raw_response_time is not None
            and (response_time_ms is None or response_time_ms < 0)
        ):
            opportunity_issues.append(f"invalid_response_time:{opportunity_id}")
            invalid_opportunity_evidence = True
            continue
        if outcome in {"HIT", "FA"} and response_time_ms is None:
            opportunity_issues.append(f"missing_response_time:{opportunity_id}")
            invalid_opportunity_evidence = True
            continue
        observed_outcomes[opportunity_id] = (
            target,
            outcome,
            actor,
            automation_active,
            response_time_ms,
        )

    for opportunity_id in sorted(set(opened_opportunities) - set(observed_outcomes)):
        opportunity_issues.append(f"unclosed_opportunity:{opportunity_id}")
        incomplete_opportunity_evidence = True

    all_hits = sum(1 for target, outcome, _, _, _ in observed_outcomes.values() if target and outcome == "HIT")
    all_misses = sum(1 for target, outcome, _, _, _ in observed_outcomes.values() if target and outcome == "MISS")
    all_fa = sum(1 for target, outcome, _, _, _ in observed_outcomes.values() if not target and outcome == "FA")
    all_cr = sum(1 for target, outcome, _, _, _ in observed_outcomes.values() if not target and outcome == "CR")
    observed_targets = all_hits + all_misses
    observed_nontargets = all_fa + all_cr
    human_outcomes = [
        (target, outcome, response_time_ms)
        for target, outcome, actor, automation_active, response_time_ms
        in observed_outcomes.values()
        if not automation_active and actor == "participant"
    ]
    automation_exposed_opportunities = sum(
        automation_active or actor == "automation"
        for _, _, actor, automation_active, _ in observed_outcomes.values()
    )
    automation_responses = sum(
        actor == "automation"
        for _, _, actor, _, _ in observed_outcomes.values()
    )
    participant_interventions_during_automation = sum(
        actor == "participant" and automation_active
        for _, _, actor, automation_active, _ in observed_outcomes.values()
    )
    observed_hits = sum(1 for target, outcome, _ in human_outcomes if target and outcome == "HIT")
    observed_misses = sum(1 for target, outcome, _ in human_outcomes if target and outcome == "MISS")
    observed_fa = sum(1 for target, outcome, _ in human_outcomes if not target and outcome == "FA")
    observed_cr = sum(1 for target, outcome, _ in human_outcomes if not target and outcome == "CR")
    human_targets = observed_hits + observed_misses
    human_nontargets = observed_fa + observed_cr
    if observed_outcomes and det and (
        n_hits != all_hits
        or n_misses != all_misses
        or n_fa != all_fa
    ):
        opportunity_issues.append(
            "legacy_opportunity_channel_mismatch:"
            f"legacy={n_hits}/{n_misses}/{n_fa};"
            f"observed={all_hits}/{all_misses}/{all_fa}"
        )
        invalid_opportunity_evidence = True
    expected_counts = (
        ("target", expected_target_opportunities, observed_targets),
        ("nontarget", expected_nontarget_opportunities, observed_nontargets),
    )
    for label, expected_count, observed_count in expected_counts:
        if expected_count is not None and observed_count != expected_count:
            opportunity_issues.append(
                f"expected_{label}_count_mismatch:{observed_count}/{expected_count}"
            )
            incomplete_opportunity_evidence = True

    if invalid_opportunity_evidence:
        observed_status = "invalid"
        dprime_observed = None
    elif incomplete_opportunity_evidence:
        observed_status = "incomplete"
        dprime_observed = None
    elif not observed_outcomes:
        observed_status = "unavailable"
        dprime_observed = None
    else:
        observed_status = (
            "complete"
            if expected_target_opportunities is not None
            and expected_nontarget_opportunities is not None
            else "unreconciled"
        )
        dprime_observed = (
            _d_prime(observed_hits, observed_misses, observed_fa, observed_cr)
            if human_targets > 0 and human_nontargets > 0
            else None
        )

    observed_hit_rate = (
        observed_hits / human_targets
        if human_targets > 0 and not invalid_opportunity_evidence and not incomplete_opportunity_evidence
        else None
    )

    human_performance_eligible = (
        observed_status == "complete"
        and automation_exposed_opportunities == 0
        and automation_responses == 0
        and human_targets > 0
        and human_nontargets > 0
    )
    human_response_times = [
        response_time_ms
        for target, outcome, response_time_ms in human_outcomes
        if target and outcome == "HIT" and response_time_ms is not None
    ]
    mean_rt_observed = (
        round(statistics.mean(human_response_times), 2)
        if observed_status == "complete" and human_response_times
        else None
    )

    return {
        "n_hits": n_hits,
        "n_misses": n_misses,
        "n_false_alarms": n_fa,
        "n_signals": n_signals,
        "hit_rate": round(observed_hit_rate, 4) if observed_hit_rate is not None else None,
        "hit_rate_legacy_v1": round(legacy_hit_rate, 4) if legacy_hit_rate is not None else None,
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
        "observed_all_n_hits": all_hits,
        "observed_all_n_misses": all_misses,
        "observed_all_n_false_alarms": all_fa,
        "observed_all_n_correct_rejections": all_cr,
        "n_observed_target_opportunities": observed_targets,
        "n_observed_nontarget_opportunities": observed_nontargets,
        "n_human_target_opportunities": human_targets,
        "n_human_nontarget_opportunities": human_nontargets,
        "n_automated_opportunities": automation_exposed_opportunities,
        "n_automation_exposed_opportunities": automation_exposed_opportunities,
        "n_automation_responses": automation_responses,
        "n_participant_interventions_during_automation": (
            participant_interventions_during_automation
        ),
        "human_performance_eligible": human_performance_eligible,
        "human_performance_status": (
            "complete_pure_human"
            if human_performance_eligible
            else (
                "automation_exposed"
                if automation_exposed_opportunities
                else "insufficient_human_classes_or_lifecycle"
            )
        ),
        "n_opened_opportunities": len(opened_opportunities),
        "expected_target_opportunities": expected_target_opportunities,
        "expected_nontarget_opportunities": expected_nontarget_opportunities,
        "observed_opportunity_status": observed_status,
        "observed_opportunity_issues": opportunity_issues,
        "observed_measurement_basis": "observed_protocol_defined_opportunities",
        "observed_opportunity_reconciled": observed_status == "complete",
        # Conversion can establish internal completeness, not whether the
        # supplied expectations came from a valid session-bound manifest.
        "observed_confirmatory_eligible": False,
        "confirmatory_eligibility_basis": "requires_valid_session_bound_manifest",
        "mean_rt_ms": mean_rt_observed,
        "mean_rt_ms_legacy_v1": mean_rt_legacy,
    }


def _isa_metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    isa_rows = [
        r for r in rows
        if r.get("type") == "performance"
        and r.get("module") == "genericscales"
        and r.get("address") in (ISA_TITLE, ISA_TITLE_ES)
    ]

    probes: list[dict[str, Any]] = []
    invalid_probes: list[dict[str, Any]] = []
    for r in isa_rows:
        t = _float_or_none(r.get("scenario_time", ""))
        v = _float_or_none(r.get("value", ""))
        if v is not None and 1 <= v <= 10:
            probes.append({"scenario_time": round(t, 3) if t is not None else None, "value": round(v, 2)})
        else:
            invalid_probes.append({
                "scenario_time": round(t, 3) if t is not None else None,
                "value_raw": round(v, 4) if v is not None else None,
                "reason": (
                    "outside_isa_1_10_domain"
                    if v is not None
                    else "missing_or_nonfinite_isa_value"
                ),
            })

    values = [p["value"] for p in probes]
    return {
        "n_rows_observed": len(isa_rows),
        "n_probes_completed": len(values),
        "probes": probes,
        "mean": round(statistics.mean(values), 4) if values else None,
        "sd": round(statistics.stdev(values), 4) if len(values) > 1 else None,
        "n_invalid_probes": len(invalid_probes),
        "invalid_probes": invalid_probes,
        "confirmatory_eligible": bool(values) and not invalid_probes,
        "measurement_basis": (
            "observed_valid_isa_1_10"
            if values and not invalid_probes
            else "missing_or_invalid_isa"
        ),
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
    observations_by_subscale: dict[str, int] = {s: 0 for s in NASA_TLX_SUBSCALES}
    invalid_observations: list[dict[str, Any]] = []
    for r in tlx_rows:
        addr = r["address"]
        key = _ES_TO_EN.get(addr, NASA_TLX_SUBSCALE_ALIASES.get(addr, addr))
        v = _float_or_none(r.get("value", ""))
        if key in subscales:
            observations_by_subscale[key] += 1
            if v is not None:
                subscales[key] = round(v, 2)
                if not 0 <= v <= 10:
                    invalid_observations.append({
                        "subscale": key.lower().replace(" ", "_"),
                        "value_raw": round(v, 4),
                        "reason": "outside_nasa_tlx_0_10_domain",
                    })
            else:
                invalid_observations.append({
                    "subscale": key.lower().replace(" ", "_"),
                    "value_raw": None,
                    "reason": "missing_or_nonfinite_value",
                })

    filled = [v for v in subscales.values() if v is not None]
    legacy_sum = round(sum(filled), 4) if filled else None
    invalid_subscales = sorted({
        observation["subscale"] for observation in invalid_observations
    })
    duplicate_subscales = [
        key.lower().replace(" ", "_")
        for key, count in observations_by_subscale.items()
        if count > 1
    ]
    complete = (
        len(filled) == len(NASA_TLX_SUBSCALES)
        and len(tlx_rows) == len(NASA_TLX_SUBSCALES)
        and not invalid_subscales
        and not duplicate_subscales
    )
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
        "n_rows_observed": len(tlx_rows),
        "duplicate_subscales": duplicate_subscales,
        "invalid_subscales": invalid_subscales,
        "invalid_observations": invalid_observations,
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
        return {
            "value": None,
            "value_raw": None,
            "valid": False,
            "n_observations": 0,
            "observations": [],
            "duplicate_presentations": False,
            "invalid_values": [],
            "confirmatory_eligible": False,
        }

    observations: list[dict[str, Any]] = []
    invalid_values: list[dict[str, Any]] = []
    for row in bedford_rows:
        raw_value = _float_or_none(row.get("value", ""))
        row_valid = raw_value is not None and 1 <= raw_value <= 10
        observation = {
            "scenario_time": _float_or_none(row.get("scenario_time", "")),
            "value_raw": round(raw_value, 2) if raw_value is not None else None,
            "valid": row_valid,
        }
        observations.append(observation)
        if not row_valid:
            invalid_values.append({
                "value_raw": round(raw_value, 4) if raw_value is not None else None,
                "reason": (
                    "outside_bedford_1_10_domain"
                    if raw_value is not None
                    else "missing_or_nonfinite_value"
                ),
            })

    exactly_one = len(observations) == 1
    raw = observations[0]["value_raw"] if exactly_one else None
    valid = exactly_one and observations[0]["valid"]
    return {
        "value": round(raw) if valid else None,
        "value_raw": raw,
        "valid": valid,
        "n_observations": len(observations),
        "observations": observations,
        "duplicate_presentations": len(observations) > 1,
        "invalid_values": invalid_values,
        "confirmatory_eligible": valid,
    }


def _sagat_metric(
    rows: list[dict],
    manifest_path: Path | None,
    *,
    expected_participant_id: str | None = None,
    expected_block_num: int | None = None,
) -> dict:
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

    # Manifest cross-check. A malformed or wrong-identity manifest never alters
    # observed SAGAT results and never becomes an inferred plan.
    n_freezes_planned: int | None = None
    manifest_status = "unavailable"
    manifest_issues: list[str] = []
    manifest: dict[str, Any] | None = None
    if manifest_path is not None:
        if not manifest_path.is_file():
            manifest_status = "missing"
            manifest_issues.append("manifest_path_missing")
        else:
            try:
                candidate = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                candidate = None
                manifest_issues.append("manifest_unreadable_or_invalid_json")
            if not isinstance(candidate, dict):
                manifest_issues.append("manifest_not_an_object")
            else:
                manifest = candidate
                if (
                    expected_participant_id is not None
                    and manifest.get("participant_id") != expected_participant_id
                ):
                    manifest_issues.append("participant_id_mismatch")
                if (
                    expected_block_num is not None
                    and manifest.get("block_num") != expected_block_num
                ):
                    manifest_issues.append("block_num_mismatch")
                freezes = manifest.get("freezes")
                if not isinstance(freezes, list):
                    manifest_issues.append("freezes_not_a_list")
                else:
                    seen_freezes: set[str] = set()
                    for index, planned in enumerate(freezes):
                        if not isinstance(planned, dict):
                            manifest_issues.append(f"freeze_not_an_object:{index}")
                            continue
                        freeze_id = planned.get("freeze_id")
                        if not isinstance(freeze_id, str) or not freeze_id.strip():
                            manifest_issues.append(f"invalid_freeze_id:{index}")
                        elif freeze_id in seen_freezes:
                            manifest_issues.append(f"duplicate_freeze_id:{freeze_id}")
                        else:
                            seen_freezes.add(freeze_id)
                            if (
                                expected_participant_id is not None
                                and expected_block_num is not None
                                and not freeze_id.startswith(
                                    f"{expected_participant_id}_b{expected_block_num}_f"
                                )
                            ):
                                manifest_issues.append(
                                    f"freeze_id_identity_mismatch:{freeze_id}"
                                )
                        scenario_time = planned.get("scenario_time_sec")
                        if (
                            isinstance(scenario_time, bool)
                            or not isinstance(scenario_time, (int, float))
                            or not math.isfinite(float(scenario_time))
                            or scenario_time < 0
                        ):
                            manifest_issues.append(
                                f"invalid_freeze_scenario_time:{index}"
                            )
                        probe_ids = planned.get("probe_ids")
                        if (
                            not isinstance(probe_ids, list)
                            or not probe_ids
                            or any(
                                not isinstance(probe_id, str) or not probe_id.strip()
                                for probe_id in probe_ids
                            )
                            or len(set(probe_ids)) != len(probe_ids)
                        ):
                            manifest_issues.append(f"invalid_probe_ids:{index}")
                    planned_lookup = {
                        item.get("freeze_id"): item
                        for item in freezes
                        if isinstance(item, dict)
                        and isinstance(item.get("freeze_id"), str)
                    }
                    for executed in freeze_details:
                        planned = planned_lookup.get(executed["freeze_id"])
                        if planned is None:
                            manifest_issues.append(
                                f"unplanned_executed_freeze:{executed['freeze_id']}"
                            )
                            continue
                        observed_probe_ids = [
                            probe["probe_id"] for probe in executed["probes"]
                        ]
                        if observed_probe_ids != planned.get("probe_ids"):
                            manifest_issues.append(
                                f"probe_id_mismatch:{executed['freeze_id']}"
                            )
            manifest_status = "invalid" if manifest_issues else "verified"

    if manifest_status == "verified" and manifest is not None:
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
        "manifest_status": manifest_status,
        "manifest_path": str(manifest_path) if manifest_path is not None else None,
        "manifest_issues": manifest_issues,
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


def _comm_metrics(
    rows: list[dict[str, str]],
    expected_opportunities: int | None = None,
) -> dict[str, Any]:
    """Convert COMM outcomes without inventing presentation opportunities.

    Historical OpenMATB logs contain outcome rows but no evidence that the
    corresponding prompt was successfully presented or that its response
    window opened.  Those values remain available under ``*_legacy_v1`` only.
    Corrected fields are derived exclusively from the explicit v1 opportunity
    lifecycle emitted by the instrumented runtime.
    """
    perf = [r for r in rows
            if r.get("type") == "performance" and r.get("module") == "communications"]

    sdt_rows = [r for r in perf if r.get("address") == "sdt_value"]
    rt_rows  = [r for r in perf if r.get("address") == "response_time"]

    legacy_outcomes = [r.get("value", "").upper() for r in sdt_rows]
    legacy_hits = legacy_outcomes.count("HIT")
    legacy_misses = legacy_outcomes.count("MISS")
    legacy_fa = legacy_outcomes.count("FA")
    legacy_cr = legacy_outcomes.count("CR")
    legacy_signals = legacy_hits + legacy_misses
    legacy_noise = legacy_fa + legacy_cr
    legacy_rt_values = [
        value
        for row in rt_rows
        if (value := _float_or_none(row.get("value", ""))) is not None
    ]

    opportunity_rows = [
        row for row in perf if row.get("address") == "comm_opportunity_v1"
    ]
    lifecycles: dict[str, dict[str, Any]] = {}
    opportunity_issues: list[str] = []
    structurally_invalid = False

    def mark_invalid(message: str) -> None:
        nonlocal structurally_invalid
        opportunity_issues.append(message)
        structurally_invalid = True

    for row in opportunity_rows:
        try:
            payload = json.loads(
                row.get("value", ""),
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"non-finite JSON constant: {value}")
                ),
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            mark_invalid("invalid_json")
            continue
        if not isinstance(payload, dict):
            mark_invalid("invalid_payload")
            continue
        opportunity_id = payload.get("opportunity_id")
        destination = payload.get("destination")
        phase = payload.get("phase")
        if payload.get("schema_version") != "1.0":
            mark_invalid(f"unsupported_schema:{opportunity_id or 'missing'}")
            continue
        if not isinstance(opportunity_id, str) or not opportunity_id.strip():
            mark_invalid("missing_opportunity_id")
            continue
        if destination not in {"own", "other"}:
            mark_invalid(f"invalid_destination:{opportunity_id}")
            continue
        if phase not in {
            "opened", "presentation_started", "response_window_opened",
            "closed", "invalidated",
        }:
            mark_invalid(f"invalid_phase:{opportunity_id}")
            continue

        lifecycle = lifecycles.get(opportunity_id)
        if phase == "opened":
            if lifecycle is not None:
                mark_invalid(f"duplicate_open:{opportunity_id}")
                continue
            automation_active = payload.get("automation_active", False)
            if type(automation_active) is not bool:
                mark_invalid(f"invalid_automation_state:{opportunity_id}")
                continue
            lifecycles[opportunity_id] = {
                "destination": destination,
                "automation_active": automation_active,
                "events": [payload],
            }
            continue
        if lifecycle is None:
            mark_invalid(f"phase_without_open:{opportunity_id}:{phase}")
            continue
        if lifecycle["destination"] != destination:
            mark_invalid(f"destination_mismatch:{opportunity_id}")
            continue
        automation_active = payload.get(
            "automation_active", lifecycle["automation_active"]
        )
        if (
            type(automation_active) is not bool
            or automation_active != lifecycle["automation_active"]
        ):
            mark_invalid(f"automation_state_mismatch:{opportunity_id}")
            continue
        lifecycle["events"].append(payload)

    valid_trials: list[dict[str, Any]] = []
    invalidated_count = 0
    required_phases = [
        "opened", "presentation_started", "response_window_opened", "closed"
    ]
    for opportunity_id, lifecycle in lifecycles.items():
        events = lifecycle["events"]
        phases = [event["phase"] for event in events]
        if "invalidated" in phases:
            invalidated_count += 1
            mark_invalid(f"invalidated:{opportunity_id}")
            continue
        if phases != required_phases:
            mark_invalid(
                f"incomplete_or_out_of_order:{opportunity_id}:"
                + ",".join(phases)
            )
            continue

        presentation = events[1]
        if presentation.get("software_play_invoked") is not True:
            mark_invalid(f"presentation_not_invoked:{opportunity_id}")
            continue
        if not isinstance(presentation.get("physical_onset_measured"), bool):
            mark_invalid(f"physical_onset_flag_missing:{opportunity_id}")
            continue

        closed = events[-1]
        destination = lifecycle["destination"]
        outcome = str(closed.get("outcome") or "").upper()
        allowed_outcomes = {"HIT", "MISS"} if destination == "own" else {"FA", "CR"}
        if outcome not in allowed_outcomes:
            mark_invalid(f"invalid_outcome:{opportunity_id}:{outcome or 'missing'}")
            continue
        raw_rt = closed.get("response_time_ms")
        response_time_ms = None if raw_rt is None else _float_or_none(raw_rt)
        if raw_rt is not None and (response_time_ms is None or response_time_ms < 0):
            mark_invalid(f"invalid_response_time:{opportunity_id}")
            continue
        if outcome in {"HIT", "FA"} and response_time_ms is None:
            mark_invalid(f"missing_response_time:{opportunity_id}")
            continue
        response_actor = closed.get(
            "response_actor",
            "automation" if lifecycle["automation_active"] else "participant",
        )
        if response_actor not in {"participant", "automation"}:
            mark_invalid(f"invalid_response_actor:{opportunity_id}")
            continue
        if response_actor == "automation" and not lifecycle["automation_active"]:
            mark_invalid(f"automation_actor_without_active_allocation:{opportunity_id}")
            continue
        valid_trials.append({
            "opportunity_id": opportunity_id,
            "destination": destination,
            "outcome": outcome,
            "response_time_ms": response_time_ms,
            "physical_onset_measured": presentation["physical_onset_measured"],
            "response_actor": response_actor,
            "automation_active": lifecycle["automation_active"],
        })

    observed_status: str
    if structurally_invalid:
        observed_status = "invalid"
    elif not opportunity_rows:
        observed_status = "unavailable"
    elif expected_opportunities is None:
        observed_status = "complete_unreconciled"
    elif (
        not isinstance(expected_opportunities, int)
        or isinstance(expected_opportunities, bool)
        or expected_opportunities < 0
    ):
        opportunity_issues.append("invalid_expected_opportunity_count")
        observed_status = "invalid"
    elif len(lifecycles) != expected_opportunities:
        opportunity_issues.append(
            f"expected_count_mismatch:expected={expected_opportunities}:"
            f"opened={len(lifecycles)}"
        )
        observed_status = "count_mismatch"
    else:
        observed_status = "complete"

    # Any malformed/incomplete lifecycle makes the corrected aggregate null as
    # a unit. Selectively dropping invalid trials would bias performance upward.
    all_usable_trials = (
        valid_trials
        if observed_status in {"complete", "complete_unreconciled"}
        else []
    )
    usable_trials = [
        trial
        for trial in all_usable_trials
        if trial["response_actor"] == "participant"
        and not trial["automation_active"]
    ]
    automation_exposed_opportunities = sum(
        trial["automation_active"] or trial["response_actor"] == "automation"
        for trial in all_usable_trials
    )
    automation_responses = sum(
        trial["response_actor"] == "automation" for trial in all_usable_trials
    )
    participant_interventions_during_automation = sum(
        trial["automation_active"] and trial["response_actor"] == "participant"
        for trial in all_usable_trials
    )
    n_hits = sum(trial["outcome"] == "HIT" for trial in usable_trials)
    n_misses = sum(trial["outcome"] == "MISS" for trial in usable_trials)
    n_fa = sum(trial["outcome"] == "FA" for trial in usable_trials)
    n_cr = sum(trial["outcome"] == "CR" for trial in usable_trials)
    n_signals = n_hits + n_misses
    n_noise = n_fa + n_cr
    hit_rate = n_hits / n_signals if n_signals else None
    fa_rate = n_fa / n_noise if n_noise else None
    observed_rt_values = [
        trial["response_time_ms"]
        for trial in usable_trials
        if trial["response_time_ms"] is not None
    ]

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
        "mean_rt_ms": (
            round(statistics.mean(observed_rt_values), 2)
            if observed_rt_values else None
        ),
        "n_opened_opportunities": len(lifecycles),
        "n_observed_opportunities": len(all_usable_trials),
        "n_human_observed_opportunities": len(usable_trials),
        "n_automated_opportunities": automation_exposed_opportunities,
        "n_automation_exposed_opportunities": automation_exposed_opportunities,
        "n_automation_responses": automation_responses,
        "n_participant_interventions_during_automation": (
            participant_interventions_during_automation
        ),
        "human_performance_eligible": (
            observed_status == "complete"
            and automation_exposed_opportunities == 0
            and automation_responses == 0
        ),
        "n_invalidated_opportunities": invalidated_count,
        "expected_opportunities": expected_opportunities,
        "observed_opportunity_status": observed_status,
        "observed_opportunity_issues": opportunity_issues,
        "observed_opportunity_reconciled": observed_status == "complete",
        "observed_measurement_basis": "explicit_prompt_and_response_window_lifecycle",
        "physical_onset_measurements_present": bool(all_usable_trials) and all(
            trial["physical_onset_measured"] for trial in all_usable_trials
        ),
        # Runtime booleans are not a rig qualification report. COMM remains
        # descriptive until physical audio onset is independently qualified.
        "physical_onset_qualified": False,
        "observed_confirmatory_eligible": False,
        "confirmatory_eligibility_basis": (
            "requires_valid_session_manifest_and_physical_audio_onset_qualification"
        ),
        "n_hits_legacy_v1": legacy_hits,
        "n_misses_legacy_v1": legacy_misses,
        "n_false_alarms_legacy_v1": legacy_fa,
        "n_correct_rejections_legacy_v1": legacy_cr,
        "n_signals_legacy_v1": legacy_signals,
        "n_noise_trials_legacy_v1": legacy_noise,
        "hit_rate_legacy_v1": (
            round(legacy_hits / legacy_signals, 4) if legacy_signals else None
        ),
        "fa_rate_legacy_v1": (
            round(legacy_fa / legacy_noise, 4) if legacy_noise else None
        ),
        "d_prime_legacy_v1": _d_prime(
            legacy_hits, legacy_misses, legacy_fa, legacy_cr
        ),
        "mean_rt_ms_legacy_v1": (
            round(statistics.mean(legacy_rt_values), 2)
            if legacy_rt_values else None
        ),
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
    sagat_manifest_path: Path | None = None,
    expected_sysmon_target_opportunities: int | None = None,
    expected_sysmon_nontarget_opportunities: int | None = None,
    expected_comm_opportunities: int | None = None,
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
        sagat_manifest_dir: Optional directory in which to look for the exact
            ``{participant_id}_block{N}_sagat_manifest.json`` filename. The CSV
            directory and repo-owned questionnaire assets are fallback locations.
        sagat_manifest_path: Optional explicit SAGAT manifest. Mutually exclusive
            with ``sagat_manifest_dir``. Its embedded participant and block
            identity must still match this session before planned freezes are used.
        expected_sysmon_target_opportunities: Untrusted planned target count used
            only for internal reconciliation. Callers establish manifest validity.
        expected_sysmon_nontarget_opportunities: Untrusted planned non-target count
            used only for internal reconciliation. Callers establish validity.
        expected_comm_opportunities: Untrusted planned COMM opportunity count used
            only for internal reconciliation. Callers establish manifest validity.

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
        # The converter can preserve and score historical OpenMATB CSV, but CSV
        # is not the v3 immutable event stream. This marker prevents a valid
        # scenario manifest from silently upgrading a legacy derivative into
        # authoritative, event-reconciled evidence.
        "scientific_source_status": LEGACY_CSV_SOURCE_STATUS,
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
        "sysmon": _sysmon_metrics(
            rows,
            alerttimeout_sec,
            sysmon_n_indicators,
            duration,
            expected_sysmon_target_opportunities,
            expected_sysmon_nontarget_opportunities,
        ),
        "track": _track_metrics(rows),
        "resman": _resman_metrics(rows),
        "isa": _isa_metrics(rows),
        "nasatlx": _nasatlx_metrics(rows),
        "bedford": _bedford_metric(rows),
        "comm": _comm_metrics(rows, expected_comm_opportunities),
    }

    # Bind a plan only by explicit path or exact session identity. A broad glob and
    # "first file wins" would silently attach another participant's plan whenever
    # a directory contains multiple manifests.
    if sagat_manifest_dir is not None and sagat_manifest_path is not None:
        raise ValueError(
            "sagat_manifest_dir and sagat_manifest_path are mutually exclusive"
        )

    block_match = re.fullmatch(r"(?:block[_-]?)?(\d+)", block_name, re.IGNORECASE)
    block_num = int(block_match.group(1)) if block_match else None
    participant_is_filename_safe = bool(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", participant_id)
    )
    selection_issues: list[str] = []
    selected_manifest = Path(sagat_manifest_path) if sagat_manifest_path else None

    if selected_manifest is None:
        if not participant_is_filename_safe:
            selection_issues.append("manifest_selection_unsafe_participant_id")
        if block_num is None:
            selection_issues.append("manifest_selection_non_numeric_block_name")
        if not selection_issues:
            exact_name = f"{participant_id}_block{block_num}_sagat_manifest.json"
            search_dirs: list[Path] = []
            if sagat_manifest_dir is not None:
                search_dirs.append(Path(sagat_manifest_dir))
            search_dirs.append(Path(csv_path).parent)
            repo_root = Path(__file__).resolve().parents[1]
            search_dirs.append(repo_root / "matb_integration" / "questionnaires")

            exact_candidates: dict[Path, Path] = {}
            for directory in search_dirs:
                candidate = directory / exact_name
                if candidate.is_file():
                    exact_candidates[candidate.resolve()] = candidate
            if len(exact_candidates) == 1:
                selected_manifest = next(iter(exact_candidates.values()))
            elif len(exact_candidates) > 1:
                selection_issues.append("manifest_selection_ambiguous_exact_matches")

    sagat = _sagat_metric(
        rows,
        manifest_path=selected_manifest,
        expected_participant_id=participant_id,
        expected_block_num=block_num,
    )
    if selection_issues:
        sagat["manifest_status"] = "invalid"
        sagat["manifest_issues"] = [
            *sagat.get("manifest_issues", []),
            *selection_issues,
        ]
        sagat["n_freezes_planned"] = None
    record["sagat"] = sagat

    if extra_metadata:
        if not isinstance(extra_metadata, dict):
            raise TypeError("extra_metadata must be a JSON object")
        collisions = sorted(set(extra_metadata) & set(record))
        if collisions:
            raise ValueError(
                "extra_metadata cannot overwrite reserved conversion fields: "
                + ", ".join(collisions)
            )
        try:
            json.dumps(extra_metadata, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("extra_metadata must contain only finite JSON values") from exc
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
    line = json.dumps(record, ensure_ascii=False, allow_nan=False)

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
