"""Append-only session records and atomic private-engine checkpoints."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import BinaryIO

from matb_integration.suas.domain.serialization import canonical_data, canonical_json, canonical_sha256
from matb_integration.suas.scenarios.loader import load_scenario

from .checkpoints import load_checkpoint
from .records import ArtifactInfo, RecordKind, RecordingError, SessionRecord

_CHECKPOINT_INTERVAL_MS = 5_000
_PRIVATE_CHECKPOINT_FIELDS = frozenset({
    "engine_version", "scenario_id", "scenario_sha256", "block_id", "clock", "tick",
    "simulation_time_ms", "state_version", "world", "sensor_prng", "sensor_reports",
    "link_applied_event_ids", "conflict_applied_event_ids", "conflict_pending_releases",
    "sensor_due_times", "coverage_cells", "separation", "command_results",
    "authoritative_state_sha256",
})


class SessionRecorder:
    """Owns a run directory whose records can only be appended."""

    def __init__(self, run_dir: Path, manifest: Mapping[str, object], scenario_yaml: str) -> None:
        self.run_dir = Path(run_dir)
        self.checkpoints_dir = self.run_dir / "checkpoints"
        self._last_sequence = 0
        self._checkpoint_version = 0
        self._last_checkpoint_time_ms: int | None = None
        self._last_checkpoint_block_id: str | None = None
        self._last_checkpoint: ArtifactInfo | None = None
        if not isinstance(scenario_yaml, str):
            raise RecordingError("scenario_yaml must be text")
        try:
            canonical_data(manifest)
            self.run_dir.mkdir(parents=True, exist_ok=False)
            self.checkpoints_dir.mkdir(exist_ok=False)
            self._write_atomic(self.run_dir / "manifest.json", canonical_json(manifest).encode("utf-8"))
            self._write_atomic(self.run_dir / "scenario.yaml", scenario_yaml.encode("utf-8"))
            events_path = self.run_dir / "events.jsonl"
            with events_path.open("xb"):
                pass
            self._events: BinaryIO = events_path.open("ab")
        except (OSError, TypeError, ValueError) as exc:
            raise RecordingError(f"recording initialization failed: {exc}") from exc

    @classmethod
    def open_existing(cls, run_dir: Path) -> "SessionRecorder":
        run_dir = Path(run_dir)
        if (run_dir / "checksums.sha256").exists() or (run_dir / "partial-run.json").exists():
            raise RecordingError("sealed run cannot be reopened for appends")
        manifest_path = run_dir / "manifest.json"
        scenario_path = run_dir / "scenario.yaml"
        events_path = run_dir / "events.jsonl"
        checkpoints_dir = run_dir / "checkpoints"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict) or canonical_json(manifest) != manifest_path.read_text(encoding="utf-8"):
                raise ValueError("manifest is not canonical")
            scenario = load_scenario(scenario_path)
            if manifest.get("scenario_id") != scenario.definition.scenario_id or manifest.get("scenario_sha256") != scenario.sha256:
                raise ValueError("manifest does not match frozen scenario")
            if not checkpoints_dir.is_dir() or not events_path.is_file():
                raise ValueError("run is missing recording artifacts")
            instance = cls.__new__(cls)
            instance.run_dir = run_dir
            instance.checkpoints_dir = checkpoints_dir
            instance._last_sequence = instance._read_last_sequence(events_path)
            instance._checkpoint_version = 0
            instance._last_checkpoint_time_ms = None
            instance._last_checkpoint_block_id = None
            instance._last_checkpoint = None
            instance._read_checkpoint_metadata()
            instance._events = events_path.open("ab")
            return instance
        except (OSError, TypeError, ValueError, json.JSONDecodeError, RecordingError) as exc:
            raise RecordingError(f"cannot reopen recording: {exc}") from exc

    def append(self, record: SessionRecord) -> None:
        if not isinstance(record, SessionRecord):
            raise RecordingError("record append failed: record must be a SessionRecord")
        if record.sequence <= self._last_sequence:
            raise RecordingError("record sequence must be strictly increasing")
        try:
            self._write_line(canonical_json(record).encode("utf-8"))
        except (OSError, TypeError, ValueError) as exc:
            raise RecordingError(f"record append failed: {exc}") from exc
        self._last_sequence = record.sequence

    def checkpoint(self, snapshot: Mapping[str, object]) -> ArtifactInfo:
        engine = self._validated_private_snapshot(snapshot)
        block_id = engine["block_id"]
        simulation_time_ms = engine["simulation_time_ms"]
        if block_id != self._last_checkpoint_block_id:
            self._last_checkpoint_block_id = block_id
            self._last_checkpoint_time_ms = None
        if self._last_checkpoint_time_ms is not None:
            if simulation_time_ms < self._last_checkpoint_time_ms:
                raise RecordingError("checkpoint simulation time must not decrease within a block")
            if simulation_time_ms - self._last_checkpoint_time_ms < _CHECKPOINT_INTERVAL_MS:
                assert self._last_checkpoint is not None
                return self._last_checkpoint
        ordinal = self._checkpoint_version + 1
        path = self.checkpoints_dir / f"checkpoint-{ordinal:08d}.json.gz"
        wrapper = {"checkpoint_version": ordinal, "record_sequence": self._last_sequence, "engine": engine}
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            with gzip.GzipFile(filename=str(temporary), mode="wb", mtime=0) as stream:
                stream.write(canonical_json(wrapper).encode("utf-8"))
            self._fsync_path(temporary)
            os.replace(temporary, path)
            artifact = self._artifact("checkpoint", path)
        except (OSError, TypeError, ValueError) as exc:
            raise RecordingError(f"checkpoint write failed: {exc}") from exc
        self._checkpoint_version = ordinal
        self._last_checkpoint_time_ms = simulation_time_ms
        self._last_checkpoint = artifact
        return artifact

    def close(self) -> None:
        self._events.close()

    def _write_line(self, payload: bytes) -> None:
        self._events.write(payload + b"\n")
        self._events.flush()
        os.fsync(self._events.fileno())

    @staticmethod
    def _write_atomic(path: Path, payload: bytes) -> None:
        temporary = path.with_name(path.name + ".tmp")
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)

    @staticmethod
    def _fsync_path(path: Path) -> None:
        with path.open("rb") as stream:
            os.fsync(stream.fileno())

    @staticmethod
    def _artifact(kind: str, path: Path) -> ArtifactInfo:
        data = path.read_bytes()
        return ArtifactInfo(kind=kind, path=path, sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))

    @staticmethod
    def _read_last_sequence(events_path: Path) -> int:
        previous = 0
        for line_number, raw_line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw_line:
                raise RecordingError(f"events.jsonl has an empty line at {line_number}")
            try:
                data = json.loads(raw_line)
                record = SessionRecord(**data)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RecordingError(f"events.jsonl has an invalid record at {line_number}: {exc}") from exc
            if canonical_json(record) != raw_line:
                raise RecordingError(f"events.jsonl record at {line_number} is not canonical")
            if record.sequence <= previous:
                raise RecordingError("events.jsonl sequences are not strictly increasing")
            previous = record.sequence
        return previous

    def _read_checkpoint_metadata(self) -> None:
        for path in sorted(self.checkpoints_dir.glob("checkpoint-*.json.gz")):
            wrapper = load_checkpoint(path)
            ordinal = wrapper["checkpoint_version"]
            if ordinal != self._checkpoint_version + 1 or path.name != f"checkpoint-{ordinal:08d}.json.gz":
                raise RecordingError("checkpoint filenames are not contiguous")
            engine = self._validated_private_snapshot(wrapper["engine"])
            if wrapper["record_sequence"] > self._last_sequence:
                raise RecordingError("checkpoint refers to records that do not exist")
            self._checkpoint_version = ordinal
            self._last_checkpoint_block_id = engine["block_id"]
            self._last_checkpoint_time_ms = engine["simulation_time_ms"]
            self._last_checkpoint = self._artifact("checkpoint", path)

    @staticmethod
    def _validated_private_snapshot(snapshot: Mapping[str, object]) -> dict[str, object]:
        if not isinstance(snapshot, Mapping):
            raise RecordingError("checkpoint requires a private engine snapshot")
        engine = dict(snapshot)
        if set(engine) != _PRIVATE_CHECKPOINT_FIELDS:
            raise RecordingError("checkpoint requires a private engine snapshot")
        digest = engine.pop("authoritative_state_sha256")
        if not isinstance(digest, str) or canonical_sha256(engine) != digest:
            raise RecordingError("invalid authoritative checkpoint hash")
        block_id = engine.get("block_id")
        simulation_time_ms = engine.get("simulation_time_ms")
        state_version = engine.get("state_version")
        if not isinstance(block_id, str) or not block_id:
            raise RecordingError("checkpoint has an invalid block_id")
        for value, name in ((simulation_time_ms, "simulation_time_ms"), (state_version, "state_version")):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RecordingError(f"checkpoint has an invalid {name}")
        return dict(snapshot)
