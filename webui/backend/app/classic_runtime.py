"""Guarded lifecycle for Polar-synchronized classic OpenMATB attempts."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import secrets
import sys
import time
from typing import Any
from uuid import uuid4

import numpy as np

from app.classic_persistence import (
    ClassicAttemptContext,
    ClassicPersistenceError,
    SQLModelClassicPersistence,
)
from app.classic_schemas import (
    ClassicArtifactView,
    ClassicDebriefView,
    ClassicSessionView,
    CreateClassicSession,
    PreparedClassicSession,
)
from matb_integration.log_converter import convert_session
from matb_integration.openmatb_events import (
    OPENMATB_EVENT_SCHEMA_VERSION,
    OpenMATBEventTail as _OpenMATBEventTail,
    find_openmatb_event as _find_openmatb_event,
)
from matb_integration.physiology.acquisition import (
    AcquisitionLifecycleError,
    PolarConnectionManager,
    PolarSessionRecorder,
    PolarSessionResult,
    recover_polar_session_journal,
)
from matb_integration.physiology.hrv import HRV_ANALYSIS_VERSION, analyze_rr_phase
from matb_integration.physiology.durability import (
    fsync_directory as _fsync_directory,
    make_private_directory,
    open_private_exclusive,
)
from matb_integration.physiology.openmatb_process import (
    OpenMATBLauncher,
)
from matb_integration.physiology.reporting import (
    build_session_bundle,
    discard_incomplete_bundle,
    load_complete_bundle,
)


BASELINE_DURATION_SECONDS = 300.0
TASK_DURATION_SECONDS = 900.0
RECOVERY_DURATION_SECONDS = 300.0
TASK_BOUNDARY_WATCHDOG_SECONDS = 1800.0
POST_TASK_QUESTIONNAIRE_TIMEOUT_SECONDS = 600.0
# OpenMATB schedules the terminal stop/questionnaire events at 900 s.  Allow a
# small scheduler/logging boundary tolerance, but never accept an early window
# merely because the child emitted its natural-completion marker.
MIN_TASK_COMPLETION_SCENARIO_TIME_SECONDS = TASK_DURATION_SECONDS - 2.0


class ClassicRuntimeError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(slots=True)
class _ActiveClassicSession:
    request: CreateClassicSession
    lease_hash: str
    run_dir: Path
    scenario_sha256: str | None
    openmatb_source_sha256: str | None
    test_mode: bool
    wall_time_scale: float
    task: asyncio.Task[None] | None = None
    recorder: PolarSessionRecorder | None = None
    current_phase: str | None = None
    abort_reason: str | None = None
    requested_terminal_status: str | None = None
    error_code: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _publish_private_text(path: Path, text: str) -> None:
    """Atomically publish one private, fsynced synthetic capture file."""

    destination = Path(path)
    make_private_directory(destination.parent)
    if destination.is_symlink():
        raise ClassicRuntimeError("classic_capture_path_invalid")
    if destination.exists():
        if not destination.is_file():
            raise ClassicRuntimeError("classic_capture_path_invalid")
        return
    staging = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        with open_private_exclusive(staging, binary=False) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, destination)
        _fsync_directory(destination.parent)
    finally:
        with suppress(FileNotFoundError):
            staging.unlink()


def _post_task_elapsed_seconds(attempt: Any) -> float | None:
    started = attempt.task_finished_at
    finished = attempt.recovery_started_at
    if started is None or finished is None:
        return None
    return max(0.0, float((finished - started).total_seconds()))


def _missing_physiology() -> PolarSessionResult:
    phase_results: dict[str, dict[str, Any]] = {}
    for phase, duration in (
        ("baseline", BASELINE_DURATION_SECONDS),
        ("task", TASK_DURATION_SECONDS),
        ("recovery", RECOVERY_DURATION_SECONDS),
    ):
        analysis = analyze_rr_phase(
            np.asarray([], dtype=float),
            nominal_duration_s=duration,
            coverage_fraction=0.0,
        )
        analysis["phase_started"] = False
        analysis["quality"]["reason_codes"] = ["phase_not_started"]
        analysis["time_domain"] = {
            "status": "not_computable",
            "reason_code": "phase_not_started",
            "metrics": None,
        }
        analysis["frequency_domain"] = {
            "status": "not_computable",
            "reason_codes": ["phase_not_started"],
            "metrics": None,
            "psd": [],
        }
        phase_results[phase] = analysis
    return PolarSessionResult(
        rr_records=(),
        phase_results=phase_results,
        clock_anchors=(),
        malformed_packet_count=0,
        disconnect_count=0,
        queue_overflow_count=0,
        contact_loss_detected=False,
    )


def _overall_physiology_quality(result: PolarSessionResult, *, overridden: bool) -> str:
    if overridden:
        return "missing_performance_only"
    order = {
        "excellent": 0,
        "good": 1,
        "acceptable": 2,
        "poor": 3,
        "unusable": 4,
        "insufficient_data": 5,
    }
    labels = [
        str(phase.get("quality", {}).get("label", "insufficient_data"))
        for phase in result.phase_results.values()
    ]
    return max(labels, key=lambda label: order.get(label, 5)) if labels else "insufficient_data"


def _physiology_availability(result: PolarSessionResult, *, overridden: bool) -> str:
    if overridden:
        return "not_acquired_performance_only"
    expected = {"baseline", "task", "recovery"}
    if set(result.phase_results) != expected:
        return "incomplete_phases"
    for phase in result.phase_results.values():
        for domain in ("time_domain", "frequency_domain"):
            value = phase.get(domain)
            if not isinstance(value, dict) or value.get("status") != "ok":
                return "gated"
    return "fully_computable"


def _has_natural_openmatb_completion(events_path: Path, *, session_id: str) -> bool:
    """Return true only for the scheduler's natural-completion marker.

    ``scenario_finished`` is deliberately not sufficient: it is also emitted
    when a participant closes the MATB window early.
    """

    return (
        _find_openmatb_event(
            events_path,
            "scenario_completed",
            session_id=session_id,
        )
        is not None
    )


def _acquisition_provenance(polar: PolarConnectionManager) -> dict[str, Any]:
    status = polar.status
    try:
        bleak_version = importlib.metadata.version("bleak")
    except importlib.metadata.PackageNotFoundError:
        bleak_version = None
    return {
        "polar_backend": status.backend_name,
        # The advertised H10 name commonly contains a stable unit suffix. Keep
        # it available only in transient operator status, never in exports.
        "device_model": "Polar H10" if status.device_identifier_sha256 else None,
        "bleak_version": bleak_version,
        "host_system": platform.system(),
        "host_release": platform.release(),
        "python_version": platform.python_version(),
        "python_executable_name": Path(sys.executable).name,
        "hrv_analysis_version": HRV_ANALYSIS_VERSION,
        "rr_source": "bluetooth_sig_heart_rate_measurement_0x2a37",
        "rr_unit": "1/1024_second",
        "timestamp_method": "host_rr_robust_offset_v1",
    }


class ClassicManager:
    def __init__(
        self,
        *,
        artifact_root: Path,
        persistence: SQLModelClassicPersistence,
        polar: PolarConnectionManager,
        launcher: OpenMATBLauncher | Any,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        test_mode: bool = False,
        wall_time_scale: float = 1.0,
    ) -> None:
        if (
            isinstance(wall_time_scale, bool)
            or not isinstance(wall_time_scale, (int, float))
            or not np.isfinite(wall_time_scale)
            or not 0.001 <= float(wall_time_scale) <= 1.0
            or (not test_mode and float(wall_time_scale) != 1.0)
        ):
            raise ValueError("invalid_classic_wall_time_scale")
        self.artifact_root = Path(artifact_root).resolve()
        make_private_directory(self.artifact_root)
        self.persistence = persistence
        self.polar = polar
        self.launcher = launcher
        self._sleep = sleep
        self.test_mode = bool(test_mode)
        self.wall_time_scale = float(wall_time_scale)
        self._active: _ActiveClassicSession | None = None
        self._lock = asyncio.Lock()

    def scenarios(self) -> tuple[str, ...]:
        return self.launcher.available_scenarios()

    @staticmethod
    def _validated_digest(value: Any, *, error_code: str) -> str:
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ClassicRuntimeError(error_code)
        return value

    def _scenario_sha256(self, scenario_name: str) -> str:
        try:
            digest = self.launcher.scenario_sha256(scenario_name)
        except Exception as exc:
            code = getattr(exc, "code", "openmatb_scenario_hash_failed")
            raise ClassicRuntimeError(str(code)) from exc
        return self._validated_digest(digest, error_code="openmatb_scenario_hash_invalid")

    def _openmatb_source_sha256(self) -> str:
        try:
            digest = self.launcher.application_sha256()
        except Exception as exc:
            code = getattr(exc, "code", "openmatb_source_hash_failed")
            raise ClassicRuntimeError(str(code)) from exc
        return self._validated_digest(digest, error_code="openmatb_source_hash_invalid")

    def _provenance(self, active: _ActiveClassicSession) -> dict[str, Any]:
        return {
            **_acquisition_provenance(self.polar),
            "scenario_sha256": active.scenario_sha256,
            "openmatb_source_sha256": active.openmatb_source_sha256,
            "test_mode": active.test_mode,
            "wall_time_scale": active.wall_time_scale,
        }

    def recover_orphaned_attempts(self) -> int:
        """Seal restart-interrupted attempts from their fsynced RR journal."""

        active_statuses = {
            "PREPARED",
            "BASELINE",
            "TASK",
            "POST_TASK",
            "RECOVERY",
            "FINALIZING",
        }
        repairable_terminal_statuses = {"ABORTED", "INTERRUPTED"}
        recovered = 0
        for context in self.persistence.list_attempts():
            attempt = context.attempt
            is_active = attempt.status in active_statuses
            registered_artifacts = self.persistence.list_artifacts(attempt.id)
            repairable_terminal = (
                attempt.status in repairable_terminal_statuses
                and not registered_artifacts
            )
            run_dir = (self.artifact_root / attempt.artifact_root).resolve()
            if self.artifact_root not in run_dir.parents:
                if not is_active and not repairable_terminal:
                    continue
                terminal_status = (
                    attempt.terminal_intent_status
                    if attempt.terminal_intent_status in repairable_terminal_statuses
                    else (
                        attempt.status
                        if repairable_terminal
                        else "INTERRUPTED"
                    )
                )
                terminal_reason = (
                    attempt.terminal_intent_reason_code
                    or attempt.failure_reason_code
                    or "classic_artifact_path"
                )
                self._preserve_terminal_intent(
                    attempt.id,
                    status=terminal_status,
                    reason=terminal_reason,
                )
                recovered += 1
                continue
            if registered_artifacts:
                self._validate_registered_bundle(
                    attempt.id,
                    run_dir,
                    registered_artifacts,
                )
                continue
            has_commit_marker = (run_dir / "checksums.sha256").is_file()
            if not is_active and not repairable_terminal and not has_commit_marker:
                continue
            make_private_directory(run_dir)
            complete_bundle = load_complete_bundle(run_dir)
            if complete_bundle is not None:
                inventory, document = complete_bundle
                self._commit_recovered_bundle(
                    context,
                    run_dir,
                    inventory=inventory,
                    document=document,
                )
                recovered += 1
                continue
            if not is_active and not repairable_terminal:
                continue
            discard_incomplete_bundle(run_dir)
            request = CreateClassicSession(
                participant_id=context.participant_id,
                visit_ordinal=context.visit_ordinal,
                workload_level=attempt.workload_level,
                scenario_name=attempt.scenario_name,
                performance_only_override=attempt.performance_only_override,
                override_reason_code=attempt.override_reason_code,
            )
            active = _ActiveClassicSession(
                request=request,
                lease_hash=attempt.controller_lease_hash or "",
                run_dir=run_dir,
                scenario_sha256=attempt.scenario_sha256,
                openmatb_source_sha256=attempt.openmatb_source_sha256,
                test_mode=attempt.test_mode,
                wall_time_scale=attempt.wall_time_scale,
            )
            journal = run_dir / ".capture" / "polar-rr-journal.jsonl"
            physiology = _missing_physiology()
            if attempt.terminal_intent_status in repairable_terminal_statuses:
                terminal_status = str(attempt.terminal_intent_status)
                recovery_reason = str(
                    attempt.terminal_intent_reason_code
                    or attempt.failure_reason_code
                    or "backend_process_restart"
                )
            elif repairable_terminal:
                terminal_status = attempt.status
                recovery_reason = str(
                    attempt.failure_reason_code or "backend_process_restart"
                )
            else:
                terminal_status = "INTERRUPTED"
                recovery_reason = "backend_process_restart"
            if journal.is_file():
                try:
                    physiology = recover_polar_session_journal(journal)
                except AcquisitionLifecycleError as exc:
                    physiology = _missing_physiology()
                    if recovery_reason == "backend_process_restart":
                        recovery_reason = f"backend_process_restart_{exc.code}"
            try:
                self._seal_terminal_bundle(
                    active,
                    attempt.id,
                    physiology=physiology,
                    status=terminal_status,
                    reason=recovery_reason,
                    recovery_from_validated_bundle=repairable_terminal,
                )
            except Exception:
                self._preserve_terminal_intent(
                    attempt.id,
                    status=terminal_status,
                    reason=recovery_reason,
                )
            recovered += 1
        return recovered

    @staticmethod
    def _validate_registered_bundle(
        session_id: str,
        run_dir: Path,
        registered_artifacts: list[Any],
    ) -> None:
        try:
            complete = load_complete_bundle(run_dir)
        except Exception as exc:
            raise ClassicRuntimeError("classic_registered_bundle_integrity_failed") from exc
        if complete is None:
            raise ClassicRuntimeError("classic_registered_bundle_missing")
        inventory, document = complete
        expected = {
            artifact.relative_path: (
                artifact.kind,
                artifact.sha256,
                artifact.size_bytes,
            )
            for artifact in registered_artifacts
        }
        actual = {
            artifact.relative_path: (
                artifact.kind,
                artifact.sha256,
                artifact.size_bytes,
            )
            for artifact in inventory
        }
        if expected != actual or document.get("session", {}).get("session_id") != session_id:
            raise ClassicRuntimeError("classic_registered_bundle_integrity_failed")

    def _commit_recovered_bundle(
        self,
        context: ClassicAttemptContext,
        run_dir: Path,
        *,
        inventory: Any,
        document: dict[str, Any],
    ) -> None:
        attempt = context.attempt
        session = document.get("session")
        metrics = document.get("matb_metrics")
        phase_results = document.get("phase_results")
        if (
            not isinstance(session, dict)
            or not isinstance(metrics, dict)
            or not isinstance(phase_results, dict)
            or session.get("session_id") != attempt.id
            or session.get("participant_id") != context.participant_id
            or session.get("visit_ordinal") != context.visit_ordinal
            or session.get("workload_level") != attempt.workload_level
            or (
                attempt.scenario_sha256 is not None
                and session.get("scenario_sha256") != attempt.scenario_sha256
            )
            or (
                attempt.openmatb_source_sha256 is not None
                and session.get("openmatb_source_sha256")
                != attempt.openmatb_source_sha256
            )
            or bool(session.get("test_mode", False)) != attempt.test_mode
            or float(session.get("wall_time_scale", 1.0)) != attempt.wall_time_scale
        ):
            raise ClassicRuntimeError("classic_committed_bundle_mismatch")
        source = run_dir / "openmatb-session.csv"
        source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
        physiology_quality = str(
            session.get("physiology_quality", "insufficient_data")
        )
        stored_summary = session.get("hrv_summary")
        hrv_document = {
            "phases": phase_results,
            "summary": (
                stored_summary
                if isinstance(stored_summary, dict)
                else {"quality": physiology_quality, "legacy_bundle_recovery": True}
            ),
        }
        status = str(session.get("status"))
        if status == "COMPLETE":
            task_validity = str(session.get("task_validity"))
            self.persistence.finalize_attempt_with_artifacts(
                attempt.id,
                task_validity=task_validity,
                physiology_quality=physiology_quality,
                source_csv_filename="openmatb-session.csv",
                source_csv_sha256=source_digest,
                metrics=metrics,
                hrv=hrv_document,
                inventory=inventory,
                failure_reason_code=session.get("failure_reason_code"),
                recovery_from_validated_bundle=True,
            )
            return
        if status in {"ABORTED", "INTERRUPTED"}:
            self.persistence.terminate_attempt_with_artifacts(
                attempt.id,
                status=status,
                reason_code=str(
                    session.get("failure_reason_code") or "backend_process_restart"
                ),
                task_validity="invalid",
                physiology_quality=physiology_quality,
                source_csv_filename="openmatb-session.csv",
                source_csv_sha256=source_digest,
                metrics=metrics,
                hrv=hrv_document,
                inventory=inventory,
                recovery_from_validated_bundle=True,
            )
            return
        raise ClassicRuntimeError("classic_committed_bundle_status_invalid")

    async def prepare_session(self, request: CreateClassicSession) -> PreparedClassicSession:
        async with self._lock:
            if self._active is not None:
                raise ClassicRuntimeError("classic_active_session")
            if request.scenario_name not in self.scenarios():
                raise ClassicRuntimeError("classic_scenario_not_available")
            scenario_sha256 = self._scenario_sha256(request.scenario_name)
            openmatb_source_sha256 = self._openmatb_source_sha256()
            if not request.performance_only_override:
                polar_status = self.polar.status
                fresh_preflight = (
                    self.polar.preflight_is_fresh(max_age_ns=120_000_000_000)
                )
                if polar_status.state != "connected" or not fresh_preflight:
                    raise ClassicRuntimeError("polar_preflight_required")
            session_id = str(uuid4())
            lease = secrets.token_urlsafe(32)
            lease_hash = hashlib.sha256(lease.encode("utf-8")).hexdigest()
            run_dir = (self.artifact_root / session_id).resolve()
            if self.artifact_root not in run_dir.parents:
                raise ClassicRuntimeError("classic_artifact_path")
            try:
                attempt = self.persistence.create_attempt(
                    participant_id=request.participant_id,
                    visit_ordinal=request.visit_ordinal,
                    workload_level=request.workload_level,
                    scenario_name=request.scenario_name,
                    scenario_sha256=scenario_sha256,
                    openmatb_source_sha256=openmatb_source_sha256,
                    test_mode=self.test_mode,
                    wall_time_scale=self.wall_time_scale,
                    artifact_root=session_id,
                    session_id=session_id,
                    controller_lease_hash=lease_hash,
                    performance_only_override=request.performance_only_override,
                    override_reason_code=request.override_reason_code,
                )
                if not request.performance_only_override:
                    attempt = self.persistence.update_attempt_state(
                        session_id,
                        battery_level_at_start=self.polar.status.battery_level,
                    )
            except ClassicPersistenceError as exc:
                raise ClassicRuntimeError(exc.code) from exc
            make_private_directory(run_dir, exist_ok=False)
            self._active = _ActiveClassicSession(
                request=request,
                lease_hash=lease_hash,
                run_dir=run_dir,
                scenario_sha256=scenario_sha256,
                openmatb_source_sha256=openmatb_source_sha256,
                test_mode=self.test_mode,
                wall_time_scale=self.wall_time_scale,
            )
            context = ClassicAttemptContext(
                attempt=attempt,
                participant_id=request.participant_id,
                visit_ordinal=request.visit_ordinal,
            )
            return PreparedClassicSession(
                **self._view(context).model_dump(),
                controller_lease=lease,
            )

    async def start_session(self, session_id: str, lease: str) -> ClassicSessionView:
        async with self._lock:
            active = self._require_active(session_id, lease)
            if active.task is not None:
                raise ClassicRuntimeError("classic_session_already_started")
            if not active.request.performance_only_override:
                if (
                    self.polar.status.state != "connected"
                    or not self.polar.preflight_is_fresh(
                        max_age_ns=120_000_000_000
                    )
                ):
                    raise ClassicRuntimeError("polar_preflight_required")
            active.task = asyncio.create_task(self._run(active, session_id))
        return self.session_view(session_id)

    async def wait_until_finished(self, session_id: str) -> ClassicSessionView:
        active = self._active
        if active is not None and self._session_id(active) == session_id and active.task is not None:
            await active.task
        return self.session_view(session_id)

    async def abort(self, session_id: str, lease: str, reason_code: str) -> ClassicSessionView:
        async with self._lock:
            active = self._require_active(session_id, lease)
            active.abort_reason = reason_code
            active.requested_terminal_status = "ABORTED"
            task = active.task
            if task is None:
                try:
                    self._seal_terminal_bundle(
                        active,
                        session_id,
                        physiology=_missing_physiology(),
                        status="ABORTED",
                        reason=reason_code,
                    )
                except Exception:
                    self._preserve_terminal_intent(
                        session_id,
                        status="ABORTED",
                        reason=reason_code,
                    )
                self._active = None
                return self.session_view(session_id)
        await self.launcher.abort()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self._seal_after_unscheduled_cancellation(
            active,
            session_id,
            status="ABORTED",
            reason=reason_code,
        )
        return self.session_view(session_id)

    def session_view(self, session_id: str) -> ClassicSessionView:
        try:
            return self._view(self.persistence.get_attempt_context(session_id))
        except ClassicPersistenceError as exc:
            raise ClassicRuntimeError(exc.code) from exc

    def history(
        self,
        *,
        participant_id: str | None = None,
        visit_ordinal: int | None = None,
    ) -> list[ClassicSessionView]:
        return [
            self._view(context)
            for context in self.persistence.list_attempts(
                participant_id=participant_id,
                visit_ordinal=visit_ordinal,
            )
        ]

    def artifacts(self, session_id: str) -> list[ClassicArtifactView]:
        try:
            return [
                ClassicArtifactView.model_validate(artifact, from_attributes=True)
                for artifact in self.persistence.list_artifacts(session_id)
            ]
        except ClassicPersistenceError as exc:
            raise ClassicRuntimeError(exc.code) from exc

    def visit_summary(self, participant_id: str, visit_ordinal: int) -> dict[str, Any]:
        contexts = self.persistence.list_attempts(
            participant_id=participant_id,
            visit_ordinal=visit_ordinal,
        )
        if not contexts:
            raise ClassicRuntimeError("visit_not_found")
        workloads: dict[str, dict[str, Any]] = {}
        for context in contexts:
            attempt = context.attempt
            group = workloads.setdefault(
                attempt.workload_level,
                {
                    "selected_attempt_id": self.persistence.selected_attempt_id(
                        visit_id=attempt.visit_id,
                        workload_level=attempt.workload_level,
                    ),
                    "attempts": [],
                },
            )
            group["attempts"].append(
                {
                    "session": self._view(context).model_dump(mode="json"),
                    "matb_metrics": (
                        json.loads(attempt.metrics_json) if attempt.metrics_json else {}
                    ),
                    "hrv": json.loads(attempt.hrv_json) if attempt.hrv_json else {},
                }
            )
        return {
            "schema_version": "matb-classic-visit-summary-v1",
            "participant_id": participant_id,
            "visit_ordinal": visit_ordinal,
            "selection_audit": [
                {
                    "workload_level": row.workload_level,
                    "previous_attempt_id": row.previous_attempt_id,
                    "new_attempt_id": row.new_attempt_id,
                    "reason_code": row.reason_code,
                    "actor": row.actor,
                    "changed_at": row.changed_at.isoformat(),
                }
                for row in self.persistence.list_selection_audits(
                    participant_id=participant_id,
                    visit_ordinal=visit_ordinal,
                )
            ],
            "workloads": workloads,
        }

    def debrief(self, session_id: str) -> ClassicDebriefView:
        try:
            context = self.persistence.get_attempt_context(session_id)
        except ClassicPersistenceError as exc:
            raise ClassicRuntimeError(exc.code) from exc
        attempt = context.attempt
        if (
            attempt.status not in {"COMPLETE", "ABORTED", "INTERRUPTED"}
            or attempt.metrics_json is None
            or attempt.hrv_json is None
        ):
            raise ClassicRuntimeError("classic_debrief_unavailable")
        selected = (
            self.persistence.selected_attempt_id(
                visit_id=attempt.visit_id,
                workload_level=attempt.workload_level,
            )
            == attempt.id
        )
        return ClassicDebriefView(
            session=self._view(context),
            matb_metrics=json.loads(attempt.metrics_json),
            hrv=json.loads(attempt.hrv_json),
            selected_for_visit=selected,
        )

    def select_attempt(self, session_id: str, reason_code: str) -> ClassicSessionView:
        try:
            self.persistence.select_attempt(session_id, reason_code=reason_code)
        except ClassicPersistenceError as exc:
            raise ClassicRuntimeError(exc.code) from exc
        return self.session_view(session_id)

    def resolve_artifact(self, session_id: str, relative_path: str) -> Path:
        registered = {artifact.relative_path for artifact in self.artifacts(session_id)}
        if relative_path not in registered:
            raise ClassicRuntimeError("classic_artifact_not_found")
        context = self.persistence.get_attempt_context(session_id)
        session_root = (self.artifact_root / context.attempt.artifact_root).resolve()
        path = (session_root / relative_path).resolve()
        if session_root not in path.parents or not path.is_file():
            raise ClassicRuntimeError("classic_artifact_not_found")
        return path

    async def shutdown(self) -> None:
        active = self._active
        if active is not None:
            session_id = self._session_id(active)
            active.abort_reason = "backend_shutdown"
            active.requested_terminal_status = "INTERRUPTED"
            if active.task is not None:
                await self.launcher.abort()
                active.task.cancel()
                try:
                    await active.task
                except asyncio.CancelledError:
                    pass
            else:
                self._seal_after_unscheduled_cancellation(
                    active,
                    session_id,
                    status="INTERRUPTED",
                    reason="backend_shutdown",
                )
            self._active = None
        await self.polar.shutdown()

    async def _run(self, active: _ActiveClassicSession, session_id: str) -> None:
        physiology = _missing_physiology()
        process_result: Any | None = None
        try:
            if not active.request.performance_only_override:
                active.recorder = await self.polar.start_recording(
                    session_id,
                    journal_path=active.run_dir
                    / ".capture"
                    / "polar-rr-journal.jsonl",
                )
            await self._run_phase(
                active,
                session_id,
                "baseline",
                BASELINE_DURATION_SECONDS,
            )
            process_result = await self._run_openmatb_task_window(active, session_id)
            await self._run_phase(
                active,
                session_id,
                "recovery",
                RECOVERY_DURATION_SECONDS,
            )
            self.persistence.update_attempt_state(
                session_id,
                status="FINALIZING",
                recovery_finished_at=_utcnow(),
            )
            if active.recorder is not None:
                physiology = await self.polar.stop_recording()
                active.recorder = None
            if process_result is None:
                raise ClassicRuntimeError("openmatb_result_missing")
            matb_metrics = convert_session(
                process_result.source_csv,
                participant_id=active.request.participant_id,
                block_name=f"visit_{active.request.visit_ordinal}_{active.request.workload_level.casefold()}",
                workload_level=active.request.workload_level,
                extra_metadata={"classic_session_id": session_id},
            )
            natural_completion = _has_natural_openmatb_completion(
                process_result.synchronized_events,
                session_id=session_id,
            )
            task_start_event = _find_openmatb_event(
                process_result.synchronized_events,
                "scenario_started",
                session_id=session_id,
            )
            task_boundary_event = _find_openmatb_event(
                process_result.synchronized_events,
                "task_window_completed",
                session_id=session_id,
            )
            task_start_observed = task_start_event is not None
            task_boundary_observed = (
                task_boundary_event is not None
                and self._valid_task_boundary_event(task_boundary_event)
            )
            observed_scenario_time = matb_metrics.get("scenario_time_max_s")
            scenario_duration_complete = bool(
                isinstance(observed_scenario_time, (int, float))
                and not isinstance(observed_scenario_time, bool)
                and np.isfinite(observed_scenario_time)
                and observed_scenario_time
                >= MIN_TASK_COMPLETION_SCENARIO_TIME_SECONDS
            )
            task_validity = (
                "valid"
                if (
                    not self.test_mode
                    and process_result.exit_code == 0
                    and int(matb_metrics.get("n_rows", 0)) > 0
                    and natural_completion
                    and task_start_observed
                    and task_boundary_observed
                    and scenario_duration_complete
                )
                else "invalid"
            )
            failure_reason_code = None
            if task_validity != "valid":
                if self.test_mode:
                    failure_reason_code = "test_mode_attempt"
                elif process_result.exit_code == 0 and not natural_completion:
                    failure_reason_code = "openmatb_task_incomplete"
                elif (
                    process_result.exit_code == 0
                    and int(matb_metrics.get("n_rows", 0)) > 0
                    and not scenario_duration_complete
                ):
                    failure_reason_code = "openmatb_task_too_short"
                elif process_result.exit_code == 0 and not task_boundary_observed:
                    failure_reason_code = "openmatb_task_boundary_missing"
                elif process_result.exit_code == 0 and not task_start_observed:
                    failure_reason_code = "openmatb_task_start_missing"
                else:
                    failure_reason_code = "openmatb_task_invalid"
            physiology_quality = _overall_physiology_quality(
                physiology,
                overridden=active.request.performance_only_override,
            )
            physiology_availability = _physiology_availability(
                physiology,
                overridden=active.request.performance_only_override,
            )
            source_bytes = process_result.source_csv.read_bytes()
            source_digest = hashlib.sha256(source_bytes).hexdigest()
            context = self.persistence.get_attempt_context(session_id)
            provenance = self._provenance(active)
            hrv_summary = {
                "quality": physiology_quality,
                "availability": physiology_availability,
                "disconnect_count": physiology.disconnect_count,
                "malformed_packet_count": physiology.malformed_packet_count,
                "queue_overflow_count": physiology.queue_overflow_count,
                "contact_loss_detected": physiology.contact_loss_detected,
            }
            session_payload = {
                "session_id": session_id,
                "participant_id": active.request.participant_id,
                "visit_ordinal": active.request.visit_ordinal,
                "workload_level": active.request.workload_level,
                "attempt_number": context.attempt.attempt_number,
                "scenario_name": active.request.scenario_name,
                "scenario_sha256": active.scenario_sha256,
                "openmatb_source_sha256": active.openmatb_source_sha256,
                "test_mode": active.test_mode,
                "wall_time_scale": active.wall_time_scale,
                "post_task_questionnaire_timeout_seconds": (
                    POST_TASK_QUESTIONNAIRE_TIMEOUT_SECONDS * active.wall_time_scale
                ),
                "post_task_questionnaire_elapsed_seconds": (
                    _post_task_elapsed_seconds(context.attempt)
                ),
                "status": "COMPLETE",
                "task_validity": task_validity,
                "physiology_quality": physiology_quality,
                "physiology_availability": physiology_availability,
                "performance_only_override": active.request.performance_only_override,
                "override_reason_code": active.request.override_reason_code,
                "polar_backend": provenance["polar_backend"],
                "acquisition_mode": (
                    "performance_only"
                    if active.request.performance_only_override
                    else "polar_h10_rr"
                ),
                "provenance": provenance,
                "openmatb_exit_code": process_result.exit_code,
                "openmatb_natural_completion": natural_completion,
                "openmatb_task_start_observed": task_start_observed,
                "openmatb_task_boundary_observed": task_boundary_observed,
                "openmatb_task_boundary_scenario_time_s": (
                    task_boundary_event.get("scenario_time")
                    if task_boundary_event is not None
                    else None
                ),
                "openmatb_expected_duration_s": TASK_DURATION_SECONDS,
                "openmatb_max_scenario_time_s": observed_scenario_time,
                "openmatb_duration_complete": scenario_duration_complete,
                "malformed_heart_rate_packet_count": physiology.malformed_packet_count,
                "bluetooth_disconnect_count": physiology.disconnect_count,
                "acquisition_queue_overflow_count": physiology.queue_overflow_count,
                "contact_loss_detected": physiology.contact_loss_detected,
                "failure_reason_code": failure_reason_code,
                "hrv_summary": hrv_summary,
            }
            hrv_document = {
                "phases": physiology.phase_results,
                "summary": hrv_summary,
            }
            inventory = build_session_bundle(
                active.run_dir,
                session=session_payload,
                matb_metrics=matb_metrics,
                phase_results=physiology.phase_results,
                rr_records=physiology.rr_records,
                clock_anchors=physiology.clock_anchors,
                openmatb_csv=process_result.source_csv,
                synchronized_events=process_result.synchronized_events,
            )
            self.persistence.finalize_attempt_with_artifacts(
                session_id,
                task_validity=task_validity,
                physiology_quality=physiology_quality,
                source_csv_filename="openmatb-session.csv",
                source_csv_sha256=source_digest,
                metrics=matb_metrics,
                hrv=hrv_document,
                inventory=inventory,
                failure_reason_code=failure_reason_code,
            )
        except asyncio.CancelledError:
            partial = await self._stop_recorder_after_failure(active)
            terminal_status = active.requested_terminal_status or "INTERRUPTED"
            terminal_reason = active.abort_reason or "classic_task_cancelled"
            try:
                self._seal_terminal_bundle(
                    active,
                    session_id,
                    physiology=partial or _missing_physiology(),
                    status=terminal_status,
                    reason=terminal_reason,
                )
            except Exception:
                self._preserve_terminal_intent(
                    session_id,
                    status=terminal_status,
                    reason=terminal_reason,
                )
            raise
        except Exception as exc:
            partial = await self._stop_recorder_after_failure(active)
            code = getattr(exc, "code", None) or f"classic_runtime_failure_{type(exc).__name__.casefold()}"
            active.error_code = str(code)
            try:
                self._seal_terminal_bundle(
                    active,
                    session_id,
                    physiology=partial or _missing_physiology(),
                    status="INTERRUPTED",
                    reason=str(code),
                )
            except Exception:
                self._preserve_terminal_intent(
                    session_id,
                    status="INTERRUPTED",
                    reason=str(code),
                )
        finally:
            async with self._lock:
                if self._active is active:
                    self._active = None

    async def _run_phase(
        self,
        active: _ActiveClassicSession,
        session_id: str,
        phase: str,
        duration_seconds: float,
    ) -> None:
        fields: dict[str, Any] = {"status": phase.upper()}
        if phase == "baseline":
            fields["baseline_started_at"] = _utcnow()
        elif phase == "recovery":
            fields["recovery_started_at"] = _utcnow()
        self.persistence.update_attempt_state(session_id, **fields)
        active.current_phase = phase
        if active.recorder is not None:
            active.recorder.begin_phase(phase, nominal_duration_s=duration_seconds)
        await self._wait_duration(duration_seconds)
        if active.recorder is not None:
            active.recorder.end_phase(phase)
        active.current_phase = None

    async def _wait_duration(self, duration_seconds: float) -> None:
        awaited = self._sleep(duration_seconds)
        if awaited is not None:
            await awaited

    async def _run_openmatb_task_window(
        self,
        active: _ActiveClassicSession,
        session_id: str,
    ) -> Any:
        """End task physiology at the child's 900-scenario-second marker."""

        if self._scenario_sha256(active.request.scenario_name) != active.scenario_sha256:
            raise ClassicRuntimeError("openmatb_scenario_changed_after_prepare")
        if self._openmatb_source_sha256() != active.openmatb_source_sha256:
            raise ClassicRuntimeError("openmatb_source_changed_after_prepare")

        process_task = asyncio.create_task(
            self.launcher.run(
                scenario_name=active.request.scenario_name,
                session_id=session_id,
                output_dir=active.run_dir / ".capture",
            )
        )
        events_path = active.run_dir / ".capture" / "openmatb-events.jsonl"
        loop = asyncio.get_running_loop()
        started: asyncio.Future[dict[str, Any]] = loop.create_future()
        boundary_task = asyncio.create_task(
            self._monitor_openmatb_task_boundaries(
                events_path,
                session_id=session_id,
                started=started,
            )
        )
        watchdog_task = asyncio.create_task(
            asyncio.sleep(TASK_BOUNDARY_WATCHDOG_SECONDS)
        )
        try:
            done, _ = await asyncio.wait(
                {process_task, started, boundary_task, watchdog_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if started in done:
                self._start_task_phase(active, session_id, await started)
            elif process_task in done:
                result = await process_task
                self._finish_task_phase_from_completed_process(
                    active,
                    session_id,
                    result.synchronized_events,
                )
                for task in (boundary_task, watchdog_task):
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                return result
            elif boundary_task in done:
                # A malformed stream can fail before scenario_started.
                await boundary_task
                raise ClassicRuntimeError("openmatb_task_start_missing")
            else:
                raise ClassicRuntimeError("openmatb_task_boundary_timeout")

            done, _ = await asyncio.wait(
                {process_task, boundary_task, watchdog_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if boundary_task in done:
                boundary_event = await boundary_task
                watchdog_task.cancel()
                with suppress(asyncio.CancelledError):
                    await watchdog_task
                self._finish_task_phase(
                    active,
                    session_id,
                    boundary_event=boundary_event,
                )
                return await self._await_post_task_process(active, process_task)

            if process_task in done:
                result = await process_task
                boundary_event = _find_openmatb_event(
                    result.synchronized_events,
                    "task_window_completed",
                    session_id=session_id,
                )
                for task in (boundary_task, watchdog_task):
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                if active.current_phase == "task":
                    self._finish_task_phase(
                        active,
                        session_id,
                        boundary_event=boundary_event,
                    )
                return result

            boundary_task.cancel()
            with suppress(asyncio.CancelledError):
                await boundary_task
            await self.launcher.abort()
            with suppress(asyncio.CancelledError, Exception):
                await process_task
            raise ClassicRuntimeError("openmatb_task_boundary_timeout")
        except BaseException:
            with suppress(asyncio.CancelledError, Exception):
                await self.launcher.abort()
            if not started.done():
                started.cancel()
            for task in (process_task, boundary_task, watchdog_task):
                if not task.done():
                    task.cancel()
            for task in (process_task, boundary_task, watchdog_task):
                with suppress(asyncio.CancelledError, Exception):
                    await task
            raise

    async def _await_post_task_process(
        self,
        active: _ActiveClassicSession,
        process_task: asyncio.Task[Any],
    ) -> Any:
        """Bound participant-facing post-task forms before recovery can begin."""

        timeout_seconds = (
            POST_TASK_QUESTIONNAIRE_TIMEOUT_SECONDS * active.wall_time_scale
        )
        try:
            return await asyncio.wait_for(
                asyncio.shield(process_task),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            raise ClassicRuntimeError("openmatb_post_task_timeout") from exc

    async def _monitor_openmatb_task_boundaries(
        self,
        events_path: Path,
        *,
        session_id: str,
        started: asyncio.Future[dict[str, Any]],
    ) -> dict[str, Any]:
        tail = _OpenMATBEventTail(events_path, session_id=session_id)
        try:
            while True:
                for event in tail.read_new():
                    event_name = event.get("event")
                    if event_name == "scenario_started":
                        if started.done() or not self._valid_task_start_event(event):
                            raise ClassicRuntimeError("openmatb_task_start_invalid")
                        started.set_result(event)
                    elif event_name == "task_window_completed":
                        if not started.done() or not self._valid_task_boundary_event(event):
                            raise ClassicRuntimeError("openmatb_task_boundary_invalid")
                        return event
                await asyncio.sleep(0.02)
        except BaseException as exc:
            if not started.done():
                if isinstance(exc, asyncio.CancelledError):
                    started.cancel()
                else:
                    started.set_exception(exc)
            raise

    def _finish_task_phase_from_completed_process(
        self,
        active: _ActiveClassicSession,
        session_id: str,
        events_path: Path,
    ) -> None:
        start_event = _find_openmatb_event(
            events_path,
            "scenario_started",
            session_id=session_id,
        )
        if start_event is not None:
            self._start_task_phase(active, session_id, start_event)
        boundary_event = _find_openmatb_event(
            events_path,
            "task_window_completed",
            session_id=session_id,
        )
        if active.current_phase == "task":
            self._finish_task_phase(
                active,
                session_id,
                boundary_event=boundary_event,
            )

    def _start_task_phase(
        self,
        active: _ActiveClassicSession,
        session_id: str,
        event: dict[str, Any],
    ) -> None:
        if active.current_phase is not None or not self._valid_task_start_event(event):
            raise ClassicRuntimeError("openmatb_task_start_invalid")
        boundary_monotonic_ns = self._event_integer(event, "received_monotonic_ns")
        if active.recorder is not None:
            active.recorder.begin_phase(
                "task",
                nominal_duration_s=TASK_DURATION_SECONDS,
                boundary_monotonic_ns=boundary_monotonic_ns,
            )
        active.current_phase = "task"
        self.persistence.update_attempt_state(
            session_id,
            status="TASK",
            task_started_at=self._event_utc(event),
        )

    def _finish_task_phase(
        self,
        active: _ActiveClassicSession,
        session_id: str,
        *,
        boundary_event: dict[str, Any] | None = None,
    ) -> None:
        if active.current_phase != "task":
            raise ClassicRuntimeError("openmatb_task_phase_not_started")
        if boundary_event is not None and not self._valid_task_boundary_event(boundary_event):
            raise ClassicRuntimeError("openmatb_task_boundary_invalid")
        if active.recorder is not None:
            boundary_monotonic_ns = self._event_integer(
                boundary_event,
                "received_monotonic_ns",
            ) if boundary_event is not None else None
            active.recorder.end_phase(
                "task",
                boundary_monotonic_ns=boundary_monotonic_ns,
                use_observed_duration=boundary_event is not None,
            )
        active.current_phase = None
        self.persistence.update_attempt_state(
            session_id,
            status="POST_TASK",
            task_finished_at=(
                self._event_utc(boundary_event)
                if boundary_event is not None
                else _utcnow()
            ),
        )

    @staticmethod
    def _event_integer(event: dict[str, Any], field: str) -> int:
        value = event.get(field)
        if isinstance(value, bool):
            raise ClassicRuntimeError("openmatb_event_timestamp_invalid")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        raise ClassicRuntimeError("openmatb_event_timestamp_invalid")

    @classmethod
    def _event_utc(cls, event: dict[str, Any]) -> datetime:
        value = cls._event_integer(event, "received_utc_ns")
        try:
            return datetime.fromtimestamp(value / 1_000_000_000, tz=timezone.utc)
        except (OSError, OverflowError, ValueError) as exc:
            raise ClassicRuntimeError("openmatb_event_timestamp_invalid") from exc

    @staticmethod
    def _event_scenario_time(event: dict[str, Any]) -> float | None:
        value = event.get("scenario_time")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        numeric = float(value)
        return numeric if np.isfinite(numeric) else None

    @classmethod
    def _valid_task_start_event(cls, event: dict[str, Any]) -> bool:
        scenario_time = cls._event_scenario_time(event)
        return scenario_time is not None and 0.0 <= scenario_time <= 2.0

    @classmethod
    def _valid_task_boundary_event(cls, event: dict[str, Any]) -> bool:
        scenario_time = cls._event_scenario_time(event)
        return (
            scenario_time is not None
            and MIN_TASK_COMPLETION_SCENARIO_TIME_SECONDS
            <= scenario_time
            <= TASK_DURATION_SECONDS + 2.0
        )

    async def _stop_recorder_after_failure(
        self,
        active: _ActiveClassicSession,
    ) -> PolarSessionResult | None:
        recorder = active.recorder
        journal = active.run_dir / ".capture" / "polar-rr-journal.jsonl"
        if recorder is None:
            try:
                return recover_polar_session_journal(journal)
            except AcquisitionLifecycleError:
                return None
        if active.current_phase is not None:
            try:
                recorder.end_phase(active.current_phase)
            except AcquisitionLifecycleError:
                pass
            active.current_phase = None
        try:
            result = await self.polar.stop_recording()
        except Exception:
            try:
                result = recover_polar_session_journal(journal)
            except AcquisitionLifecycleError:
                result = None
        active.recorder = None
        return result

    def _seal_terminal_bundle(
        self,
        active: _ActiveClassicSession,
        session_id: str,
        *,
        physiology: PolarSessionResult,
        status: str,
        reason: str,
        recovery_from_validated_bundle: bool = False,
    ) -> None:
        capture_dir = active.run_dir / ".capture"
        make_private_directory(capture_dir)
        source_csv = capture_dir / "openmatb-session.csv"
        if not source_csv.exists():
            _publish_private_text(
                source_csv,
                "logtime,scenario_time,type,module,address,value\n",
            )
        events = capture_dir / "openmatb-events.jsonl"
        if not events.exists():
            _publish_private_text(
                events,
                json.dumps(
                    {
                        "schema_version": OPENMATB_EVENT_SCHEMA_VERSION,
                        "session_id": session_id,
                        "sequence": 1,
                        "received_monotonic_ns": str(time.monotonic_ns()),
                        "received_utc_ns": str(time.time_ns()),
                        "event": status.casefold(),
                        "reason_code": reason,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
            )
        metrics = convert_session(
            source_csv,
            participant_id=active.request.participant_id,
            block_name=f"visit_{active.request.visit_ordinal}_{active.request.workload_level.casefold()}",
            workload_level=active.request.workload_level,
            extra_metadata={"classic_session_id": session_id},
        )
        physiology_quality = _overall_physiology_quality(
            physiology,
            overridden=active.request.performance_only_override,
        )
        physiology_availability = _physiology_availability(
            physiology,
            overridden=active.request.performance_only_override,
        )
        context = self.persistence.get_attempt_context(session_id)
        provenance = self._provenance(active)
        hrv_summary = {
            "quality": physiology_quality,
            "availability": physiology_availability,
            "disconnect_count": physiology.disconnect_count,
            "malformed_packet_count": physiology.malformed_packet_count,
            "queue_overflow_count": physiology.queue_overflow_count,
            "contact_loss_detected": physiology.contact_loss_detected,
        }
        session_payload = {
            "session_id": session_id,
            "participant_id": active.request.participant_id,
            "visit_ordinal": active.request.visit_ordinal,
            "workload_level": active.request.workload_level,
            "attempt_number": context.attempt.attempt_number,
            "scenario_name": active.request.scenario_name,
            "scenario_sha256": active.scenario_sha256,
            "openmatb_source_sha256": active.openmatb_source_sha256,
            "test_mode": active.test_mode,
            "wall_time_scale": active.wall_time_scale,
            "post_task_questionnaire_timeout_seconds": (
                POST_TASK_QUESTIONNAIRE_TIMEOUT_SECONDS * active.wall_time_scale
            ),
            "post_task_questionnaire_elapsed_seconds": (
                _post_task_elapsed_seconds(context.attempt)
            ),
            "status": status,
            "task_validity": "invalid",
            "physiology_quality": physiology_quality,
            "physiology_availability": physiology_availability,
            "performance_only_override": active.request.performance_only_override,
            "override_reason_code": active.request.override_reason_code,
            "polar_backend": provenance["polar_backend"],
            "acquisition_mode": (
                "performance_only"
                if active.request.performance_only_override
                else "polar_h10_rr"
            ),
            "provenance": provenance,
            "failure_reason_code": reason,
            "bluetooth_disconnect_count": physiology.disconnect_count,
            "malformed_heart_rate_packet_count": physiology.malformed_packet_count,
            "acquisition_queue_overflow_count": physiology.queue_overflow_count,
            "contact_loss_detected": physiology.contact_loss_detected,
            "hrv_summary": hrv_summary,
        }
        hrv_document = {
            "phases": physiology.phase_results,
            "summary": hrv_summary,
        }
        inventory = build_session_bundle(
            active.run_dir,
            session=session_payload,
            matb_metrics=metrics,
            phase_results=physiology.phase_results,
            rr_records=physiology.rr_records,
            clock_anchors=physiology.clock_anchors,
            openmatb_csv=source_csv,
            synchronized_events=events,
        )
        source_digest = hashlib.sha256(source_csv.read_bytes()).hexdigest()
        self.persistence.terminate_attempt_with_artifacts(
            session_id,
            status=status,
            reason_code=reason[:128],
            task_validity="invalid",
            physiology_quality=physiology_quality,
            source_csv_filename="openmatb-session.csv",
            source_csv_sha256=source_digest,
            metrics=metrics,
            hrv=hrv_document,
            inventory=inventory,
            recovery_from_validated_bundle=recovery_from_validated_bundle,
        )

    def _preserve_terminal_intent(
        self,
        session_id: str,
        *,
        status: str,
        reason: str,
    ) -> None:
        """Commit a published bundle or retain a retryable terminal intent."""

        if status not in {"ABORTED", "INTERRUPTED"}:
            raise ClassicRuntimeError("classic_terminal_intent_invalid")
        try:
            context = self.persistence.get_attempt_context(session_id)
            run_dir = (self.artifact_root / context.attempt.artifact_root).resolve()
            try:
                complete_bundle = (
                    load_complete_bundle(run_dir)
                    if self.artifact_root in run_dir.parents
                    else None
                )
            except Exception:
                # Preserve the intent even if a published marker must later be
                # investigated as an integrity failure during startup.
                complete_bundle = None
            if complete_bundle is not None:
                inventory, document = complete_bundle
                try:
                    self._commit_recovered_bundle(
                        context,
                        run_dir,
                        inventory=inventory,
                        document=document,
                    )
                except Exception:
                    # Keep the database row mutable: the checksum marker is the
                    # durable recovery point for the next startup attempt.
                    pass
                else:
                    return
            context = self.persistence.get_attempt_context(session_id)
            if context.attempt.status in {"COMPLETE", "ABORTED", "INTERRUPTED"}:
                # A legacy bare terminal row remains discoverable by startup
                # reconciliation even though it cannot be made mutable here.
                return
            self.persistence.update_attempt_state(
                session_id,
                status="FINALIZING",
                failure_reason_code=reason[:128],
                terminal_intent_status=status,
                terminal_intent_reason_code=reason[:128],
            )
        except (ClassicPersistenceError, OSError) as exc:
            raise ClassicRuntimeError("classic_terminal_intent_persistence_failed") from exc

    def _seal_after_unscheduled_cancellation(
        self,
        active: _ActiveClassicSession,
        session_id: str,
        *,
        status: str,
        reason: str,
    ) -> None:
        """Seal a cancellation if its task never entered ``_run``."""

        context = self.persistence.get_attempt_context(session_id)
        if context.attempt.status in {"COMPLETE", "ABORTED", "INTERRUPTED"}:
            return
        physiology = _missing_physiology()
        journal = active.run_dir / ".capture" / "polar-rr-journal.jsonl"
        if journal.is_file():
            try:
                physiology = recover_polar_session_journal(journal)
            except AcquisitionLifecycleError:
                pass
        try:
            self._seal_terminal_bundle(
                active,
                session_id,
                physiology=physiology,
                status=status,
                reason=reason,
            )
        except Exception:
            self._preserve_terminal_intent(
                session_id,
                status=status,
                reason=reason,
            )
        if self._active is active:
            self._active = None

    def _require_active(self, session_id: str, lease: str) -> _ActiveClassicSession:
        active = self._active
        if active is None or self._session_id(active) != session_id:
            raise ClassicRuntimeError("classic_session_not_active")
        candidate = hashlib.sha256(lease.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(candidate, active.lease_hash):
            raise ClassicRuntimeError("classic_invalid_lease")
        return active

    @staticmethod
    def _session_id(active: _ActiveClassicSession) -> str:
        return active.run_dir.name

    @staticmethod
    def _view(context: ClassicAttemptContext) -> ClassicSessionView:
        attempt = context.attempt
        return ClassicSessionView(
            id=attempt.id,
            participant_id=context.participant_id,
            visit_id=attempt.visit_id,
            visit_ordinal=context.visit_ordinal,
            workload_level=attempt.workload_level,
            attempt_number=attempt.attempt_number,
            scenario_name=attempt.scenario_name,
            scenario_sha256=attempt.scenario_sha256,
            openmatb_source_sha256=attempt.openmatb_source_sha256,
            test_mode=attempt.test_mode,
            wall_time_scale=attempt.wall_time_scale,
            post_task_timeout_seconds=(
                POST_TASK_QUESTIONNAIRE_TIMEOUT_SECONDS * attempt.wall_time_scale
            ),
            status=attempt.status,
            task_validity=attempt.task_validity,
            physiology_quality=attempt.physiology_quality,
            performance_only_override=attempt.performance_only_override,
            failure_reason_code=attempt.failure_reason_code,
            battery_level_at_start=attempt.battery_level_at_start,
            created_at=attempt.created_at,
            baseline_started_at=attempt.baseline_started_at,
            task_started_at=attempt.task_started_at,
            task_finished_at=attempt.task_finished_at,
            recovery_started_at=attempt.recovery_started_at,
            recovery_finished_at=attempt.recovery_finished_at,
            finished_at=attempt.finished_at,
        )


__all__ = [
    "BASELINE_DURATION_SECONDS",
    "ClassicManager",
    "ClassicRuntimeError",
    "RECOVERY_DURATION_SECONDS",
    "TASK_DURATION_SECONDS",
]
