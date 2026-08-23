"""Portable contract reader for OpenMATB synchronized JSONL events."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


OPENMATB_EVENT_SCHEMA_VERSION = "openmatb-synchronized-event-v2"
_LEGACY_EVENT_SCHEMA_VERSION = "openmatb-synchronized-event-v1"
_SUPPORTED_EVENT_SCHEMAS = {
    _LEGACY_EVENT_SCHEMA_VERSION,
    OPENMATB_EVENT_SCHEMA_VERSION,
}


class OpenMATBEventStreamError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def validate_openmatb_event(
    record: object,
    *,
    session_id: str,
    expected_sequence: int,
) -> dict[str, Any]:
    """Validate identity/order and the v2 nanosecond encoding contract."""

    if not isinstance(record, dict):
        raise OpenMATBEventStreamError("openmatb_event_stream_invalid")
    schema_version = record.get("schema_version")
    sequence = record.get("sequence")
    if (
        schema_version not in _SUPPORTED_EVENT_SCHEMAS
        or record.get("session_id") != session_id
        or isinstance(sequence, bool)
        or sequence != expected_sequence
    ):
        raise OpenMATBEventStreamError("openmatb_event_stream_invalid")
    if schema_version == OPENMATB_EVENT_SCHEMA_VERSION:
        for field in ("received_monotonic_ns", "received_utc_ns"):
            value = record.get(field)
            if not isinstance(value, str) or not value.isdigit():
                raise OpenMATBEventStreamError("openmatb_event_stream_invalid")
    return record


class OpenMATBEventTail:
    """Incrementally read and validate each complete JSONL record once."""

    def __init__(self, path: Path, *, session_id: str) -> None:
        self.path = Path(path)
        self.session_id = session_id
        self.offset = 0
        self.pending = b""
        self.sequence = 0

    def read_new(self) -> tuple[dict[str, Any], ...]:
        try:
            with self.path.open("rb") as stream:
                stream.seek(0, 2)
                size = stream.tell()
                if size < self.offset:
                    raise OpenMATBEventStreamError(
                        "openmatb_event_stream_truncated"
                    )
                stream.seek(self.offset)
                chunk = stream.read()
        except FileNotFoundError:
            return ()
        self.offset += len(chunk)
        if not chunk:
            return ()
        parts = (self.pending + chunk).split(b"\n")
        self.pending = parts.pop()
        parsed: list[dict[str, Any]] = []
        for raw_line in parts:
            if not raw_line:
                raise OpenMATBEventStreamError("openmatb_event_stream_invalid")
            try:
                record = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, TypeError, ValueError) as exc:
                raise OpenMATBEventStreamError(
                    "openmatb_event_stream_invalid"
                ) from exc
            expected_sequence = self.sequence + 1
            parsed.append(
                validate_openmatb_event(
                    record,
                    session_id=self.session_id,
                    expected_sequence=expected_sequence,
                )
            )
            self.sequence = expected_sequence
        return tuple(parsed)


def find_openmatb_event(
    events_path: Path,
    event_name: str,
    *,
    session_id: str,
) -> dict[str, Any] | None:
    """Validate a completed sidecar and return its first requested event."""

    try:
        payload = Path(events_path).read_bytes()
    except OSError:
        return None
    if payload and not payload.endswith(b"\n"):
        raise OpenMATBEventStreamError("openmatb_event_stream_truncated")
    found: dict[str, Any] | None = None
    for sequence, raw_line in enumerate(payload.splitlines(), start=1):
        if not raw_line:
            raise OpenMATBEventStreamError("openmatb_event_stream_invalid")
        try:
            raw_record = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, TypeError, ValueError) as exc:
            raise OpenMATBEventStreamError("openmatb_event_stream_invalid") from exc
        record = validate_openmatb_event(
            raw_record,
            session_id=session_id,
            expected_sequence=sequence,
        )
        if found is None and record.get("event") == event_name:
            found = record
    return found


__all__ = [
    "OPENMATB_EVENT_SCHEMA_VERSION",
    "OpenMATBEventStreamError",
    "OpenMATBEventTail",
    "find_openmatb_event",
    "validate_openmatb_event",
]
