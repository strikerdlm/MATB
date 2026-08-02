"""Deterministic sensor evidence and operator-facing contact workflow."""

from __future__ import annotations

from collections.abc import MutableMapping, Sequence
from typing import TYPE_CHECKING

from matb_integration.suas.domain.enums import (
    AircraftMode, ContactClassification, ContactEvidence, ContactPriority, ContactWorkflow,
    EventKind, SensorState,
)
from matb_integration.suas.domain.events import DomainEvent
from matb_integration.suas.domain.geometry import distance_mm
from matb_integration.suas.domain.models import ScenarioDefinition, WorldState
from matb_integration.suas.domain.scenario_context import bind_world_scenario, scenario_for_world
from matb_integration.suas.engine.energy import (
    fail_aircraft_if_energy_exhausted, refresh_energy_reserve,
)
from matb_integration.suas.engine.prng import PCG32, derive_stream_seed

if TYPE_CHECKING:
    from matb_integration.suas.engine.coverage import CoverageGrid


_REPORT_HISTORY: dict[int, dict[str, list[dict[str, object]]]] = {}


class SensorSystem:
    """Independent PCG streams for every aircraft/contact observation pair."""

    def __init__(self, scenario: ScenarioDefinition) -> None:
        self._scenario = scenario
        self._streams: dict[str, PCG32] = {}
        self._reports: dict[str, list[dict[str, object]]] = {}

    def step(
        self,
        state: WorldState,
        *,
        now_ms: int,
        coverage: CoverageGrid | None = None,
    ) -> tuple[DomainEvent, ...]:
        """Process every due nominal scan in lexical aircraft/contact order."""

        if isinstance(now_ms, bool) or not isinstance(now_ms, int) or now_ms < 0:
            raise ValueError("now_ms must be non-negative integer milliseconds")
        bind_world_scenario(state, self._scenario)
        events: list[DomainEvent] = []
        for aircraft_id in sorted(state.aircraft):
            aircraft = state.aircraft[aircraft_id]
            definition = self._scenario.aircraft[aircraft_id]
            if aircraft.mode in (AircraftMode.RECOVERED, AircraftMode.MISSION_FAILED):
                while aircraft.next_sensor_scan_ms <= now_ms:
                    aircraft.next_sensor_scan_ms += definition.sensor.scan_interval_ms
                continue
            while aircraft.next_sensor_scan_ms <= now_ms:
                scan_at_ms = aircraft.next_sensor_scan_ms
                aircraft.next_sensor_scan_ms += definition.sensor.scan_interval_ms
                if aircraft.sensor is not SensorState.NOMINAL:
                    continue
                aircraft.energy_units -= definition.energy.sensor_units_per_scan
                if coverage is not None:
                    coverage.mark_scan(state, aircraft_id)
                pairs = [(aircraft_id, contact_id) for contact_id in sorted(state.contacts)]
                events.extend(self.scan_pairs(state, pairs=pairs, at_ms=scan_at_ms))
                # Contact evidence is ordered before same-timestamp energy alerts.
                failed = fail_aircraft_if_energy_exhausted(
                    state, aircraft, definition, events, at_ms=scan_at_ms,
                )
                refresh_energy_reserve(
                    state, aircraft, definition, events, at_ms=scan_at_ms,
                )
                if failed:
                    while aircraft.next_sensor_scan_ms <= now_ms:
                        aircraft.next_sensor_scan_ms += definition.sensor.scan_interval_ms
                    break
        return tuple(events)

    def scan_pairs(
        self,
        state: WorldState,
        *,
        pairs: Sequence[tuple[str, str]],
        at_ms: int | None = None,
    ) -> tuple[DomainEvent, ...]:
        """Run explicit observations, primarily for deterministic integrations/tests."""

        bind_world_scenario(state, self._scenario)
        timestamp = state.simulation_time_ms if at_ms is None else at_ms
        events: list[DomainEvent] = []
        for aircraft_id, contact_id in pairs:
            if aircraft_id not in state.aircraft or contact_id not in state.contacts:
                continue
            events.extend(self._scan_pair(state, aircraft_id, contact_id, at_ms=timestamp))
        return tuple(events)

    def public_snapshot(self, state: WorldState) -> dict[str, object]:
        """Return the safe contact projection bound to this system's scenario."""

        return public_snapshot(state, scenario=self._scenario)

    def apply_contact_action(
        self, state: WorldState, contact_id: str, action: str, **values: object,
    ) -> tuple[DomainEvent, ...]:
        """Apply an operator action while retaining immutable reports privately."""

        return apply_contact_action(state, contact_id, action, report_history=self._reports, **values)

    def report_history(self, contact_id: str) -> tuple[dict[str, object], ...]:
        """Return immutable copies of reports created through this contact subsystem."""

        return tuple(dict(report) for report in self._reports.get(contact_id, ()))

    def _scan_pair(
        self, state: WorldState, aircraft_id: str, contact_id: str, *, at_ms: int,
    ) -> tuple[DomainEvent, ...]:
        aircraft = state.aircraft[aircraft_id]
        if aircraft.sensor is not SensorState.NOMINAL:
            return ()
        definition = self._scenario.aircraft[aircraft_id]
        contact_definition = self._scenario.contacts.get(contact_id)
        if contact_definition is None:
            return ()
        if distance_mm(aircraft.position, contact_definition.position) > definition.sensor.radius_mm:
            return ()
        stream = self._stream_for(aircraft_id, contact_id)
        if not stream.bernoulli_ppm(definition.sensor.detection_probability_ppm):
            return ()
        contact = state.contacts[contact_id]
        contact.successful_scans += 1
        events: list[DomainEvent] = []
        if contact.evidence is ContactEvidence.NONE:
            contact.evidence = ContactEvidence.DETECTED
            contact.workflow = ContactWorkflow.DETECTED
            events.append(_emit(
                state, at_ms, EventKind.CONTACT_EVIDENCE_CHANGED, (contact_id,),
                {"from": ContactEvidence.NONE.value, "to": ContactEvidence.DETECTED.value},
            ))
        if (
            contact.evidence is ContactEvidence.DETECTED
            and contact.successful_scans >= definition.sensor.scans_to_inspectable
        ):
            contact.evidence = ContactEvidence.INSPECTABLE
            events.append(_emit(
                state, at_ms, EventKind.CONTACT_EVIDENCE_CHANGED, (contact_id,),
                {"from": ContactEvidence.DETECTED.value, "to": ContactEvidence.INSPECTABLE.value},
            ))
        return tuple(events)

    def _stream_for(self, aircraft_id: str, contact_id: str) -> PCG32:
        key = f"{aircraft_id}:{contact_id}"
        stream = self._streams.get(key)
        if stream is None:
            seed, increment = derive_stream_seed(self._scenario.seed, "sensor", key)
            stream = self._streams[key] = PCG32(seed=seed, stream=increment)
        return stream


def apply_contact_action(
    state: WorldState,
    contact_id: str,
    action: str,
    *,
    classification: ContactClassification | str | None = None,
    priority: ContactPriority | str | None = None,
    note_code: str | None = None,
    at_ms: int | None = None,
    report_history: MutableMapping[str, list[dict[str, object]]] | None = None,
) -> tuple[DomainEvent, ...]:
    """Apply one gated contact action, returning no events when it is rejected."""

    try:
        contact = state.contacts[contact_id]
    except KeyError as error:
        raise ValueError(f"world does not contain contact {contact_id}") from error
    timestamp = state.simulation_time_ms if at_ms is None else at_ms
    if action == "INSPECT_CONTACT":
        if not (
            contact.evidence is ContactEvidence.INSPECTABLE
            and contact.workflow in (ContactWorkflow.DETECTED, ContactWorkflow.INSPECTED)
        ):
            return ()
        previous = contact.workflow
        contact.workflow = ContactWorkflow.INSPECTED
        return (_workflow_event(state, timestamp, contact_id, previous, contact.workflow),)
    if action == "CLASSIFY_CONTACT":
        if contact.workflow not in (
            ContactWorkflow.INSPECTED, ContactWorkflow.CLASSIFIED,
            ContactWorkflow.PRIORITIZED, ContactWorkflow.REPORTED,
        ) or classification is None:
            return ()
        try:
            value = ContactClassification(classification)
        except ValueError as error:
            raise ValueError("classification is invalid") from error
        previous = contact.workflow
        corrected = previous is ContactWorkflow.REPORTED and contact.classification is not value
        if contact.classification is not value:
            contact.classification = value
            contact.revision += 1
        if previous is not ContactWorkflow.REPORTED:
            contact.workflow = ContactWorkflow.CLASSIFIED
        events = [_workflow_event(state, timestamp, contact_id, previous, contact.workflow)]
        if corrected:
            events.append(_emit(
                state, timestamp, EventKind.CONTACT_CORRECTED, (contact_id,),
                {"field": "classification", "revision": contact.revision},
            ))
        return tuple(events)
    if action == "SET_CONTACT_PRIORITY":
        if contact.workflow not in (
            ContactWorkflow.CLASSIFIED, ContactWorkflow.PRIORITIZED, ContactWorkflow.REPORTED,
        ) or priority is None:
            return ()
        try:
            value = ContactPriority(priority)
        except ValueError as error:
            raise ValueError("priority is invalid") from error
        previous = contact.workflow
        corrected = previous is ContactWorkflow.REPORTED and contact.priority is not value
        if contact.priority is not value:
            contact.priority = value
            contact.revision += 1
        if previous is not ContactWorkflow.REPORTED:
            contact.workflow = ContactWorkflow.PRIORITIZED
        events = [_workflow_event(state, timestamp, contact_id, previous, contact.workflow)]
        if corrected:
            events.append(_emit(
                state, timestamp, EventKind.CONTACT_CORRECTED, (contact_id,),
                {"field": "priority", "revision": contact.revision},
            ))
        return tuple(events)
    if action == "REPORT_CONTACT":
        if not (
            contact.workflow in (ContactWorkflow.PRIORITIZED, ContactWorkflow.REPORTED)
            and contact.classification is not None
            and contact.priority is not None
            and contact.revision != contact.last_reported_revision
        ):
            return ()
        previous = contact.workflow
        contact.workflow = ContactWorkflow.REPORTED
        report_id = f"{contact_id}:R{len(contact.report_ids) + 1:04d}"
        replaces = contact.report_ids[-1] if contact.report_ids else None
        contact.report_ids.append(report_id)
        contact.last_reported_revision = contact.revision
        report = {
            "report_id": report_id,
            "replaces_report_id": replaces,
            "revision": contact.revision,
            "classification": contact.classification.value,
            "priority": contact.priority.value,
            "note_code": note_code,
        }
        (report_history if report_history is not None else _REPORT_HISTORY.setdefault(id(state), {})) \
            .setdefault(contact_id, []).append(report)
        return (_emit(
            state, timestamp, EventKind.CONTACT_WORKFLOW_CHANGED, (contact_id,),
            {"from": previous.value, "to": contact.workflow.value, **report},
        ),)
    raise ValueError(f"unsupported contact action {action}")


def public_snapshot(state: WorldState, *, scenario: ScenarioDefinition | None = None) -> dict[str, object]:
    """Project contact state without leaking hidden truth or reporting requirements."""

    resolved_scenario = scenario or scenario_for_world(state)
    if scenario is not None:
        bind_world_scenario(state, scenario)
    contacts: dict[str, dict[str, object]] = {}
    for contact_id in sorted(state.contacts):
        contact = state.contacts[contact_id]
        projected: dict[str, object] = {
            "contact_id": contact_id,
            "evidence": contact.evidence.value,
            "workflow": contact.workflow.value,
            "classification": contact.classification.value if contact.classification else None,
            "priority": contact.priority.value if contact.priority else None,
            "report_ids": list(contact.report_ids),
        }
        if resolved_scenario is not None and contact.evidence is not ContactEvidence.NONE:
            position = resolved_scenario.contacts[contact_id].position
            projected["position"] = {"x_mm": position.x_mm, "y_mm": position.y_mm}
        contacts[contact_id] = projected
    return {"contacts": contacts}


def _workflow_event(
    state: WorldState, at_ms: int, contact_id: str,
    previous: ContactWorkflow, current: ContactWorkflow,
) -> DomainEvent:
    return _emit(
        state, at_ms, EventKind.CONTACT_WORKFLOW_CHANGED, (contact_id,),
        {"from": previous.value, "to": current.value},
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
