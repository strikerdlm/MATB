"""Deterministic, descriptive mission outcome metrics.

The reducer in this module intentionally consumes the immutable recording
stream.  It does not inspect a live engine or infer hidden scenario truth from
operator-facing projections.  Event payloads use small, stable codes (for
example ``coverage_updated`` and ``contact_reported``); a few spellings used by
the domain event enums are accepted as equivalent aliases.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping, Set
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any

from matb_integration.suas.recording.records import RecordKind, SessionRecord


_PPM = 1_000_000
_MISSING = object()


@dataclass(frozen=True, slots=True)
class CoverageMetrics:
    covered_cells: int = 0
    eligible_cells: int = 0
    coverage_ppm: int = 0
    percent: float = 0.0
    target_ppm: int | None = None
    component: float = 0.0


@dataclass(frozen=True, slots=True)
class ContactMetrics:
    required_contacts: int = 0
    reported_contacts: int = 0
    correct_reports: int = 0
    false_reports: int = 0
    unreported_contacts: int = 0
    correct_fraction: float = 0.0
    target_ppm: int | None = None
    component: float = 0.0
    report_latency_ms: int | None = None
    max_report_latency_ms: int | None = None


@dataclass(frozen=True, slots=True)
class CommandMetrics:
    accepted: int = 0
    rejected: int = 0
    duplicate: int = 0
    total: int = 0


@dataclass(frozen=True, slots=True)
class AlertMetrics:
    opened: int = 0
    closed: int = 0
    acknowledged: int = 0
    advisory: int = 0
    critical: int = 0
    fatal: int = 0
    acknowledgement_latency_ms: int | None = None
    max_acknowledgement_latency_ms: int | None = None


@dataclass(frozen=True, slots=True)
class LinkMetrics:
    lost_count: int = 0
    lost_duration_ms: int = 0
    degraded_count: int = 0
    nominal_count: int = 0
    max_lost_duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class SeparationMetrics:
    advisory_violations: int = 0
    critical_violations: int = 0
    alerts_closed: int = 0
    critical_duration_ms: int = 0
    max_critical_duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class AssetMetrics:
    active_aircraft: int = 0
    recovered: int = 0
    failed: int = 0
    preserved: int = 0
    preservation_fraction: float = 0.0
    target_ppm: int | None = None
    component: float = 0.0
    recovery_latency_ms: int | None = None
    max_recovery_latency_ms: int | None = None


@dataclass(frozen=True, slots=True)
class TimelinessMetrics:
    required_actions: int = 0
    completed_actions: int = 0
    on_time_actions: int = 0
    late_actions: int = 0
    missed_actions: int = 0
    on_time_fraction: float = 0.0
    target_ppm: int | None = None
    component: float = 0.0
    action_latency_ms: int | None = None
    max_action_latency_ms: int | None = None


@dataclass(frozen=True, slots=True)
class BlockMetrics:
    """All deterministic block components plus a labelled composite.

    ``mission_score`` is deliberately a descriptive feedback composite, not a
    pass/fail or participant-performance grade.  ``research`` is reserved for
    the Phase 5 human-factors extension and remains an empty mapping here.
    """

    coverage: CoverageMetrics = field(default_factory=CoverageMetrics)
    contacts: ContactMetrics = field(default_factory=ContactMetrics)
    commands: CommandMetrics = field(default_factory=CommandMetrics)
    alerts: AlertMetrics = field(default_factory=AlertMetrics)
    links: LinkMetrics = field(default_factory=LinkMetrics)
    separation: SeparationMetrics = field(default_factory=SeparationMetrics)
    assets: AssetMetrics = field(default_factory=AssetMetrics)
    timeliness: TimelinessMetrics = field(default_factory=TimelinessMetrics)
    mission_score: float = 0.0
    composite_label: str = "descriptive_feedback_only"
    component_inputs: Mapping[str, float] = field(default_factory=dict)
    research: Mapping[str, object] = field(default_factory=dict)
    session_id: str | None = None
    block_id: str | None = None

    @property
    def components(self) -> Mapping[str, float]:
        """Alias retained for callers that render component cards."""

        return self.component_inputs

    def to_dict(self) -> dict[str, object]:
        """Return only canonical JSON-safe snake_case keys and values."""

        return {
            "session_id": self.session_id,
            "block_id": self.block_id,
            "coverage": _canonical(self.coverage),
            "contacts": _canonical(self.contacts),
            "commands": _canonical(self.commands),
            "alerts": _canonical(self.alerts),
            "links": _canonical(self.links),
            "separation": _canonical(self.separation),
            "assets": _canonical(self.assets),
            "timeliness": _canonical(self.timeliness),
            "mission_score": self.mission_score,
            "composite_label": self.composite_label,
            "component_inputs": dict(self.component_inputs),
            "research": _canonical(self.research),
        }


def normalize_component(observed_ppm: Any = None, target_ppm: Any = None, **kwargs: Any) -> float:
    """Normalize an observed fraction expressed in ppm against a target.

    Both values are ppm (parts per million), making integer ratios exact and
    avoiding floating-point ambiguity at the event-reduction boundary.  The
    result is rounded to two decimals and clamped to ``[0, 100]``.  ``observed``
    and ``target`` keyword aliases are accepted for small report integrations.
    """

    if observed_ppm is None and "observed" in kwargs:
        observed_ppm = kwargs.pop("observed")
    if target_ppm is None and "target" in kwargs:
        target_ppm = kwargs.pop("target")
    if kwargs:
        raise TypeError(f"unexpected keyword argument {next(iter(kwargs))!r}")
    observed = _positive_or_zero_number(observed_ppm, "observed_ppm", allow_zero=True)
    target = _positive_or_zero_number(target_ppm, "target_ppm", allow_zero=False)
    raw = 100.0 * float(observed) / float(target)
    return round(max(0.0, min(100.0, raw)), 2)


def mission_score(coverage: float, contacts: float, assets: float, timeliness: float) -> float:
    """Calculate the descriptive weighted composite for one block."""

    raw = 0.30 * coverage + 0.30 * contacts + 0.20 * assets + 0.20 * timeliness
    return round(max(0.0, min(100.0, raw)), 2)


def derive_block_metrics(records: Iterable[SessionRecord], manifest: Mapping[str, object] | object) -> BlockMetrics:
    """Reduce one ordered block recording in a single pass.

    The sequence/session/block checks happen while records are consumed, so a
    caller may provide a generator without materialising or re-reading it.
    Stable payload aliases are intentionally narrow; malformed values raise a
    descriptive ``ValueError`` instead of silently changing denominators.
    """

    thresholds = _read_thresholds(manifest)
    expected_session = _optional_text(manifest, "session_id")
    expected_block = _optional_text(manifest, "block_id")

    session_id: str | None = None
    block_id: str | None = None
    active_aircraft: int | None = None
    required_contacts = 0
    required_actions = 0
    covered_cells = eligible_cells = 0
    coverage_ppm: int | None = None
    correct_reports = false_reports = 0
    reported_contact_ids: set[str] = set()
    contact_latencies: list[int] = []
    accepted = rejected = duplicate = 0
    alert_opened = alert_closed = alert_acknowledged = 0
    alert_advisory = alert_critical = alert_fatal = 0
    ack_latencies: list[int] = []
    lost_count = degraded_count = nominal_count = 0
    lost_duration_ms = 0
    lost_durations: list[int] = []
    open_lost_links: dict[str, int] = {}
    advisory_violations = critical_violations = separation_closed = 0
    critical_duration_ms = 0
    critical_durations: list[int] = []
    recovered_ids: set[str] = set()
    failed_ids: set[str] = set()
    recovered_count_without_id = failed_count_without_id = 0
    recovery_latencies: list[int] = []
    on_time_actions = late_actions = missed_actions = completed_actions = 0
    action_ids: dict[str, tuple[bool, bool]] = {}
    action_latencies: list[int] = []
    observed_any = False
    expected_sequence = 1
    last_simulation_time_ms: int | None = None

    for record in records:
        observed_any = True
        if not isinstance(record, SessionRecord):
            raise ValueError("records must contain SessionRecord values")
        if record.sequence != expected_sequence:
            raise ValueError(f"sequence gap: expected {expected_sequence}, got {record.sequence}")
        expected_sequence += 1
        # Keep the terminal simulation timestamp while consuming the iterable.
        # The reducer deliberately supports one-shot generators, so it must not
        # attempt to iterate ``records`` a second time when closing an open
        # link at the block boundary.
        last_simulation_time_ms = record.simulation_time_ms
        if session_id is None:
            session_id = record.session_id
        elif record.session_id != session_id:
            raise ValueError("session mismatch")
        if block_id is None:
            block_id = record.block_id
        elif record.block_id != block_id:
            raise ValueError("block mismatch")
        if expected_session is not None and record.session_id != expected_session:
            raise ValueError("session mismatch")
        if expected_block is not None and record.block_id != expected_block:
            raise ValueError("block mismatch")

        payload = _payload_view(record.payload)
        code = _code(payload)
        time_ms = record.simulation_time_ms

        # Lifecycle metadata supplies explicit denominators.  Reading it on
        # every lifecycle row permits a final snapshot to carry authoritative
        # counts without a second pass.
        active_value = _first_value(payload, "active_aircraft", "active_aircraft_count", "aircraft_count")
        if active_value is not _MISSING:
            active_aircraft = _nonnegative_int(active_value, "active_aircraft")
        aircraft_ids = _first_value(payload, "aircraft_ids", "active_aircraft_ids")
        if aircraft_ids is not _MISSING and active_aircraft is None:
            active_aircraft = _sequence_len(aircraft_ids, "active_aircraft_ids")
        required_value = _first_value(payload, "required_contacts", "required_contact_count", "contact_denominator")
        if required_value is not _MISSING:
            required_contacts = _nonnegative_int(required_value, "required_contacts")
        required_action_value = _first_value(payload, "required_actions", "required_action_count", "action_denominator")
        if required_action_value is not _MISSING:
            required_actions = _nonnegative_int(required_action_value, "required_actions")

        # Coverage is a latest/final-state component, not a sum of updates.
        if _is_coverage_code(code) or any(key in payload for key in ("coverage_ppm", "covered_cells", "eligible_cells")):
            parsed = _coverage_values(payload)
            if parsed is not None:
                covered_cells, eligible_cells, coverage_ppm = parsed

        if _is_command_result(record.kind, code, payload):
            status = _status(payload, code)
            if status == "accepted":
                accepted += 1
            elif status == "rejected":
                rejected += 1
            elif status == "duplicate":
                duplicate += 1

        if _is_contact_code(code, payload):
            correctness = _contact_correctness(payload, code)
            contact_id = _text_value(_first_value(payload, "contact_id", "id"))
            if contact_id is not None:
                if contact_id in reported_contact_ids and correctness is None:
                    continue
                reported_contact_ids.add(contact_id)
            if correctness is True:
                correct_reports += 1
            elif correctness is False:
                false_reports += 1
            latency = _duration(payload, "latency_ms", "report_latency_ms")
            if latency is not None:
                contact_latencies.append(latency)

        if _is_alert_record(record.kind, code, payload):
            lifecycle = _alert_lifecycle(payload, code)
            if lifecycle == "opened":
                alert_opened += 1
            elif lifecycle == "closed":
                alert_closed += 1
            elif lifecycle == "acknowledged":
                alert_acknowledged += 1
            severity = _severity(payload, code)
            if severity == "ADVISORY":
                alert_advisory += 1
            elif severity == "CRITICAL":
                alert_critical += 1
            elif severity == "FATAL":
                alert_fatal += 1
            latency = _duration(payload, "acknowledgement_latency_ms", "ack_latency_ms")
            if latency is not None:
                ack_latencies.append(latency)

        if _is_link_code(code, payload):
            state_to = _upper_text(_first_value(payload, "to", "state", "link_state"))
            state_from = _upper_text(_first_value(payload, "from", "previous_state"))
            aircraft_id = _text_value(_first_value(payload, "aircraft_id", "entity_id")) or "__session__"
            duration = _duration(payload, "duration_ms", "lost_duration_ms")
            if "DEGRADED" in code or state_to == "DEGRADED":
                degraded_count += 1
            if "NOMINAL" in code or state_to == "NOMINAL":
                nominal_count += 1
            is_lost = "LOST" in code or state_to == "LOST"
            if is_lost and state_to != "NOMINAL":
                lost_count += 1
                if duration is not None:
                    lost_duration_ms += duration
                    lost_durations.append(duration)
                else:
                    open_lost_links.setdefault(aircraft_id, time_ms)
            if state_from == "LOST" and state_to and state_to != "LOST":
                started = open_lost_links.pop(aircraft_id, None)
                if started is not None:
                    closed_duration = time_ms - started
                    if closed_duration < 0:
                        raise ValueError("link loss duration is negative")
                    lost_duration_ms += closed_duration
                    lost_durations.append(closed_duration)

        if _is_separation_code(code, payload):
            severity = _severity(payload, code)
            if "CLOSED" in code or _upper_text(_first_value(payload, "state", "lifecycle")) == "CLOSED":
                separation_closed += 1
            elif severity == "CRITICAL" or "CRITICAL" in code or _bool_value(_first_value(payload, "critical")) is True:
                critical_violations += 1
                duration = _duration(payload, "duration_ms", "critical_duration_ms")
                if duration is not None:
                    critical_duration_ms += duration
                    critical_durations.append(duration)
            else:
                advisory_violations += 1

        if _is_asset_code(code, payload):
            aircraft_id = _text_value(_first_value(payload, "aircraft_id", "entity_id"))
            if "RECOVER" in code or _upper_text(_first_value(payload, "to", "mode", "status")) == "RECOVERED":
                if aircraft_id is None:
                    recovered_count_without_id += 1
                else:
                    recovered_ids.add(aircraft_id)
                duration = _duration(payload, "latency_ms", "recovery_latency_ms")
                if duration is not None:
                    recovery_latencies.append(duration)
            elif "FAIL" in code or "LOST" in code or _upper_text(_first_value(payload, "to", "mode", "status")) in {"MISSION_FAILED", "FAILED"}:
                if aircraft_id is None:
                    failed_count_without_id += 1
                else:
                    failed_ids.add(aircraft_id)

        if _is_action_code(code, payload):
            action_id = _text_value(_first_value(payload, "action_id", "required_action_id", "id"))
            on_time = _bool_value(_first_value(payload, "on_time", "on_time_action"))
            if on_time is None:
                on_time = not ("LATE" in code or "MISSED" in code or _upper_text(_first_value(payload, "status", "outcome")) in {"LATE", "MISSED"})
            missed = "MISSED" in code or _upper_text(_first_value(payload, "status", "outcome")) == "MISSED"
            if action_id is None:
                if missed:
                    missed_actions += 1
                elif on_time:
                    on_time_actions += 1
                else:
                    late_actions += 1
                completed_actions += 0 if missed else 1
            else:
                action_ids[action_id] = (on_time, missed)
            latency = _duration(payload, "latency_ms", "action_latency_ms")
            if latency is not None:
                action_latencies.append(latency)

    if not observed_any:
        raise ValueError("no records")
    if active_aircraft is None:
        inferred = len(recovered_ids | failed_ids) + recovered_count_without_id + failed_count_without_id
        active_aircraft = inferred
    if active_aircraft <= 0:
        raise ValueError("no active aircraft")

    # Close a loss that remains active at the block boundary using the last
    # observed simulation timestamp.  Explicit durations remain authoritative.
    if open_lost_links:
        assert last_simulation_time_ms is not None
        final_time = last_simulation_time_ms
        for started in open_lost_links.values():
            duration = final_time - started
            if duration < 0:
                raise ValueError("link loss duration is negative")
            lost_duration_ms += duration
            lost_durations.append(duration)

    if coverage_ppm is None:
        coverage_ppm = _fraction_to_ppm(covered_cells, eligible_cells) if eligible_cells else 0
    elif eligible_cells == 0 and covered_cells:
        raise ValueError("coverage eligible denominator is zero")
    coverage_percent = round(100.0 * float(coverage_ppm) / _PPM, 2)

    contact_required = required_contacts
    if contact_required == 0:
        contact_fraction = 1.0
        contact_component = 100.0
    else:
        contact_fraction = correct_reports / contact_required
        contact_component = normalize_component(_fraction_to_ppm(correct_reports, contact_required), thresholds["contacts"])

    if required_actions == 0:
        timeliness_fraction = 1.0
        timeliness_component = 100.0
    else:
        if action_ids:
            on_time_actions = sum(1 for on_time, missed in action_ids.values() if on_time and not missed)
            late_actions = sum(1 for on_time, missed in action_ids.values() if not on_time and not missed)
            missed_actions = sum(1 for _, missed in action_ids.values() if missed)
            completed_actions = on_time_actions + late_actions
        timeliness_fraction = on_time_actions / required_actions
        timeliness_component = normalize_component(_fraction_to_ppm(on_time_actions, required_actions), thresholds["timeliness"])

    recovered = len(recovered_ids) + recovered_count_without_id
    failed = len(failed_ids) + failed_count_without_id
    preserved = max(0, active_aircraft - failed)
    # An explicit recovered count is useful to reports, while preservation is
    # based on assets not in a terminal failure state.
    preservation_fraction = preserved / active_aircraft
    asset_component = normalize_component(_fraction_to_ppm(preserved, active_aircraft), thresholds["assets"])
    coverage_component = normalize_component(coverage_ppm, thresholds["coverage"])
    components = {
        "coverage": coverage_component,
        "contacts": contact_component,
        "assets": asset_component,
        "timeliness": timeliness_component,
    }
    score = mission_score(**components)

    coverage_metrics = CoverageMetrics(covered_cells, eligible_cells, coverage_ppm, coverage_percent, thresholds["coverage"], coverage_component)
    contact_metrics = ContactMetrics(
        contact_required, correct_reports + false_reports, correct_reports, false_reports,
        max(0, contact_required - correct_reports), contact_fraction, thresholds["contacts"],
        contact_component, min(contact_latencies) if contact_latencies else None,
        max(contact_latencies) if contact_latencies else None,
    )
    command_metrics = CommandMetrics(accepted, rejected, duplicate, accepted + rejected + duplicate)
    alert_metrics = AlertMetrics(
        alert_opened, alert_closed, alert_acknowledged, alert_advisory, alert_critical, alert_fatal,
        min(ack_latencies) if ack_latencies else None, max(ack_latencies) if ack_latencies else None,
    )
    link_metrics = LinkMetrics(
        lost_count, lost_duration_ms, degraded_count, nominal_count,
        max(lost_durations) if lost_durations else None,
    )
    separation_metrics = SeparationMetrics(
        advisory_violations, critical_violations, separation_closed, critical_duration_ms,
        max(critical_durations) if critical_durations else None,
    )
    asset_metrics = AssetMetrics(
        active_aircraft, recovered, failed, preserved, preservation_fraction,
        thresholds["assets"], asset_component,
        min(recovery_latencies) if recovery_latencies else None,
        max(recovery_latencies) if recovery_latencies else None,
    )
    timeliness_metrics = TimelinessMetrics(
        required_actions, completed_actions, on_time_actions, late_actions, missed_actions,
        timeliness_fraction, thresholds["timeliness"], timeliness_component,
        min(action_latencies) if action_latencies else None,
        max(action_latencies) if action_latencies else None,
    )
    return BlockMetrics(
        coverage=coverage_metrics,
        contacts=contact_metrics,
        commands=command_metrics,
        alerts=alert_metrics,
        links=link_metrics,
        separation=separation_metrics,
        assets=asset_metrics,
        timeliness=timeliness_metrics,
        mission_score=score,
        component_inputs=components,
        session_id=session_id,
        block_id=block_id,
    )


def _read_thresholds(manifest: Mapping[str, object] | object) -> dict[str, int]:
    containers: list[Any] = []
    if isinstance(manifest, Mapping):
        for key in ("metric_thresholds", "thresholds", "metrics"):
            value = manifest.get(key)
            if value is not None:
                containers.append(value)
        containers.append(manifest)
    else:
        for key in ("metric_thresholds", "thresholds", "metrics"):
            value = getattr(manifest, key, None)
            if value is not None:
                containers.append(value)
        containers.append(manifest)
    names = {
        "coverage": ("coverage_target_ppm", "coverage_target_percent", "coverage_target", "coverage"),
        "contacts": (
            "contact_effectiveness_target_ppm", "contact_effectiveness_target_percent",
            "contact_effectiveness_target", "contacts_target_ppm", "contacts_target",
        ),
        "assets": (
            "asset_preservation_target_ppm", "asset_preservation_target_percent",
            "asset_preservation_target", "assets_target_ppm", "assets_target",
        ),
        "timeliness": (
            "timeliness_target_ppm", "timeliness_target_percent", "timeliness_target",
        ),
    }
    result: dict[str, int] = {}
    for component, candidates in names.items():
        raw = _lookup(containers, candidates)
        if raw is _MISSING:
            raise ValueError(f"missing {component} target")
        result[component] = _target_to_ppm(raw, component, candidates, containers)
        if result[component] <= 0:
            raise ValueError(f"{component} target must be positive")
    return result


def _target_to_ppm(raw: Any, component: str, candidates: tuple[str, ...], containers: list[Any]) -> int:
    number = _number(raw, f"{component} target")
    if number <= 0:
        raise ValueError(f"{component} target must be positive")
    # A ppm key is unambiguous.  Percent keys use percentage points.  Bare
    # coverage values follow the scenario schema (0..100 percent); other bare
    # values follow the schema's 0..1 fraction convention when possible.
    selected = next((name for name in candidates if _lookup(containers, (name,)) is not _MISSING), "")
    if selected.endswith("_ppm"):
        return int(round(float(number)))
    if selected.endswith("_percent"):
        return int(round(float(number) * 10_000))
    if component == "coverage":
        if number <= 1:
            return int(round(float(number) * _PPM))
        if number <= 100:
            return int(round(float(number) * 10_000))
    elif number <= 1:
        return int(round(float(number) * _PPM))
    if number <= 100:
        return int(round(float(number) * 10_000))
    return int(round(float(number)))


def _lookup(containers: list[Any], names: tuple[str, ...]) -> Any:
    for container in containers:
        if isinstance(container, Mapping):
            for name in names:
                if name in container:
                    return container[name]
        else:
            for name in names:
                value = getattr(container, name, _MISSING)
                if value is not _MISSING:
                    return value
    return _MISSING


def _optional_text(container: Mapping[str, object] | object, key: str) -> str | None:
    value = container.get(key) if isinstance(container, Mapping) else getattr(container, key, None)
    return value if isinstance(value, str) and value else None


def _payload_view(payload: Mapping[str, object]) -> dict[str, object]:
    """Flatten a record payload and one canonical domain-event envelope."""

    view: dict[str, object] = dict(payload)
    nested = payload.get("event")
    if isinstance(nested, Mapping):
        view.update(nested)
        nested_payload = nested.get("payload")
        if isinstance(nested_payload, Mapping):
            view.update(nested_payload)
    nested_payload = payload.get("payload")
    if isinstance(nested_payload, Mapping):
        view.update(nested_payload)
    return view


def _code(payload: Mapping[str, object]) -> str:
    value = _first_value(payload, "code", "event_code", "result_code", "kind", "type", "name", "event")
    if isinstance(value, Mapping):
        value = _first_value(value, "code", "kind", "type", "name")
    text = _text_value(value) or ""
    return _normal_code(text)


def _normal_code(value: str) -> str:
    return value.strip().upper().replace("-", "_").replace(" ", "_")


def _first_value(payload: Mapping[str, object], *keys: str) -> object:
    for key in keys:
        if key in payload:
            return payload[key]
    return _MISSING


def _text_value(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _upper_text(value: object) -> str | None:
    text = _text_value(value)
    return text.upper() if text is not None else None


def _bool_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "on", "1"}:
            return True
        if normalized in {"false", "no", "off", "0"}:
            return False
    return None


def _number(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or value is _MISSING or value is None:
        raise ValueError(f"{label} must be numeric")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not number.is_finite():
        raise ValueError(f"{label} must be finite")
    return number


def _positive_or_zero_number(value: object, label: str, *, allow_zero: bool) -> Decimal:
    number = _number(value, label)
    if (allow_zero and number < 0) or (not allow_zero and number <= 0):
        qualifier = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"{label} must be {qualifier}")
    return number


def _nonnegative_int(value: object, label: str) -> int:
    number = _number(value, label)
    if number < 0 or number != number.to_integral_value():
        raise ValueError(f"{label} must be a nonnegative integer")
    return int(number)


def _sequence_len(value: object, label: str) -> int:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Iterable):
        raise ValueError(f"{label} must be a sequence")
    return len(tuple(value))


def _duration(payload: Mapping[str, object], *keys: str) -> int | None:
    value = _first_value(payload, *keys)
    if value is _MISSING:
        return None
    duration = _nonnegative_int(value, keys[0])
    return duration


def _fraction_to_ppm(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return int(round(_PPM * numerator / denominator))


def _coverage_values(payload: Mapping[str, object]) -> tuple[int, int, int] | None:
    covered = _first_value(payload, "covered_cells", "covered_cell_count")
    eligible = _first_value(payload, "eligible_cells", "eligible_cell_count")
    ppm = _first_value(payload, "coverage_ppm")
    fraction = _first_value(payload, "coverage_fraction", "covered_fraction", "fraction", "percent")
    if covered is not _MISSING:
        covered_i = _nonnegative_int(covered, "covered_cells")
    else:
        covered_i = 0
    if eligible is not _MISSING:
        eligible_i = _nonnegative_int(eligible, "eligible_cells")
    else:
        eligible_i = 0
    if ppm is not _MISSING:
        ppm_i = _nonnegative_int(ppm, "coverage_ppm")
    elif fraction is not _MISSING:
        value = _number(fraction, "coverage fraction")
        if value > 1:
            value /= 100
        if value < 0:
            raise ValueError("coverage fraction must be nonnegative")
        ppm_i = int(round(float(value) * _PPM))
    elif eligible_i:
        ppm_i = _fraction_to_ppm(covered_i, eligible_i)
    else:
        return None
    if ppm_i > _PPM and fraction is not _MISSING:
        raise ValueError("coverage fraction exceeds 100 percent")
    return covered_i, eligible_i, ppm_i


def _is_coverage_code(code: str) -> bool:
    return "COVERAGE" in code


def _is_command_result(kind: RecordKind, code: str, payload: Mapping[str, object]) -> bool:
    if kind is RecordKind.COMMAND_RESULT:
        return True
    return kind is RecordKind.COMMAND and (
        "status" in payload or "result" in payload or "outcome" in payload
    )


def _status(payload: Mapping[str, object], code: str) -> str | None:
    value = _first_value(payload, "status", "result", "outcome", "code")
    status = _normal_code(_text_value(value) or code)
    if status in {"ACCEPTED", "OK", "SUCCESS", "COMMAND_ACCEPTED"} or "ACCEPTED" in status:
        return "accepted"
    if status in {"REJECTED", "FAILED", "ERROR", "COMMAND_REJECTED"} or "REJECT" in status:
        return "rejected"
    if status in {"DUPLICATE", "COMMAND_DUPLICATE"}:
        return "duplicate"
    return None


def _is_contact_code(code: str, payload: Mapping[str, object]) -> bool:
    return "CONTACT" in code and ("REPORT" in code or _first_value(payload, "correct", "is_correct") is not _MISSING)


def _contact_correctness(payload: Mapping[str, object], code: str) -> bool | None:
    value = _first_value(payload, "correct", "is_correct")
    parsed = _bool_value(value)
    if parsed is not None:
        return parsed
    if "FALSE" in code or "INCORRECT" in code:
        return False
    if "CORRECT" in code:
        return True
    return None


def _is_alert_record(kind: RecordKind, code: str, payload: Mapping[str, object]) -> bool:
    return kind is RecordKind.ALERT or "ALERT" in code or any(term in code for term in ("LINK_LOST", "SEPARATION_"))


def _alert_lifecycle(payload: Mapping[str, object], code: str) -> str | None:
    state = _upper_text(_first_value(payload, "lifecycle", "state", "status", "action"))
    if state in {"OPEN", "OPENED", "STARTED"} or "OPENED" in code:
        return "opened"
    if state in {"CLOSED", "CLOSE", "RESOLVED"} or "CLOSED" in code:
        return "closed"
    if state in {"ACK", "ACKNOWLEDGED"} or "ACK" in code:
        return "acknowledged"
    return None


def _severity(payload: Mapping[str, object], code: str) -> str | None:
    value = _upper_text(_first_value(payload, "severity", "level"))
    if value in {"ADVISORY", "CRITICAL", "FATAL"}:
        return value
    for severity in ("FATAL", "CRITICAL", "ADVISORY"):
        if severity in code:
            return severity
    return None


def _is_link_code(code: str, payload: Mapping[str, object]) -> bool:
    return "LINK" in code or _first_value(payload, "link_state", "lost_duration_ms") is not _MISSING


def _is_separation_code(code: str, payload: Mapping[str, object]) -> bool:
    return "SEPARATION" in code or _first_value(payload, "critical", "critical_duration_ms") is not _MISSING


def _is_asset_code(code: str, payload: Mapping[str, object]) -> bool:
    return any(term in code for term in ("RECOVER", "AIRCRAFT_FAIL", "AIRCRAFT_LOST", "ASSET")) or _first_value(payload, "aircraft_id", "asset_id") is not _MISSING and any(term in code for term in ("MODE", "STATUS"))


def _is_action_code(code: str, payload: Mapping[str, object]) -> bool:
    return "ACTION" in code or _first_value(payload, "on_time", "on_time_action", "required_action_id") is not _MISSING


def _canonical(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_canonical(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import fields

        return {item.name: _canonical(getattr(value, item.name)) for item in fields(value)}
    return value
