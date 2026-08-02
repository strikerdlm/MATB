"""Append-only session records and atomic private-engine checkpoints."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import BinaryIO

from matb_integration.suas.domain.serialization import canonical_data, canonical_json, canonical_sha256
from matb_integration.suas.scenarios.loader import load_scenario, load_scenario_text

from .artifacts import artifact_inventory, build_checksum_file, verify_checksum_file, write_json_artifact
from .checkpoints import load_checkpoint
from .records import ArtifactInfo, RecordKind, RecordingError, SessionRecord
from .replay import ReplayResult, ReplayStatus

_CHECKPOINT_INTERVAL_MS = 5_000
_PRIVATE_CHECKPOINT_FIELDS = frozenset({
    "engine_version", "scenario_id", "scenario_sha256", "block_id", "clock", "tick",
    "simulation_time_ms", "state_version", "world", "sensor_prng", "sensor_reports",
    "link_applied_event_ids", "conflict_applied_event_ids", "conflict_pending_releases",
    "sensor_due_times", "coverage_cells", "separation", "command_results",
    "authoritative_state_sha256",
})
_CHECKPOINT_FILENAME = re.compile(r"checkpoint-[0-9]{8}\.json\.gz")


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
        self._closed = False
        self._sealed = False
        if not isinstance(scenario_yaml, str):
            raise RecordingError("scenario_yaml must be text")
        try:
            canonical_data(manifest)
            scenario = load_scenario_text(scenario_yaml, source_name="session scenario")
            if (manifest.get("scenario_id") != scenario.definition.scenario_id
                    or manifest.get("scenario_sha256") != scenario.sha256):
                raise RecordingError("manifest does not match normalized scenario")
        except RecordingError:
            raise
        except (TypeError, ValueError) as exc:
            raise RecordingError(f"recording initialization failed: {exc}") from exc
        try:
            if self.run_dir.exists():
                if not self.run_dir.is_dir() or any(self.run_dir.iterdir()):
                    raise RecordingError("recording initialization failed: run directory is not empty")
            else:
                self.run_dir.mkdir(parents=True, exist_ok=False)
            self.checkpoints_dir.mkdir(exist_ok=False)
            self._write_atomic(self.run_dir / "manifest.json", canonical_json(manifest).encode("utf-8"))
            self._write_atomic(self.run_dir / "scenario.yaml", scenario.normalized_yaml.encode("utf-8"))
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
            invalid_checkpoint_paths = [
                path.name for path in checkpoints_dir.iterdir()
                if not path.is_file() or _CHECKPOINT_FILENAME.fullmatch(path.name) is None
            ]
            if invalid_checkpoint_paths:
                raise RecordingError("partial checkpoint artifact is present")
            instance = cls.__new__(cls)
            instance.run_dir = run_dir
            instance.checkpoints_dir = checkpoints_dir
            instance._last_sequence = instance._read_last_sequence(events_path)
            instance._checkpoint_version = 0
            instance._last_checkpoint_time_ms = None
            instance._last_checkpoint_block_id = None
            instance._last_checkpoint = None
            instance._read_checkpoint_metadata()
            # Reopening is append-safe, but starts in a closed state so a
            # caller can seal a frozen run directly.  ``append`` lazily opens
            # the stream again when an append is explicitly requested.
            instance._events = events_path.open("ab")
            instance._events.close()
            instance._closed = True
            instance._sealed = False
            return instance
        except (OSError, TypeError, ValueError, json.JSONDecodeError, RecordingError) as exc:
            raise RecordingError(f"cannot reopen recording: {exc}") from exc

    def append(self, record: SessionRecord) -> None:
        if self._sealed or (self.run_dir / "checksums.sha256").exists():
            raise RecordingError("sealed run is immutable")
        if not isinstance(record, SessionRecord):
            raise RecordingError("record append failed: record must be a SessionRecord")
        if record.sequence <= self._last_sequence:
            raise RecordingError("record sequence must be strictly increasing")
        try:
            self._ensure_open()
            self._write_line(canonical_json(record).encode("utf-8"))
        except (OSError, TypeError, ValueError) as exc:
            raise RecordingError(f"record append failed: {exc}") from exc
        self._last_sequence = record.sequence

    def checkpoint(self, snapshot: Mapping[str, object]) -> ArtifactInfo:
        if self._sealed or (self.run_dir / "checksums.sha256").exists():
            raise RecordingError("sealed run is immutable")
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
        if not self._closed:
            self._events.close()
            self._closed = True

    def seal(
        self,
        *,
        questionnaires: Mapping[str, object],
        metrics: Mapping[str, object],
        debrief: Mapping[str, object],
        replay: ReplayResult,
    ) -> tuple[ArtifactInfo, ...]:
        """Seal a closed recording after a successful deterministic replay."""

        if not self._closed:
            raise RecordingError("recording must be closed before sealing")
        if not isinstance(replay, ReplayResult) or replay.status is not ReplayStatus.MATCH:
            raise RecordingError("replay must match before sealing")
        checksum_path = self.run_dir / "checksums.sha256"
        if checksum_path.exists():
            if verify_checksum_file(checksum_path) != ():
                raise RecordingError("sealed run is immutable")
            expected = {
                "questionnaires.json": questionnaires,
                "metrics.json": metrics,
                "debrief.json": debrief,
                "replay-verification.json": replay,
            }
            for name, payload in expected.items():
                path = self.run_dir / name
                if not path.is_file() or path.read_bytes() != canonical_json(payload).encode("utf-8"):
                    raise RecordingError("sealed run is immutable")
            return artifact_inventory(self.run_dir)
        try:
            write_json_artifact(self.run_dir / "questionnaires.json", questionnaires)
            write_json_artifact(self.run_dir / "metrics.json", metrics)
            write_json_artifact(self.run_dir / "debrief.json", debrief)
            write_json_artifact(self.run_dir / "replay-verification.json", replay)
            build_checksum_file(self.run_dir)
            self._sealed = True
        except (OSError, TypeError, ValueError) as exc:
            raise RecordingError(f"artifact sealing failed: {exc}") from exc
        return artifact_inventory(self.run_dir)

    def seal_partial(self, *, reason: str) -> tuple[ArtifactInfo, ...]:
        """Close a run as checksum-verifiable but replay-unverified."""

        if not self._closed:
            raise RecordingError("recording must be closed before sealing")
        if not isinstance(reason, str) or not reason.strip():
            raise RecordingError("partial seal reason must be nonempty")
        partial_path = self.run_dir / "partial-run.json"
        payload = {
            "status": "partial_unverified",
            "reason": reason,
            "last_sequence": self._last_sequence,
            "last_checkpoint": self._last_checkpoint.path.name if self._last_checkpoint else None,
        }
        checksum_path = self.run_dir / "checksums.sha256"
        if checksum_path.exists():
            if verify_checksum_file(checksum_path) != () or not partial_path.is_file():
                raise RecordingError("sealed run is immutable")
            if partial_path.read_bytes() != canonical_json(payload).encode("utf-8"):
                raise RecordingError("sealed run is immutable")
            return artifact_inventory(self.run_dir, partial=True)
        if partial_path.exists() and partial_path.read_bytes() != canonical_json(payload).encode("utf-8"):
            raise RecordingError("sealed run is immutable")
        try:
            write_json_artifact(partial_path, payload)
            build_checksum_file(self.run_dir)
            self._sealed = True
        except (OSError, TypeError, ValueError) as exc:
            raise RecordingError(f"partial artifact sealing failed: {exc}") from exc
        return artifact_inventory(self.run_dir, partial=True)

    def _ensure_open(self) -> None:
        if self._events.closed:
            self._events = self.run_dir.joinpath("events.jsonl").open("ab")
            self._closed = False

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
        raw_events = events_path.read_bytes()
        if raw_events and not raw_events.endswith(b"\n"):
            raise RecordingError("events.jsonl final record is incomplete")
        for line_number, raw_line in enumerate(raw_events.split(b"\n")[:-1], start=1):
            if not raw_line:
                raise RecordingError(f"events.jsonl has an empty line at {line_number}")
            if b"\r" in raw_line:
                raise RecordingError(f"events.jsonl has non-canonical line endings at {line_number}")
            try:
                decoded_line = raw_line.decode("utf-8")
                data = json.loads(decoded_line)
                record = SessionRecord(**data)
            except (TypeError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
                raise RecordingError(f"events.jsonl has an invalid record at {line_number}: {exc}") from exc
            if canonical_json(record).encode("utf-8") != raw_line:
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
