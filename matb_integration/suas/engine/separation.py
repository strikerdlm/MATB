"""Deterministic aircraft separation lifecycle monitoring."""

from __future__ import annotations

from dataclasses import dataclass

from matb_integration.suas.domain.enums import AlertKind, AlertSeverity, EventKind
from matb_integration.suas.domain.events import AlertState, DomainEvent
from matb_integration.suas.domain.geometry import distance_mm
from matb_integration.suas.domain.models import WorldState


@dataclass(slots=True)
class _PairState:
    advisory_open: bool = False
    critical_open: bool = False
    advisory_duration_ms: int = 0
    critical_duration_ms: int = 0
    last_seen_ms: int | None = None


class SeparationMonitor:
    """Emit threshold-transition events once for lexically ordered aircraft pairs."""

    def __init__(self, *, advisory_mm: int, critical_mm: int) -> None:
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0
               for value in (advisory_mm, critical_mm)) or critical_mm >= advisory_mm:
            raise ValueError("critical separation must be positive and less than advisory")
        self.advisory_mm = advisory_mm
        self.critical_mm = critical_mm
        self._pairs: dict[str, _PairState] = {}

    def checkpoint_state(self) -> dict[str, dict[str, int | bool | None]]:
        return {
            key: {
                "advisory_open": pair.advisory_open,
                "critical_open": pair.critical_open,
                "advisory_duration_ms": pair.advisory_duration_ms,
                "critical_duration_ms": pair.critical_duration_ms,
                "last_seen_ms": pair.last_seen_ms,
            }
            for key, pair in sorted(self._pairs.items())
        }

    def restore_state(self, raw: dict[str, dict[str, int | bool | None]]) -> None:
        pairs: dict[str, _PairState] = {}
        for key, value in raw.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                raise ValueError("invalid separation checkpoint")
            pairs[key] = _PairState(
                advisory_open=_bool(value, "advisory_open"),
                critical_open=_bool(value, "critical_open"),
                advisory_duration_ms=_counter(value, "advisory_duration_ms"),
                critical_duration_ms=_counter(value, "critical_duration_ms"),
                last_seen_ms=_optional_counter(value, "last_seen_ms"),
            )
        self._pairs = pairs

    def step(self, state: WorldState) -> tuple[DomainEvent, ...]:
        events: list[DomainEvent] = []
        ids = sorted(state.aircraft)
        now_ms = state.simulation_time_ms
        for index, left_id in enumerate(ids):
            for right_id in ids[index + 1:]:
                key = f"{left_id}:{right_id}"
                pair = self._pairs.setdefault(key, _PairState())
                elapsed = 0 if pair.last_seen_ms is None else max(0, now_ms - pair.last_seen_ms)
                pair.last_seen_ms = now_ms
                separation = distance_mm(
                    state.aircraft[left_id].position, state.aircraft[right_id].position,
                )
                advisory_now = separation < self.advisory_mm
                critical_now = separation < self.critical_mm
                if pair.advisory_open:
                    pair.advisory_duration_ms += elapsed
                if pair.critical_open:
                    pair.critical_duration_ms += elapsed
                if advisory_now and not pair.advisory_open:
                    pair.advisory_open = True
                    self._open_alert(
                        state, key, AlertKind.SEPARATION_ADVISORY, AlertSeverity.ADVISORY,
                        (left_id, right_id), now_ms,
                    )
                    events.append(self._emit(
                        state, EventKind.SEPARATION_ADVISORY_OPENED, (left_id, right_id), now_ms,
                        {"pair_key": key, "distance_mm": separation, "advisory_mm": self.advisory_mm},
                    ))
                if critical_now and not pair.critical_open:
                    pair.critical_open = True
                    self._open_alert(
                        state, key, AlertKind.SEPARATION_CRITICAL, AlertSeverity.CRITICAL,
                        (left_id, right_id), now_ms,
                    )
                    events.append(self._emit(
                        state, EventKind.SEPARATION_VIOLATION, (left_id, right_id), now_ms,
                        {"pair_key": key, "distance_mm": separation, "critical_mm": self.critical_mm},
                    ))
                if not advisory_now and pair.advisory_open:
                    pair.advisory_open = False
                    pair.critical_open = False
                    self._close_alert(state, f"{AlertKind.SEPARATION_ADVISORY.value}:{key}", now_ms)
                    self._close_alert(state, f"{AlertKind.SEPARATION_CRITICAL.value}:{key}", now_ms)
                    events.append(self._emit(
                        state, EventKind.SEPARATION_ALERT_CLOSED, (left_id, right_id), now_ms,
                        {
                            "pair_key": key,
                            "distance_mm": separation,
                            "advisory_duration_ms": pair.advisory_duration_ms,
                            "critical_duration_ms": pair.critical_duration_ms,
                        },
                    ))
        return tuple(events)

    @staticmethod
    def _open_alert(
        state: WorldState, key: str, kind: AlertKind, severity: AlertSeverity,
        entity_ids: tuple[str, str], now_ms: int,
    ) -> None:
        alert_id = f"{kind.value}:{key}"
        state.alerts[alert_id] = AlertState(
            alert_id=alert_id, kind=kind, severity=severity, entity_ids=entity_ids,
            opened_sequence=state.event_sequence + 1, opened_at_ms=now_ms,
            closed_sequence=None, closed_at_ms=None, acknowledged=False,
            acknowledged_sequence=None, acknowledged_at_ms=None, payload={"pair_key": key},
        )

    @staticmethod
    def _close_alert(state: WorldState, alert_id: str, now_ms: int) -> None:
        alert = state.alerts.get(alert_id)
        if alert is not None and alert.closed_sequence is None:
            alert.closed_sequence = state.event_sequence + 1
            alert.closed_at_ms = now_ms

    @staticmethod
    def _emit(
        state: WorldState, kind: EventKind, entity_ids: tuple[str, str], now_ms: int, payload: dict,
    ) -> DomainEvent:
        state.event_sequence += 1
        return DomainEvent(
            event_id=f"{state.block_id}:{state.event_sequence:08d}", sequence=state.event_sequence,
            simulation_time_ms=now_ms, kind=kind, entity_ids=entity_ids, payload=payload,
        )


def _counter(raw: dict, key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("invalid separation checkpoint")
    return value


def _optional_counter(raw: dict, key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("invalid separation checkpoint")
    return value


def _bool(raw: dict, key: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise ValueError("invalid separation checkpoint")
    return value
