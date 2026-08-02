from __future__ import annotations

from copy import deepcopy

import pytest

from matb_integration.suas.adapters.synthetic import SyntheticVehicleBackend
from matb_integration.suas.domain.enums import (
    ContactClassification,
    ContactEvidence,
    ContactPriority,
    ContactWorkflow,
    LinkState,
)
from matb_integration.suas.engine.coverage import CoverageGrid
from matb_integration.suas.engine.sensors import (
    SensorSystem,
    apply_contact_action,
    public_snapshot,
)


def run_scans(system, state, *, pairs: list[tuple[str, str]], count: int):
    events = []
    for _ in range(count):
        events.extend(system.scan_pairs(state, pairs=pairs))
    return tuple(events)


def test_sensor_stream_for_one_pair_does_not_perturb_another(
    loaded_scenario, reference_world,
) -> None:
    """Catches accidental sharing of random draws across sensor pairs."""

    scenario = loaded_scenario.definition
    baseline_world = deepcopy(reference_world)
    observed_world = deepcopy(reference_world)
    first = SensorSystem(scenario)
    baseline = run_scans(first, baseline_world, pairs=[("UAS-01", "C-01")], count=5)
    second = SensorSystem(scenario)
    run_scans(second, observed_world, pairs=[("UAS-08", "C-12")], count=99)
    observed = run_scans(second, observed_world, pairs=[("UAS-01", "C-01")], count=5)

    assert observed == baseline


def test_hidden_truth_never_appears_in_public_snapshot(reference_world) -> None:
    """Catches accidental serialization of authoritative contact truth."""

    snapshot = public_snapshot(reference_world)
    assert "truth" not in snapshot["contacts"]["C-01"]
    assert "required_report" not in snapshot["contacts"]["C-01"]


def test_detected_contact_exposes_position_but_not_before(loaded_scenario, reference_world) -> None:
    """Catches contact position leaking before a detection event."""

    scenario = loaded_scenario.definition
    sensor = SensorSystem(scenario)
    aircraft = reference_world.aircraft["UAS-01"]
    aircraft.position = scenario.contacts["C-01"].position
    assert "position" not in public_snapshot(reference_world, scenario=scenario)["contacts"]["C-01"]

    sensor.scan_pairs(reference_world, pairs=[("UAS-01", "C-01")])
    assert public_snapshot(reference_world, scenario=scenario)["contacts"]["C-01"]["position"] == {
        "x_mm": 2_500_000, "y_mm": 1_800_000,
    }


def test_exported_snapshot_includes_detected_contact_position(loaded_scenario, reference_world) -> None:
    """Catches the one-argument public API dropping a detected contact position."""

    scenario = loaded_scenario.definition
    sensor = SensorSystem(scenario)
    reference_world.aircraft["UAS-01"].position = scenario.contacts["C-01"].position
    sensor.scan_pairs(reference_world, pairs=[("UAS-01", "C-01")])

    assert public_snapshot(reference_world)["contacts"]["C-01"]["position"] == {
        "x_mm": 2_500_000, "y_mm": 1_800_000,
    }


def test_exported_snapshot_keeps_initialized_world_position_context(loaded_scenario) -> None:
    """Catches a restored detected world losing its one-argument position projection."""

    scenario = loaded_scenario.definition
    world = SyntheticVehicleBackend().initialize(scenario, scenario.blocks["LOW"])
    world.contacts["C-01"].evidence = ContactEvidence.DETECTED

    assert public_snapshot(world)["contacts"]["C-01"]["position"] == {
        "x_mm": 2_500_000, "y_mm": 1_800_000,
    }


def test_exported_snapshot_keeps_detected_position_after_deepcopy(loaded_scenario) -> None:
    """Catches identity-bound scenario context disappearing after checkpoint restoration."""

    scenario = loaded_scenario.definition
    world = SyntheticVehicleBackend().initialize(scenario, scenario.blocks["LOW"])
    world.contacts["C-01"].evidence = ContactEvidence.DETECTED
    restored = deepcopy(world)

    assert public_snapshot(restored)["contacts"]["C-01"]["position"] == {
        "x_mm": 2_500_000, "y_mm": 1_800_000,
    }


@pytest.mark.parametrize("sensor_first", [False, True])
def test_due_scan_has_one_charge_and_detection_in_either_runtime_order(
    loaded_scenario, sensor_first: bool,
) -> None:
    """Catches backend-owned scan cursor advancement hiding the due scan from sensors."""

    scenario = loaded_scenario.definition
    backend = SyntheticVehicleBackend()
    world = backend.initialize(scenario, scenario.blocks["LOW"])
    world.aircraft["UAS-01"].position = scenario.contacts["C-01"].position
    sensor = SensorSystem(scenario)

    if sensor_first:
        sensor.step(world, now_ms=5_000)
        backend.advance(world, tick_ms=5_000)
    else:
        backend.advance(world, tick_ms=5_000)
        sensor.step(world, now_ms=world.simulation_time_ms)

    assert world.contacts["C-01"].evidence is ContactEvidence.DETECTED
    assert world.aircraft["UAS-01"].energy_units == 99_985
    assert world.aircraft["UAS-01"].next_sensor_scan_ms == 10_000


@pytest.mark.parametrize("sensor_first", [False, True])
def test_due_scan_refreshes_reserve_alert_once_at_exact_crossing(
    loaded_scenario, sensor_first: bool,
) -> None:
    """Catches scan charges leaving reserve state and threshold alerts stale."""

    scenario = loaded_scenario.definition
    backend = SyntheticVehicleBackend()
    world = backend.initialize(scenario, scenario.blocks["LOW"])
    aircraft = world.aircraft["UAS-01"]
    aircraft.position = scenario.contacts["C-01"].position
    aircraft.energy_units = 18_891
    sensor = SensorSystem(scenario)

    if sensor_first:
        sensor_events = sensor.step(world, now_ms=5_000)
        _, backend_events = backend.advance(world, tick_ms=5_000)
    else:
        _, backend_events = backend.advance(world, tick_ms=5_000)
        sensor_events = sensor.step(world, now_ms=world.simulation_time_ms)

    reserve_events = [
        event for event in (*backend_events, *sensor_events)
        if event.kind.value == "ENERGY_THRESHOLD_CROSSED"
        and event.payload["alert_kind"] == "ENERGY_RESERVE"
    ]
    assert aircraft.energy_units == 18_876
    assert aircraft.predicted_home_reserve_units == 15_000
    assert len(reserve_events) == 1
    assert reserve_events[0].payload["transition"] == "opened"
    assert reserve_events[0].simulation_time_ms == 5_000
    assert world.alerts["ENERGY_RESERVE:UAS-01"].closed_at_ms is None


def test_nominal_sensor_detects_while_link_is_lost(loaded_scenario, reference_world) -> None:
    """Catches sensor operation being incorrectly coupled to command link state."""

    scenario = loaded_scenario.definition
    sensor = SensorSystem(scenario)
    reference_world.aircraft["UAS-01"].position = scenario.contacts["C-01"].position
    reference_world.aircraft["UAS-01"].link = LinkState.LOST
    sensor.scan_pairs(reference_world, pairs=[("UAS-01", "C-01")])

    assert reference_world.contacts["C-01"].evidence is ContactEvidence.DETECTED


def test_contact_actions_require_order_and_report_revisions(reference_world) -> None:
    """Catches reporting before inspection or reporting an unchanged revision twice."""

    contact = reference_world.contacts["C-01"]
    contact.evidence = ContactEvidence.INSPECTABLE
    contact.workflow = ContactWorkflow.DETECTED

    assert apply_contact_action(reference_world, "C-01", "REPORT_CONTACT") == ()
    assert apply_contact_action(reference_world, "C-01", "INSPECT_CONTACT")
    assert apply_contact_action(
        reference_world, "C-01", "CLASSIFY_CONTACT", classification=ContactClassification.ROUTINE,
    )
    assert apply_contact_action(
        reference_world, "C-01", "SET_CONTACT_PRIORITY", priority=ContactPriority.LOW,
    )
    report = apply_contact_action(reference_world, "C-01", "REPORT_CONTACT")
    assert report[0].payload["report_id"] == "C-01:R0001"
    assert apply_contact_action(reference_world, "C-01", "REPORT_CONTACT") == ()

    corrected = apply_contact_action(
        reference_world, "C-01", "SET_CONTACT_PRIORITY", priority=ContactPriority.HIGH,
    )
    assert [event.kind.value for event in corrected] == ["CONTACT_WORKFLOW_CHANGED", "CONTACT_CORRECTED"]
    new_report = apply_contact_action(reference_world, "C-01", "REPORT_CONTACT")
    assert new_report[0].payload["report_id"] == "C-01:R0002"
    assert new_report[0].payload["replaces_report_id"] == "C-01:R0001"
    assert new_report[0].payload["revision"] == 3


def test_coverage_uses_integer_cells_and_ppm(loaded_scenario, reference_world) -> None:
    """Catches float coverage and cells outside the assigned sector."""

    scenario = loaded_scenario.definition
    reference_world.aircraft["UAS-01"].assigned_sector_id = "sector_alpha"
    reference_world.aircraft["UAS-01"].position = scenario.contacts["C-01"].position
    grid = CoverageGrid(scenario)
    updated = grid.mark_scan(reference_world, "UAS-01")
    snapshot = grid.public_snapshot(reference_world)

    assert updated
    assert isinstance(updated[0], tuple)
    sector = snapshot["sectors"]["sector_alpha"]
    assert sector["coverage_ppm"] == (
        sector["covered_count"] * 1_000_000 // sector["eligible_count"]
    )
    assert sector["covered_cells"] == sorted(
        sector["covered_cells"],
    )
