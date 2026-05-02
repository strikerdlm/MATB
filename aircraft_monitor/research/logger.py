"""Structured JSONL logger for research runs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, TextIO

from aircraft_monitor.events.base import Event
from aircraft_monitor.research.protocol import DemandBlock, ResearchProtocol

SAFE_COMPONENT_RE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True, slots=True)
class ResearchRunPaths:
    """Filesystem paths created for one research run."""

    run_dir: Path
    events_jsonl: Path
    summary_json: Path


class ResearchLogger:
    """Write bounded research events and summary data as JSON lines."""

    def __init__(
        self,
        *,
        output_dir: Path,
        participant_id: str,
        session_id: str,
        protocol: ResearchProtocol,
    ) -> None:
        """Create a logger for one participant/session/protocol run.

        Raises:
            ValueError: If participant or session identifiers are empty.
            OSError: If the output directory cannot be created.
        """
        clean_participant = participant_id.strip()
        clean_session = session_id.strip()
        if not clean_participant:
            raise ValueError("participant_id must not be empty.")
        if not clean_session:
            raise ValueError("session_id must not be empty.")

        self._participant_id = clean_participant
        self._session_id = clean_session
        self._protocol = protocol
        self._event_count = 0
        self._counts_by_block: dict[str, int] = {}
        self._counts_by_category: dict[str, int] = {}
        self._counts_by_severity: dict[str, int] = {}
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%S%fZ")
        safe_name = (
            f"{timestamp}_{self._safe_component(clean_participant)}_"
            f"{self._safe_component(clean_session)}_{protocol.modality.value}"
        )
        run_dir = output_dir / safe_name
        run_dir.mkdir(parents=True, exist_ok=False)
        self.paths = ResearchRunPaths(
            run_dir=run_dir,
            events_jsonl=run_dir / "events.jsonl",
            summary_json=run_dir / "summary.json",
        )
        self._events_file: TextIO | None = None

    def __enter__(self) -> "ResearchLogger":
        """Open the JSONL event file."""
        self._events_file = self.paths.events_jsonl.open("w", encoding="utf-8")
        self._write_jsonl(
            {
                "record_type": "run_start",
                "wall_time_utc": datetime.now(tz=UTC).isoformat(),
                "participant_id": self._participant_id,
                "session_id": self._session_id,
                "protocol": self._protocol.name,
                "modality": self._protocol.modality.value,
                "seed": self._protocol.seed,
                "blocks": [self._block_payload(block) for block in self._protocol.blocks],
            }
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the JSONL file."""
        if self._events_file is not None:
            self._events_file.close()
            self._events_file = None

    def record_event(
        self,
        *,
        block: DemandBlock,
        event: Event,
        event_index: int,
        monotonic_sec: float,
    ) -> None:
        """Record one dashboard event with trial metadata."""
        if monotonic_sec < 0.0:
            raise ValueError("monotonic_sec must be non-negative.")
        payload = {
            "record_type": "event",
            "participant_id": self._participant_id,
            "session_id": self._session_id,
            "protocol": self._protocol.name,
            "modality": self._protocol.modality.value,
            "block": block.name,
            "workload": block.workload.value,
            "automation_mode": block.automation_mode.value,
            "automation_reliability": block.automation_reliability,
            "event_index": event_index,
            "monotonic_sec": round(monotonic_sec, 6),
            "wall_time_local": event.timestamp.isoformat(),
            "severity": event.severity.value,
            "category": event.category.value,
            "title": event.title,
            "description": event.description,
            "source": event.source,
            "data": event.data,
        }
        self._event_count += 1
        self._counts_by_block[block.name] = self._counts_by_block.get(block.name, 0) + 1
        self._counts_by_category[event.category.value] = (
            self._counts_by_category.get(event.category.value, 0) + 1
        )
        self._counts_by_severity[event.severity.value] = (
            self._counts_by_severity.get(event.severity.value, 0) + 1
        )
        self._write_jsonl(payload)

    def write_summary(self) -> None:
        """Write one run summary JSON file."""
        payload = {
            "record_type": "run_summary",
            "wall_time_utc": datetime.now(tz=UTC).isoformat(),
            "participant_id": self._participant_id,
            "session_id": self._session_id,
            "protocol": self._protocol.name,
            "modality": self._protocol.modality.value,
            "seed": self._protocol.seed,
            "event_count": self._event_count,
            "counts_by_block": self._counts_by_block,
            "counts_by_category": self._counts_by_category,
            "counts_by_severity": self._counts_by_severity,
            "events_jsonl": str(self.paths.events_jsonl),
        }
        with self.paths.summary_json.open("w", encoding="utf-8") as summary_file:
            json.dump(payload, summary_file, indent=2, sort_keys=True)
            summary_file.write("\n")

    def _write_jsonl(self, payload: dict[str, Any]) -> None:
        """Write a JSON line to the active event file."""
        if self._events_file is None:
            raise RuntimeError("ResearchLogger must be used as a context manager.")
        json.dump(payload, self._events_file, sort_keys=True)
        self._events_file.write("\n")
        self._events_file.flush()

    @staticmethod
    def _block_payload(block: DemandBlock) -> dict[str, Any]:
        """Serialize block metadata."""
        return {
            "name": block.name,
            "workload": block.workload.value,
            "max_events": block.max_events,
            "workload_probe_interval_events": block.workload_probe_interval_events,
            "response_window_sec": block.response_window_sec,
            "automation_mode": block.automation_mode.value,
            "automation_reliability": block.automation_reliability,
        }

    @staticmethod
    def _safe_component(value: str) -> str:
        """Return a filesystem-safe path component."""
        safe = SAFE_COMPONENT_RE.sub("-", value.strip())
        if not safe:
            raise ValueError("Path component must not be empty after sanitization.")
        return safe
