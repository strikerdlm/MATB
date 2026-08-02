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
    critical_below: bool = False
    advisory_duration_ms: int = 0
    critical_duration_ms: int = 0
    last_seen_ms: int | None = None
    critical_transition_ms: int | None = None
    critical_duration_at_transition_ms: int | None = None


class SeparationMonitor:
    """Emit threshold-transition events once for lexically ordered aircraft pairs."""

    def __init__(self, *, advisory_mm: int, critical_mm: int, tick_ms: int = 100) -> None:
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0
               for value in (advisory_mm, critical_mm)) or critical_mm >= advisory_mm:
            raise ValueError("critical separation must be positive and less than advisory")
        if isinstance(tick_ms, bool) or not isinstance(tick_ms, int) or tick_ms <= 0:
            raise ValueError("tick_ms must be a positive integer")
        self.advisory_mm = advisory_mm
        self.critical_mm = critical_mm
        self.tick_ms = tick_ms
        self._pairs: dict[str, _PairState] = {}

    def checkpoint_state(self) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        for key, pair in sorted(self._pairs.items()):
            item: dict[str, object] = {
                "advisory_open": pair.advisory_open,
                "critical_open": pair.critical_open,
                "advisory_duration_ms": pair.advisory_duration_ms,
                "critical_duration_ms": pair.critical_duration_ms,
                "last_seen_ms": pair.last_seen_ms,
            }
            if pair.critical_transition_ms is not None:
                item["critical_occupancy"] = {
                    "below": pair.critical_below,
                    "transition_ms": pair.critical_transition_ms,
                    "duration_ms": pair.critical_duration_at_transition_ms,
                }
            result[key] = item
        return result

    def restore_state(
        self,
        raw: dict[str, dict[str, object]],
        *,
        state: WorldState | None = None,
    ) -> None:
        pairs: dict[str, _PairState] = {}
        for key, value in raw.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                raise ValueError("invalid separation checkpoint")
            base_fields = {
                "advisory_open", "critical_open", "advisory_duration_ms",
                "critical_duration_ms", "last_seen_ms",
            }
            if set(value) not in (base_fields, base_fields | {"critical_occupancy"}):
                raise ValueError("invalid separation checkpoint")
            critical_open = _bool(value, "critical_open")
            occupancy = value.get("critical_occupancy")
            critical_below = critical_open
            transition_ms = None
            duration_at_transition_ms = None
            if occupancy is not None:
                if not isinstance(occupancy, dict) or set(occupancy) != {
                    "below", "transition_ms", "duration_ms",
                }:
                    raise ValueError("invalid separation checkpoint occupancy")
                critical_below = _bool(occupancy, "below")
                transition_ms = _counter(occupancy, "transition_ms")
                duration_at_transition_ms = _counter(occupancy, "duration_ms")
            pairs[key] = _PairState(
                advisory_open=_bool(value, "advisory_open"),
                critical_open=critical_open,
                critical_below=critical_below,
                advisory_duration_ms=_counter(value, "advisory_duration_ms"),
                critical_duration_ms=_counter(value, "critical_duration_ms"),
                last_seen_ms=_optional_counter(value, "last_seen_ms"),
                critical_transition_ms=transition_ms,
                critical_duration_at_transition_ms=duration_at_transition_ms,
            )
        if state is not None:
            self._validate_restored_state(pairs, state)
        self._pairs = pairs

    def _validate_restored_state(
        self, pairs: dict[str, _PairState], state: WorldState,
    ) -> None:
        ids = sorted(state.aircraft)
        expected_keys = {
            f"{left_id}:{right_id}"
            for index, left_id in enumerate(ids)
            for right_id in ids[index + 1:]
        } if state.simulation_time_ms > 0 else set()
        if set(pairs) != expected_keys:
            raise ValueError("invalid separation checkpoint pair set")
        for key, pair in pairs.items():
            left_id, right_id = key.split(":", 1)
            if pair.last_seen_ms != state.simulation_time_ms:
                raise ValueError("invalid separation checkpoint timestamp")
            separation = distance_mm(
                state.aircraft[left_id].position, state.aircraft[right_id].position,
            )
            advisory_now = separation < self.advisory_mm
            critical_now = separation < self.critical_mm
            if pair.advisory_open != advisory_now:
                raise ValueError("invalid separation checkpoint geometry")
            if pair.critical_below != critical_now:
                raise ValueError("invalid separation checkpoint critical occupancy")
            if pair.critical_below and not pair.critical_open:
                raise ValueError("invalid separation checkpoint critical lifecycle")
            if pair.critical_open and not pair.advisory_open:
                raise ValueError("invalid separation checkpoint flags")
            if pair.critical_duration_ms > pair.advisory_duration_ms:
                raise ValueError("invalid separation checkpoint durations")
            self._validate_alert_lifecycle(
                state, key, pair.advisory_open, pair.advisory_duration_ms,
                AlertKind.SEPARATION_ADVISORY, AlertSeverity.ADVISORY,
                (left_id, right_id),
            )
            self._validate_alert_lifecycle(
                state, key, pair.critical_open, pair.critical_duration_ms,
                AlertKind.SEPARATION_CRITICAL, AlertSeverity.CRITICAL,
                (left_id, right_id), validate_duration=False,
            )
            self._validate_critical_occupancy(state, key, pair)
        for alert in state.alerts.values():
            if alert.kind not in (
                AlertKind.SEPARATION_ADVISORY, AlertKind.SEPARATION_CRITICAL,
            ):
                continue
            prefix = f"{alert.kind.value}:"
            if not alert.alert_id.startswith(prefix) or alert.alert_id[len(prefix):] not in pairs:
                raise ValueError("invalid separation checkpoint alert")

    def _validate_alert_lifecycle(
        self,
        state: WorldState,
        pair_key: str,
        expected_open: bool,
        duration_ms: int,
        kind: AlertKind,
        severity: AlertSeverity,
        entity_ids: tuple[str, str],
        *,
        validate_duration: bool = True,
    ) -> None:
        alert = state.alerts.get(f"{kind.value}:{pair_key}")
        if alert is None:
            if expected_open or duration_ms:
                raise ValueError("invalid separation checkpoint alert lifecycle")
            return
        if (
            alert.kind is not kind
            or alert.severity is not severity
            or alert.entity_ids != entity_ids
            or not self._valid_alert_payload(alert, pair_key)
            or not 0 < alert.opened_sequence <= state.event_sequence
            or not 0 <= alert.opened_at_ms <= state.simulation_time_ms
            or alert.opened_at_ms % self.tick_ms
        ):
            raise ValueError("invalid separation checkpoint alert lifecycle")
        is_open = alert.closed_sequence is None and alert.closed_at_ms is None
        if is_open != expected_open:
            raise ValueError("invalid separation checkpoint alert lifecycle")
        lifecycle_end = state.simulation_time_ms
        if not is_open:
            if (
                alert.closed_sequence is None
                or alert.closed_at_ms is None
                or not alert.opened_sequence < alert.closed_sequence <= state.event_sequence
                or not alert.opened_at_ms <= alert.closed_at_ms <= state.simulation_time_ms
                or alert.closed_at_ms % self.tick_ms
            ):
                raise ValueError("invalid separation checkpoint alert lifecycle")
            lifecycle_end = alert.closed_at_ms
        if validate_duration and duration_ms != lifecycle_end - alert.opened_at_ms:
            raise ValueError("invalid separation checkpoint durations")
        if alert.acknowledged:
            if (
                alert.acknowledged_sequence is None
                or alert.acknowledged_at_ms is None
                or not alert.opened_sequence <= alert.acknowledged_sequence <= state.event_sequence
                or not alert.opened_at_ms <= alert.acknowledged_at_ms <= lifecycle_end
            ):
                raise ValueError("invalid separation checkpoint acknowledgement")
        elif alert.acknowledged_sequence is not None or alert.acknowledged_at_ms is not None:
            raise ValueError("invalid separation checkpoint acknowledgement")

    def _validate_critical_occupancy(
        self, state: WorldState, pair_key: str, pair: _PairState,
    ) -> None:
        if (
            pair.critical_duration_ms > pair.advisory_duration_ms
            or pair.critical_duration_ms % self.tick_ms
            or pair.advisory_duration_ms % self.tick_ms
        ):
            raise ValueError("invalid separation checkpoint durations")
        alert = state.alerts.get(f"{AlertKind.SEPARATION_CRITICAL.value}:{pair_key}")
        advisory_alert = state.alerts.get(f"{AlertKind.SEPARATION_ADVISORY.value}:{pair_key}")
        if (
            alert is not None
            and advisory_alert is not None
            and alert.opened_at_ms < advisory_alert.opened_at_ms
        ):
            if (
                pair.critical_below
                or pair.critical_open
                or pair.critical_duration_ms
                or pair.critical_transition_ms is not None
                or pair.critical_duration_at_transition_ms is not None
            ):
                raise ValueError("invalid separation checkpoint stale critical occupancy")
            return
        if pair.critical_transition_ms is None:
            if pair.critical_duration_at_transition_ms is not None:
                raise ValueError("invalid separation checkpoint occupancy")
            if pair.critical_below:
                if alert is None or alert.closed_at_ms is not None:
                    raise ValueError("invalid separation checkpoint occupancy")
                expected = state.simulation_time_ms - alert.opened_at_ms
                if pair.critical_duration_ms != expected:
                    raise ValueError("invalid separation checkpoint occupancy duration")
            elif pair.critical_duration_ms != 0:
                raise ValueError("invalid separation checkpoint occupancy duration")
            return
        transition_ms = pair.critical_transition_ms
        duration_at_transition = pair.critical_duration_at_transition_ms
        if duration_at_transition is None or alert is None:
            raise ValueError("invalid separation checkpoint occupancy")
        lifecycle_end = (
            state.simulation_time_ms if alert.closed_at_ms is None else alert.closed_at_ms
        )
        if (
            not alert.opened_at_ms <= transition_ms <= lifecycle_end
            or transition_ms % self.tick_ms
            or duration_at_transition % self.tick_ms
        ):
            raise ValueError("invalid separation checkpoint occupancy timestamp")
        derived_duration, derived_below, derived_transition, duration_at_transition_derived = (
            self._derive_critical_occupancy(alert, lifecycle_end)
        )
        if (
            pair.critical_duration_ms != derived_duration
            or pair.critical_below != derived_below
            or transition_ms != derived_transition
            or duration_at_transition != duration_at_transition_derived
        ):
            raise ValueError("invalid separation checkpoint occupancy duration")
        if not 0 <= duration_at_transition <= lifecycle_end - alert.opened_at_ms:
            raise ValueError("invalid separation checkpoint occupancy duration")

    def _valid_alert_payload(self, alert: AlertState, pair_key: str) -> bool:
        allowed = {"pair_key"}
        if alert.kind is AlertKind.SEPARATION_CRITICAL:
            allowed.add("threshold_transitions")
        if set(alert.payload) not in ({"pair_key"}, allowed):
            return False
        if alert.payload.get("pair_key") != pair_key:
            return False
        transitions = alert.payload.get("threshold_transitions")
        if transitions is None:
            return True
        try:
            self._parse_threshold_transitions(alert)
        except ValueError:
            return False
        return True

    def _parse_threshold_transitions(
        self, alert: AlertState,
    ) -> tuple[tuple[int, bool], ...]:
        raw = alert.payload.get("threshold_transitions")
        if not isinstance(raw, list) or not raw:
            raise ValueError("invalid separation checkpoint threshold transitions")
        transitions: list[tuple[int, bool]] = []
        expected_below = False
        previous_ms = alert.opened_at_ms
        lifecycle_end = alert.closed_at_ms
        for item in raw:
            if not isinstance(item, dict) or set(item) != {"at_ms", "below"}:
                raise ValueError("invalid separation checkpoint threshold transitions")
            at_ms, below = item["at_ms"], item["below"]
            if (
                isinstance(at_ms, bool)
                or not isinstance(at_ms, int)
                or not isinstance(below, bool)
                or at_ms % self.tick_ms
                or not previous_ms < at_ms
                or (lifecycle_end is not None and at_ms > lifecycle_end)
                or below is not expected_below
            ):
                raise ValueError("invalid separation checkpoint threshold transitions")
            transitions.append((at_ms, below))
            previous_ms = at_ms
            expected_below = not expected_below
        return tuple(transitions)

    def _derive_critical_occupancy(
        self, alert: AlertState, lifecycle_end: int,
    ) -> tuple[int, bool, int, int]:
        transitions = self._parse_threshold_transitions(alert)
        below = True
        cursor_ms = alert.opened_at_ms
        duration_ms = 0
        duration_at_transition = 0
        for transition_ms, next_below in transitions:
            if below:
                duration_ms += transition_ms - cursor_ms
            duration_at_transition = duration_ms
            cursor_ms = transition_ms
            below = next_below
        last_transition_ms = transitions[-1][0]
        if below:
            duration_ms += lifecycle_end - cursor_ms
        return duration_ms, below, last_transition_ms, duration_at_transition

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
                if pair.critical_below:
                    pair.critical_duration_ms += elapsed
                if advisory_now and not pair.advisory_open:
                    pair.advisory_open = True
                    pair.advisory_duration_ms = 0
                    pair.critical_duration_ms = 0
                    pair.critical_below = False
                    pair.critical_transition_ms = None
                    pair.critical_duration_at_transition_ms = None
                    self._open_alert(
                        state, key, AlertKind.SEPARATION_ADVISORY, AlertSeverity.ADVISORY,
                        (left_id, right_id), now_ms,
                    )
                    events.append(self._emit(
                        state, EventKind.SEPARATION_ADVISORY_OPENED, (left_id, right_id), now_ms,
                        {"pair_key": key, "distance_mm": separation, "advisory_mm": self.advisory_mm},
                    ))
                critical_alert_id = f"{AlertKind.SEPARATION_CRITICAL.value}:{key}"
                critical_alert = state.alerts.get(critical_alert_id)
                critical_lifecycle_open = (
                    critical_alert is not None and critical_alert.closed_sequence is None
                )
                if critical_now != pair.critical_below:
                    pair.critical_below = critical_now
                    if critical_now and not critical_lifecycle_open:
                        pair.critical_transition_ms = None
                        pair.critical_duration_at_transition_ms = None
                    else:
                        pair.critical_transition_ms = now_ms
                        pair.critical_duration_at_transition_ms = pair.critical_duration_ms
                        self._record_critical_transition(
                            state, critical_alert_id, now_ms, critical_now,
                        )
                if critical_now and not critical_lifecycle_open:
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
    def _record_critical_transition(
        state: WorldState, alert_id: str, now_ms: int, below: bool,
    ) -> None:
        alert = state.alerts.get(alert_id)
        if alert is None or alert.closed_sequence is not None:
            raise RuntimeError("critical threshold transition has no open alert lifecycle")
        raw = alert.payload.get("threshold_transitions")
        transitions = [] if raw is None else list(raw)
        transitions.append({"at_ms": now_ms, "below": below})
        alert.payload = {"pair_key": alert.payload["pair_key"], "threshold_transitions": transitions}

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
