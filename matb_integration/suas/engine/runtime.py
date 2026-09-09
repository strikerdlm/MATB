"""The deterministic, headless sUAS mission runtime."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from matb_integration.suas.adapters.synthetic import SyntheticVehicleBackend
from matb_integration.suas.domain.commands import CommandEnvelope, CommandResult, CommandStatus
from matb_integration.suas.domain.enums import (
    AircraftMode, AlertKind, AlertSeverity, ContactClassification, ContactEvidence,
    ContactPriority, ContactWorkflow, EventKind, LinkState, SensorState,
)
from matb_integration.suas.domain.events import AlertState, DomainEvent
from matb_integration.suas.domain.geometry import PointMM, distance_mm
from matb_integration.suas.domain.models import AircraftState, ContactState, Route, ScenarioDefinition, WorldState
from matb_integration.suas.domain.serialization import canonical_data, canonical_sha256
from matb_integration.suas.engine.clock import SimulationClock
from matb_integration.suas.engine.coverage import CoverageGrid
from matb_integration.suas.engine.links import LinkSystem
from matb_integration.suas.engine.prng import MASK_64, PCG32, PCG32State, derive_stream_seed
from matb_integration.suas.engine.reducer import CommandReducer
from matb_integration.suas.engine.separation import SeparationMonitor
from matb_integration.suas.engine.sensors import SensorSystem, public_snapshot as public_contacts


ENGINE_VERSION = "1.0.0"
TICK_MS = 100
SNAPSHOT_INTERVAL_MS = 250
CHECKPOINT_INTERVAL_MS = 5_000


@dataclass(frozen=True, slots=True)
class StepResult:
    snapshot: dict[str, object]
    events: tuple[DomainEvent, ...]
    command_results: tuple[CommandResult, ...]


class ScheduledConflictInjector:
    """Apply each declared, deterministic convergence route exactly once."""

    def __init__(self, scenario: ScenarioDefinition) -> None:
        self._scenario = scenario
        self._applied_event_ids: set[str] = set()
        self._pending_releases: dict[str, dict[str, int]] = {}

    def checkpoint_pending_releases(self) -> dict[str, dict[str, int]]:
        return {
            event_id: dict(sorted(releases.items()))
            for event_id, releases in sorted(self._pending_releases.items())
        }

    def restore_pending_releases(self, pending: dict[str, dict[str, int]]) -> None:
        self._pending_releases = {event_id: dict(releases) for event_id, releases in pending.items()}

    def step(self, state: WorldState, *, now_ms: int) -> tuple[DomainEvent, ...]:
        events: list[DomainEvent] = list(self._release_due(state, now_ms))
        due = sorted(
            (event for event in self._scenario.conflict_events
             if event.block_id == state.block_id and event.at_ms <= now_ms
             and event.event_id not in self._applied_event_ids),
            key=lambda event: (event.at_ms, event.event_id),
        )
        for event in due:
            self._applied_event_ids.add(event.event_id)
            unavailable = self._unavailable(state, event.aircraft_a, event.aircraft_b)
            if unavailable is not None:
                events.append(self._emit(
                    state, EventKind.CONFLICT_INJECTION_SKIPPED,
                    (event.aircraft_a, event.aircraft_b), event.at_ms,
                    {"event_id": event.event_id, "reason": unavailable},
                ))
                continue
            plan = self._plan(state, event, now_ms=now_ms)
            if plan is None:
                events.append(self._emit(
                    state, EventKind.CONFLICT_INJECTION_SKIPPED,
                    (event.aircraft_a, event.aircraft_b), event.at_ms,
                    {"event_id": event.event_id, "reason": "impossible_schedule"},
                ))
                continue
            release_times, movement_times = plan
            for aircraft_id in (event.aircraft_a, event.aircraft_b):
                aircraft = state.aircraft[aircraft_id]
                aircraft.route = Route((event.convergence_point,))
                aircraft.route_leg = 0
                aircraft.route_leg_start = None
                aircraft.route_leg_target = None
                aircraft.route_leg_distance_mm = 0
                aircraft.route_leg_progress_mm = 0
                aircraft.movement_remainder = 0
                aircraft.mission_progress_ppm = 0
                target_mode = AircraftMode.HOLD if release_times[aircraft_id] > now_ms else AircraftMode.TRANSIT
                if aircraft.mode is not target_mode:
                    aircraft.previous_mode = aircraft.mode
                    aircraft.mode = target_mode
            if any(release_at_ms > now_ms for release_at_ms in release_times.values()):
                self._pending_releases[event.event_id] = release_times
            events.append(self._emit(
                state, EventKind.CONFLICT_INJECTION_STARTED,
                (event.aircraft_a, event.aircraft_b), event.at_ms,
                {
                    "event_id": event.event_id,
                    "convergence_point": _point(event.convergence_point),
                    "convergence_in_ms": event.convergence_in_ms,
                    "movement_ms": movement_times,
                    "staging_delay_ms": {key: value - now_ms for key, value in sorted(release_times.items())},
                    "planned_arrival_ms": now_ms + event.convergence_in_ms,
                },
            ))
        return tuple(events)

    def _release_due(self, state: WorldState, now_ms: int) -> tuple[DomainEvent, ...]:
        events: list[DomainEvent] = []
        for event_id, releases in sorted(self._pending_releases.items()):
            remaining: dict[str, int] = {}
            for aircraft_id, release_at_ms in sorted(releases.items()):
                if release_at_ms > now_ms:
                    remaining[aircraft_id] = release_at_ms
                    continue
                aircraft = state.aircraft[aircraft_id]
                unavailable = self._unavailable(state, aircraft_id, aircraft_id)
                if unavailable is None and aircraft.mode is AircraftMode.HOLD:
                    aircraft.previous_mode = aircraft.mode
                    aircraft.mode = AircraftMode.TRANSIT
                    events.append(self._emit(
                        state, EventKind.AIRCRAFT_MODE_CHANGED, (aircraft_id,), now_ms,
                        {"from": AircraftMode.HOLD.value, "to": AircraftMode.TRANSIT.value,
                         "conflict_event_id": event_id},
                    ))
            if remaining:
                self._pending_releases[event_id] = remaining
            else:
                del self._pending_releases[event_id]
        return tuple(events)

    def _plan(
        self, state: WorldState, event, *, now_ms: int,
    ) -> tuple[dict[str, int], dict[str, int]] | None:
        """Return deterministic release and travel durations, or no safe schedule.

        Aircraft move at a fixed adapter speed.  A direct route cannot arrive
        earlier than its fixed-point travel duration, so an over-constrained
        scenario is explicitly skipped.  When time remains, the aircraft stages
        in HOLD before release; its direct route then reaches convergence at the
        configured interval without changing speed or teleporting position.
        """
        movement_times: dict[str, int] = {}
        for aircraft_id in (event.aircraft_a, event.aircraft_b):
            aircraft = state.aircraft[aircraft_id]
            speed = self._scenario.aircraft[aircraft_id].speed_mm_per_s
            distance = distance_mm(aircraft.position, event.convergence_point)
            movement_times[aircraft_id] = _ceil_div(distance * 1_000, speed * TICK_MS) * TICK_MS
        if any(movement_ms > event.convergence_in_ms for movement_ms in movement_times.values()):
            return None
        releases = {
            # Conflict planning happens immediately before the adapter advances
            # the state for this clock tick.  Stage one tick so the first travel
            # increment begins after injection, not in its already-elapsed slot.
            aircraft_id: now_ms + event.convergence_in_ms - movement_ms + TICK_MS
            for aircraft_id, movement_ms in movement_times.items()
        }
        if any(release_at_ms % TICK_MS for release_at_ms in releases.values()):
            return None
        return releases, movement_times

    @staticmethod
    def _unavailable(state: WorldState, first: str, second: str) -> str | None:
        for aircraft_id in (first, second):
            aircraft = state.aircraft.get(aircraft_id)
            if aircraft is None:
                return "aircraft_not_in_block"
            if aircraft.link is LinkState.LOST or aircraft.mode is AircraftMode.LOST_LINK_PROCEDURE:
                return "lost_link"
            if aircraft.mode is AircraftMode.RECOVERED:
                return "recovered"
            if aircraft.mode is AircraftMode.MISSION_FAILED:
                return "mission_failed"
        return None

    @staticmethod
    def _emit(state: WorldState, kind: EventKind, entity_ids: tuple[str, ...], at_ms: int, payload: dict) -> DomainEvent:
        state.event_sequence += 1
        return DomainEvent(
            event_id=f"{state.block_id}:{state.event_sequence:08d}", sequence=state.event_sequence,
            simulation_time_ms=at_ms, kind=kind, entity_ids=entity_ids, payload=payload,
        )


class SimulationEngine:
    """Owns every mutable Phase 1 subsystem and exposes safe snapshots only."""

    def __init__(self, scenario: ScenarioDefinition, block_id: str) -> None:
        if not isinstance(scenario, ScenarioDefinition):
            raise TypeError("scenario must be a ScenarioDefinition")
        try:
            block = scenario.blocks[block_id]
        except KeyError as error:
            raise ValueError(f"unknown block {block_id}") from error
        self._scenario = scenario
        self._block_id = block.block_id
        self._clock = SimulationClock(tick_ms=TICK_MS)
        self._backend = SyntheticVehicleBackend()
        self._state = self._backend.initialize(scenario, block)
        self._sensors = SensorSystem(scenario)
        self._reducer = CommandReducer(scenario, self._sensors)
        self._links = LinkSystem(scenario)
        self._conflicts = ScheduledConflictInjector(scenario)
        self._coverage = CoverageGrid(scenario)
        self._separation = SeparationMonitor(
            advisory_mm=scenario.advisory_separation_mm,
            critical_mm=scenario.critical_separation_mm,
        )

    def step(self, commands: Sequence[CommandEnvelope] = ()) -> StepResult:
        if not isinstance(commands, Sequence):
            raise TypeError("commands must be a sequence")
        self._clock.advance()
        results, command_events = self._reducer.apply(self._state, commands, tick=self._clock.tick)
        link_events = self._run_discrete(self._links.step, self._state, now_ms=self._clock.simulation_time_ms)
        conflict_events = self._run_discrete(self._conflicts.step, self._state, now_ms=self._clock.simulation_time_ms)
        before = _discrete_fingerprint(self._state)
        self._state, vehicle_events = self._backend.advance(self._state, tick_ms=TICK_MS)
        self._increment_for_discrete_change(before)
        sensor_events = self._run_discrete(
            self._sensors.step, self._state, now_ms=self._clock.simulation_time_ms, coverage=self._coverage,
        )
        # SensorSystem owns scan-time coverage updates so scan charging, evidence,
        # and coverage remain one ordered atomic subsystem batch.
        coverage_events: tuple[DomainEvent, ...] = ()
        separation_events = self._run_discrete(self._separation.step, self._state)
        events = self._sequence(
            command_events + link_events + conflict_events + vehicle_events
            + sensor_events + coverage_events + separation_events,
        )
        return StepResult(self.snapshot(), events, results)

    def _run_discrete(self, method, *args, **kwargs) -> tuple[DomainEvent, ...]:
        before = _discrete_fingerprint(self._state)
        events = method(*args, **kwargs)
        self._increment_for_discrete_change(before)
        return events

    def _increment_for_discrete_change(self, before: object) -> None:
        if before != _discrete_fingerprint(self._state):
            self._state.version += 1

    @staticmethod
    def _sequence(events: tuple[DomainEvent, ...]) -> tuple[DomainEvent, ...]:
        # Producers allocate monotonically from one state counter. Sorting is a
        # defensive assertion of that contract, not a second source of sequence IDs.
        ordered = tuple(sorted(events, key=lambda event: event.sequence))
        if len({event.sequence for event in ordered}) != len(ordered):
            raise RuntimeError("duplicate event sequence")
        return ordered

    @property
    def state_hash(self) -> str:
        return self.checkpoint_snapshot()["authoritative_state_sha256"]  # type: ignore[return-value]

    def snapshot(self) -> dict[str, object]:
        """Return a sorted redacted projection; never use this as a checkpoint."""
        terrain_bounds = self._scenario.terrain.bounds
        aircraft = {
            aircraft_id: {
                "aircraft_id": aircraft_id,
                "label": self._scenario.aircraft[aircraft_id].label,
                "position": _point(item.position),
                "heading_mdeg": item.heading_mdeg,
                "altitude_mm": self._scenario.aircraft[aircraft_id].altitude_mm,
                "energy_units": item.energy_units,
                "predicted_home_reserve_units": item.predicted_home_reserve_units,
                "mode": item.mode.value,
                "link": item.link.value,
                "sensor": item.sensor.value,
                "assigned_sector_id": item.assigned_sector_id,
                "route": [_point(point) for point in item.route.waypoints],
                "mission_progress_ppm": item.mission_progress_ppm,
            }
            for aircraft_id, item in sorted(self._state.aircraft.items())
        }
        return {
            "scenario_id": self._scenario.scenario_id,
            "scenario_sha256": self._scenario.scenario_sha256,
            "block_id": self._block_id,
            "tick": self._state.tick,
            "simulation_time_ms": self._state.simulation_time_ms,
            "state_version": self._state.version,
            "state_sha256": self.state_hash,
            "title": {locale.value: text for locale, text in sorted(self._scenario.title.items(), key=lambda item: item[0].value)},
            "description": {locale.value: text for locale, text in sorted(self._scenario.description.items(), key=lambda item: item[0].value)},
            "terrain": {
                "bounds": {"min_x_mm": terrain_bounds[0], "min_y_mm": terrain_bounds[1], "max_x_mm": terrain_bounds[2], "max_y_mm": terrain_bounds[3]},
                "polygon": [_point(point) for point in self._scenario.terrain.vertices],
            },
            "home": _point(self._scenario.home),
            "initial_view": {
                "center": _point(self._scenario.initial_view.center),
                "width_mm": self._scenario.initial_view.width_mm,
                "height_mm": self._scenario.initial_view.height_mm,
            },
            "sectors": {key: [_point(point) for point in polygon.vertices] for key, polygon in sorted(self._scenario.sectors.items())},
            "restricted_zones": {key: [_point(point) for point in polygon.vertices] for key, polygon in sorted(self._scenario.restricted_zones.items())},
            "report_note_codes": {
                code: {locale.value: text for locale, text in sorted(labels.items(), key=lambda item: item[0].value)}
                for code, labels in sorted(self._scenario.report_note_codes.items())
            },
            "aircraft": aircraft,
            **public_contacts(self._state, scenario=self._scenario),
            "alerts": {key: canonical_data(value) for key, value in sorted(self._state.alerts.items())},
            "coverage": self._coverage.public_snapshot(self._state),
        }

    def checkpoint_snapshot(self) -> dict[str, object]:
        payload = self._checkpoint_payload()
        return {**payload, "authoritative_state_sha256": canonical_sha256(payload)}

    def _checkpoint_payload(self) -> dict[str, object]:
        streams = {
            key: canonical_data(stream.get_state())
            for key, stream in sorted(self._sensors._streams.items())
        }
        return {
            "engine_version": ENGINE_VERSION,
            "scenario_id": self._scenario.scenario_id,
            "scenario_sha256": self._scenario.scenario_sha256,
            "block_id": self._block_id,
            "clock": {"tick_ms": self._clock.tick_ms, "simulation_time_ms": self._clock.simulation_time_ms, "paused": self._clock.paused},
            "tick": self._state.tick,
            "simulation_time_ms": self._state.simulation_time_ms,
            "state_version": self._state.version,
            "world": canonical_data(self._state),
            "sensor_prng": streams,
            "sensor_reports": canonical_data(self._sensors._reports),
            "link_applied_event_ids": sorted(self._links._applied_event_ids),
            "conflict_applied_event_ids": sorted(self._conflicts._applied_event_ids),
            "conflict_pending_releases": self._conflicts.checkpoint_pending_releases(),
            "sensor_due_times": {key: value.next_sensor_scan_ms for key, value in sorted(self._state.aircraft.items())},
            "coverage_cells": [[x, y] for x, y in sorted(self._state.coverage_cells)],
            "separation": self._separation.checkpoint_state(),
            "command_results": {key: canonical_data(value) for key, value in sorted(self._reducer.results.items())},
        }

    def restore(self, checkpoint_snapshot: Mapping[str, object]) -> None:
        """Validate privately first, then atomically replace all mutable subsystems."""
        if not isinstance(checkpoint_snapshot, Mapping):
            raise TypeError("checkpoint must be a mapping")
        raw = dict(checkpoint_snapshot)
        digest = raw.pop("authoritative_state_sha256", None)
        if not isinstance(digest, str) or canonical_sha256(raw) != digest:
            raise ValueError("invalid authoritative checkpoint hash")
        candidate = SimulationEngine(self._scenario, self._block_id)
        candidate._restore_validated(raw)
        self.__dict__.update(candidate.__dict__)

    def _restore_validated(self, raw: dict[str, object]) -> None:
        required = {
            "engine_version", "scenario_id", "scenario_sha256", "block_id", "clock", "tick",
            "simulation_time_ms", "state_version", "world", "sensor_prng", "sensor_reports",
            "link_applied_event_ids", "conflict_applied_event_ids", "conflict_pending_releases", "sensor_due_times", "coverage_cells",
            "separation", "command_results",
        }
        if set(raw) != required:
            raise ValueError("checkpoint has an invalid private shape")
        if raw["engine_version"] != ENGINE_VERSION:
            raise ValueError("checkpoint engine version does not match")
        if raw["scenario_id"] != self._scenario.scenario_id or raw["scenario_sha256"] != self._scenario.scenario_sha256:
            raise ValueError("checkpoint scenario does not match")
        if raw["block_id"] != self._block_id:
            raise ValueError("checkpoint block does not match")
        clock = _mapping(raw["clock"], "clock")
        if set(clock) != {"tick_ms", "simulation_time_ms", "paused"} or clock["tick_ms"] != TICK_MS:
            raise ValueError("invalid checkpoint clock")
        time_ms = _nonnegative(clock["simulation_time_ms"], "clock simulation time")
        if not isinstance(clock["paused"], bool):
            raise ValueError("invalid checkpoint clock")
        tick = _nonnegative(raw["tick"], "tick")
        state_time = _nonnegative(raw["simulation_time_ms"], "simulation time")
        version = _nonnegative(raw["state_version"], "state version")
        if time_ms != state_time or tick != time_ms // TICK_MS:
            raise ValueError("checkpoint clock and world counters do not match")
        state = _world(_mapping(raw["world"], "world"), self._scenario, self._block_id)
        if state.tick != tick or state.simulation_time_ms != time_ms or state.version != version:
            raise ValueError("checkpoint world counters do not match")
        due = _mapping(raw["sensor_due_times"], "sensor due times")
        if set(due) != set(state.aircraft) or any(
            isinstance(due[key], bool)
            or not isinstance(due[key], int)
            or due[key] != value.next_sensor_scan_ms
            or due[key] != _expected_sensor_due_time(
                time_ms, self._scenario.aircraft[key].sensor.scan_interval_ms,
            )
            for key, value in state.aircraft.items()
        ):
            raise ValueError("checkpoint sensor due times do not match")
        coverage = raw["coverage_cells"]
        if not isinstance(coverage, list) or sorted([list(cell) for cell in state.coverage_cells]) != coverage:
            raise ValueError("checkpoint coverage does not match")
        self._clock = SimulationClock(tick_ms=TICK_MS, simulation_time_ms=time_ms, paused=clock["paused"])
        self._state = state
        self._links._applied_event_ids = _scheduled_ids(
            raw["link_applied_event_ids"], self._scenario.link_events, self._block_id, time_ms, "link event IDs",
        )
        self._conflicts._applied_event_ids = _scheduled_ids(
            raw["conflict_applied_event_ids"], self._scenario.conflict_events, self._block_id, time_ms, "conflict event IDs",
        )
        self._conflicts.restore_pending_releases(_pending_conflicts(
            raw["conflict_pending_releases"], self._scenario, self._block_id, time_ms, state,
            self._conflicts._applied_event_ids,
        ))
        streams = _mapping(raw["sensor_prng"], "sensor PRNG")
        self._sensors._streams = {
            key: PCG32.from_state(_pcg_for_pair(key, value, state, self._scenario))
            for key, value in streams.items()
        }
        reports = _mapping(raw["sensor_reports"], "sensor reports")
        if any(not isinstance(key, str) or not isinstance(value, list) for key, value in reports.items()):
            raise ValueError("invalid sensor reports")
        self._sensors._reports = {key: [dict(item) for item in value if isinstance(item, Mapping)] for key, value in reports.items()}
        if any(len(self._sensors._reports[key]) != len(value) for key, value in reports.items()):
            raise ValueError("invalid sensor report record")
        _validate_reports(self._sensors._reports, state, self._scenario)
        self._separation.restore_state(
            _mapping(raw["separation"], "separation"), state=state,
        )
        result_raw = _mapping(raw["command_results"], "command results")
        results: dict[str, CommandResult] = {}
        for key, value in result_raw.items():
            item = _mapping(value, "command result")
            if key != item.get("command_id"):
                raise ValueError("invalid command result cache")
            results[key] = CommandResult(
                command_id=_string(item.get("command_id"), "command id"),
                status=CommandStatus(_string(item.get("status"), "command status")),
                code=_string(item.get("code"), "command code"),
                applied_tick=_optional_nonnegative(item.get("applied_tick"), "applied tick"),
                state_version=_nonnegative(item.get("state_version"), "command state version"),
            )
        self._reducer.set_results(results)


def _discrete_fingerprint(state: WorldState) -> object:
    return (
        tuple((key, item.mode.value, item.link.value, item.sensor.value, item.assigned_sector_id,
               tuple(item.route.waypoints), item.lost_link_since_ms) for key, item in sorted(state.aircraft.items())),
        tuple((key, item.evidence.value, item.workflow.value,
               item.classification.value if item.classification else None,
               item.priority.value if item.priority else None, item.revision,
               tuple(item.report_ids), item.last_reported_revision) for key, item in sorted(state.contacts.items())),
        tuple((key, value.closed_sequence, value.acknowledged, value.payload) for key, value in sorted(state.alerts.items())),
    )


def _point(point: PointMM) -> dict[str, int]:
    return {"x_mm": point.x_mm, "y_mm": point.y_mm}


def _mapping(value: object, name: str) -> dict:
    if not isinstance(value, Mapping):
        raise ValueError(f"invalid checkpoint {name}")
    return dict(value)


def _string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"invalid checkpoint {name}")
    return value


def _nonnegative(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"invalid checkpoint {name}")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"invalid checkpoint {name}")
    return value


def _expected_sensor_due_time(now_ms: int, interval_ms: int) -> int:
    return (now_ms // interval_ms + 1) * interval_ms


def _optional_nonnegative(value: object, name: str) -> int | None:
    return None if value is None else _nonnegative(value, name)


def _id_set(value: object, name: str) -> set[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value) or value != sorted(set(value)):
        raise ValueError(f"invalid checkpoint {name}")
    return set(value)


def _scheduled_ids(value: object, declarations, block_id: str, now_ms: int, name: str) -> set[str]:
    applied = _id_set(value, name)
    active = {event.event_id: event for event in declarations if event.block_id == block_id}
    due = {event_id for event_id, event in active.items() if event.at_ms <= now_ms}
    if not applied.issubset(active) or not applied.issubset(due):
        raise ValueError(f"invalid checkpoint {name}")
    # Engine checkpoints are emitted only after a complete tick, so every due
    # declaration has either started or been safely skipped exactly once.
    if applied != due:
        raise ValueError(f"checkpoint {name} omit a due event")
    return applied


def _pending_conflicts(
    value: object, scenario: ScenarioDefinition, block_id: str, now_ms: int,
    state: WorldState, applied: set[str],
) -> dict[str, dict[str, int]]:
    raw = _mapping(value, "conflict pending releases")
    declarations = {
        event.event_id: event for event in scenario.conflict_events if event.block_id == block_id
    }
    if not set(raw).issubset(applied):
        raise ValueError("invalid checkpoint conflict pending releases")
    result: dict[str, dict[str, int]] = {}
    for event_id in applied:
        event = declarations[event_id]
        expected_pending: dict[str, int] = {}
        retained_plan = False
        valid_released: set[str] = set()
        for aircraft_id in (event.aircraft_a, event.aircraft_b):
            release_at_ms = _conflict_release_from_retained_route(
                state, event, scenario, aircraft_id,
            )
            if release_at_ms is None:
                if _is_legitimate_released_conflict_aircraft(state, event, aircraft_id):
                    valid_released.add(aircraft_id)
                continue
            retained_plan = True
            if release_at_ms > now_ms:
                if not _is_conflict_staging_aircraft(state, event, aircraft_id):
                    raise ValueError("invalid checkpoint conflict pending releases")
                expected_pending[aircraft_id] = release_at_ms
            elif _is_legitimate_released_conflict_aircraft(state, event, aircraft_id):
                valid_released.add(aircraft_id)
            else:
                raise ValueError("invalid checkpoint released conflict state")
        if retained_plan and set(expected_pending) | valid_released != {
            event.aircraft_a, event.aircraft_b,
        }:
            raise ValueError("invalid checkpoint released conflict state")
        release_value = raw.get(event_id)
        if expected_pending:
            if release_value is None:
                raise ValueError("checkpoint omits a pending conflict release")
            releases = _mapping(release_value, "conflict pending release")
            parsed = {
                aircraft_id: _nonnegative(at_ms, "conflict release time")
                for aircraft_id, at_ms in releases.items()
            }
            if parsed != expected_pending:
                raise ValueError("invalid checkpoint conflict pending releases")
            if any(at_ms % TICK_MS for at_ms in parsed.values()):
                raise ValueError("invalid checkpoint conflict pending releases")
            for aircraft_id in expected_pending:
                if not _is_conflict_staging_aircraft(state, event, aircraft_id):
                    raise ValueError("invalid checkpoint conflict pending releases")
            result[event_id] = parsed
        elif release_value is not None:
            raise ValueError("invalid checkpoint conflict pending releases")
    return result


def _conflict_release_from_retained_route(
    state: WorldState, event, scenario: ScenarioDefinition, aircraft_id: str,
) -> int | None:
    """Derive one release independently when its injected route is still retained."""

    aircraft = state.aircraft.get(aircraft_id)
    if aircraft is None:
        return None
    if _is_conflict_staging_aircraft(state, event, aircraft_id):
        start = aircraft.position
    elif (
        aircraft.route.waypoints == (event.convergence_point,)
        and aircraft.route_leg == 0
        and aircraft.route_leg_start is not None
        and aircraft.route_leg_target == event.convergence_point
    ):
        start = aircraft.route_leg_start
    else:
        return None
    speed = scenario.aircraft[aircraft_id].speed_mm_per_s
    movement_ms = _ceil_div(
        distance_mm(start, event.convergence_point) * 1_000, speed * TICK_MS,
    ) * TICK_MS
    if movement_ms > event.convergence_in_ms:
        return None
    return event.at_ms + event.convergence_in_ms - movement_ms + TICK_MS


def _is_conflict_staging_aircraft(state: WorldState, event, aircraft_id: str) -> bool:
    aircraft = state.aircraft.get(aircraft_id)
    if aircraft is None or aircraft.mode is not AircraftMode.HOLD:
        return False
    if aircraft.route.waypoints != (event.convergence_point,) or aircraft.route_leg != 0:
        return False
    return not (
        aircraft.route_leg_start is not None or aircraft.route_leg_target is not None
        or aircraft.route_leg_distance_mm or aircraft.route_leg_progress_mm
        or aircraft.movement_remainder
    )


def _is_legitimate_released_conflict_aircraft(state: WorldState, event, aircraft_id: str) -> bool:
    aircraft = state.aircraft.get(aircraft_id)
    if aircraft is None:
        return False
    if (
        aircraft.mode is AircraftMode.TRANSIT
        and aircraft.route.waypoints == (event.convergence_point,)
        and aircraft.route_leg == 0
        and aircraft.route_leg_start is not None
        and aircraft.route_leg_target == event.convergence_point
        and 0 < aircraft.route_leg_progress_mm < aircraft.route_leg_distance_mm
    ):
        return True
    if (
        aircraft.mode is AircraftMode.SEARCH
        and aircraft.position == event.convergence_point
        and aircraft.route_leg == 1
        and aircraft.route.waypoints == (event.convergence_point,)
    ):
        return True
    # A later safety/autonomy or operator command can legitimately take route
    # ownership after a release; these states no longer carry a pending entry.
    return aircraft.mode in (
        AircraftMode.HOLD, AircraftMode.RETURN_TO_BASE, AircraftMode.LOST_LINK_PROCEDURE,
        AircraftMode.RECOVERED, AircraftMode.MISSION_FAILED,
    )


def _pcg(value: object) -> PCG32State:
    raw = _mapping(value, "PCG state")
    if set(raw) != {"state", "increment"}:
        raise ValueError("invalid checkpoint PCG state")
    state, increment = _nonnegative(raw["state"], "PCG state"), _nonnegative(raw["increment"], "PCG increment")
    if state > MASK_64 or increment > MASK_64 or not increment & 1:
        raise ValueError("invalid checkpoint PCG state")
    return PCG32State(state=state, increment=increment)


def _pcg_for_pair(
    key: object, value: object, state: WorldState, scenario: ScenarioDefinition,
) -> PCG32State:
    if not isinstance(key, str) or key.count(":") != 1:
        raise ValueError("invalid checkpoint sensor PRNG key")
    aircraft_id, contact_id = key.split(":")
    if aircraft_id not in state.aircraft or contact_id not in state.contacts:
        raise ValueError("invalid checkpoint sensor PRNG key")
    parsed = _pcg(value)
    _, stream = derive_stream_seed(scenario.seed, "sensor", key)
    if parsed.increment != ((stream << 1) | 1) & MASK_64:
        raise ValueError("invalid checkpoint sensor PRNG increment")
    return parsed


def _validate_reports(reports: dict[str, list[dict[str, object]]], state: WorldState, scenario: ScenarioDefinition) -> None:
    if not set(reports).issubset(state.contacts):
        raise ValueError("invalid sensor reports")
    for contact_id, contact in state.contacts.items():
        history = reports.get(contact_id, [])
        if [item.get("report_id") for item in history] != contact.report_ids:
            raise ValueError("checkpoint report history does not match world")
        revisions: list[int] = []
        parsed_classifications: list[ContactClassification] = []
        parsed_priorities: list[ContactPriority] = []
        for index, report in enumerate(history):
            if set(report) != {"report_id", "replaces_report_id", "revision", "classification", "priority", "note_code"}:
                raise ValueError("invalid checkpoint report record")
            if report["report_id"] != f"{contact_id}:R{index + 1:04d}":
                raise ValueError("invalid checkpoint report record")
            expected_replacement = None if index == 0 else f"{contact_id}:R{index:04d}"
            if report["replaces_report_id"] != expected_replacement:
                raise ValueError("invalid checkpoint report record")
            if (isinstance(report["revision"], bool) or not isinstance(report["revision"], int)
                    or report["revision"] < 0):
                raise ValueError("invalid checkpoint report record")
            try:
                parsed_classifications.append(ContactClassification(report["classification"]))
                parsed_priorities.append(ContactPriority(report["priority"]))
            except (TypeError, ValueError) as error:
                raise ValueError("invalid checkpoint report record") from error
            if report["note_code"] is not None and report["note_code"] not in scenario.report_note_codes:
                raise ValueError("invalid checkpoint report record")
            revisions.append(report["revision"])
        if not history:
            if contact.last_reported_revision is not None or contact.workflow is ContactWorkflow.REPORTED:
                raise ValueError("checkpoint report state does not match history")
            continue
        if contact.workflow is not ContactWorkflow.REPORTED:
            raise ValueError("checkpoint report state does not match history")
        if any(current <= previous for previous, current in zip(revisions, revisions[1:])):
            raise ValueError("checkpoint report revisions are not strictly increasing")
        if revisions[-1] != contact.last_reported_revision:
            raise ValueError("checkpoint report revision does not match world")
        if revisions[-1] > contact.revision:
            raise ValueError("checkpoint report revision is unreachable")
        if contact.revision == revisions[-1] and (
            contact.classification is not parsed_classifications[-1]
            or contact.priority is not parsed_priorities[-1]
        ):
            raise ValueError("checkpoint report values do not match world revision")


def _ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)


def _world(raw: dict, scenario: ScenarioDefinition, block_id: str) -> WorldState:
    expected = {"block_id", "tick", "simulation_time_ms", "version", "aircraft", "contacts", "alerts", "coverage_cells", "event_sequence", "scenario_sha256"}
    if set(raw) != expected or raw["block_id"] != block_id or raw["scenario_sha256"] != scenario.scenario_sha256:
        raise ValueError("invalid checkpoint world")
    air_raw, contacts_raw, alerts_raw = _mapping(raw["aircraft"], "aircraft"), _mapping(raw["contacts"], "contacts"), _mapping(raw["alerts"], "alerts")
    block = scenario.blocks[block_id]
    if set(air_raw) != set(block.aircraft_ids) or set(contacts_raw) != set(block.contact_ids):
        raise ValueError("checkpoint entity sets do not match")
    aircraft = {key: _aircraft(_mapping(value, "aircraft")) for key, value in air_raw.items()}
    contacts = {key: _contact(_mapping(value, "contact")) for key, value in contacts_raw.items()}
    if any(value.aircraft_id != key for key, value in aircraft.items()) or any(value.contact_id != key for key, value in contacts.items()):
        raise ValueError("checkpoint entity IDs do not match")
    alerts = {key: _alert(_mapping(value, "alert")) for key, value in alerts_raw.items()}
    if any(value.alert_id != key for key, value in alerts.items()):
        raise ValueError("checkpoint alert IDs do not match")
    cells = raw["coverage_cells"]
    if not isinstance(cells, list) or any(not isinstance(cell, list) or len(cell) != 2 for cell in cells):
        raise ValueError("invalid checkpoint coverage")
    coverage = {(_nonnegative(cell[0], "coverage x"), _nonnegative(cell[1], "coverage y")) for cell in cells}
    if len(coverage) != len(cells):
        raise ValueError("invalid checkpoint coverage")
    return WorldState(
        block_id=block_id, tick=_nonnegative(raw["tick"], "world tick"),
        simulation_time_ms=_nonnegative(raw["simulation_time_ms"], "world time"),
        version=_nonnegative(raw["version"], "world version"), aircraft=aircraft, contacts=contacts,
        alerts=alerts, coverage_cells=coverage, event_sequence=_nonnegative(raw["event_sequence"], "event sequence"),
        scenario_sha256=scenario.scenario_sha256,
    )


def _as_point(value: object) -> PointMM:
    raw = _mapping(value, "point")
    if set(raw) != {"x_mm", "y_mm"}:
        raise ValueError("invalid checkpoint point")
    return PointMM(_integer(raw["x_mm"], "point x"), _integer(raw["y_mm"], "point y"))


def _aircraft(raw: dict) -> AircraftState:
    route = _mapping(raw.get("route"), "route")
    points = route.get("waypoints")
    if not isinstance(points, list): raise ValueError("invalid checkpoint route")
    target = raw.get("route_leg_target")
    start = raw.get("route_leg_start")
    return AircraftState(
        aircraft_id=_string(raw.get("aircraft_id"), "aircraft ID"), position=_as_point(raw.get("position")),
        heading_mdeg=_nonnegative(raw.get("heading_mdeg"), "heading"), energy_units=_integer(raw.get("energy_units"), "energy"),
        predicted_home_reserve_units=_integer(raw.get("predicted_home_reserve_units"), "reserve"),
        mode=AircraftMode(_string(raw.get("mode"), "mode")), previous_mode=AircraftMode(raw["previous_mode"]) if raw.get("previous_mode") is not None else None,
        link=LinkState(_string(raw.get("link"), "link")), sensor=SensorState(_string(raw.get("sensor"), "sensor")),
        assigned_sector_id=raw.get("assigned_sector_id") if raw.get("assigned_sector_id") is None or isinstance(raw.get("assigned_sector_id"), str) else _raise("invalid sector"),
        route=Route(tuple(_as_point(point) for point in points)), route_leg=_nonnegative(raw.get("route_leg"), "route leg"),
        movement_remainder=_nonnegative(raw.get("movement_remainder"), "movement remainder"), energy_remainder=_nonnegative(raw.get("energy_remainder"), "energy remainder"),
        lost_link_since_ms=_optional_nonnegative(raw.get("lost_link_since_ms"), "lost link time"), last_communication_ms=_nonnegative(raw.get("last_communication_ms"), "communication time"),
        next_sensor_scan_ms=_nonnegative(raw.get("next_sensor_scan_ms"), "sensor time"), mission_progress_ppm=_nonnegative(raw.get("mission_progress_ppm"), "mission progress"),
        last_accepted_command_id=raw.get("last_accepted_command_id") if raw.get("last_accepted_command_id") is None or isinstance(raw.get("last_accepted_command_id"), str) else _raise("invalid command ID"),
        route_leg_start=_as_point(start) if start is not None else None, route_leg_target=_as_point(target) if target is not None else None,
        route_leg_distance_mm=_nonnegative(raw.get("route_leg_distance_mm"), "route distance"), route_leg_progress_mm=_nonnegative(raw.get("route_leg_progress_mm"), "route progress"),
    )


def _contact(raw: dict) -> ContactState:
    reports = raw.get("report_ids")
    if not isinstance(reports, list) or any(not isinstance(item, str) for item in reports): raise ValueError("invalid reports")
    return ContactState(
        contact_id=_string(raw.get("contact_id"), "contact ID"), evidence=ContactEvidence(_string(raw.get("evidence"), "evidence")),
        successful_scans=_nonnegative(raw.get("successful_scans"), "successful scans"), workflow=ContactWorkflow(_string(raw.get("workflow"), "workflow")),
        classification=ContactClassification(raw["classification"]) if raw.get("classification") is not None else None,
        priority=ContactPriority(raw["priority"]) if raw.get("priority") is not None else None, revision=_nonnegative(raw.get("revision"), "revision"),
        last_reported_revision=_optional_nonnegative(raw.get("last_reported_revision"), "reported revision"), report_ids=list(reports),
    )


def _alert(raw: dict) -> AlertState:
    entities = raw.get("entity_ids")
    payload = raw.get("payload")
    if not isinstance(entities, list) or any(not isinstance(value, str) for value in entities) or not isinstance(payload, dict): raise ValueError("invalid alert")
    return AlertState(
        alert_id=_string(raw.get("alert_id"), "alert ID"), kind=AlertKind(_string(raw.get("kind"), "alert kind")), severity=AlertSeverity(_string(raw.get("severity"), "alert severity")),
        entity_ids=tuple(entities), opened_sequence=_nonnegative(raw.get("opened_sequence"), "opened sequence"), opened_at_ms=_nonnegative(raw.get("opened_at_ms"), "opened time"),
        closed_sequence=_optional_nonnegative(raw.get("closed_sequence"), "closed sequence"), closed_at_ms=_optional_nonnegative(raw.get("closed_at_ms"), "closed time"),
        acknowledged=raw.get("acknowledged") if isinstance(raw.get("acknowledged"), bool) else _raise("invalid acknowledgement"),
        acknowledged_sequence=_optional_nonnegative(raw.get("acknowledged_sequence"), "acknowledgement sequence"), acknowledged_at_ms=_optional_nonnegative(raw.get("acknowledged_at_ms"), "acknowledgement time"), payload=dict(payload),
    )


def _raise(message: str):
    raise ValueError(message)
