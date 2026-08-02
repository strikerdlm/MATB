"""Scheduled command-link transitions and their safe lost-link procedure."""

from __future__ import annotations

from matb_integration.suas.domain.enums import AircraftMode, EventKind, LinkState
from matb_integration.suas.domain.events import DomainEvent
from matb_integration.suas.domain.models import Route, ScenarioDefinition, WorldState


LOST_LINK_HOLD_MS = 10_000


class LinkSystem:
    """Apply each declared link event once and enforce lost-link autonomy."""

    def __init__(self, scenario: ScenarioDefinition) -> None:
        self._scenario = scenario
        self._applied_event_ids: set[str] = set()

    def step(self, state: WorldState, *, now_ms: int) -> tuple[DomainEvent, ...]:
        """Apply due events, then progress any expired lost-link hold."""

        _require_time(now_ms)
        events: list[DomainEvent] = []
        due = sorted(
            (
                event for event in self._scenario.link_events
                if event.block_id == state.block_id
                and event.at_ms <= now_ms
                and event.event_id not in self._applied_event_ids
            ),
            key=lambda event: (event.at_ms, event.event_id),
        )
        for event in due:
            self._applied_event_ids.add(event.event_id)
            events.extend(self.force_state(state, event.aircraft_id, event.state, at_ms=event.at_ms))
        for aircraft_id in sorted(state.aircraft):
            aircraft = state.aircraft[aircraft_id]
            if (
                aircraft.link is LinkState.LOST
                and aircraft.lost_link_since_ms is not None
                and now_ms - aircraft.lost_link_since_ms >= LOST_LINK_HOLD_MS
                and aircraft.mode is AircraftMode.LOST_LINK_PROCEDURE
            ):
                definition = self._scenario.aircraft[aircraft_id]
                aircraft.route = Route((definition.home,))
                aircraft.route_leg = 0
                aircraft.route_leg_start = None
                aircraft.route_leg_target = None
                aircraft.route_leg_distance_mm = 0
                aircraft.route_leg_progress_mm = 0
                aircraft.movement_remainder = 0
                events.append(_set_mode(state, aircraft, AircraftMode.RETURN_TO_BASE, now_ms))
        return tuple(events)

    def force_state(
        self, state: WorldState, aircraft_id: str, link_state: LinkState, *, at_ms: int,
    ) -> tuple[DomainEvent, ...]:
        """Set a link state for a test/control adapter without bypassing safety rules."""

        _require_time(at_ms)
        if not isinstance(link_state, LinkState):
            link_state = LinkState(link_state)
        try:
            aircraft = state.aircraft[aircraft_id]
        except KeyError as error:
            raise ValueError(f"world does not contain aircraft {aircraft_id}") from error
        if aircraft.link is link_state:
            return ()
        events = [_emit(
            state,
            at_ms,
            EventKind.LINK_STATE_CHANGED,
            (aircraft_id,),
            {"from": aircraft.link.value, "to": link_state.value},
        )]
        aircraft.link = link_state
        if link_state is LinkState.LOST:
            aircraft.previous_mode = aircraft.mode
            aircraft.mode = AircraftMode.LOST_LINK_PROCEDURE
            aircraft.lost_link_since_ms = at_ms
            events.append(_emit(
                state,
                at_ms,
                EventKind.LOST_LINK_PROCEDURE_STARTED,
                (aircraft_id,),
                {"hold_ms": LOST_LINK_HOLD_MS, "previous_mode": aircraft.previous_mode.value},
            ))
        elif aircraft.lost_link_since_ms is not None:
            aircraft.lost_link_since_ms = None
            if aircraft.mode is AircraftMode.LOST_LINK_PROCEDURE:
                # Link recovery does not implicitly restore a stale search assignment.
                aircraft.mode = AircraftMode.HOLD
                events.append(_emit(
                    state,
                    at_ms,
                    EventKind.AIRCRAFT_MODE_CHANGED,
                    (aircraft_id,),
                    {"from": AircraftMode.LOST_LINK_PROCEDURE.value, "to": AircraftMode.HOLD.value},
                ))
        return tuple(events)

    @staticmethod
    def accepts_aircraft_commands(state: WorldState, aircraft_id: str) -> bool:
        """Return whether the command channel may accept a new aircraft command."""

        try:
            return state.aircraft[aircraft_id].link is not LinkState.LOST
        except KeyError as error:
            raise ValueError(f"world does not contain aircraft {aircraft_id}") from error


def _set_mode(
    state: WorldState, aircraft, mode: AircraftMode, at_ms: int,
) -> DomainEvent:
    previous = aircraft.mode
    aircraft.previous_mode = previous
    aircraft.mode = mode
    return _emit(
        state, at_ms, EventKind.AIRCRAFT_MODE_CHANGED, (aircraft.aircraft_id,),
        {"from": previous.value, "to": mode.value},
    )


def _emit(
    state: WorldState, at_ms: int, kind: EventKind, entity_ids: tuple[str, ...], payload: dict,
) -> DomainEvent:
    state.event_sequence += 1
    return DomainEvent(
        event_id=f"{state.block_id}:{state.event_sequence:08d}",
        sequence=state.event_sequence,
        simulation_time_ms=at_ms,
        kind=kind,
        entity_ids=entity_ids,
        payload=payload,
    )


def _require_time(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("time must be a non-negative integer milliseconds")
