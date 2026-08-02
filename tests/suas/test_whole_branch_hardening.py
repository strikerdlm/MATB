from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from matb_integration.suas.domain.commands import (
    AssignSector,
    CommandEnvelope,
    CommandStatus,
    ReportContact,
    SetWaypoint,
)
from matb_integration.suas.domain.enums import (
    AircraftMode,
    ContactClassification,
    ContactEvidence,
    ContactPriority,
    ContactWorkflow,
)
from matb_integration.suas.domain.geometry import PointMM, PolygonMM
from matb_integration.suas.domain.models import Route
from matb_integration.suas.domain.serialization import canonical_sha256
from matb_integration.suas.engine.runtime import SimulationEngine
from matb_integration.suas.scenarios.loader import load_scenario_text

from .helpers import envelope, rectangle


REFERENCE = Path("scenarios/suas/reference_area_search.yaml")


def test_set_waypoint_rejects_segment_that_exits_concave_terrain(loaded_scenario) -> None:
    scenario = _concave_command_scenario(loaded_scenario.definition)
    engine = SimulationEngine(scenario, "LOW")

    result = engine.step([envelope(
        "outside-route",
        expected=0,
        command=SetWaypoint("UAS-01", PointMM(5_000_000, 4_000_000)),
    )]).command_results[0]

    assert result.status is CommandStatus.REJECTED
    assert result.code == "route_outside_terrain"
    assert engine._state.aircraft["UAS-01"].route == Route(())


def test_assign_sector_rejects_transit_segment_that_exits_concave_terrain(
    loaded_scenario,
) -> None:
    scenario = _concave_command_scenario(loaded_scenario.definition)
    engine = SimulationEngine(scenario, "LOW")

    result = engine.step([envelope(
        "outside-sector-route",
        expected=0,
        command=AssignSector("UAS-01", "sector_alpha"),
    )]).command_results[0]

    assert result.status is CommandStatus.REJECTED
    assert result.code == "route_outside_terrain"
    assert engine._state.aircraft["UAS-01"].assigned_sector_id is None


@pytest.mark.parametrize(
    ("energy_units", "status"),
    [(4_400, CommandStatus.ACCEPTED), (4_399, CommandStatus.REJECTED)],
)
def test_waypoint_reserve_uses_mission_speed_outbound_and_return_speed_home(
    loaded_scenario, energy_units: int, status: CommandStatus,
) -> None:
    scenario = loaded_scenario.definition
    original = scenario.aircraft["UAS-01"]
    definition = replace(original, speed_mm_per_s=10_000, return_speed_mm_per_s=100_000)
    scenario = replace(scenario, aircraft={**scenario.aircraft, "UAS-01": definition})
    engine = SimulationEngine(scenario, "LOW")
    engine._state.aircraft["UAS-01"].energy_units = energy_units

    result = engine.step([envelope(
        f"reserve-{energy_units}",
        expected=0,
        command=SetWaypoint("UAS-01", PointMM(1_600_000, 4_000_000)),
    )]).command_results[0]

    assert result.status is status
    if status is CommandStatus.REJECTED:
        assert result.code == "critical_reserve"


def test_assign_sector_reserve_prices_generated_mission_legs_at_mission_speed(
    loaded_scenario,
) -> None:
    scenario = loaded_scenario.definition
    original = scenario.aircraft["UAS-01"]
    definition = replace(original, speed_mm_per_s=10_000, return_speed_mm_per_s=100_000)
    scenario = replace(scenario, aircraft={**scenario.aircraft, "UAS-01": definition})
    engine = SimulationEngine(scenario, "LOW")
    engine._state.aircraft["UAS-01"].energy_units = 10_000

    result = engine.step([envelope(
        "sector-reserve",
        expected=0,
        command=AssignSector("UAS-01", "sector_alpha"),
    )]).command_results[0]

    assert result.status is CommandStatus.REJECTED
    assert result.code == "critical_reserve"


def test_scan_exhaustion_fails_away_aircraft_in_same_tick_and_round_trips(
    loaded_scenario,
) -> None:
    scenario = loaded_scenario.definition
    engine = SimulationEngine(scenario, "LOW")
    aircraft = engine._state.aircraft["UAS-01"]
    aircraft.position = PointMM(1_000_000, 1_000_000)
    for _ in range(48):
        engine.step()
    aircraft.energy_units = 3
    aircraft.energy_remainder = 0
    pre_scan = engine.step()
    assert [event.kind.value for event in pre_scan.events] == [
        "ENERGY_THRESHOLD_CROSSED", "ENERGY_THRESHOLD_CROSSED",
    ]

    result = engine.step()

    assert aircraft.energy_units == -2
    assert aircraft.mode is AircraftMode.MISSION_FAILED
    assert [event.kind.value for event in result.events] == ["AIRCRAFT_MODE_CHANGED"]
    checkpoint = engine.checkpoint_snapshot()
    restored = SimulationEngine(scenario, "LOW")
    restored.restore(checkpoint)
    assert restored.state_hash == engine.state_hash
    assert restored._state.aircraft["UAS-01"].energy_units == -2
    assert restored._state.aircraft["UAS-01"].mode is AircraftMode.MISSION_FAILED


def test_negative_cartesian_scenario_checkpoint_restores_end_to_end() -> None:
    raw = yaml.safe_load(REFERENCE.read_text(encoding="utf-8"))
    _translate_x_coordinates(raw, -13_000)
    loaded = load_scenario_text(yaml.safe_dump(raw, sort_keys=False))
    scenario = loaded.definition
    assert scenario.terrain.bounds == (-13_000_000, 0, -1_000_000, 8_000_000)
    assert scenario.home.x_mm == -12_400_000
    assert all(contact.position.x_mm < 0 for contact in scenario.contacts.values())
    assert all(event.convergence_point.x_mm < 0 for event in scenario.conflict_events)
    engine = SimulationEngine(scenario, "LOW")
    waypoint = PointMM(-11_400_000, 4_000_000)
    accepted = engine.step([envelope(
        "negative-waypoint", expected=0, command=SetWaypoint("UAS-01", waypoint),
    )]).command_results[0]
    assert accepted.status is CommandStatus.ACCEPTED
    assert engine._state.aircraft["UAS-01"].route.waypoints == (waypoint,)

    checkpoint = engine.checkpoint_snapshot()
    restored = SimulationEngine(scenario, "LOW")
    restored.restore(checkpoint)

    assert restored.state_hash == engine.state_hash
    assert restored._state.aircraft["UAS-01"].position.x_mm < 0
    assert restored._state.aircraft["UAS-01"].route.waypoints == (waypoint,)


def test_initial_view_rectangle_crossing_concave_notch_is_rejected() -> None:
    raw = yaml.safe_load(REFERENCE.read_text(encoding="utf-8"))
    raw["terrain"]["vertices"] = [
        {"x_m": 0, "y_m": 0},
        {"x_m": 5_800, "y_m": 0},
        {"x_m": 5_800, "y_m": 800},
        {"x_m": 6_200, "y_m": 800},
        {"x_m": 6_200, "y_m": 0},
        {"x_m": 12_000, "y_m": 0},
        {"x_m": 12_000, "y_m": 8_000},
        {"x_m": 0, "y_m": 8_000},
    ]

    with pytest.raises(ValueError, match="initial view is outside terrain"):
        load_scenario_text(yaml.safe_dump(raw, sort_keys=False))


def test_unhashable_command_id_is_stably_rejected_without_mutation(loaded_scenario) -> None:
    engine = SimulationEngine(loaded_scenario.definition, "LOW")
    malformed = CommandEnvelope([], 0, SetWaypoint("UAS-01", PointMM(1_000_000, 4_000_000)))  # type: ignore[arg-type]

    result = engine.step([malformed]).command_results[0]

    assert result.status is CommandStatus.REJECTED
    assert result.code == "invalid_command_id"
    assert result.command_id == ""
    assert engine._state.aircraft["UAS-01"].route == Route(())
    assert engine._state.aircraft["UAS-01"].last_accepted_command_id is None
    assert engine._reducer.results == {}


def test_rehashed_sensor_cursor_tampering_is_rejected_atomically(loaded_scenario) -> None:
    engine = SimulationEngine(loaded_scenario.definition, "LOW")
    for _ in range(50):
        engine.step()
    checkpoint = engine.checkpoint_snapshot()
    checkpoint["sensor_due_times"]["UAS-01"] = 999_999_900
    checkpoint["world"]["aircraft"]["UAS-01"]["next_sensor_scan_ms"] = 999_999_900
    _rehash(checkpoint)
    before = engine.state_hash

    with pytest.raises(ValueError, match="sensor due"):
        engine.restore(checkpoint)

    assert engine.state_hash == before


@pytest.mark.parametrize("tamper", ["omit_pair", "duration", "flag", "alert"])
def test_rehashed_separation_tampering_is_rejected_atomically(
    loaded_scenario, tamper: str,
) -> None:
    engine = SimulationEngine(loaded_scenario.definition, "LOW")
    engine.step()
    checkpoint = engine.checkpoint_snapshot()
    pair_key = "UAS-01:UAS-02"
    if tamper == "omit_pair":
        checkpoint["separation"].pop(pair_key)
    elif tamper == "duration":
        checkpoint["separation"][pair_key]["advisory_duration_ms"] = 100
    elif tamper == "flag":
        checkpoint["separation"][pair_key]["critical_open"] = False
    else:
        checkpoint["world"]["alerts"].pop(f"SEPARATION_ADVISORY:{pair_key}")
    _rehash(checkpoint)
    before = engine.state_hash

    with pytest.raises(ValueError, match="separation"):
        engine.restore(checkpoint)

    assert engine.state_hash == before


@pytest.mark.parametrize("tamper", ["future", "nonmonotonic", "last_mismatch"])
def test_rehashed_report_revision_tampering_is_rejected_atomically(
    loaded_scenario, tamper: str,
) -> None:
    engine = SimulationEngine(loaded_scenario.definition, "LOW")
    contact = engine._state.contacts["C-01"]
    contact.evidence = ContactEvidence.INSPECTABLE
    contact.workflow = ContactWorkflow.PRIORITIZED
    contact.classification = ContactClassification.ROUTINE
    contact.priority = ContactPriority.LOW
    contact.revision = 1
    engine.step([envelope("report-1", expected=0, command=ReportContact("C-01", "observed"))])
    contact.priority = ContactPriority.HIGH
    contact.revision = 2
    engine.step([envelope(
        "report-2", expected=engine._state.version, command=ReportContact("C-01", "needs_review"),
    )])
    checkpoint = engine.checkpoint_snapshot()
    reports = checkpoint["sensor_reports"]["C-01"]
    if tamper == "future":
        reports[-1]["revision"] = 999
    elif tamper == "nonmonotonic":
        reports[-1]["revision"] = reports[0]["revision"]
    else:
        checkpoint["world"]["contacts"]["C-01"]["last_reported_revision"] = 1
    _rehash(checkpoint)
    before = engine.state_hash

    with pytest.raises(ValueError, match="report"):
        engine.restore(checkpoint)

    assert engine.state_hash == before


def test_unmodified_checkpoint_continuation_remains_identical(loaded_scenario) -> None:
    original = SimulationEngine(loaded_scenario.definition, "LOW")
    for _ in range(51):
        original.step()
    checkpoint = original.checkpoint_snapshot()
    restored = SimulationEngine(loaded_scenario.definition, "LOW")
    restored.restore(checkpoint)

    for _ in range(25):
        left = original.step()
        right = restored.step()
        assert left.events == right.events
        assert left.command_results == right.command_results
        assert original.state_hash == restored.state_hash


def _concave_command_scenario(scenario):
    terrain = PolygonMM((
        PointMM(0, 0), PointMM(6_000_000, 0), PointMM(6_000_000, 6_000_000),
        PointMM(4_000_000, 6_000_000), PointMM(4_000_000, 3_000_000),
        PointMM(3_000_000, 3_000_000), PointMM(3_000_000, 6_000_000),
        PointMM(0, 6_000_000),
    ))
    sector = rectangle(4_500_000, 3_500_000, 5_500_000, 4_500_000)
    return replace(
        scenario,
        terrain=terrain,
        sectors={**scenario.sectors, "sector_alpha": sector},
        restricted_zones={},
    )


def _translate_x_coordinates(value, offset_m: int) -> None:
    if isinstance(value, dict):
        if "x_m" in value:
            value["x_m"] += offset_m
        for child in value.values():
            _translate_x_coordinates(child, offset_m)
    elif isinstance(value, list):
        for child in value:
            _translate_x_coordinates(child, offset_m)


def _rehash(checkpoint: dict[str, object]) -> None:
    payload = dict(checkpoint)
    payload.pop("authoritative_state_sha256")
    checkpoint["authoritative_state_sha256"] = canonical_sha256(payload)
