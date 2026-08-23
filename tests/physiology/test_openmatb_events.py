from __future__ import annotations

import json
from pathlib import Path

import pytest

from matb_integration.openmatb_events import (
    OPENMATB_EVENT_SCHEMA_VERSION,
    OpenMATBEventStreamError,
    OpenMATBEventTail,
    find_openmatb_event,
)


SESSION_ID = "de4ad40d-7cbb-4b2a-a4c6-9f839a086c4e"


def _event(sequence: int, event: str) -> bytes:
    return (
        json.dumps(
            {
                "schema_version": OPENMATB_EVENT_SCHEMA_VERSION,
                "session_id": SESSION_ID,
                "sequence": sequence,
                "received_monotonic_ns": str(1_000_000_000 + sequence),
                "received_utc_ns": str(2_000_000_000 + sequence),
                "scenario_time": 0.0 if sequence == 1 else 900.0,
                "event": event,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def test_incremental_tail_waits_for_complete_record_and_preserves_order(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    first = _event(1, "scenario_started")
    second = _event(2, "task_window_completed")
    split = len(second) // 2
    path.write_bytes(first + second[:split])
    tail = OpenMATBEventTail(path, session_id=SESSION_ID)

    assert [record["event"] for record in tail.read_new()] == ["scenario_started"]
    with path.open("ab") as stream:
        stream.write(second[split:])
    assert [record["event"] for record in tail.read_new()] == [
        "task_window_completed"
    ]
    assert tail.read_new() == ()


def test_v2_requires_decimal_string_nanoseconds_and_exact_sequence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    invalid = json.loads(_event(1, "scenario_started"))
    invalid["received_monotonic_ns"] = 1_000_000_001
    path.write_text(json.dumps(invalid) + "\n", encoding="utf-8")

    with pytest.raises(OpenMATBEventStreamError, match="openmatb_event_stream_invalid"):
        OpenMATBEventTail(path, session_id=SESSION_ID).read_new()

    path.write_bytes(_event(2, "scenario_started"))
    with pytest.raises(OpenMATBEventStreamError, match="openmatb_event_stream_invalid"):
        OpenMATBEventTail(path, session_id=SESSION_ID).read_new()


def test_completed_reader_rejects_a_non_newline_terminated_final_record(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(_event(1, "scenario_started").rstrip(b"\n"))

    with pytest.raises(OpenMATBEventStreamError, match="openmatb_event_stream_truncated"):
        find_openmatb_event(path, "scenario_started", session_id=SESSION_ID)


def test_completed_reader_accepts_legacy_v1_integer_timestamps(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        json.dumps(
            {
                "schema_version": "openmatb-synchronized-event-v1",
                "session_id": SESSION_ID,
                "sequence": 1,
                "received_monotonic_ns": 1_000_000_001,
                "received_utc_ns": 2_000_000_001,
                "scenario_time": 0.0,
                "event": "scenario_started",
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    record = find_openmatb_event(
        path,
        "scenario_started",
        session_id=SESSION_ID,
    )
    assert record is not None
    assert record["sequence"] == 1
