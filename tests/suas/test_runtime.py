from copy import deepcopy

import pytest

from matb_integration.suas.engine.runtime import SimulationEngine


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
