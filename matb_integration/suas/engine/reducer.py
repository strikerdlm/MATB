"""Authoritative validation and application of typed operator commands."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from matb_integration.suas.domain.commands import (
    AcknowledgeAlert, AssignSector, ClassifyContact, CommandEnvelope,
    CommandResult, CommandStatus, Hold, InspectContact, OperatorCommand,
    ReportContact, ResumeMission, ReturnToBase, SetContactPriority, SetWaypoint,
)
from matb_integration.suas.domain.enums import AircraftMode, EventKind, LinkState
from matb_integration.suas.domain.events import DomainEvent
from matb_integration.suas.domain.geometry import PointMM, PolygonMM, distance_mm
from matb_integration.suas.domain.models import Route, ScenarioDefinition, WorldState
from matb_integration.suas.engine.energy import ceil_div
from matb_integration.suas.engine.routes import lawnmower_route
from matb_integration.suas.engine.sensors import apply_contact_action


_AIRCRAFT_COMMANDS = (AssignSector, SetWaypoint, Hold, ResumeMission, ReturnToBase)
_TERMINAL_MODES = (AircraftMode.RECOVERED, AircraftMode.MISSION_FAILED)


class CommandReducer:
    """Apply envelopes once, retaining a private idempotency cache by command ID."""

    def __init__(self, scenario: ScenarioDefinition) -> None:
        self._scenario = scenario
        self._results: dict[str, CommandResult] = {}

    @property
    def results(self) -> dict[str, CommandResult]:
        """Return a detached result cache suitable for a private checkpoint."""

        return dict(self._results)

    def set_results(self, results: dict[str, CommandResult]) -> None:
        self._results = dict(results)

    def apply(
        self, state: WorldState, commands: Sequence[CommandEnvelope], *, tick: int,
    ) -> tuple[tuple[CommandResult, ...], tuple[DomainEvent, ...]]:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        results: list[CommandResult] = []
        events: list[DomainEvent] = []
        for envelope in commands:
            if not isinstance(envelope, CommandEnvelope):
                raise TypeError("commands must be CommandEnvelope instances")
            cached = self._results.get(envelope.command_id)
            if cached is not None:
                results.append(replace(cached, status=CommandStatus.DUPLICATE))
                continue
            result, command_events = self._apply_one(state, envelope, tick=tick)
            self._results[envelope.command_id] = result
            results.append(result)
            events.extend(command_events)
        return tuple(results), tuple(events)

    def _apply_one(
        self, state: WorldState, envelope: CommandEnvelope, *, tick: int,
    ) -> tuple[CommandResult, tuple[DomainEvent, ...]]:
        if not _valid_identifier(envelope.command_id):
            return self._reject(envelope.command_id, "invalid_command_id", state), ()
        if (
            isinstance(envelope.expected_state_version, bool)
            or not isinstance(envelope.expected_state_version, int)
            or envelope.expected_state_version < 0
        ):
            return self._reject(envelope.command_id, "invalid_state_version", state), ()
        if envelope.expected_state_version != state.version:
            return self._reject(envelope.command_id, "stale_state_version", state), ()
        command = envelope.command
        if not isinstance(command, (
            AssignSector, SetWaypoint, Hold, ResumeMission, ReturnToBase,
            AcknowledgeAlert, InspectContact, ClassifyContact, SetContactPriority, ReportContact,
        )):
            return self._reject(envelope.command_id, "unsupported_command", state), ()
        try:
            events = self._mutate(state, command)
        except _Rejected as rejected:
            return self._reject(envelope.command_id, rejected.code, state), ()
        state.version += 1
        if isinstance(command, _AIRCRAFT_COMMANDS):
            state.aircraft[command.aircraft_id].last_accepted_command_id = envelope.command_id
        return CommandResult(
            command_id=envelope.command_id,
            status=CommandStatus.ACCEPTED,
            code="accepted",
            applied_tick=tick,
            state_version=state.version,
        ), events

    def _mutate(self, state: WorldState, command: OperatorCommand) -> tuple[DomainEvent, ...]:
        if isinstance(command, AssignSector):
            aircraft = self._aircraft(state, command.aircraft_id)
            self._validate_aircraft_control(aircraft)
            try:
                sector = self._scenario.sectors[command.sector_id]
            except KeyError as error:
                raise _Rejected("unknown_sector") from error
            # Adjacent sensor footprints meet at the sector boundary; using the
            # footprint diameter avoids an energy-impossible 100 m micro-grid.
            route = lawnmower_route(sector, self._scenario.aircraft[command.aircraft_id].sensor.radius_mm * 2)
            self._validate_route(aircraft.position, route)
            self._validate_reserve(state, aircraft.aircraft_id, aircraft.position, route)
            aircraft.assigned_sector_id = command.sector_id
            self._set_route(aircraft, route)
            return self._set_mode_event(state, aircraft, AircraftMode.TRANSIT)
        if isinstance(command, SetWaypoint):
            aircraft = self._aircraft(state, command.aircraft_id)
            self._validate_aircraft_control(aircraft)
            if not isinstance(command.waypoint, PointMM):
                raise _Rejected("invalid_waypoint")
            route = Route((command.waypoint,))
            self._validate_route(aircraft.position, route)
            self._validate_reserve(state, aircraft.aircraft_id, aircraft.position, route)
            self._set_route(aircraft, route)
            return self._set_mode_event(state, aircraft, AircraftMode.TRANSIT)
        if isinstance(command, Hold):
            aircraft = self._aircraft(state, command.aircraft_id)
            self._validate_aircraft_control(aircraft)
            return self._set_mode_event(state, aircraft, AircraftMode.HOLD)
        if isinstance(command, ResumeMission):
            aircraft = self._aircraft(state, command.aircraft_id)
            self._validate_aircraft_control(aircraft)
            if aircraft.mode is not AircraftMode.HOLD or not aircraft.route.waypoints:
                raise _Rejected("invalid_mode")
            remaining = Route(aircraft.route.waypoints[aircraft.route_leg:])
            self._validate_reserve(state, aircraft.aircraft_id, aircraft.position, remaining)
            target_mode = aircraft.previous_mode
            if target_mode not in (AircraftMode.TRANSIT, AircraftMode.SEARCH):
                target_mode = AircraftMode.TRANSIT
            return self._set_mode_event(state, aircraft, target_mode)
        if isinstance(command, ReturnToBase):
            aircraft = self._aircraft(state, command.aircraft_id)
            self._validate_aircraft_control(aircraft)
            self._set_route(aircraft, Route((self._scenario.aircraft[aircraft.aircraft_id].home,)))
            return self._set_mode_event(state, aircraft, AircraftMode.RETURN_TO_BASE)
        if isinstance(command, AcknowledgeAlert):
            try:
                alert = state.alerts[command.alert_id]
            except KeyError as error:
                raise _Rejected("alert_not_found") from error
            if alert.closed_sequence is not None:
                raise _Rejected("alert_closed")
            if alert.acknowledged:
                raise _Rejected("alert_already_acknowledged")
            alert.acknowledged = True
            alert.acknowledged_sequence = state.event_sequence
            alert.acknowledged_at_ms = state.simulation_time_ms
            return ()
        if isinstance(command, InspectContact):
            self._contact(state, command.contact_id)
            return self._contact_events(state, command.contact_id, "INSPECT_CONTACT")
        if isinstance(command, ClassifyContact):
            self._contact(state, command.contact_id)
            return self._contact_events(
                state, command.contact_id, "CLASSIFY_CONTACT", classification=command.classification,
            )
        if isinstance(command, SetContactPriority):
            self._contact(state, command.contact_id)
            return self._contact_events(
                state, command.contact_id, "SET_CONTACT_PRIORITY", priority=command.priority,
            )
        if isinstance(command, ReportContact):
            self._contact(state, command.contact_id)
            if command.note_code not in self._scenario.report_note_codes:
                raise _Rejected("unknown_report_note_code")
            events = self._contact_events(state, command.contact_id, "REPORT_CONTACT")
            events[0].payload["note_code"] = command.note_code
            return events
        raise _Rejected("unsupported_command")

    def _contact_events(self, state: WorldState, contact_id: str, action: str, **values: object) -> tuple[DomainEvent, ...]:
        events = apply_contact_action(state, contact_id, action, **values)
        if not events:
            raise _Rejected("invalid_contact_workflow")
        return events

    def _aircraft(self, state: WorldState, aircraft_id: str):
        try:
            return state.aircraft[aircraft_id]
        except KeyError as error:
            raise _Rejected("aircraft_not_found") from error

    def _contact(self, state: WorldState, contact_id: str):
        try:
            return state.contacts[contact_id]
        except KeyError as error:
            raise _Rejected("contact_not_found") from error

    @staticmethod
    def _validate_aircraft_control(aircraft) -> None:
        if aircraft.link is LinkState.LOST:
            raise _Rejected("link_lost")
        if aircraft.mode in _TERMINAL_MODES or aircraft.mode is AircraftMode.LOST_LINK_PROCEDURE:
            raise _Rejected("invalid_mode")

    def _validate_route(self, start: PointMM, route: Route) -> None:
        previous = start
        for waypoint in route.waypoints:
            if not self._scenario.terrain.contains(waypoint):
                raise _Rejected("waypoint_outside_terrain")
            for zone in self._scenario.restricted_zones.values():
                if _segment_intersects_polygon(previous, waypoint, zone):
                    raise _Rejected("restricted_zone")
            previous = waypoint

    def _validate_reserve(
        self, state: WorldState, aircraft_id: str, start: PointMM, route: Route,
    ) -> None:
        definition = self._scenario.aircraft[aircraft_id]
        point = start
        distance = 0
        for waypoint in route.waypoints:
            distance += distance_mm(point, waypoint)
            point = waypoint
        distance += distance_mm(point, definition.home)
        cost = ceil_div(distance * definition.energy.transit_units_per_s, definition.return_speed_mm_per_s)
        aircraft = state.aircraft[aircraft_id]
        if aircraft.energy_units - cost < 0:
            raise _Rejected("critical_reserve")

    @staticmethod
    def _set_route(aircraft, route: Route) -> None:
        aircraft.route = route
        aircraft.route_leg = 0
        aircraft.route_leg_start = None
        aircraft.route_leg_target = None
        aircraft.route_leg_distance_mm = 0
        aircraft.route_leg_progress_mm = 0
        aircraft.movement_remainder = 0
        aircraft.mission_progress_ppm = 0

    @staticmethod
    def _set_mode_event(
        state: WorldState, aircraft, mode: AircraftMode,
    ) -> tuple[DomainEvent, ...]:
        if aircraft.mode is mode:
            return ()
        previous = aircraft.mode
        aircraft.previous_mode = previous
        aircraft.mode = mode
        state.event_sequence += 1
        return (DomainEvent(
            event_id=f"{state.block_id}:{state.event_sequence:08d}",
            sequence=state.event_sequence,
            simulation_time_ms=state.simulation_time_ms,
            kind=EventKind.AIRCRAFT_MODE_CHANGED,
            entity_ids=(aircraft.aircraft_id,),
            payload={"from": previous.value, "to": mode.value},
        ),)

    def _reject(self, command_id: str, code: str, state: WorldState) -> CommandResult:
        return CommandResult(command_id, CommandStatus.REJECTED, code, None, state.version)

class _Rejected(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


def _valid_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= 256


def _segment_intersects_polygon(start: PointMM, end: PointMM, polygon: PolygonMM) -> bool:
    if polygon.contains(start) or polygon.contains(end):
        return True
    vertices = polygon.vertices
    return any(
        _segments_intersect(start, end, vertices[index], vertices[(index + 1) % len(vertices)])
        for index in range(len(vertices))
    )


def _segments_intersect(a: PointMM, b: PointMM, c: PointMM, d: PointMM) -> bool:
    def cross(origin: PointMM, first: PointMM, second: PointMM) -> int:
        return ((first.x_mm - origin.x_mm) * (second.y_mm - origin.y_mm)
                - (first.y_mm - origin.y_mm) * (second.x_mm - origin.x_mm))
    def on(point: PointMM, left: PointMM, right: PointMM) -> bool:
        return cross(left, right, point) == 0 and min(left.x_mm, right.x_mm) <= point.x_mm <= max(left.x_mm, right.x_mm) and min(left.y_mm, right.y_mm) <= point.y_mm <= max(left.y_mm, right.y_mm)
    ab_c, ab_d, cd_a, cd_b = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
    if ab_c == 0 and on(c, a, b): return True
    if ab_d == 0 and on(d, a, b): return True
    if cd_a == 0 and on(a, c, d): return True
    if cd_b == 0 and on(b, c, d): return True
    return (ab_c > 0) != (ab_d > 0) and (cd_a > 0) != (cd_b > 0)
