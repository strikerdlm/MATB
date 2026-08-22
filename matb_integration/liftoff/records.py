"""Immutable canonical records for Liftoff telemetry and phase markers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import re
from typing import ClassVar
from uuid import UUID

from .protocol import LiftoffPacket

_BOUNDED_CODE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _validate_session_id(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("session_id must be a canonical UUID")
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("session_id must be a canonical UUID") from exc
    if str(parsed) != value:
        raise ValueError("session_id must be a canonical UUID")


def _validate_sequence(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("sequence must be positive")


def _validate_monotonic_ns(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("received_monotonic_ns must be nonnegative")


def _validate_utc(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("received_utc must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("received_utc must be a UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("received_utc must be a UTC timestamp")


@dataclass(frozen=True, slots=True)
class TelemetryRecord:
    schema_version: ClassVar[str] = "liftoff-telemetry-v1"

    session_id: str
    sequence: int
    received_monotonic_ns: int
    received_utc: str
    packet: LiftoffPacket

    def __post_init__(self) -> None:
        _validate_session_id(self.session_id)
        _validate_sequence(self.sequence)
        _validate_monotonic_ns(self.received_monotonic_ns)
        _validate_utc(self.received_utc)
        if not isinstance(self.packet, LiftoffPacket):
            raise ValueError("packet must be a LiftoffPacket")

    def as_dict(self) -> dict[str, object]:
        packet = self.packet
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "sequence": self.sequence,
            "received_monotonic_ns": self.received_monotonic_ns,
            "received_utc": self.received_utc,
            "simulator_time": packet.simulator_time,
            "position_native": list(packet.position_native),
            "attitude_native": list(packet.attitude_native),
            "velocity_native": list(packet.velocity_native),
            "angular_rate_native": list(packet.angular_rate_native),
            "processed_input": list(packet.processed_input),
            "battery_voltage": packet.battery_voltage,
            "charge_percent": packet.charge_percent,
            "motor_rpm": list(packet.motor_rpm),
        }


class MarkerKind(StrEnum):
    RECORDING_STARTED = "recording_started"
    BASELINE_STARTED = "baseline_started"
    BASELINE_FINISHED = "baseline_finished"
    TASK_STARTED = "task_started"
    TASK_FINISHED = "task_finished"
    RECOVERY_STARTED = "recovery_started"
    RECOVERY_FINISHED = "recovery_finished"
    RECORDING_FINISHED = "recording_finished"
    QUESTIONNAIRES_COMPLETED = "questionnaires_completed"
    SESSION_SEALED = "session_sealed"
    AMENDMENT = "amendment"


@dataclass(frozen=True, slots=True)
class MarkerRecord:
    schema_version: ClassVar[str] = "liftoff-marker-v1"

    session_id: str
    sequence: int
    received_monotonic_ns: int
    received_utc: str
    kind: MarkerKind | str
    phase: str
    source: str
    reason_code: str | None = None
    amendment_of_sequence: int | None = None

    def __post_init__(self) -> None:
        _validate_session_id(self.session_id)
        _validate_sequence(self.sequence)
        _validate_monotonic_ns(self.received_monotonic_ns)
        _validate_utc(self.received_utc)
        try:
            kind = MarkerKind(self.kind)
        except ValueError as exc:
            raise ValueError("kind must be a declared marker kind") from exc
        object.__setattr__(self, "kind", kind)
        for value, name in ((self.phase, "phase"), (self.source, "source")):
            if not isinstance(value, str) or _BOUNDED_CODE.fullmatch(value) is None:
                raise ValueError(f"{name} must be a bounded code")
        if self.reason_code is not None and _BOUNDED_CODE.fullmatch(self.reason_code) is None:
            raise ValueError("reason_code must be a bounded code")
        if kind is MarkerKind.AMENDMENT:
            if (
                isinstance(self.amendment_of_sequence, bool)
                or not isinstance(self.amendment_of_sequence, int)
                or self.amendment_of_sequence <= 0
                or self.amendment_of_sequence >= self.sequence
            ):
                raise ValueError("amendment_of_sequence must reference an earlier marker")
        elif self.amendment_of_sequence is not None:
            raise ValueError("amendment_of_sequence is only valid for amendment markers")

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "sequence": self.sequence,
            "received_monotonic_ns": self.received_monotonic_ns,
            "received_utc": self.received_utc,
            "kind": self.kind.value,
            "phase": self.phase,
            "source": self.source,
        }
        if self.reason_code is not None:
            payload["reason_code"] = self.reason_code
        if self.amendment_of_sequence is not None:
            payload["amendment_of_sequence"] = self.amendment_of_sequence
        return payload


__all__ = ["MarkerKind", "MarkerRecord", "TelemetryRecord"]
