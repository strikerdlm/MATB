from copy import deepcopy
from dataclasses import replace

import pytest

from matb_integration.suas.domain.commands import ReportContact, ReturnToBase
from matb_integration.suas.domain.enums import ContactClassification, ContactEvidence, ContactPriority, ContactWorkflow
from matb_integration.suas.domain.geometry import PointMM
from matb_integration.suas.domain.serialization import canonical_sha256
from matb_integration.suas.engine.runtime import SimulationEngine
from .helpers import envelope


def test_same_tick_events_have_stable_sequence(loaded_scenario) -> None:
    left = SimulationEngine(loaded_scenario.definition, "HIGH")
    right = SimulationEngine(loaded_scenario.definition, "HIGH")
    assert left.step().events == right.step().events
    assert left.state_hash == right.state_hash


def test_checkpoint_round_trip_is_authoritative_and_atomic(loaded_scenario) -> None:
    engine = SimulationEngine(loaded_scenario.definition, "LOW")
    for _ in range(4):
        engine.step()
    checkpoint = engine.checkpoint_snapshot()
    expected = engine.state_hash
    engine.step()
    engine.restore(checkpoint)
    assert engine.state_hash == expected
    bad = deepcopy(checkpoint)
    bad["state_version"] = 999
    before = engine.state_hash
    with pytest.raises(ValueError):
        engine.restore(bad)
    assert engine.state_hash == before


def test_public_snapshot_does_not_leak_private_truth_or_schedules(loaded_scenario) -> None:
    engine = SimulationEngine(loaded_scenario.definition, "LOW")
    snapshot = engine.snapshot()
    rendered = repr(snapshot)
    assert "truth_priority" not in rendered
    assert "required_report" not in rendered
    assert "conflict_events" not in rendered


@pytest.mark.parametrize("field, value", [
    ("link_applied_event_ids", ["medium_uas03_lost"]),
    ("conflict_applied_event_ids", ["low_conflict_01"]),
    ("sensor_prng", {"foreign:stream": {"state": 1, "increment": 1}}),
])
def test_rehashed_checkpoint_rejects_semantic_schedule_and_prng_tampering(
    loaded_scenario, field, value,
) -> None:
    engine = SimulationEngine(loaded_scenario.definition, "LOW")
    checkpoint = engine.checkpoint_snapshot()
    checkpoint[field] = value
    payload = dict(checkpoint)
    payload.pop("authoritative_state_sha256")
    checkpoint["authoritative_state_sha256"] = canonical_sha256(payload)
    before = engine.state_hash
    with pytest.raises(ValueError):
        engine.restore(checkpoint)
    assert engine.state_hash == before


def test_conflict_uses_configured_arrival_interval(loaded_scenario) -> None:
    scenario = loaded_scenario.definition
    original = next(event for event in scenario.conflict_events if event.event_id == "low_conflict_01")
    conflict = replace(original, convergence_point=PointMM(1_200_000, 4_000_000))
    scenario = replace(scenario, conflict_events=(conflict,))
    engine = SimulationEngine(scenario, "LOW")
    events = []
    first_arrivals: dict[str, int] = {}
    for _ in range(3_300):
        events.extend(engine.step().events)
        for aircraft_id in ("UAS-01", "UAS-02"):
            if (aircraft_id not in first_arrivals
                    and engine._state.aircraft[aircraft_id].position == conflict.convergence_point):
                first_arrivals[aircraft_id] = engine._state.simulation_time_ms
    started = [event for event in events if event.kind.value == "CONFLICT_INJECTION_STARTED"]
    assert len(started) == 1
    assert first_arrivals == {"UAS-01": 330_000, "UAS-02": 330_000}
    assert engine._state.aircraft["UAS-01"].position == conflict.convergence_point
    assert engine._state.aircraft["UAS-02"].position == conflict.convergence_point


def test_impossible_conflict_interval_is_skipped_without_route_mutation(loaded_scenario) -> None:
    engine = SimulationEngine(loaded_scenario.definition, "LOW")
    events = []
    for _ in range(3_000):
        events.extend(engine.step().events)
    skipped = [event for event in events if event.kind.value == "CONFLICT_INJECTION_SKIPPED"]
    assert skipped[-1].payload["reason"] == "impossible_schedule"
    assert engine._state.aircraft["UAS-01"].route.waypoints == ()
    assert engine._state.aircraft["UAS-02"].route.waypoints == ()


@pytest.mark.parametrize("mutate", [
    lambda pending: pending.clear(),
    lambda pending: pending["low_conflict_01"].update({"UAS-01": 300_200}),
])
def test_rehashed_checkpoint_rejects_omitted_or_retimed_pending_conflict_release(
    loaded_scenario, mutate,
) -> None:
    scenario = loaded_scenario.definition
    original = next(event for event in scenario.conflict_events if event.event_id == "low_conflict_01")
    scenario = replace(scenario, conflict_events=(replace(
        original, convergence_point=PointMM(1_200_000, 4_000_000),
    ),))
    engine = SimulationEngine(scenario, "LOW")
    for _ in range(3_000):
        engine.step()
    checkpoint = engine.checkpoint_snapshot()
    mutate(checkpoint["conflict_pending_releases"])
    payload = dict(checkpoint)
    payload.pop("authoritative_state_sha256")
    checkpoint["authoritative_state_sha256"] = canonical_sha256(payload)
    before = engine.state_hash
    with pytest.raises(ValueError):
        engine.restore(checkpoint)
    assert engine.state_hash == before


def test_staggered_conflict_checkpoint_restores_after_first_release(loaded_scenario) -> None:
    scenario, engine = _staggered_conflict_after_first_release(loaded_scenario)
    checkpoint = engine.checkpoint_snapshot()
    restored = SimulationEngine(scenario, "LOW")
    restored.restore(checkpoint)
    assert restored.state_hash == engine.state_hash


def test_staggered_conflict_checkpoint_restores_after_released_aircraft_returns_to_base(
    loaded_scenario,
) -> None:
    scenario, engine = _staggered_conflict_after_first_release(loaded_scenario)
    result = engine.step([envelope(
        "safety-rtb", expected=engine._state.version, command=ReturnToBase("UAS-01"),
    )])
    assert result.command_results[0].status.value == "accepted"
    assert engine._state.simulation_time_ms == 301_200
    assert engine._state.aircraft["UAS-01"].mode.value == "RETURN_TO_BASE"
    assert engine._state.aircraft["UAS-02"].mode.value == "HOLD"
    checkpoint = engine.checkpoint_snapshot()
    assert checkpoint["conflict_pending_releases"] == {
        "low_conflict_01": {"UAS-02": 302_100},
    }
    restored = SimulationEngine(scenario, "LOW")
    restored.restore(checkpoint)
    assert restored.state_hash == engine.state_hash


@pytest.mark.parametrize("tamper", ["omitted", "retimed", "foreign", "stale"])
def test_rehashed_safety_rerouted_checkpoint_rejects_pending_conflict_tampering(
    loaded_scenario, tamper,
) -> None:
    scenario, engine = _staggered_conflict_after_first_release(loaded_scenario)
    result = engine.step([envelope(
        "safety-rtb", expected=engine._state.version, command=ReturnToBase("UAS-01"),
    )])
    assert result.command_results[0].status.value == "accepted"
    checkpoint = engine.checkpoint_snapshot()
    pending = checkpoint["conflict_pending_releases"]
    if tamper == "omitted":
        pending.clear()
    elif tamper == "retimed":
        pending["low_conflict_01"]["UAS-02"] = 302_200
    elif tamper == "foreign":
        pending["foreign_conflict"] = {"UAS-02": 302_100}
    else:
        pending["low_conflict_01"]["UAS-02"] = 301_100
    payload = dict(checkpoint)
    payload.pop("authoritative_state_sha256")
    checkpoint["authoritative_state_sha256"] = canonical_sha256(payload)
    before = engine.state_hash
    with pytest.raises(ValueError):
        engine.restore(checkpoint)
    assert engine.state_hash == before


def _staggered_conflict_after_first_release(loaded_scenario):
    scenario = loaded_scenario.definition
    original = next(event for event in scenario.conflict_events if event.event_id == "low_conflict_01")
    scenario = replace(scenario, conflict_events=(replace(
        original, convergence_point=PointMM(1_200_000, 4_000_000),
    ),))
    engine = SimulationEngine(scenario, "LOW")
    for _ in range(2_999):
        engine.step()
    engine._state.aircraft["UAS-01"].position = PointMM(620_000, 4_000_000)
    engine._state.aircraft["UAS-02"].position = PointMM(640_000, 4_000_000)
    for _ in range(12):
        engine.step()
    assert engine._state.simulation_time_ms == 301_100
    assert engine._state.aircraft["UAS-01"].mode.value == "TRANSIT"
    assert engine._state.aircraft["UAS-02"].mode.value == "HOLD"
    checkpoint = engine.checkpoint_snapshot()
    assert checkpoint["conflict_pending_releases"] == {
        "low_conflict_01": {"UAS-02": 302_100},
    }
    return scenario, engine


def test_report_note_and_history_survive_private_checkpoint(loaded_scenario) -> None:
    engine = SimulationEngine(loaded_scenario.definition, "LOW")
    contact = engine._state.contacts["C-01"]
    contact.evidence = ContactEvidence.INSPECTABLE
    contact.workflow = ContactWorkflow.PRIORITIZED
    contact.classification = ContactClassification.ROUTINE
    contact.priority = ContactPriority.LOW
    contact.revision = 1
    result = engine.step([envelope("report", expected=0, command=ReportContact("C-01", "observed"))])
    assert result.command_results[0].status.value == "accepted"
    checkpoint = engine.checkpoint_snapshot()
    restored = SimulationEngine(loaded_scenario.definition, "LOW")
    restored.restore(checkpoint)
    assert restored._sensors.report_history("C-01") == ({
        "report_id": "C-01:R0001", "replaces_report_id": None, "revision": 1,
        "classification": "routine", "priority": "LOW", "note_code": "observed",
    },)
