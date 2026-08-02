"""Deterministic fixed-point vehicle adapter used by the reference simulator."""

from __future__ import annotations

from matb_integration.suas.domain.enums import (
    AircraftMode, ContactEvidence, ContactWorkflow,
)
from matb_integration.suas.domain.events import DomainEvent
from matb_integration.suas.domain.geometry import PointMM, distance_mm, heading_mdeg
from matb_integration.suas.domain.models import (
    AircraftDefinition, AircraftState, BlockDefinition, ContactState, Route,
    ScenarioDefinition, WorldState,
)
from matb_integration.suas.engine.sensors import bind_world_scenario
from matb_integration.suas.engine.energy import refresh_energy_reserve


class SyntheticVehicleBackend:
    """A no-I/O backend whose integer operations are replay-stable."""

    def __init__(self) -> None:
        self._aircraft_definitions: dict[str, AircraftDefinition] = {}

    def initialize(self, scenario: ScenarioDefinition, block: BlockDefinition) -> WorldState:
        definitions: dict[str, AircraftDefinition] = {}
        for aircraft_id in block.aircraft_ids:
            try:
                definitions[aircraft_id] = scenario.aircraft[aircraft_id]
            except KeyError as error:
                raise ValueError(f"block {block.block_id} references missing aircraft {aircraft_id}") from error
        missing_contacts = [contact_id for contact_id in block.contact_ids if contact_id not in scenario.contacts]
        if missing_contacts:
            raise ValueError(f"block {block.block_id} references missing contact {missing_contacts[0]}")
        self._aircraft_definitions = definitions
        aircraft = {
            aircraft_id: _initial_aircraft_state(definition)
            for aircraft_id, definition in sorted(definitions.items())
        }
        contacts = {
            contact_id: ContactState(
                contact_id=contact_id,
                evidence=ContactEvidence.NONE,
                successful_scans=0,
                workflow=ContactWorkflow.UNDETECTED,
                classification=None,
                priority=None,
                revision=0,
                last_reported_revision=None,
                report_ids=[],
            )
            for contact_id in sorted(block.contact_ids)
        }
        state = WorldState(
            block_id=block.block_id,
            tick=0,
            simulation_time_ms=0,
            version=0,
            aircraft=aircraft,
            contacts=contacts,
            alerts={},
            coverage_cells=set(),
            event_sequence=0,
        )
        bind_world_scenario(state, scenario)
        return state

    def advance(
        self, state: WorldState, *, tick_ms: int,
    ) -> tuple[WorldState, tuple[DomainEvent, ...]]:
        """Advance all active aircraft in lexical ID order by one exact tick."""

        if isinstance(tick_ms, bool) or not isinstance(tick_ms, int) or tick_ms <= 0:
            raise ValueError("tick_ms must be a positive integer")
        if not self._aircraft_definitions:
            raise RuntimeError("initialize must be called before advance")
        state.tick += 1
        state.simulation_time_ms += tick_ms
        state.version += 1
        events: list[DomainEvent] = []
        for aircraft_id in sorted(state.aircraft):
            aircraft = state.aircraft[aircraft_id]
            definition = self._aircraft_definitions.get(aircraft_id)
            if definition is None:
                raise ValueError(f"world references missing aircraft definition {aircraft_id}")
            if aircraft.mode in (AircraftMode.RECOVERED, AircraftMode.MISSION_FAILED):
                refresh_energy_reserve(
                    state, aircraft, definition, events, at_ms=state.simulation_time_ms,
                )
                continue
            rate = _consumption_rate(aircraft.mode, definition)
            numerator = rate * tick_ms + aircraft.energy_remainder
            aircraft.energy_units -= numerator // 1_000
            aircraft.energy_remainder = numerator % 1_000
            self._advance_position(aircraft, definition, tick_ms, state, events)
            if aircraft.energy_units <= 0 and aircraft.position != definition.home:
                self._set_mode(state, aircraft, AircraftMode.MISSION_FAILED, events)
            refresh_energy_reserve(
                state, aircraft, definition, events, at_ms=state.simulation_time_ms,
            )
        return state, tuple(events)

    def _advance_position(
        self,
        aircraft: AircraftState,
        definition: AircraftDefinition,
        tick_ms: int,
        state: WorldState,
        events: list[DomainEvent],
    ) -> None:
        if aircraft.mode not in (
            AircraftMode.TRANSIT, AircraftMode.SEARCH, AircraftMode.RETURN_TO_BASE,
        ):
            return
        speed = (
            definition.return_speed_mm_per_s
            if aircraft.mode == AircraftMode.RETURN_TO_BASE
            else definition.speed_mm_per_s
        )
        numerator = speed * tick_ms + aircraft.movement_remainder
        remaining = numerator // 1_000
        aircraft.movement_remainder = numerator % 1_000
        while remaining > 0 and aircraft.route_leg < len(aircraft.route.waypoints):
            target = aircraft.route.waypoints[aircraft.route_leg]
            if aircraft.route_leg_target != target or aircraft.route_leg_start is None:
                aircraft.route_leg_start = aircraft.position
                aircraft.route_leg_target = target
                aircraft.route_leg_distance_mm = distance_mm(aircraft.position, target)
                aircraft.route_leg_progress_mm = 0
            distance = aircraft.route_leg_distance_mm
            if distance == 0:
                aircraft.route_leg += 1
                _reset_route_leg_progress(aircraft)
                continue
            budget = min(remaining, distance - aircraft.route_leg_progress_mm)
            start = aircraft.route_leg_start
            aircraft.heading_mdeg = heading_mdeg(target.x_mm - start.x_mm, target.y_mm - start.y_mm)
            aircraft.route_leg_progress_mm += budget
            if aircraft.route_leg_progress_mm == distance:
                aircraft.position = target
                aircraft.route_leg += 1
                _reset_route_leg_progress(aircraft)
            else:
                aircraft.position = PointMM(
                    start.x_mm + (target.x_mm - start.x_mm) * aircraft.route_leg_progress_mm // distance,
                    start.y_mm + (target.y_mm - start.y_mm) * aircraft.route_leg_progress_mm // distance,
                )
            remaining -= budget
        self._update_route_completion(aircraft, state, events)

    def _update_route_completion(
        self, aircraft: AircraftState, state: WorldState, events: list[DomainEvent]) -> None:
        if aircraft.route_leg < len(aircraft.route.waypoints):
            if aircraft.route.waypoints:
                aircraft.mission_progress_ppm = min(
                    999_999, aircraft.route_leg * 1_000_000 // len(aircraft.route.waypoints),
                )
            return
        if aircraft.route.waypoints:
            aircraft.mission_progress_ppm = 1_000_000
        if aircraft.mode == AircraftMode.TRANSIT:
            self._set_mode(state, aircraft, AircraftMode.SEARCH, events)
        elif aircraft.mode == AircraftMode.RETURN_TO_BASE and aircraft.position == self._aircraft_definitions[aircraft.aircraft_id].home:
            self._set_mode(state, aircraft, AircraftMode.RECOVERED, events)

    def _set_mode(
        self,
        state: WorldState,
        aircraft: AircraftState,
        mode: AircraftMode,
        events: list[DomainEvent],
    ) -> None:
        if aircraft.mode == mode:
            return
        previous = aircraft.mode
        aircraft.previous_mode = previous
        aircraft.mode = mode
        events.append(_emit(
            state,
            kind="AIRCRAFT_MODE_CHANGED",
            entity_ids=(aircraft.aircraft_id,),
            payload={"from": previous.value, "to": mode.value},
        ))

def _initial_aircraft_state(definition: AircraftDefinition) -> AircraftState:
    return AircraftState(
        aircraft_id=definition.aircraft_id,
        position=definition.home,
        heading_mdeg=0,
        energy_units=definition.energy.initial_units,
        predicted_home_reserve_units=definition.energy.initial_units,
        mode=AircraftMode.READY,
        previous_mode=None,
        link=definition.initial_link,
        sensor=definition.initial_sensor,
        assigned_sector_id=None,
        route=Route(()),
        route_leg=0,
        movement_remainder=0,
        energy_remainder=0,
        lost_link_since_ms=None,
        last_communication_ms=0,
        next_sensor_scan_ms=definition.sensor.scan_interval_ms,
        mission_progress_ppm=0,
        last_accepted_command_id=None,
    )


def _reset_route_leg_progress(aircraft: AircraftState) -> None:
    aircraft.route_leg_start = None
    aircraft.route_leg_target = None
    aircraft.route_leg_distance_mm = 0
    aircraft.route_leg_progress_mm = 0


def _consumption_rate(mode: AircraftMode, definition: AircraftDefinition) -> int:
    if mode in (AircraftMode.TRANSIT, AircraftMode.RETURN_TO_BASE):
        return definition.energy.transit_units_per_s
    if mode == AircraftMode.SEARCH:
        return definition.energy.search_units_per_s
    return definition.energy.idle_units_per_s


def _emit(
    state: WorldState, *, kind: str, entity_ids: tuple[str, ...], payload: dict[str, object],
) -> DomainEvent:
    from matb_integration.suas.domain.enums import EventKind

    state.event_sequence += 1
    return DomainEvent(
        event_id=f"{state.block_id}:{state.event_sequence:08d}",
        sequence=state.event_sequence,
        simulation_time_ms=state.simulation_time_ms,
        kind=EventKind(kind),
        entity_ids=entity_ids,
        payload=payload,
    )
