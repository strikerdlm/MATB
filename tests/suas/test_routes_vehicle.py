from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

from matb_integration.suas.adapters.synthetic import SyntheticVehicleBackend
from matb_integration.suas.domain.enums import AircraftMode
from matb_integration.suas.domain.geometry import PointMM
from matb_integration.suas.domain.models import Route
from matb_integration.suas.engine.routes import lawnmower_route
from .helpers import rectangle


def test_lawnmower_route_is_inside_sector_and_alternates() -> None:
    sector = rectangle(0, 0, 4_000_000, 2_000_000)
    route = lawnmower_route(sector, spacing_mm=500_000)
    assert len(route.waypoints) == 8
    assert all(sector.contains(point) for point in route.waypoints)
    assert route.waypoints[0].x_mm < route.waypoints[1].x_mm
    assert route.waypoints[2].x_mm > route.waypoints[3].x_mm


def test_vehicle_step_is_fixed_point_and_energy_exact(loaded_scenario) -> None:
    scenario = loaded_scenario.definition
    backend = SyntheticVehicleBackend()
    state = backend.initialize(scenario, scenario.blocks["LOW"])
    state.aircraft["UAS-01"].route = Route((PointMM(1_600_000, 4_000_000),))
    state.aircraft["UAS-01"].mode = AircraftMode.TRANSIT
    before = state.aircraft["UAS-01"].energy_units
    for _ in range(10):
        state, _ = backend.advance(state, tick_ms=100)
    assert state.aircraft["UAS-01"].position.x_mm == 620_000
    assert state.aircraft["UAS-01"].energy_units == before - 40


def test_vehicle_carries_diagonal_leg_progress_until_a_coordinate_moves(loaded_scenario) -> None:
    """A one-mm tick on a diagonal may move neither coordinate initially."""

    loaded = loaded_scenario.definition
    aircraft = dict(loaded.aircraft)
    aircraft["UAS-01"] = replace(aircraft["UAS-01"], speed_mm_per_s=10)
    scenario = replace(loaded, aircraft=MappingProxyType(aircraft))
    backend = SyntheticVehicleBackend()
    state = backend.initialize(scenario, scenario.blocks["LOW"])
    state.aircraft["UAS-01"].route = Route((PointMM(601_000, 4_001_000),))
    state.aircraft["UAS-01"].mode = AircraftMode.TRANSIT

    for _ in range(5):
        state, _ = backend.advance(state, tick_ms=100)

    aircraft_state = state.aircraft["UAS-01"]
    assert aircraft_state.position == PointMM(600_003, 4_000_003)
    assert aircraft_state.route_leg == 0


def test_initialize_uses_only_block_aircraft_and_reference_world_is_fresh(
    loaded_scenario, reference_world,
) -> None:
    scenario = loaded_scenario.definition
    assert tuple(sorted(reference_world.aircraft)) == ("UAS-01", "UAS-02")
    reference_world.aircraft["UAS-01"].energy_units = 0
    fresh = SyntheticVehicleBackend().initialize(scenario, scenario.blocks["LOW"])
    assert fresh.aircraft["UAS-01"].energy_units == 100_000
