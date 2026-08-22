"""Typed, validated records and artifact metadata for sUAS recordings."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from matb_integration.recording.records import ArtifactInfo
from matb_integration.suas.domain.serialization import canonical_data


class RecordKind(StrEnum):
    LIFECYCLE = "lifecycle"
    COMMAND = "command"
    COMMAND_RESULT = "command_result"
    DOMAIN_EVENT = "domain_event"
    ALERT = "alert"
    PROBE = "probe"
    QUESTIONNAIRE = "questionnaire"
    PROTOCOL_DEVIATION = "protocol_deviation"
    CHECKPOINT = "checkpoint"


class RecordingError(RuntimeError):
    """Raised when a durable recording operation cannot be completed."""


@dataclass(frozen=True, slots=True)
class SessionRecord:
    session_id: str
    block_id: str
    sequence: int
    simulation_time_ms: int
    wall_time_utc: str
    state_version: int
    kind: RecordKind
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, str) or not self.session_id:
            raise ValueError("session_id must be nonempty")
        if not isinstance(self.block_id, str) or not self.block_id:
            raise ValueError("block_id must be nonempty")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence <= 0:
            raise ValueError("sequence must be positive")
        if isinstance(self.simulation_time_ms, bool) or not isinstance(self.simulation_time_ms, int) or self.simulation_time_ms < 0:
            raise ValueError("simulation_time_ms must be nonnegative")
        if isinstance(self.state_version, bool) or not isinstance(self.state_version, int) or self.state_version < 0:
            raise ValueError("state_version must be nonnegative")
        if not isinstance(self.wall_time_utc, str):
            raise ValueError("wall_time_utc must be a UTC timestamp")
        try:
            parsed = datetime.fromisoformat(self.wall_time_utc.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("wall_time_utc must be parseable") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ValueError("wall_time_utc must be UTC")
        if not isinstance(self.payload, Mapping):
            raise ValueError("payload must be a mapping")
        try:
            kind = RecordKind(self.kind)
        except ValueError as exc:
            raise ValueError("kind must be a known record kind") from exc
        object.__setattr__(self, "kind", kind)
        try:
            canonical_data(self.payload)
        except (TypeError, ValueError) as exc:
            raise ValueError("payload must be JSON-safe") from exc
