"""Strict bilingual sUAS SAGAT probe loading and private truth rendering."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from pathlib import Path
from typing import Mapping

import yaml

from matb_integration.suas.domain.enums import (
    AircraftMode,
    AlertSeverity,
    ContactEvidence,
    ContactWorkflow,
    LinkState,
    Locale,
    SensorState,
)
from matb_integration.suas.domain.geometry import PointMM, distance_mm
from matb_integration.suas.domain.models import (
    AircraftState,
    BlockDefinition,
    ScenarioDefinition,
    WorldState,
)
from matb_integration.suas.domain.scenario_context import scenario_for_world
from matb_integration.suas.engine.coverage import CoverageGrid


_QUESTIONNAIRES = Path(__file__).resolve().parents[2] / "questionnaires"
_BANK_FILES = {Locale.EN: "sagat_suas_en.yaml", Locale.ES_CO: "sagat_suas_es.yaml"}
_ROW_FIELDS = {
    "probe_id", "sa_level", "domain", "question", "answer_evaluator",
    "option_source", "timeout_s",
}
_PROBE_CONTRACT = {
    "suas_l1_lost_links": (1, "perception", "integer_0_8"),
    "suas_l1_lowest_battery": (1, "perception", "active_aircraft"),
    "suas_l1_unreported": (1, "perception", "integer_0_8"),
    "suas_l2_largest_gap": (2, "comprehension", "sectors"),
    "suas_l2_attention": (2, "comprehension", "aircraft_or_none"),
    "suas_l2_mission_state": (2, "comprehension", "coverage_band"),
    "suas_l3_reserve_first": (3, "projection", "aircraft_or_none"),
    "suas_l3_next_sector": (3, "projection", "active_aircraft"),
    "suas_l3_conflict_risk": (3, "projection", "aircraft_pair_or_none"),
}
_OPTION_SOURCES = {
    "integer_0_8", "active_aircraft", "sectors", "coverage_band",
    "aircraft_or_none", "aircraft_pair_or_none",
}
_UNCERTAINTY = {Locale.EN: "Unknown", Locale.ES_CO: "No sé"}
_NONE = {Locale.EN: "None", Locale.ES_CO: "Ninguna"}
_COVERAGE_BANDS = {
    Locale.EN: ("Low", "Moderate", "High"),
    Locale.ES_CO: ("Baja", "Moderada", "Alta"),
}
_INACTIVE_MODES = {AircraftMode.RECOVERED, AircraftMode.MISSION_FAILED}


@dataclass(frozen=True, slots=True)
class ProbeTemplate:
    probe_id: str
    sa_level: int
    domain: str
    question: str
    answer_evaluator: str
    option_source: str
    timeout_s: int
    locale: Locale


@dataclass(frozen=True, slots=True)
class RenderedProbe:
    probe_id: str
    sa_level: int
    domain: str
    question: str
    options: tuple[str, ...]
    correct_answer: str
    timeout_ms: int
    unscorable_reason: str | None = None

    def to_public_dict(self) -> dict[str, object]:
        """Return the client-safe probe without private truth or scoring metadata."""

        return {
            "probe_id": self.probe_id,
            "sa_level": self.sa_level,
            "domain": self.domain,
            "question": self.question,
            "options": list(self.options),
            "timeout_ms": self.timeout_ms,
        }


def load_suas_probe_bank(
    locale: Locale | str,
    *,
    questionnaire_dir: Path | str | None = None,
) -> dict[str, ProbeTemplate]:
    """Load one bank after validating both locale banks and their parity."""

    selected = Locale(locale)
    directory = Path(questionnaire_dir) if questionnaire_dir is not None else _QUESTIONNAIRES
    banks = {
        bank_locale: _load_bank(directory / filename, bank_locale)
        for bank_locale, filename in _BANK_FILES.items()
    }
    if set(banks[Locale.EN]) != set(banks[Locale.ES_CO]):
        raise ValueError("sUAS probe bank EN/es key mismatch")
    for probe_id in banks[Locale.EN]:
        left, right = banks[Locale.EN][probe_id], banks[Locale.ES_CO][probe_id]
        if (
            left.sa_level, left.domain, left.answer_evaluator,
            left.option_source, left.timeout_s,
        ) != (
            right.sa_level, right.domain, right.answer_evaluator,
            right.option_source, right.timeout_s,
        ):
            raise ValueError(f"sUAS probe bank EN/es contract mismatch for {probe_id}")
    return banks[selected]


def render_probe(
    template: ProbeTemplate,
    state: WorldState,
    scenario: ScenarioDefinition | None = None,
    *,
    public_snapshot: Mapping[str, object] | None = None,
    block: BlockDefinition | None = None,
) -> RenderedProbe:
    """Privately derive one answer from the frozen authoritative state."""

    if not isinstance(template, ProbeTemplate) or not isinstance(state, WorldState):
        raise TypeError("render_probe requires a ProbeTemplate and private WorldState")
    del public_snapshot  # Browser projections are never an answer source.
    resolved_scenario = scenario or scenario_for_world(state)
    resolved_block = block
    if resolved_block is None and resolved_scenario is not None:
        resolved_block = resolved_scenario.blocks.get(state.block_id)
    options = _options(template, state, resolved_scenario)
    evaluator = _EVALUATORS[template.answer_evaluator]
    answer, reason = evaluator(
        state, resolved_scenario, resolved_block, template.locale,
    )
    if answer not in options:
        answer = _UNCERTAINTY[template.locale]
        reason = reason or "authoritative answer is absent from the declared option set"
    return RenderedProbe(
        probe_id=template.probe_id,
        sa_level=template.sa_level,
        domain=template.domain,
        question=template.question,
        options=options,
        correct_answer=answer,
        timeout_ms=template.timeout_s * 1_000,
        unscorable_reason=reason,
    )


def _load_bank(path: Path, locale: Locale) -> dict[str, ProbeTemplate]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"unable to load sUAS probe bank {path}") from error
    if not isinstance(document, dict) or set(document) != {"format_version", "locale", "probes"}:
        raise ValueError("sUAS probe bank has unknown keys or missing fields")
    format_version = document["format_version"]
    if (
        isinstance(format_version, bool)
        or not isinstance(format_version, int)
        or format_version != 1
        or document["locale"] != locale.value
    ):
        raise ValueError("sUAS probe bank format or locale mismatch")
    rows = document["probes"]
    if not isinstance(rows, list):
        raise ValueError("sUAS probe bank probes must be a list")
    result: dict[str, ProbeTemplate] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != _ROW_FIELDS:
            raise ValueError("sUAS probe bank row has unknown keys or missing fields")
        probe_id = row["probe_id"]
        if not isinstance(probe_id, str) or probe_id in result:
            raise ValueError("sUAS probe bank contains a duplicate or invalid probe ID")
        contract = _PROBE_CONTRACT.get(probe_id)
        if contract is None or row["answer_evaluator"] != probe_id:
            raise ValueError(f"sUAS probe bank has unknown evaluator {row['answer_evaluator']}")
        level, domain, source = contract
        row_level = row["sa_level"]
        if (
            isinstance(row_level, bool)
            or not isinstance(row_level, int)
            or row_level != level
            or row["domain"] != domain
        ):
            raise ValueError(f"sUAS probe bank level/domain mismatch for {probe_id}")
        option_source = row["option_source"]
        if (
            not isinstance(option_source, str)
            or option_source not in _OPTION_SOURCES
            or option_source != source
        ):
            raise ValueError(f"sUAS probe bank has unknown or mismatched option source for {probe_id}")
        timeout = row["timeout_s"]
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 5 <= timeout <= 60:
            raise ValueError(f"sUAS probe bank timeout outside 5-60 s for {probe_id}")
        if not isinstance(row["question"], str) or not row["question"].strip():
            raise ValueError(f"sUAS probe bank question is invalid for {probe_id}")
        result[probe_id] = ProbeTemplate(
            probe_id, level, domain, row["question"].strip(), probe_id, source, timeout, locale,
        )
    if set(result) != set(_PROBE_CONTRACT):
        raise ValueError("sUAS probe bank must contain the same nine probe IDs")
    return result


def _options(
    template: ProbeTemplate, state: WorldState, scenario: ScenarioDefinition | None,
) -> tuple[str, ...]:
    uncertainty = _UNCERTAINTY[template.locale]
    active = tuple(
        aircraft_id for aircraft_id, aircraft in sorted(state.aircraft.items())
        if aircraft.mode not in _INACTIVE_MODES
    )
    if template.option_source == "integer_0_8":
        values = tuple(str(value) for value in range(9))
    elif template.option_source == "active_aircraft":
        values = active
    elif template.option_source == "sectors":
        values = tuple(sorted(scenario.sectors)) if scenario is not None else ()
    elif template.option_source == "coverage_band":
        values = _COVERAGE_BANDS[template.locale]
    elif template.option_source == "aircraft_or_none":
        values = active + (_NONE[template.locale],)
    elif template.option_source == "aircraft_pair_or_none":
        values = tuple(f"{left}:{right}" for left, right in combinations(active, 2)) + (
            _NONE[template.locale],
        )
    else:  # Bank validation makes this unreachable for normal callers.
        raise ValueError(f"unknown option source {template.option_source}")
    return values + (uncertainty,)


def _lost_links(state, scenario, block, locale):
    del scenario, block, locale
    return str(sum(item.link is LinkState.LOST for item in state.aircraft.values())), None


def _lowest_battery(state, scenario, block, locale):
    del block
    candidates: list[tuple[Fraction, str]] = []
    for aircraft_id, aircraft in sorted(state.aircraft.items()):
        if aircraft.mode in _INACTIVE_MODES:
            continue
        capacity = scenario.aircraft[aircraft_id].energy.capacity_units if scenario else 1
        candidates.append((Fraction(aircraft.energy_units, capacity), aircraft_id))
    return _unique_min(candidates, locale, "no unique active-aircraft energy minimum")


def _unreported(state, scenario, block, locale):
    del scenario, block, locale
    count = sum(
        contact.evidence in (ContactEvidence.DETECTED, ContactEvidence.INSPECTABLE)
        and contact.workflow is not ContactWorkflow.REPORTED
        for contact in state.contacts.values()
    )
    return str(count), None


def _largest_gap(state, scenario, block, locale):
    del block
    if scenario is None:
        return _unknown(locale, "scenario geometry is unavailable")
    sectors = CoverageGrid(scenario).public_snapshot(state)["sectors"]
    candidates = [(details["coverage_ppm"], sector_id) for sector_id, details in sectors.items()]
    return _unique_min(candidates, locale, "no unique largest coverage gap")


def _attention(state, scenario, block, locale):
    del scenario, block
    severity = {AlertSeverity.ADVISORY: 1, AlertSeverity.CRITICAL: 2, AlertSeverity.FATAL: 3}
    active_ids = set(state.aircraft)
    alerts = sorted(
        (alert for alert in state.alerts.values() if alert.closed_sequence is None),
        key=lambda alert: (-severity[alert.severity], alert.opened_sequence, alert.alert_id),
    )
    if not alerts:
        return _NONE[locale], None
    entities = tuple(entity for entity in alerts[0].entity_ids if entity in active_ids)
    if len(entities) != 1:
        return _unknown(locale, "highest-severity alert does not identify one aircraft")
    return entities[0], None


def _mission_state(state, scenario, block, locale):
    del block
    if scenario is None:
        return _unknown(locale, "scenario coverage geometry is unavailable")
    sectors = CoverageGrid(scenario).public_snapshot(state)["sectors"].values()
    covered = sum(item["covered_count"] for item in sectors)
    eligible = sum(item["eligible_count"] for item in sectors)
    if not eligible:
        return _unknown(locale, "scenario has no eligible coverage cells")
    ppm = covered * 1_000_000 // eligible
    band = 0 if ppm < 333_334 else 1 if ppm < 666_667 else 2
    return _COVERAGE_BANDS[locale][band], None


def _reserve_first(state, scenario, block, locale):
    del block
    if scenario is None:
        return _unknown(locale, "scenario energy definitions are unavailable")
    candidates: list[tuple[Fraction, str]] = []
    for aircraft_id, aircraft in sorted(state.aircraft.items()):
        if aircraft.mode in _INACTIVE_MODES:
            continue
        definition = scenario.aircraft[aircraft_id]
        rate = _energy_rate(aircraft, definition)
        if rate <= 0:
            continue
        margin = max(0, aircraft.energy_units - aircraft.predicted_home_reserve_units)
        candidates.append((Fraction(margin, 1) / rate, aircraft_id))
    if not candidates:
        return _NONE[locale], None
    return _unique_min(candidates, locale, "no unique reserve crossing projection")


def _next_sector(state, scenario, block, locale):
    del block
    if scenario is None:
        return _unknown(locale, "scenario speed definitions are unavailable")
    candidates: list[tuple[Fraction, str]] = []
    for aircraft_id, aircraft in sorted(state.aircraft.items()):
        if (
            aircraft.mode not in (AircraftMode.TRANSIT, AircraftMode.SEARCH)
            or aircraft.assigned_sector_id is None
            or aircraft.route_leg >= len(aircraft.route.waypoints)
        ):
            continue
        remaining = _remaining_route_mm(aircraft)
        speed = scenario.aircraft[aircraft_id].speed_mm_per_s
        candidates.append((Fraction(remaining, speed), aircraft_id))
    return _unique_min(candidates, locale, "no unique aircraft has a completable sector route")


def _conflict_risk(state, scenario, block, locale):
    del block
    if scenario is None:
        return _unknown(locale, "scenario speed definitions are unavailable")
    active = [
        aircraft for aircraft in state.aircraft.values()
        if aircraft.mode not in _INACTIVE_MODES
    ]
    if len(active) < 2:
        return _NONE[locale], None
    projected = {
        aircraft.aircraft_id: _project_position(aircraft, scenario, horizon_s=60)
        for aircraft in active
    }
    candidates = [
        (distance_mm(projected[left], projected[right]), f"{left}:{right}")
        for left, right in combinations(sorted(projected), 2)
    ]
    return _unique_min(candidates, locale, "no unique minimum projected separation")


def _unique_min(candidates, locale: Locale, reason: str):
    if not candidates:
        return _unknown(locale, reason)
    minimum = min(value for value, _ in candidates)
    answers = [answer for value, answer in candidates if value == minimum]
    return (answers[0], None) if len(answers) == 1 else _unknown(locale, reason)


def _unknown(locale: Locale, reason: str) -> tuple[str, str]:
    return _UNCERTAINTY[locale], reason


def _energy_rate(aircraft, definition) -> Fraction:
    if aircraft.mode in (AircraftMode.TRANSIT, AircraftMode.RETURN_TO_BASE):
        base = definition.energy.transit_units_per_s
    elif aircraft.mode is AircraftMode.SEARCH:
        base = definition.energy.search_units_per_s
    else:
        base = definition.energy.idle_units_per_s
    sensor = Fraction(0)
    if aircraft.sensor is SensorState.NOMINAL:
        sensor = Fraction(
            definition.energy.sensor_units_per_scan * 1_000,
            definition.sensor.scan_interval_ms,
        )
    return Fraction(base) + sensor


def _remaining_route_mm(aircraft: AircraftState) -> int:
    cursor = aircraft.position
    remaining = 0
    for target in aircraft.route.waypoints[aircraft.route_leg:]:
        remaining += distance_mm(cursor, target)
        cursor = target
    return remaining


def _project_position(
    aircraft: AircraftState, scenario: ScenarioDefinition, *, horizon_s: int,
) -> PointMM:
    if aircraft.mode not in (
        AircraftMode.TRANSIT, AircraftMode.SEARCH, AircraftMode.RETURN_TO_BASE,
    ):
        return aircraft.position
    definition = scenario.aircraft[aircraft.aircraft_id]
    speed = (
        definition.return_speed_mm_per_s
        if aircraft.mode is AircraftMode.RETURN_TO_BASE
        else definition.speed_mm_per_s
    )
    budget = speed * horizon_s
    cursor = aircraft.position
    for target in aircraft.route.waypoints[aircraft.route_leg:]:
        segment = distance_mm(cursor, target)
        if segment == 0:
            cursor = target
            continue
        if budget >= segment:
            budget -= segment
            cursor = target
            continue
        return PointMM(
            cursor.x_mm + (target.x_mm - cursor.x_mm) * budget // segment,
            cursor.y_mm + (target.y_mm - cursor.y_mm) * budget // segment,
        )
    return cursor


_EVALUATORS = {
    "suas_l1_lost_links": _lost_links,
    "suas_l1_lowest_battery": _lowest_battery,
    "suas_l1_unreported": _unreported,
    "suas_l2_largest_gap": _largest_gap,
    "suas_l2_attention": _attention,
    "suas_l2_mission_state": _mission_state,
    "suas_l3_reserve_first": _reserve_first,
    "suas_l3_next_sector": _next_sector,
    "suas_l3_conflict_risk": _conflict_risk,
}
