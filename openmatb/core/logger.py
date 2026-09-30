# Copyright 2023-2026, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

import json
import math
import os
import platform
import re
from hashlib import sha256
from collections import namedtuple
from csv import DictWriter
from datetime import datetime, timezone
from pathlib import Path
from random import Random
from threading import Lock
from time import perf_counter, perf_counter_ns
from typing import IO, Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from core.constants import PATHS, REPLAY_MODE
from core.recordsink import BoundedAsyncSink, SinkCloseTimeout, SinkWorkerError
from core.scenarioprovenance import BoundScenarioManifest
from core.utils import find_the_first_available_session_number

_logger: Logger | None = None
EVENT_SCHEMA_VERSION = "1.0"
TIMING_QC_SCHEMA_VERSION = "2.0"
RUNTIME_EVENT_ID_VERSION = "1.0"
SCIENTIFIC_COMPONENT_ID = "matb-runtime"
_MISSING_SOURCE_COMMITS = frozenset({"unavailable", "unknown"})
_FULL_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_RESERVED_EVENT_METADATA_KEYS = frozenset({
    "event_schema_version",
    "runtime_contract_status",
    "scientific_contract_status",
    "sequence",
    "session_id",
    "scientific_session_id",
    "event_id",
    "component_id",
    "component_version",
    "profile_id",
    "source_commit",
    "source_dirty",
    "source_commit_status",
    "scenario_sha256",
    "scenario_manifest_status",
    "scenario_manifest_sha256",
    "experiment_spec_sha256",
    "experiment_seed",
    "scenario_compiler_id",
    "scenario_compiler_version",
    "recorded_monotonic_ns",
    "logger_write_monotonic_ns",
    "clock_domain",
    "scenario_time_s",
    "scenario_time_ns",
    "record_type",
    "module",
    "address",
    "value",
    "dispatch_lateness_ms",
    "nonfinite_fields_normalized",
})
TIMING_SAMPLE_CAPACITY = 16_384
_TIMING_SERIES_SEEDS = {
    "update_interval": 0x4D41544201,
    "scenario_delta": 0x4D41544202,
    "event_lateness": 0x4D41544203,
    "logger_write_latency": 0x4D41544204,
    "lsl_write_latency": 0x4D41544205,
}


class _BoundedTimingAccumulator:
    """Exact counts/extrema plus a deterministic bounded quantile reservoir."""

    __slots__ = (
        "_count",
        "_invalid_count",
        "_lock",
        "_maximum",
        "_over_100_ms_count",
        "_rng",
        "_sample",
        "capacity",
    )

    def __init__(self, *, capacity: int, seed: int) -> None:
        if capacity < 1:
            raise ValueError("timing reservoir capacity must be positive")
        self.capacity = capacity
        self._sample: list[float] = []
        self._count = 0
        self._invalid_count = 0
        self._maximum: float | None = None
        self._over_100_ms_count = 0
        self._rng = Random(seed)
        self._lock = Lock()

    def add(self, value: float) -> None:
        observed = float(value)
        with self._lock:
            if not math.isfinite(observed):
                self._invalid_count += 1
                return
            self._count += 1
            self._maximum = observed if self._maximum is None else max(self._maximum, observed)
            if observed > 100.0:
                self._over_100_ms_count += 1
            if len(self._sample) < self.capacity:
                self._sample.append(observed)
                return
            replacement = self._rng.randrange(self._count)
            if replacement < self.capacity:
                self._sample[replacement] = observed

    def summary(self) -> dict[str, Any]:
        with self._lock:
            ordered = sorted(self._sample)
            count = self._count
            invalid_count = self._invalid_count
            maximum = self._maximum
        def percentile(probability: float) -> float | None:
            if not ordered:
                return None
            index = max(0, math.ceil(len(ordered) * probability) - 1)
            return round(ordered[index], 6)
        return {
            "n": count,
            "invalid_n": invalid_count,
            "retained_n": len(ordered),
            "retention_capacity": self.capacity,
            "quantile_method": "deterministic_algorithm_r_reservoir_nearest_rank",
            "quantiles_approximate": count > len(ordered),
            "median_ms": percentile(0.50),
            "p95_ms": percentile(0.95),
            "p99_ms": percentile(0.99),
            "max_ms": round(maximum, 6) if maximum is not None else None,
        }

    @property
    def over_100_ms_count(self) -> int:
        with self._lock:
            return self._over_100_ms_count


def _source_commit_status(value: Any, source_dirty: bool | None) -> str:
    normalized = str(value or "").strip()
    if not normalized or normalized.lower() in _MISSING_SOURCE_COMMITS:
        return "provisional_missing_provenance"
    if _FULL_GIT_OID.fullmatch(normalized) is None:
        return "provisional_invalid_source_commit"
    if source_dirty is True:
        return "provisional_dirty_source_tree"
    if source_dirty is not False:
        return "provisional_unverified_source_tree"
    return "complete"


def _runtime_contract_status(scientific_context: dict[str, Any]) -> str:
    required_provenance = (
        scientific_context.get("scenario_sha256"),
        scientific_context.get("profile_id"),
        scientific_context.get("component_version"),
    )
    if not all(value and str(value).strip() for value in required_provenance):
        return "provisional_missing_provenance"
    source_status = _source_commit_status(
        scientific_context.get("source_commit"),
        scientific_context.get("source_dirty"),
    )
    if source_status != "complete":
        return source_status
    manifest_status = scientific_context.get("scenario_manifest_status")
    if manifest_status != "verified":
        return str(manifest_status or "provisional_missing_scenario_manifest")
    return "complete"


def _normalize_nonfinite_json(value: Any, *, path: str = "") -> tuple[Any, list[str]]:
    """Replace legacy NaN/Infinity with JSON null and retain exact field paths."""
    if isinstance(value, float) and not math.isfinite(value):
        return None, [path or "$"]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        changed: list[str] = []
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            normalized_item, child_changed = _normalize_nonfinite_json(item, path=child_path)
            normalized[str(key)] = normalized_item
            changed.extend(child_changed)
        return normalized, changed
    if isinstance(value, (list, tuple)):
        normalized_items: list[Any] = []
        changed = []
        for index, item in enumerate(value):
            child_path = f"{path}[{index}]" if path else f"[{index}]"
            normalized_item, child_changed = _normalize_nonfinite_json(item, path=child_path)
            normalized_items.append(normalized_item)
            changed.extend(child_changed)
        return normalized_items, changed
    return value, []


def get_logger() -> Logger:
    global _logger
    if _logger is None:
        _logger = Logger()
    return _logger


def set_logger(lg: Logger | None) -> None:
    global _logger
    _logger = lg


class AuthoritativeLogFailure(RuntimeError):
    """The immutable JSONL sink failed; the logger enters fail-stop state."""


class Logger:
    def __init__(self) -> None:
        self.datetime: datetime = datetime.now()
        self.fields_list: list[str] = ["logtime", "scenario_time", "type", "module", "address", "value"]
        self.slot: type = namedtuple("Row", self.fields_list)
        self.maxfloats: int = 6  # Time logged at microsecond precision
        self.session_id: int | None = None
        self.lsl: Any = None

        self.session_id = find_the_first_available_session_number()
        self._scientific_session_uuid: UUID = uuid4()
        self._scientific_context: dict[str, Any] = {}
        self.mode: str = "w"

        self.scenario_time: float = 0  # Updated by the scheduler class

        self.file: IO[str] | None = None
        self.events_file: IO[str] | None = None
        self.lsl_observations_file: IO[str] | None = None
        self.writer: DictWriter | None = None
        self.queue: list[Any] = list()
        self.metadata_queue: list[dict[str, Any]] = list()
        self.event_sequence: int = 0
        self._last_update_monotonic_ns: int | None = None
        self._last_scenario_time: float | None = None
        for series_name in _TIMING_SERIES_SEEDS:
            self._timing_accumulator(series_name)
        self._lsl_sink: BoundedAsyncSink[dict[str, Any]] | None = None
        self._lsl_sink_target: Any | None = None
        self._last_lsl_sink_evidence: dict[str, Any] | None = None
        self._lsl_sink_close_error: str | None = None
        self._lsl_observation_lock = Lock()
        self._started_monotonic_ns: int = perf_counter_ns()

        if not REPLAY_MODE:
            self.session_id, self.path = self._claim_session_path(
                PATHS["SESSIONS"],
                self.datetime,
                self.session_id,
            )
            self.events_path: Path = self.path.with_suffix(".events.jsonl")
            self.lsl_observations_path: Path = self.path.with_suffix(".lsl_observations.jsonl")
            self.timing_qc_path: Path = self.path.with_suffix(".timing_qc.json")
            self.scenario_provenance_path: Path = self.path.with_suffix(
                ".scenario_provenance.json"
            )
            self.scenario_manifest_archive_path: Path = self.path.with_suffix(
                ".scenario.manifest.json"
            )
            self.open()

    @staticmethod
    def _claim_session_path(
        sessions_root: Path,
        started_at: datetime,
        initial_candidate: int,
    ) -> tuple[int, Path]:
        """Atomically reserve a numeric session identity and its CSV path.

        Scanning existing filenames alone is racy: two processes can choose the
        same missing number before either opens its file. Persistent O_EXCL claim
        files serialize that decision across processes and preserve consumed IDs
        even if a process crashes during bootstrap.
        """

        root = Path(sessions_root)
        date_directory = root / started_at.strftime("%Y-%m-%d")
        claims_directory = root / ".session_claims"
        date_directory.mkdir(parents=True, exist_ok=True)
        claims_directory.mkdir(parents=True, exist_ok=True)
        candidate = max(1, int(initial_candidate))
        while True:
            claim_path = claims_directory / f"{candidate}.claim"
            try:
                claim_fd = os.open(
                    claim_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError:
                candidate += 1
                continue
            try:
                os.write(
                    claim_fd,
                    (
                        started_at.isoformat(timespec="microseconds")
                        + f" session_id={candidate}\n"
                    ).encode("utf-8"),
                )
            finally:
                os.close(claim_fd)

            path = date_directory / (
                f"{candidate}_{started_at.strftime('%y%m%d_%H%M%S')}.csv"
            )
            try:
                csv_fd = os.open(
                    path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError:
                # The claim remains as an audit trail for the consumed identity.
                candidate += 1
                continue
            else:
                os.close(csv_fd)
                return candidate, path

    @property
    def scientific_session_id(self) -> str:
        """Stable UUID used to disambiguate every session-scoped side channel."""
        return str(self._scientific_session_uuid)

    # TODO: see if we can/should merge record_* methods into one
    def record_event(
        self,
        event: Any,
        *,
        dispatch_start_monotonic_ns: int | None = None,
        dispatch_end_monotonic_ns: int | None = None,
    ) -> None:
        if len(event.command) == 1:
            adress: str = "self"
            value: str = event.command[0]
        elif len(event.command) == 2:
            adress = event.command[0]
            value = event.command[1]
        slot: list[Any] = [perf_counter(), self.scenario_time, "event", event.plugin, adress, value]
        metadata: dict[str, Any] = {
            "scheduled_scenario_time_s": event.time_sec,
            "scenario_line": event.line,
        }
        if dispatch_start_monotonic_ns is not None:
            metadata["dispatch_start_monotonic_ns"] = dispatch_start_monotonic_ns
        if dispatch_end_monotonic_ns is not None:
            metadata["dispatch_end_monotonic_ns"] = dispatch_end_monotonic_ns
        self.write_single_slot(slot, metadata=metadata)
        if event.plugin == "labstreaminglayer" and adress == "marker" and str(value):
            pending = getattr(self, "_pending_explicit_lsl_markers", [])
            pending.append({
                "message": str(value),
                "source_sequence": getattr(self, "event_sequence", None),
                "source_event_id": getattr(self, "_last_runtime_event_id", None),
            })
            self._pending_explicit_lsl_markers = pending

    def record_event_failure(
        self,
        event: Any,
        *,
        dispatch_start_monotonic_ns: int,
        dispatch_end_monotonic_ns: int,
        error_type: str,
        error_message: str,
        failure_phase: str,
    ) -> None:
        """Persist one terminal, non-retryable scenario-dispatch failure."""
        command = [str(item) for item in event.command]
        address = command[0] if command else "unknown"
        normalized_error_type = str(error_type)[:256] or "UnknownError"
        normalized_error_message = str(error_message)[:4096]
        slot: list[Any] = [
            perf_counter(),
            self.scenario_time,
            "event_dispatch_failure",
            event.plugin,
            address,
            normalized_error_type,
        ]
        self.write_single_slot(
            slot,
            metadata={
                "scheduled_scenario_time_s": event.time_sec,
                "scenario_line": event.line,
                "dispatch_start_monotonic_ns": dispatch_start_monotonic_ns,
                "dispatch_end_monotonic_ns": dispatch_end_monotonic_ns,
                "dispatch_status": "failed_terminal",
                "session_status": "invalid_dispatch_failure",
                "failed_command": command,
                "error_type": normalized_error_type,
                "error_message": normalized_error_message,
                "failure_phase": str(failure_phase)[:256],
            },
        )

    def configure_scientific_context(
        self,
        *,
        scenario_sha256: str,
        profile_id: str,
        source_commit: str,
        component_version: str,
        scenario_manifest_evidence: dict[str, Any],
        source_dirty: bool | None = None,
        preparation_hold: bool = False,
    ) -> None:
        """Attach immutable scenario and software provenance to future records."""
        if re.fullmatch(r"[0-9a-f]{64}", scenario_sha256) is None:
            raise ValueError("scenario_sha256 must be a lowercase SHA-256 digest")
        values = {
            "profile_id": profile_id,
            "component_version": component_version,
        }
        for field_name, value in values.items():
            if not value or value != value.strip():
                raise ValueError(f"{field_name} must be non-empty and trimmed")
        normalized_source_commit = source_commit.strip()
        if not normalized_source_commit:
            raise ValueError("source_commit must not be empty")
        if normalized_source_commit.lower() in _MISSING_SOURCE_COMMITS:
            normalized_source_commit = normalized_source_commit.lower()
        manifest_status = scenario_manifest_evidence.get("status")
        manifest_digest = scenario_manifest_evidence.get("scenario_manifest_sha256")
        manifest_identity = scenario_manifest_evidence.get("manifest_identity")
        if not isinstance(manifest_status, str) or not manifest_status:
            raise ValueError("scenario manifest evidence status is required")
        if manifest_digest is not None and re.fullmatch(r"[0-9a-f]{64}", manifest_digest) is None:
            raise ValueError("scenario manifest evidence digest is malformed")
        if manifest_identity is not None and not isinstance(manifest_identity, dict):
            raise ValueError("scenario manifest identity must be an object or null")
        identity = manifest_identity or {}
        self._scientific_context = {
            "scenario_sha256": scenario_sha256,
            **values,
            "source_commit": normalized_source_commit,
            "source_dirty": source_dirty,
            "scenario_manifest_status": manifest_status,
            "scenario_manifest_sha256": manifest_digest,
            "experiment_spec_sha256": identity.get("experiment_spec_sha256"),
            "experiment_seed": identity.get("experiment_seed"),
            "scenario_compiler_id": identity.get("scenario_compiler_id"),
            "scenario_compiler_version": identity.get("scenario_compiler_version"),
        }
        if not REPLAY_MODE and getattr(self, "path", None) is not None:
            from matb_integration.evidence.writer import EvidenceWriter
            if getattr(self, "_evidence_writer", None) is not None:
                raise ValueError("scientific context is already bound")
            self._evidence_writer = EvidenceWriter(
                self.path, self.scientific_session_id, self._scientific_context,
                json.loads(os.environ.get("MATB_EVIDENCE_IDENTITY", "{}")),
            )
            self._evidence_preparation_held = preparation_hold
            self._evidence_writer.lifecycle("prepared" if preparation_hold else "started", self.scenario_time, perf_counter_ns())
        # Bind the legacy CSV session to the exact runtime scenario. This row is
        # required before a separately uploaded manifest can confer confirmatory
        # eligibility; filenames alone are not cryptographic provenance.
        self.log_manual_entry(scenario_sha256, key="scenario_sha256")

    def admit_preflight(self) -> None:
        """Record acquisition admission without altering the prepared source identity."""
        if getattr(self, "_evidence_preparation_held", False):
            self._evidence_writer.lifecycle("started", self.scenario_time, perf_counter_ns())
            self._evidence_preparation_held = False

    def configure_evidence_tasks(self, tasks: list[str]) -> None:
        writer = getattr(self, "_evidence_writer", None)
        if writer is not None:
            writer.set_tasks(tasks)

    def record_task_lifecycle(self, module: str, phase: str) -> None:
        writer = getattr(self, "_evidence_writer", None)
        if writer is None:
            return
        try:
            writer.record({"type": "task_lifecycle", "module": module, "address": "self",
                           "value": phase, "scenario_time": self.scenario_time},
                          {"recorded_monotonic_ns": perf_counter_ns()})
        except Exception as exc:
            self._authoritative_sink_failure = {"status": "failed_fail_stop", "error_type": type(exc).__name__}
            raise AuthoritativeLogFailure("scientific task lifecycle write failed") from exc

    def finalize_evidence(self, completion: str = "interrupted") -> None:
        writer = getattr(self, "_evidence_writer", None)
        if writer is None or writer.sealed:
            return
        if not writer.failed:
            writer.lifecycle("completed" if completion == "completed" else "interrupted",
                             self.scenario_time, perf_counter_ns(), completion)
        if self.file is not None and not self.file.closed:
            self.file.flush()
        if getattr(self, "events_file", None) is not None and not self.events_file.closed:
            self.events_file.flush()
        artifacts = {"legacy_csv": self.path, "runtime_envelope": self.events_path}
        archive = getattr(self, "scenario_manifest_archive_path", None)
        if archive is not None:
            artifacts["scenario_manifest"] = archive
        writer.seal(completion="completed" if completion == "completed" else "interrupted", artifacts=artifacts)

    def archive_scenario_manifest(self, bound: BoundScenarioManifest) -> None:
        """Persist the exact manifest snapshot and its verification evidence."""
        evidence = dict(bound.evidence)
        provenance_path = getattr(self, "scenario_provenance_path", None)
        if provenance_path is not None:
            Path(provenance_path).write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
        if bound.content is not None:
            observed = sha256(bound.content).hexdigest()
            if observed != evidence.get("scenario_manifest_sha256"):
                raise ValueError("scenario manifest snapshot digest changed before archival")
            archive_path = getattr(self, "scenario_manifest_archive_path", None)
            if archive_path is not None:
                Path(archive_path).write_bytes(bound.content)
                if self._file_integrity(Path(archive_path))["sha256"] != observed:
                    raise OSError("archived scenario manifest failed post-write verification")
            writer = getattr(self, "_evidence_writer", None)
            if writer is not None:
                manifest = json.loads(bound.content)
                if writer.manifest.condition == "UNSPECIFIED":
                    writer.manifest.condition = str((manifest.get("parameters") or {}).get(
                        "suite_profile_name", manifest.get("workload_level", "UNSPECIFIED")))
        self.log_manual_entry(
            json.dumps(evidence, sort_keys=True, separators=(",", ":"), allow_nan=False),
            key="scenario_manifest_evidence",
        )

    @staticmethod
    def expected_event_id(
        *,
        session_id: UUID | str,
        sequence: int,
        event_type: str,
    ) -> UUID:
        """Return a deterministic identity for the runtime-event v1 envelope."""
        identity = json.dumps(
            [
                "openmatb.runtime-event",
                RUNTIME_EVENT_ID_VERSION,
                str(UUID(str(session_id))),
                SCIENTIFIC_COMPONENT_ID,
                sequence,
                event_type,
            ],
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        return uuid5(NAMESPACE_URL, identity)

    def record_input(self, module: str, key: str, state: str) -> None:
        slot: list[Any] = [perf_counter(), self.scenario_time, "input", module, key, state]
        self.write_single_slot(slot)

    def record_aoi(self, container: Any, name: str) -> None:
        plugin: str = name.split("_")[0]
        widget: str = "_".join(name.split("_")[1:])
        slot: list[Any] = [perf_counter(), self.scenario_time, "aoi", plugin, widget, container.get_x1y1x2y2()]
        self.write_single_slot(slot)

    def record_state(self, graph_name: str, attribute: str, value: Any) -> None:
        module: str = graph_name.split("_")[0]
        graph_name = "_".join(graph_name.split("_")[1:])
        address: str = f"{graph_name}, {attribute}"
        slot: list[Any] = [perf_counter(), self.scenario_time, "state", module, address, value]
        self.write_single_slot(slot)

    def record_parameter(self, plugin: str, address: str, value: Any) -> None:
        slot: list[Any] = [perf_counter(), self.scenario_time, "parameter", plugin, address, value]
        self.write_single_slot(slot)

    def log_performance(self, module: str, metric: str, value: Any, *,
                        automation_active: bool | None = None, sample_interval_ms: int | float | None = None) -> None:
        slot: list[Any] = [perf_counter(), self.scenario_time, "performance", module, metric, value]
        self.write_single_slot(slot, metadata={"automation_active": automation_active, "sample_interval_ms": sample_interval_ms})

    def record_a_pseudorandom_value(self, module: str, seed: int, output: Any) -> None:
        slot: list[Any] = [perf_counter(), self.scenario_time, "seed_value", module, "", seed]
        self.write_single_slot(slot)
        slot = [perf_counter(), self.scenario_time, "seed_output", module, "", output]
        self.write_single_slot(slot)

    def log_manual_entry(self, entry: str, key: str = "manual") -> None:
        terminal_marker_already_persisted = bool(
            entry == "end" and getattr(self, "_terminal_marker_persisted", False)
        )
        if not terminal_marker_already_persisted:
            slot: list[Any] = [perf_counter(), self.scenario_time, key, "", "", entry]
            self.write_single_slot(slot)
            if entry == "end":
                self._terminal_marker_persisted = True
        # The scheduler emits this terminal marker before the process exits.  Write
        # (but do not close) the QC sidecar here so an ordinary completed session
        # always has timing evidence even when GUI teardown bypasses __exit__.
        if entry == "end":
            sinks_closed = self.close_async_sinks()
            self._terminal_shutdown_complete = sinks_closed
            self._terminal_shutdown_error = (
                None
                if sinks_closed
                else "async_sinks_did_not_drain_before_terminal_deadline"
            )
            self.write_timing_qc()
            if self.file is not None and not self.file.closed:
                self.file.flush()
            events_file = getattr(self, "events_file", None)
            if events_file is not None and not events_file.closed:
                events_file.flush()
            lsl_observations_file = getattr(self, "lsl_observations_file", None)
            if lsl_observations_file is not None and not lsl_observations_file.closed:
                lsl_observations_file.flush()
            if not sinks_closed:
                raise SinkCloseTimeout(
                    "terminal marker persisted, but async sinks did not drain; refusing clean exit"
                )

    def __enter__(self) -> Logger:
        self.open()
        return self

    def __exit__(self, type: Any, value: Any, traceback: Any) -> None:
        self.close()

    def open(self) -> None:
        create_header: bool = not (self.path.exists() and self.mode == "a")
        self.file = open(str(self.path), self.mode, newline="", encoding="utf-8")
        self.writer = DictWriter(self.file, fieldnames=self.fields_list)
        if create_header:
            self.writer.writeheader()
        events_path = getattr(self, "events_path", None)
        if events_path is not None and (self.events_file is None or self.events_file.closed):
            events_mode = "a" if self.mode == "a" else "w"
            self.events_file = open(str(events_path), events_mode, encoding="utf-8")
        lsl_observations_path = getattr(self, "lsl_observations_path", None)
        if lsl_observations_path is not None and (
            self.lsl_observations_file is None or self.lsl_observations_file.closed
        ):
            observations_mode = "a" if self.mode == "a" else "w"
            self.lsl_observations_file = open(
                str(lsl_observations_path), observations_mode, encoding="utf-8"
            )

    def close(self) -> None:
        sinks_closed = self.close_async_sinks()
        self.finalize_evidence()
        self.write_timing_qc()
        if self.file is not None and not self.file.closed:
            self.file.flush()
            self.file.close()
        events_file = getattr(self, "events_file", None)
        if events_file is not None and not events_file.closed:
            events_file.flush()
            events_file.close()
        if (
            sinks_closed
            and getattr(self, "lsl_observations_file", None) is not None
            and not self.lsl_observations_file.closed
        ):
            self.lsl_observations_file.flush()
            self.lsl_observations_file.close()
        elif not sinks_closed:
            observations_file = getattr(self, "lsl_observations_file", None)
            if observations_file is not None and not observations_file.closed:
                observations_file.flush()
            raise SinkCloseTimeout(
                "LSL sink is still draining; its observation file remains open for a safe retry"
            )

    def add_row_to_queue(self, row: Any) -> None:
        self.queue.append(row)

    def empty_queue(self) -> None:
        self.queue = list()
        self.metadata_queue = list()

    def round_row(self, row: Any) -> Any:
        new_list: list[Any] = list()
        for col in row:
            new_value: Any = round(col, self.maxfloats) if isinstance(col, (float, int)) else col
            new_list.append(new_value)
        return self.slot(*new_list)

    def write_row_queue(self, change_dict: dict[str, Any] | None = None) -> None:
        if not REPLAY_MODE:
            prior_failure = getattr(self, "_authoritative_sink_failure", None)
            if prior_failure is not None:
                raise AuthoritativeLogFailure(
                    "authoritative JSONL logger is in fail-stop state: "
                    + prior_failure["error_type"]
                )
            if len(self.queue) == 0:
                print(_("Warning, queue is empty"))
            else:
                while self.queue:
                    this_row = self.queue[0]
                    row_dict: dict[str, Any] = self.round_row(this_row)._asdict()
                    if change_dict is not None:
                        for k, v in change_dict.items():
                            row_dict[k] = v
                    metadata_queue = getattr(self, "metadata_queue", [])
                    metadata = metadata_queue[0] if metadata_queue else {}
                    try:
                        # JSONL is the scientific source of truth. Commit it
                        # before attempting the compatibility CSV sink.
                        event_payload = self.write_jsonl_row(row_dict, metadata)
                        evidence_writer = getattr(self, "_evidence_writer", None)
                        if evidence_writer is not None:
                            # Use the unrounded native row, never reconstituted CSV time.
                            evidence_metadata = {**metadata, "recorded_monotonic_ns": event_payload["recorded_monotonic_ns"]}
                            evidence_metadata["compatibility_row"] = {
                                key: "" if row_dict[key] is None else str(row_dict[key])
                                for key in ("scenario_time", "type", "module", "address", "value")}
                            native_row = this_row._asdict()
                            # Missing task measurements use the same JSON null as
                            # the linked runtime envelope, which records their paths.
                            # Preserve native timing and finite measurement precision.
                            native_row["value"] = _normalize_nonfinite_json(native_row["value"])[0]
                            evidence_writer.record(native_row, evidence_metadata,
                                                   runtime_event_id=event_payload["event_id"])
                    except Exception as exc:  # noqa: BLE001 - enter explicit fail-stop state
                        self.queue.pop(0)
                        if metadata_queue:
                            metadata_queue.pop(0)
                        self._authoritative_sink_failure = {
                            "status": "failed_fail_stop",
                            "error_type": type(exc).__name__,
                            "error_message": str(exc),
                            "sequence_attempted": getattr(self, "event_sequence", None),
                        }
                        raise AuthoritativeLogFailure(
                            "authoritative JSONL write failed; logger entered fail-stop state"
                        ) from exc

                    # Once the authoritative event is durable, never replay it.
                    self.queue.pop(0)
                    if metadata_queue:
                        metadata_queue.pop(0)
                    if not getattr(self, "_legacy_csv_sink_failed", False):
                        try:
                            self.writer.writerow(row_dict)
                        except Exception as exc:  # noqa: BLE001 - JSONL remains authoritative
                            self._legacy_csv_sink_failed = True
                            self._legacy_csv_failure_count = (
                                getattr(self, "_legacy_csv_failure_count", 0) + 1
                            )
                            self._legacy_csv_sink_failure = {
                                "status": "failed_disabled",
                                "error_type": type(exc).__name__,
                                "error_message": str(exc),
                                "source_sequence": event_payload.get("sequence"),
                                "source_event_id": event_payload.get("event_id"),
                            }
                    if self.lsl is not None:
                        self._submit_lsl_record(row_dict, event_payload)

    def write_single_slot(self, values: list[Any], metadata: dict[str, Any] | None = None) -> None:
        if getattr(self, "_authoritative_sink_failure", None) is not None:
            raise AuthoritativeLogFailure(
                "authoritative JSONL logger is in fail-stop state"
            )
        supplied_metadata = dict(metadata or {})
        collisions = sorted(set(supplied_metadata) & _RESERVED_EVENT_METADATA_KEYS)
        if collisions:
            raise ValueError(
                "reserved event metadata cannot be overridden: " + ", ".join(collisions)
            )
        row: Any = self.slot(*values)
        self.add_row_to_queue(row)
        if not hasattr(self, "metadata_queue"):
            self.metadata_queue = []
        row_metadata = supplied_metadata
        # Capture the authoritative host-monotonic timestamp directly.  The legacy
        # CSV logtime is rounded and must not be converted back into nanoseconds.
        row_metadata.setdefault("recorded_monotonic_ns", perf_counter_ns())
        self.metadata_queue.append(row_metadata)
        self.write_row_queue()

    def write_jsonl_row(
        self,
        row_dict: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Write an additive, versioned event record without changing legacy CSV."""
        events_file = getattr(self, "events_file", None)
        metadata = dict(metadata or {})
        recorded_ns_raw = metadata.pop("recorded_monotonic_ns", None)
        collisions = sorted(set(metadata) & _RESERVED_EVENT_METADATA_KEYS)
        if collisions:
            raise ValueError(
                "reserved event metadata cannot be overridden: " + ", ".join(collisions)
            )
        if recorded_ns_raw is None:
            # Compatibility for callers that bypass write_single_slot.  New runtime
            # paths always supply the direct observation above.
            recorded_ns_raw = perf_counter_ns()
        recorded_ns = int(recorded_ns_raw)
        write_ns = perf_counter_ns()
        latency_ms = max(0.0, (write_ns - recorded_ns) / 1_000_000)
        self._timing_accumulator("logger_write_latency").add(latency_ms)
        self.event_sequence = getattr(self, "event_sequence", 0) + 1
        scientific_session_id = getattr(self, "_scientific_session_uuid", None)
        if scientific_session_id is None:
            scientific_session_id = uuid5(
                NAMESPACE_URL,
                f"openmatb.runtime.session|legacy-{self.session_id}",
            )
            self._scientific_session_uuid = scientific_session_id
        scientific_context = getattr(self, "_scientific_context", {})
        scenario_sha256 = scientific_context.get("scenario_sha256")
        source_commit_status = _source_commit_status(
            scientific_context.get("source_commit"),
            scientific_context.get("source_dirty"),
        )
        runtime_contract_status = _runtime_contract_status(scientific_context)
        event_id = self.expected_event_id(
            session_id=scientific_session_id,
            sequence=self.event_sequence,
            event_type=str(row_dict["type"]),
        )
        payload: dict[str, Any] = {
            "event_schema_version": EVENT_SCHEMA_VERSION,
            "runtime_contract_status": runtime_contract_status,
            # This additive runtime envelope is intentionally not the separately
            # published ScientificEventV3 + TimingObservationV1 contract pair.
            "scientific_contract_status": "not_scientific_event_v3",
            "sequence": self.event_sequence,
            "session_id": self.session_id,
            "scientific_session_id": str(scientific_session_id),
            "event_id": str(event_id),
            "component_id": SCIENTIFIC_COMPONENT_ID,
            "component_version": scientific_context.get("component_version"),
            "profile_id": scientific_context.get("profile_id"),
            "source_commit": scientific_context.get("source_commit"),
            "source_dirty": scientific_context.get("source_dirty"),
            "source_commit_status": source_commit_status,
            "scenario_sha256": scenario_sha256,
            "scenario_manifest_status": scientific_context.get("scenario_manifest_status"),
            "scenario_manifest_sha256": scientific_context.get("scenario_manifest_sha256"),
            "experiment_spec_sha256": scientific_context.get("experiment_spec_sha256"),
            "experiment_seed": scientific_context.get("experiment_seed"),
            "scenario_compiler_id": scientific_context.get("scenario_compiler_id"),
            "scenario_compiler_version": scientific_context.get("scenario_compiler_version"),
            "recorded_monotonic_ns": recorded_ns,
            "logger_write_monotonic_ns": write_ns,
            "clock_domain": "python.perf_counter",
            "scenario_time_s": row_dict["scenario_time"],
            "scenario_time_ns": int(round(float(row_dict["scenario_time"]) * 1_000_000_000)),
            "record_type": row_dict["type"],
            "module": row_dict["module"],
            "address": row_dict["address"],
            "value": row_dict["value"],
        }
        payload.update(metadata)
        scheduled = payload.get("scheduled_scenario_time_s")
        if isinstance(scheduled, (int, float)):
            lateness = max(0.0, (float(row_dict["scenario_time"]) - float(scheduled)) * 1000)
            payload["dispatch_lateness_ms"] = round(lateness, 6)
            self._timing_accumulator("event_lateness").add(lateness)
        payload, nonfinite_paths = _normalize_nonfinite_json(payload)
        if nonfinite_paths:
            payload["nonfinite_fields_normalized"] = nonfinite_paths
        self._last_runtime_event_id = payload["event_id"]
        if events_file is not None:
            events_file.write(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                    allow_nan=False,
                )
                + "\n"
            )
            events_file.flush()
        return payload

    def _submit_lsl_record(self, row_dict: dict[str, Any], event_payload: dict[str, Any]) -> None:
        target = self.lsl
        if target is None:
            return
        self.submit_lsl_marker(
            target,
            ";".join(str(value) for value in row_dict.values()),
            source_sequence=event_payload["sequence"],
            source_event_id=event_payload.get("event_id"),
            marker_kind="runtime_record",
        )

    def submit_lsl_marker(
        self,
        target: Any,
        message: str,
        *,
        source_sequence: int | None = None,
        source_event_id: str | None = None,
        marker_kind: str = "explicit_marker",
    ) -> bool:
        """Submit every LSL marker through the bounded, auditable worker."""
        if target is None:
            return False
        if (
            marker_kind == "explicit_marker"
            and source_sequence is None
            and source_event_id is None
        ):
            pending = getattr(self, "_pending_explicit_lsl_markers", [])
            for index, candidate in enumerate(pending):
                if candidate.get("message") == str(message):
                    matched = pending.pop(index)
                    source_sequence = matched.get("source_sequence")
                    source_event_id = matched.get("source_event_id")
                    break
        record = {
            "message": str(message),
            # A missing link remains missing. Guessing "the latest event" can
            # silently bind an explicit marker to a different same-tick command.
            "source_sequence": source_sequence,
            "source_event_id": source_event_id,
            "marker_kind": marker_kind,
        }
        try:
            sink = self._ensure_lsl_sink(target)
            accepted = sink.submit(record)
            if not accepted:
                self._write_lsl_observation(
                    {
                        "schema_version": "1.0",
                        "source_sequence": record["source_sequence"],
                        "source_event_id": record.get("source_event_id"),
                        "marker_kind": record["marker_kind"],
                        "delivery_status": "dropped",
                        "drop_reason": "queue_full_drop_newest",
                        "observed_monotonic_ns": perf_counter_ns(),
                    }
                )
            return accepted
        except RuntimeError as exc:
            # The authoritative CSV/JSONL record is already durable. Preserve the
            # optional stream failure as QC evidence without relabeling local data.
            self._lsl_sink_close_error = str(exc)
            sink = getattr(self, "_lsl_sink", None)
            if sink is not None:
                try:
                    self._last_lsl_sink_evidence = sink.evidence().to_dict()
                except Exception:  # noqa: BLE001 - evidence lookup must not mask the source record
                    pass
            if isinstance(exc, SinkWorkerError):
                failure_reason = "sink_worker_unavailable"
            elif isinstance(exc, SinkCloseTimeout):
                failure_reason = "sink_close_timeout"
            else:
                failure_reason = "sink_state_unavailable"
            self._write_lsl_observation({
                "schema_version": "1.0",
                "source_sequence": record["source_sequence"],
                "source_event_id": record.get("source_event_id"),
                "marker_kind": record["marker_kind"],
                "delivery_status": "failed",
                "failure_reason": failure_reason,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "observed_monotonic_ns": perf_counter_ns(),
            })
            return False

    def _ensure_lsl_sink(self, target: Any) -> BoundedAsyncSink[dict[str, Any]]:
        sink = getattr(self, "_lsl_sink", None)
        if sink is not None and getattr(self, "_lsl_sink_target", None) is target:
            return sink
        if sink is not None:
            if not self.close_async_sinks():
                raise SinkCloseTimeout(
                    "cannot replace the LSL target while the previous sink is still draining"
                )

        self._lsl_sink_target = target

        def publish(record: dict[str, Any]) -> None:
            started_ns = perf_counter_ns()
            observation: dict[str, Any] = {
                "schema_version": "1.0",
                "source_sequence": record["source_sequence"],
                "source_event_id": record.get("source_event_id"),
                "marker_kind": record.get("marker_kind"),
                "push_call_started_monotonic_ns": started_ns,
            }
            try:
                result = target.push(record["message"])
            except Exception as exc:
                finished_ns = perf_counter_ns()
                observation.update({
                    "push_call_finished_monotonic_ns": finished_ns,
                    "delivery_status": "failed",
                    "failure_reason": "push_exception",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                })
                self._timing_accumulator("lsl_write_latency").add(
                    (finished_ns - started_ns) / 1_000_000
                )
                self._write_lsl_observation(observation)
                raise

            finished_ns = perf_counter_ns()
            self._timing_accumulator("lsl_write_latency").add(
                (finished_ns - started_ns) / 1_000_000
            )
            observation["push_call_finished_monotonic_ns"] = finished_ns
            lsl_time = result.get("lsl_time_s") if isinstance(result, dict) else None
            valid_lsl_time = (
                isinstance(lsl_time, (int, float))
                and not isinstance(lsl_time, bool)
                and math.isfinite(float(lsl_time))
            )
            if not valid_lsl_time:
                observation.update({
                    "delivery_status": "failed",
                    "failure_reason": "missing_or_invalid_lsl_timestamp",
                    "result_type": type(result).__name__,
                })
                self._write_lsl_observation(observation)
                raise RuntimeError("LSL push returned no finite lsl_time_s delivery evidence")

            assert isinstance(result, dict)
            normalized_result, nonfinite_paths = _normalize_nonfinite_json(result)
            observation.update(normalized_result)
            if nonfinite_paths:
                observation["nonfinite_fields_normalized"] = nonfinite_paths
            observation["delivery_status"] = "delivered"
            self._write_lsl_observation(observation)

        self._lsl_sink = BoundedAsyncSink(
            name="lsl",
            writer=publish,
            capacity=int(getattr(self, "_lsl_sink_capacity", 4096)),
            overflow_policy="drop_newest",
        )
        return self._lsl_sink

    def _write_lsl_observation(self, observation: dict[str, Any]) -> bool:
        observations_file = getattr(self, "lsl_observations_file", None)
        if observations_file is None:
            return False
        if getattr(self, "_lsl_observation_sink_failed", False):
            return False
        lock = getattr(self, "_lsl_observation_lock", None)
        if lock is None:
            lock = Lock()
            self._lsl_observation_lock = lock
        try:
            with lock:
                observations_file.write(
                    json.dumps(
                        observation,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                        allow_nan=False,
                    )
                    + "\n"
                )
                observations_file.flush()
        except Exception as exc:  # noqa: BLE001 - optional evidence sidecar only
            self._lsl_observation_sink_failed = True
            self._lsl_observation_failure_count = (
                getattr(self, "_lsl_observation_failure_count", 0) + 1
            )
            self._lsl_observation_sink_failure = {
                "status": "failed_disabled",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            return False
        return True

    def close_async_sinks(self, timeout_s: float = 5.0) -> bool:
        sink = getattr(self, "_lsl_sink", None)
        if sink is None:
            return True
        try:
            sink.close(timeout_s=timeout_s)
        except SinkCloseTimeout as exc:
            self._lsl_sink_close_error = str(exc)
            self._last_lsl_sink_evidence = sink.evidence().to_dict()
            return False
        except SinkWorkerError as exc:
            self._lsl_sink_close_error = str(exc)
        self._last_lsl_sink_evidence = sink.evidence().to_dict()
        self._lsl_sink = None
        self._lsl_sink_target = None
        return True

    def _timing_accumulator(self, name: str) -> _BoundedTimingAccumulator:
        try:
            seed = _TIMING_SERIES_SEEDS[name]
        except KeyError as exc:
            raise ValueError(f"unknown timing series: {name}") from exc
        attribute = f"_timing_{name}"
        accumulator = getattr(self, attribute, None)
        if accumulator is None:
            accumulator = _BoundedTimingAccumulator(
                capacity=TIMING_SAMPLE_CAPACITY,
                seed=seed,
            )
            setattr(self, attribute, accumulator)
        return accumulator

    def timing_qc_summary(self) -> dict[str, Any]:
        intervals = self._timing_accumulator("update_interval")
        scenario_deltas = self._timing_accumulator("scenario_delta")
        lateness = self._timing_accumulator("event_lateness")
        logger_latency = self._timing_accumulator("logger_write_latency")
        lsl_latency = self._timing_accumulator("lsl_write_latency")
        active_lsl_sink = getattr(self, "_lsl_sink", None)
        lsl_sink_evidence = (
            active_lsl_sink.evidence().to_dict()
            if active_lsl_sink is not None
            else getattr(self, "_last_lsl_sink_evidence", None)
        )

        scientific_session_id = getattr(self, "_scientific_session_uuid", None)
        if scientific_session_id is None:
            scientific_session_id = uuid5(
                NAMESPACE_URL,
                f"openmatb.runtime.session|legacy-{self.session_id}",
            )
            self._scientific_session_uuid = scientific_session_id
        scientific_context = dict(getattr(self, "_scientific_context", {}))
        source_status = _source_commit_status(
            scientific_context.get("source_commit"),
            scientific_context.get("source_dirty"),
        )
        runtime_contract_status = _runtime_contract_status(scientific_context)

        return {
            "timing_qc_schema_version": TIMING_QC_SCHEMA_VERSION,
            "session_id": self.session_id,
            "scientific_session_id": str(scientific_session_id),
            "component_id": SCIENTIFIC_COMPONENT_ID,
            "component_version": scientific_context.get("component_version"),
            "profile_id": scientific_context.get("profile_id"),
            "scenario_sha256": scientific_context.get("scenario_sha256"),
            "scenario_manifest_status": scientific_context.get("scenario_manifest_status"),
            "scenario_manifest_sha256": scientific_context.get("scenario_manifest_sha256"),
            "experiment_spec_sha256": scientific_context.get("experiment_spec_sha256"),
            "experiment_seed": scientific_context.get("experiment_seed"),
            "scenario_compiler_id": scientific_context.get("scenario_compiler_id"),
            "scenario_compiler_version": scientific_context.get("scenario_compiler_version"),
            "source_commit": scientific_context.get("source_commit"),
            "source_dirty": scientific_context.get("source_dirty"),
            "source_commit_status": source_status,
            "runtime_contract_status": runtime_contract_status,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "software_clock": "python.perf_counter_ns",
            "runtime": {"python": platform.python_version(), "platform": platform.platform()},
            "update_interval": intervals.summary(),
            "scenario_delta": scenario_deltas.summary(),
            "long_update_stalls_over_100ms": intervals.over_100_ms_count,
            "event_dispatch_lateness": lateness.summary(),
            "logger_write_latency": logger_latency.summary(),
            "lsl_push_call_latency": lsl_latency.summary(),
            "sinks": {
                "events_jsonl": (
                    getattr(self, "_authoritative_sink_failure", None)
                    or {"status": "authoritative"}
                ),
                "legacy_csv": (
                    {
                        **getattr(self, "_legacy_csv_sink_failure", {}),
                        "failure_count": getattr(self, "_legacy_csv_failure_count", 0),
                    }
                    if getattr(self, "_legacy_csv_sink_failed", False)
                    else {"status": "available", "failure_count": 0}
                ),
                "lsl": lsl_sink_evidence,
                "lsl_close_error": getattr(self, "_lsl_sink_close_error", None),
                "lsl_observations_jsonl": (
                    {
                        **getattr(self, "_lsl_observation_sink_failure", {}),
                        "failure_count": getattr(
                            self, "_lsl_observation_failure_count", 0
                        ),
                    }
                    if getattr(self, "_lsl_observation_sink_failed", False)
                    else {"status": "available", "failure_count": 0}
                ),
            },
            "session_completion": {
                "terminal_marker_persisted": bool(
                    getattr(self, "_terminal_marker_persisted", False)
                ),
                "async_sinks_drained": bool(
                    getattr(self, "_terminal_shutdown_complete", False)
                ),
                "status": (
                    "complete"
                    if getattr(self, "_terminal_shutdown_complete", False)
                    else (
                        "invalid_shutdown_pending_retry"
                        if getattr(self, "_terminal_marker_persisted", False)
                        else "not_terminalized"
                    )
                ),
                "error": getattr(self, "_terminal_shutdown_error", None),
            },
            "artifacts": self._artifact_integrity(),
            "physical_onset": {
                "available": False,
                "reason": "requires session-specific photodiode or audio-loopback measurement",
            },
            "interpretation": "software timing QC only; not evidence of physical stimulus-onset latency",
        }

    @staticmethod
    def _file_integrity(path: Path) -> dict[str, Any]:
        digest = sha256()
        size_bytes = 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                size_bytes += len(chunk)
        return {
            "filename": path.name,
            "size_bytes": size_bytes,
            "sha256": digest.hexdigest(),
        }

    def _artifact_integrity(self) -> dict[str, dict[str, Any]]:
        artifacts: dict[str, dict[str, Any]] = {}
        for role, attribute in (
            ("csv", "path"),
            ("events_jsonl", "events_path"),
            ("lsl_observations_jsonl", "lsl_observations_path"),
            ("scenario_provenance", "scenario_provenance_path"),
            ("scenario_manifest", "scenario_manifest_archive_path"),
        ):
            candidate = getattr(self, attribute, None)
            if candidate is None:
                continue
            path = Path(candidate)
            if path.is_file():
                artifacts[role] = self._file_integrity(path)
            else:
                artifacts[role] = {
                    "filename": path.name,
                    "size_bytes": None,
                    "sha256": None,
                    "status": "missing",
                }
        return artifacts

    def write_timing_qc(self) -> None:
        path = getattr(self, "timing_qc_path", None)
        if path is None:
            return
        for handle_name in ("file", "events_file", "lsl_observations_file"):
            handle = getattr(self, handle_name, None)
            if handle is not None and not handle.closed:
                handle.flush()
        path.write_text(
            json.dumps(self.timing_qc_summary(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def set_totaltime(self, totaltime: float) -> None:
        self.totaltime: float = totaltime

    def set_scenario_time(self, scenario_time: float) -> None:
        now_ns = perf_counter_ns()
        last_ns = getattr(self, "_last_update_monotonic_ns", None)
        last_scenario_time = getattr(self, "_last_scenario_time", None)
        if last_ns is not None:
            self._timing_accumulator("update_interval").add(
                (now_ns - last_ns) / 1_000_000
            )
        if last_scenario_time is not None:
            self._timing_accumulator("scenario_delta").add(
                max(0.0, (scenario_time - last_scenario_time) * 1000)
            )
        self._last_update_monotonic_ns = now_ns
        self._last_scenario_time = scenario_time
        self.scenario_time = scenario_time
