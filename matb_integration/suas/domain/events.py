"""Stable event and alert records emitted by the authoritative domain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .enums import AlertKind, AlertSeverity, EventKind


JSONValue: TypeAlias = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]


@dataclass(slots=True)
class AlertState:
    """Lifecycle state for an operator-visible alert with a stable ID."""

    alert_id: str
    kind: AlertKind
    severity: AlertSeverity
    entity_ids: tuple[str, ...]
    opened_sequence: int
    opened_at_ms: int
    closed_sequence: int | None
    closed_at_ms: int | None
    acknowledged: bool
    acknowledged_sequence: int | None
    acknowledged_at_ms: int | None
    payload: dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """An immutable event ordered by sequence within a simulation run."""

    event_id: str
    sequence: int
    simulation_time_ms: int
    kind: EventKind
    entity_ids: tuple[str, ...]
    payload: dict[str, JSONValue]
