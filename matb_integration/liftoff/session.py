"""Append-only, file-first Liftoff research session recorder."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import time
from uuid import UUID

from matb_integration.recording.artifacts import (
    ArtifactProfile,
    artifact_inventory,
    build_checksum_file,
    write_json_artifact,
)
from matb_integration.recording.records import ArtifactInfo

from .metrics import VisibleResults, compute_metrics
from .protocol import LIFTOFF_ALL_V1, decode_packet
from .quality import assess_quality
from .receiver import ReceiverHealth
from .records import MarkerKind, MarkerRecord, TelemetryRecord

LIFTOFF_PROFILE = ArtifactProfile(
    frozen_names=(
        "session-manifest.json",
        "liftoff-configuration.json",
        "telemetry.raw",
        "telemetry.jsonl",
        "markers.jsonl",
    ),
    sealed_names=(
        "results.json",
        "result-screen.png",
        "result-screen.jpg",
        "questionnaires.json",
        "physiology-link.json",
        "telemetry-quality.json",
        "metrics.json",
        "debrief.json",
    ),
)
_RAW_FRAME = struct.Struct("<4sQQqH")
_ARTIFACT_KINDS = {
    "session-manifest.json": "session_manifest",
    "liftoff-configuration.json": "liftoff_configuration",
    "telemetry.raw": "telemetry_raw",
    "telemetry.jsonl": "telemetry_canonical",
    "markers.jsonl": "markers",
    "results.json": "visible_results",
    "result-screen.png": "result_screen",
    "result-screen.jpg": "result_screen",
    "questionnaires.json": "questionnaires",
    "physiology-link.json": "physiology_link",
    "telemetry-quality.json": "telemetry_quality",
    "metrics.json": "metrics",
    "debrief.json": "debrief",
}
_TRANSITIONS = {
    ("PREPARED", MarkerKind.RECORDING_STARTED): "RECORDING",
    ("RECORDING", MarkerKind.BASELINE_STARTED): "BASELINE",
    ("BASELINE", MarkerKind.BASELINE_FINISHED): "BASELINE_FINISHED",
    ("BASELINE_FINISHED", MarkerKind.TASK_STARTED): "TASK",
    ("TASK", MarkerKind.TASK_FINISHED): "TASK_FINISHED",
    ("TASK_FINISHED", MarkerKind.RECOVERY_STARTED): "RECOVERY",
    ("RECOVERY", MarkerKind.RECOVERY_FINISHED): "RECOVERY_FINISHED",
    ("RECOVERY_FINISHED", MarkerKind.RECORDING_FINISHED): "FINISHED",
    ("FINISHED", MarkerKind.QUESTIONNAIRES_COMPLETED): "QUESTIONNAIRES",
    ("QUESTIONNAIRES", MarkerKind.SESSION_SEALED): "SEALING",
}
_MARKER_PHASE = {
    MarkerKind.RECORDING_STARTED: "recording",
    MarkerKind.BASELINE_STARTED: "baseline",
    MarkerKind.BASELINE_FINISHED: "baseline",
    MarkerKind.TASK_STARTED: "task",
    MarkerKind.TASK_FINISHED: "task",
    MarkerKind.RECOVERY_STARTED: "recovery",
    MarkerKind.RECOVERY_FINISHED: "recovery",
    MarkerKind.RECORDING_FINISHED: "recording",
    MarkerKind.QUESTIONNAIRES_COMPLETED: "questionnaires",
    MarkerKind.SESSION_SEALED: "session",
}


class SessionLifecycleError(RuntimeError):
    """Raised when an append or lifecycle transition would violate evidence."""


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("received_utc must be timezone-aware UTC")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _write_bytes_atomic(path: Path, payload: bytes) -> Path:
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    return path


class LiftoffSessionRecorder:
    """Own one immutable-after-seal Liftoff artifact directory."""

    @classmethod
    def prepare(
        cls,
        run_dir: Path,
        *,
        manifest: Mapping[str, object],
        batch_size: int = 64,
    ) -> "LiftoffSessionRecorder":
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            raise SessionLifecycleError("invalid_batch_size")
        manifest_data = dict(manifest)
        cls._validate_manifest(manifest_data)
        configuration = manifest_data["configuration"]
        assert isinstance(configuration, Mapping)
        root = Path(run_dir)
        if root.exists() and (not root.is_dir() or any(root.iterdir())):
            raise SessionLifecycleError("run_directory_not_empty")
        created_root = not root.exists()
        try:
            root.mkdir(parents=True, exist_ok=not created_root)
            write_json_artifact(root / "session-manifest.json", manifest_data)
            write_json_artifact(root / "liftoff-configuration.json", dict(configuration))
            raw_stream = (root / "telemetry.raw").open("xb")
            telemetry_stream = (root / "telemetry.jsonl").open("xb")
            marker_stream = (root / "markers.jsonl").open("xb")
        except (OSError, TypeError, ValueError) as exc:
            raise SessionLifecycleError(f"session_prepare_failed:{exc}") from exc

        instance = cls.__new__(cls)
        instance.run_dir = root
        instance.manifest = manifest_data
        instance.session_id = str(manifest_data["session_id"])
        instance._batch_size = batch_size
        instance._raw_stream = raw_stream
        instance._telemetry_stream = telemetry_stream
        instance._marker_stream = marker_stream
        instance._packet_sequence = 0
        instance._marker_sequence = 0
        instance._records: list[TelemetryRecord] = []
        instance._receiver_health = ReceiverHealth()
        instance._state = "PREPARED"
        instance._sealed = False
        instance._closed = False
        instance._results: VisibleResults | None = None
        instance._questionnaires: dict[str, object] | None = None
        instance._physiology_link: dict[str, object] | None = None
        instance._result_screen: bytes | None = None
        return instance

    @staticmethod
    def _validate_manifest(manifest: Mapping[str, object]) -> None:
        try:
            session_id = manifest["session_id"]
            configuration = manifest["configuration"]
            configuration_sha256 = manifest["configuration_sha256"]
            telemetry_profile = manifest["telemetry_profile"]
            expected_rate_hz = manifest["expected_rate_hz"]
        except KeyError as exc:
            raise SessionLifecycleError(f"manifest_missing:{exc.args[0]}") from exc
        try:
            if not isinstance(session_id, str) or str(UUID(session_id)) != session_id:
                raise ValueError
        except (TypeError, ValueError, AttributeError) as exc:
            raise SessionLifecycleError("invalid_session_id") from exc
        if not isinstance(configuration, Mapping):
            raise SessionLifecycleError("invalid_configuration")
        actual_hash = hashlib.sha256(_canonical_bytes(dict(configuration))).hexdigest()
        if configuration_sha256 != actual_hash:
            raise SessionLifecycleError("configuration_hash_mismatch")
        if telemetry_profile != LIFTOFF_ALL_V1:
            raise SessionLifecycleError("unsupported_telemetry_profile")
        if (
            isinstance(expected_rate_hz, bool)
            or not isinstance(expected_rate_hz, (int, float))
            or not math.isfinite(expected_rate_hz)
            or expected_rate_hz <= 0
        ):
            raise SessionLifecycleError("invalid_expected_rate_hz")

    def append_packet(
        self,
        payload: bytes,
        *,
        received_monotonic_ns: int,
        received_utc: datetime,
    ) -> TelemetryRecord:
        self._require_mutable()
        if isinstance(received_monotonic_ns, bool) or not isinstance(received_monotonic_ns, int) or received_monotonic_ns < 0:
            raise SessionLifecycleError("invalid_monotonic_time")
        if not isinstance(payload, bytes):
            raise SessionLifecycleError("invalid_packet_payload")
        try:
            packet = decode_packet(payload)
            received_utc_text = _format_utc(received_utc)
        except (TypeError, ValueError) as exc:
            raise SessionLifecycleError(f"packet_rejected:{exc}") from exc
        sequence = self._packet_sequence + 1
        record = TelemetryRecord(
            session_id=self.session_id,
            sequence=sequence,
            received_monotonic_ns=received_monotonic_ns,
            received_utc=received_utc_text,
            packet=packet,
        )
        utc_ns = int(received_utc.timestamp() * 1_000_000_000)
        frame = _RAW_FRAME.pack(
            b"LFT1",
            sequence,
            received_monotonic_ns,
            utc_ns,
            len(payload),
        ) + payload
        try:
            self._raw_stream.write(frame)
            self._telemetry_stream.write(_canonical_bytes(record.as_dict()) + b"\n")
        except OSError as exc:
            raise SessionLifecycleError(f"telemetry_append_failed:{exc}") from exc
        self._packet_sequence = sequence
        self._records.append(record)
        self._receiver_health.valid_packets = len(self._records)
        if sequence % self._batch_size == 0:
            self._flush_high_rate()
        return record

    def mark(
        self,
        kind: MarkerKind | str,
        *,
        source: str = "operator",
        reason_code: str | None = None,
        amendment_of_sequence: int | None = None,
        received_monotonic_ns: int | None = None,
        received_utc: datetime | None = None,
    ) -> MarkerRecord:
        self._require_mutable()
        try:
            marker_kind = MarkerKind(kind)
        except ValueError as exc:
            raise SessionLifecycleError("invalid_marker_kind") from exc
        if marker_kind is MarkerKind.TASK_STARTED and self._state == "BASELINE":
            raise SessionLifecycleError("task_before_baseline_finished")
        if marker_kind is MarkerKind.AMENDMENT:
            next_state = self._state
            phase = self._state.lower()
        else:
            next_state = _TRANSITIONS.get((self._state, marker_kind))
            if next_state is None:
                raise SessionLifecycleError(
                    f"invalid_marker_transition:{self._state.lower()}:{marker_kind.value}"
                )
            phase = _MARKER_PHASE[marker_kind]
        monotonic_ns = time.monotonic_ns() if received_monotonic_ns is None else received_monotonic_ns
        utc = datetime.now(timezone.utc) if received_utc is None else received_utc
        self._flush_high_rate()
        try:
            marker = MarkerRecord(
                session_id=self.session_id,
                sequence=self._marker_sequence + 1,
                received_monotonic_ns=monotonic_ns,
                received_utc=_format_utc(utc),
                kind=marker_kind,
                phase=phase,
                source=source,
                reason_code=reason_code,
                amendment_of_sequence=amendment_of_sequence,
            )
            self._marker_stream.write(_canonical_bytes(marker.as_dict()) + b"\n")
            self._marker_stream.flush()
            os.fsync(self._marker_stream.fileno())
        except (OSError, TypeError, ValueError) as exc:
            raise SessionLifecycleError(f"marker_append_failed:{exc}") from exc
        self._marker_sequence = marker.sequence
        self._state = next_state
        return marker

    def update_receiver_health(self, health: ReceiverHealth) -> None:
        self._require_mutable()
        if not isinstance(health, ReceiverHealth):
            raise SessionLifecycleError("invalid_receiver_health")
        self._receiver_health = health

    def attach_results(self, results: VisibleResults, *, screenshot: bytes | None = None) -> Path:
        self._require_mutable()
        if not isinstance(results, VisibleResults):
            raise SessionLifecycleError("invalid_visible_results")
        payload = {
            "schema_version": "liftoff-visible-results-v1",
            "valid_lap_times_s": list(results.valid_lap_times_s),
            "invalid_laps": results.invalid_laps,
            "observer_restart_count": results.observer_restart_count,
        }
        self._write_json_once("results.json", payload)
        if screenshot is not None:
            if not isinstance(screenshot, bytes) or not screenshot:
                raise SessionLifecycleError("invalid_result_screen")
            if screenshot.startswith(b"\x89PNG\r\n\x1a\n"):
                screenshot_name = "result-screen.png"
            elif screenshot.startswith(b"\xff\xd8\xff"):
                screenshot_name = "result-screen.jpg"
            else:
                raise SessionLifecycleError("invalid_result_screen")
            other_name = "result-screen.jpg" if screenshot_name.endswith(".png") else "result-screen.png"
            if (self.run_dir / other_name).exists():
                raise SessionLifecycleError("artifact_immutable:result-screen")
            self._write_bytes_once(screenshot_name, screenshot)
            self._result_screen = screenshot
        self._results = results
        return self.run_dir / "results.json"

    def attach_questionnaires(self, questionnaires: Mapping[str, object]) -> Path:
        self._require_mutable()
        payload = dict(questionnaires)
        self._write_json_once("questionnaires.json", payload)
        self._questionnaires = payload
        return self.run_dir / "questionnaires.json"

    def attach_physiology_link(self, physiology_link: Mapping[str, object]) -> Path:
        self._require_mutable()
        payload = dict(physiology_link)
        self._write_json_once("physiology-link.json", payload)
        self._physiology_link = payload
        return self.run_dir / "physiology-link.json"

    def seal(
        self,
        *,
        results: VisibleResults | None = None,
        questionnaires: Mapping[str, object] | None = None,
        screenshot: bytes | None = None,
    ) -> tuple[ArtifactInfo, ...]:
        self._require_mutable()
        if self._state != "FINISHED":
            raise SessionLifecycleError("session_not_finished")
        if results is not None:
            self.attach_results(results, screenshot=screenshot)
        if questionnaires is not None:
            self.attach_questionnaires(questionnaires)
        if self._results is None:
            raise SessionLifecycleError("visible_results_required")
        if self._questionnaires is None:
            raise SessionLifecycleError("questionnaires_required")
        if self._physiology_link is None:
            self.attach_physiology_link({"status": "missing", "sync_quality": "missing"})

        self.mark(MarkerKind.QUESTIONNAIRES_COMPLETED, source="system")
        quality = assess_quality(
            self._records,
            self._receiver_health,
            expected_rate_hz=float(self.manifest["expected_rate_hz"]),
        )
        metrics = compute_metrics(
            self._records,
            self._results,
            coordinate_units_validated=bool(self.manifest.get("coordinate_units_validated", False)),
        )
        write_json_artifact(self.run_dir / "telemetry-quality.json", asdict(quality))
        write_json_artifact(self.run_dir / "metrics.json", metrics)
        debrief = {
            "schema_version": "liftoff-debrief-v1",
            "session_id": self.session_id,
            "status": "finished",
            "validity": quality.validity,
            "packet_count": len(self._records),
            "marker_count": self._marker_sequence + 1,
            "primary": metrics["primary"],
            "physiology_status": self._physiology_link.get("status", "missing"),
        }
        write_json_artifact(self.run_dir / "debrief.json", debrief)
        self.mark(MarkerKind.SESSION_SEALED, source="system")
        self._close_streams()
        build_checksum_file(self.run_dir, profile=LIFTOFF_PROFILE)
        self._sealed = True
        return self._inventory()

    def seal_partial(self, reason_code: str) -> tuple[ArtifactInfo, ...]:
        self._require_mutable()
        if not isinstance(reason_code, str) or not reason_code:
            raise SessionLifecycleError("invalid_partial_reason")
        payload = {
            "schema_version": "liftoff-partial-run-v1",
            "session_id": self.session_id,
            "status": "partial_unverified",
            "reason_code": reason_code,
            "last_packet_sequence": self._packet_sequence,
            "last_marker_sequence": self._marker_sequence,
            "lifecycle_state": self._state,
        }
        write_json_artifact(self.run_dir / LIFTOFF_PROFILE.partial_name, payload)
        self._close_streams()
        build_checksum_file(self.run_dir, profile=LIFTOFF_PROFILE)
        self._sealed = True
        return self._inventory(partial=True)

    def _write_json_once(self, name: str, payload: object) -> None:
        path = self.run_dir / name
        expected = _canonical_bytes(payload)
        if path.exists():
            if not path.is_file() or path.read_bytes() != expected:
                raise SessionLifecycleError(f"artifact_immutable:{name}")
            return
        write_json_artifact(path, payload)

    def _write_bytes_once(self, name: str, payload: bytes) -> None:
        path = self.run_dir / name
        if path.exists():
            if not path.is_file() or path.read_bytes() != payload:
                raise SessionLifecycleError(f"artifact_immutable:{name}")
            return
        _write_bytes_atomic(path, payload)

    def _flush_high_rate(self) -> None:
        if self._closed:
            return
        for stream in (self._raw_stream, self._telemetry_stream):
            stream.flush()
            os.fsync(stream.fileno())

    def _close_streams(self) -> None:
        if self._closed:
            return
        self._flush_high_rate()
        self._marker_stream.flush()
        os.fsync(self._marker_stream.fileno())
        for stream in (self._raw_stream, self._telemetry_stream, self._marker_stream):
            stream.close()
        self._closed = True

    def _require_mutable(self) -> None:
        if self._sealed or self._closed or (self.run_dir / LIFTOFF_PROFILE.checksum_name).exists():
            raise SessionLifecycleError("session_sealed")

    def _inventory(self, *, partial: bool = False) -> tuple[ArtifactInfo, ...]:
        return artifact_inventory(
            self.run_dir,
            profile=LIFTOFF_PROFILE,
            partial=partial,
            kind_by_name=_ARTIFACT_KINDS,
        )


__all__ = [
    "LIFTOFF_PROFILE",
    "LiftoffSessionRecorder",
    "SessionLifecycleError",
]
