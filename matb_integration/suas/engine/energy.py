"""Shared deterministic energy-reserve and threshold-alert calculations."""

from __future__ import annotations

from matb_integration.suas.domain.enums import AircraftMode, AlertKind, AlertSeverity, EventKind
from matb_integration.suas.domain.events import AlertState, DomainEvent
from matb_integration.suas.domain.geometry import distance_mm
from matb_integration.suas.domain.models import AircraftDefinition, AircraftState, WorldState


def refresh_energy_reserve(
    state: WorldState,
    aircraft: AircraftState,
    definition: AircraftDefinition,
    events: list[DomainEvent],
    *,
    at_ms: int,
) -> None:
    """Refresh reserve and threshold lifecycle immediately after an energy change."""

    return_cost = ceil_div(
        distance_mm(aircraft.position, definition.home) * definition.energy.transit_units_per_s,
        definition.return_speed_mm_per_s,
    )
    margin = ceil_div(
        definition.energy.capacity_units * definition.energy.reserve_margin_ppm,
        1_000_000,
    )
    aircraft.predicted_home_reserve_units = aircraft.energy_units - return_cost
    _set_alert(
        state, aircraft, AlertKind.ENERGY_RESERVE, AlertSeverity.ADVISORY,
        aircraft.predicted_home_reserve_units <= margin, margin, at_ms, events,
    )
    _set_alert(
        state, aircraft, AlertKind.ENERGY_CRITICAL, AlertSeverity.CRITICAL,
        aircraft.predicted_home_reserve_units < 0, 0, at_ms, events,
    )


def fail_aircraft_if_energy_exhausted(
    state: WorldState,
    aircraft: AircraftState,
    definition: AircraftDefinition,
    events: list[DomainEvent],
    *,
    at_ms: int,
) -> bool:
    """Apply the authoritative away-from-home exhaustion transition once."""

    if (
        aircraft.energy_units > 0
        or aircraft.position == definition.home
        or aircraft.mode in (AircraftMode.RECOVERED, AircraftMode.MISSION_FAILED)
    ):
        return False
    previous = aircraft.mode
    aircraft.previous_mode = previous
    aircraft.mode = AircraftMode.MISSION_FAILED
    events.append(_emit(
        state,
        at_ms,
        EventKind.AIRCRAFT_MODE_CHANGED,
        (aircraft.aircraft_id,),
        {"from": previous.value, "to": AircraftMode.MISSION_FAILED.value},
    ))
    return True


def ceil_div(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    return -(-numerator // denominator)


def _set_alert(
    state: WorldState,
    aircraft: AircraftState,
    kind: AlertKind,
    severity: AlertSeverity,
    should_be_open: bool,
    boundary: int,
    at_ms: int,
    events: list[DomainEvent],
) -> None:
    alert_id = f"{kind.value}:{aircraft.aircraft_id}"
    current = state.alerts.get(alert_id)
    open_now = current is not None and current.closed_sequence is None
    if open_now == should_be_open:
        return
    if should_be_open:
        sequence = state.event_sequence + 1
        state.alerts[alert_id] = AlertState(
            alert_id=alert_id,
            kind=kind,
            severity=severity,
            entity_ids=(aircraft.aircraft_id,),
            opened_sequence=sequence,
            opened_at_ms=at_ms,
            closed_sequence=None,
            closed_at_ms=None,
            acknowledged=False,
            acknowledged_sequence=None,
            acknowledged_at_ms=None,
            payload={"boundary_units": boundary, "predicted_home_reserve_units": aircraft.predicted_home_reserve_units},
        )
        transition = "opened"
    else:
        assert current is not None
        current.closed_sequence = state.event_sequence + 1
        current.closed_at_ms = at_ms
        current.payload = {
            "boundary_units": boundary,
            "predicted_home_reserve_units": aircraft.predicted_home_reserve_units,
        }
        transition = "closed"
    events.append(_emit(
        state, at_ms, EventKind.ENERGY_THRESHOLD_CROSSED, (aircraft.aircraft_id,),
        {
            "alert_kind": kind.value,
            "transition": transition,
            "boundary_units": boundary,
            "predicted_home_reserve_units": aircraft.predicted_home_reserve_units,
        },
    ))


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
