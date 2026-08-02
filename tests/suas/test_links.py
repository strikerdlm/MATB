from __future__ import annotations

from matb_integration.suas.adapters.synthetic import SyntheticVehicleBackend
from matb_integration.suas.domain.enums import AircraftMode, LinkState
from matb_integration.suas.engine.links import LinkSystem


def test_lost_link_holds_ten_seconds_then_returns_home(
    loaded_scenario, reference_world,
) -> None:
    """Catches an unsafe lost-link transition before its full hold expires."""

    links = LinkSystem(loaded_scenario.definition)
    links.force_state(reference_world, "UAS-01", LinkState.LOST, at_ms=1_000)
    assert reference_world.aircraft["UAS-01"].mode is AircraftMode.LOST_LINK_PROCEDURE

    links.step(reference_world, now_ms=10_900)
    assert reference_world.aircraft["UAS-01"].mode is AircraftMode.LOST_LINK_PROCEDURE

    events = links.step(reference_world, now_ms=11_000)
    aircraft = reference_world.aircraft["UAS-01"]
    assert aircraft.mode is AircraftMode.RETURN_TO_BASE
    assert aircraft.route.waypoints == (loaded_scenario.definition.home,)
    assert [event.kind.value for event in events] == ["AIRCRAFT_MODE_CHANGED"]


def test_recovery_keeps_lost_aircraft_holding_until_explicit_reassignment(
    loaded_scenario, reference_world,
) -> None:
    """Catches recovery incorrectly resuming a pre-loss SEARCH assignment."""

    links = LinkSystem(loaded_scenario.definition)
    aircraft = reference_world.aircraft["UAS-01"]
    aircraft.mode = AircraftMode.SEARCH
    links.force_state(reference_world, "UAS-01", LinkState.LOST, at_ms=1_000)
    links.force_state(reference_world, "UAS-01", LinkState.NOMINAL, at_ms=2_000)

    assert aircraft.link is LinkState.NOMINAL
    assert aircraft.lost_link_since_ms is None
    assert aircraft.mode is AircraftMode.HOLD
    assert aircraft.previous_mode is AircraftMode.SEARCH


def test_scheduled_link_event_applies_once_by_event_id(loaded_scenario) -> None:
    """Catches repeat processing of the same scheduled link event."""

    scenario = loaded_scenario.definition
    world = SyntheticVehicleBackend().initialize(scenario, scenario.blocks["MEDIUM"])
    links = LinkSystem(scenario)
    first = links.step(world, now_ms=220_000)
    second = links.step(world, now_ms=220_000)

    assert [event.kind.value for event in first] == [
        "LINK_STATE_CHANGED", "LOST_LINK_PROCEDURE_STARTED",
    ]
    assert world.aircraft["UAS-03"].link is LinkState.LOST
    assert second == ()
