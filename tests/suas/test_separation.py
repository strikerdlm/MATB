from dataclasses import replace

import pytest

from matb_integration.suas.domain.serialization import canonical_sha256
from matb_integration.suas.engine.separation import SeparationMonitor
from matb_integration.suas.engine.runtime import SimulationEngine
from .helpers import event_kinds, place_pair


def test_separation_alert_opens_and_closes_once(reference_world) -> None:
    monitor = SeparationMonitor(advisory_mm=300_000, critical_mm=150_000)
    place_pair(reference_world, 290_000)
    assert event_kinds(monitor.step(reference_world)) == ["SEPARATION_ADVISORY_OPENED"]
    assert monitor.step(reference_world) == ()
    place_pair(reference_world, 140_000)
    assert event_kinds(monitor.step(reference_world)) == ["SEPARATION_VIOLATION"]
    place_pair(reference_world, 400_000)
    assert event_kinds(monitor.step(reference_world)) == ["SEPARATION_ALERT_CLOSED"]


def test_critical_duration_counts_only_below_critical_intervals_across_restore(
    loaded_scenario,
) -> None:
    scenario = replace(
        loaded_scenario.definition,
        advisory_separation_mm=300_000,
        critical_separation_mm=150_000,
    )
    original = SimulationEngine(scenario, "LOW")
    place_pair(original._state, 140_000)
    opened = original.step()
    assert event_kinds(opened.events) == [
        "SEPARATION_ADVISORY_OPENED", "SEPARATION_VIOLATION",
    ]

    place_pair(original._state, 200_000)
    assert original.step().events == ()
    checkpoint = original.checkpoint_snapshot()
    assert checkpoint["separation"]["UAS-01:UAS-02"]["critical_duration_ms"] == 100
    assert checkpoint["separation"]["UAS-01:UAS-02"]["critical_occupancy"] == {
        "below": False,
        "transition_ms": 200,
        "duration_ms": 100,
    }

    restored = SimulationEngine(scenario, "LOW")
    restored.restore(checkpoint)
    for engine in (original, restored):
        place_pair(engine._state, 200_000)
        assert engine.step().events == ()
        place_pair(engine._state, 400_000)
        closed = engine.step().events
        assert event_kinds(closed) == ["SEPARATION_ALERT_CLOSED"]
        assert closed[0].payload["advisory_duration_ms"] == 300
        assert closed[0].payload["critical_duration_ms"] == 100

    assert restored.state_hash == original.state_hash


@pytest.mark.parametrize(
    "tamper",
    ["correlated_duration", "correlated_tick_duration", "off_tick_transition"],
)
def test_checkpoint_rejects_falsified_critical_occupancy_provenance(
    loaded_scenario, tamper: str,
) -> None:
    scenario = replace(
        loaded_scenario.definition,
        advisory_separation_mm=300_000,
        critical_separation_mm=150_000,
    )
    source = SimulationEngine(scenario, "LOW")
    place_pair(source._state, 140_000)
    source.step()
    place_pair(source._state, 200_000)
    source.step()
    checkpoint = source.checkpoint_snapshot()
    pair = checkpoint["separation"]["UAS-01:UAS-02"]
    occupancy = pair["critical_occupancy"]
    if tamper == "correlated_duration":
        pair["critical_duration_ms"] = 50
        occupancy["duration_ms"] = 50
    elif tamper == "correlated_tick_duration":
        pair["critical_duration_ms"] = 0
        occupancy["duration_ms"] = 0
    else:
        occupancy["transition_ms"] = 150
    payload = dict(checkpoint)
    payload.pop("authoritative_state_sha256")
    checkpoint["authoritative_state_sha256"] = canonical_sha256(payload)

    target = SimulationEngine(scenario, "LOW")
    before = target.state_hash
    with pytest.raises(ValueError, match="separation checkpoint"):
        target.restore(checkpoint)
    assert target.state_hash == before
