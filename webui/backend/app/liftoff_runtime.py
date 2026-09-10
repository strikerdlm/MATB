"""Guarded process-local runtime for Liftoff collection sessions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import os
from typing import Any
from uuid import uuid4

from app.liftoff_models import LiftoffSession
from app.liftoff_persistence import SQLModelLiftoffPersistence
from app.liftoff_schemas import (
    CreateLiftoffSession,
    LiftoffAction,
    LiftoffArtifactView,
    LiftoffDebriefView,
    LiftoffReadinessView,
    LiftoffSessionView,
    PhysiologyLinkRequest,
    PhysiologyLinkView,
    PreparedLiftoffSession,
    QuestionnairesRequest,
    VisibleResultsRequest,
)
from app.study_protocol import selected_protocol
from app.hrv_task_client import (
    HRV_COMMIT,
    HRV_SCHEMA_SHA256,
    HrvTaskContractError,
    HrvTaskTemporaryError,
    PolarRecordingMetadataRequest,
    TaskSessionHrvRequest,
    TaskSessionHrvResponse,
    UtcSegment,
)
from matb_integration.recording.artifacts import write_json_artifact
from matb_integration.liftoff.metrics import VisibleResults
from matb_integration.liftoff.protocol import LIFTOFF_ALL_V1
from matb_integration.liftoff.session import LiftoffSessionRecorder, SessionLifecycleError

_ACTION_MARKER: dict[LiftoffAction, str] = {
    "baseline/start": "baseline_started",
    "baseline/finish": "baseline_finished",
    "task/start": "task_started",
    "task/finish": "task_finished",
    "recovery/start": "recovery_started",
    "recovery/finish": "recovery_finished",
}
_ACTION_STATUS: dict[LiftoffAction, str] = {
    "baseline/start": "BASELINE",
    "baseline/finish": "BASELINE",
    "task/start": "TASK",
    "task/finish": "TASK",
    "recovery/start": "RECOVERY",
    "recovery/finish": "FINISHED",
}


class LiftoffRuntimeError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(slots=True)
class _ActiveLiftoffSession:
    recorder: LiftoffSessionRecorder
    lease_hash: str


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def build_session_manifest(
    *,
    request: CreateLiftoffSession,
    session_id: str,
    configuration_sha256: str,
    assignment_context: dict | None = None,
) -> dict[str, object]:
    protocol = selected_protocol()
    if assignment_context:
        from types import SimpleNamespace
        visit = SimpleNamespace(**assignment_context['assigned_visit'])
    else:
        try:
            visit = next(item for item in protocol.visits if item.ordinal == request.visit_ordinal)
        except StopIteration as exc:
            raise LiftoffRuntimeError("liftoff_visit_not_in_protocol") from exc
    configuration = request.configuration.model_dump(mode="json")
    return {
        "schema_version": "liftoff-session-manifest-v1",
        "execution_purpose": request.execution_purpose,
        "locale": request.locale,
        "session_id": session_id,
        "participant_id": request.participant_id,
        "visit_ordinal": visit.ordinal,
        "visit_code": visit.code,
        "scheduled_day": visit.scheduled_day,
        "attempt_number": 0,
        "protocol_id": assignment_context["study_id"] if assignment_context else protocol.protocol_id,
        "protocol_version": assignment_context["version_id"] if assignment_context else protocol.protocol_version,
        "schedule_sha256": assignment_context["schedule_sha256"] if assignment_context else protocol.schedule_sha256,
        **({"assignment_id": assignment_context["assignment_id"], "study_version_id": assignment_context["version_id"]} if assignment_context else {}),
        "liftoff_build": request.configuration.liftoff_build,
        "track_id": request.configuration.track_id,
        "telemetry_profile": request.configuration.telemetry_profile,
        "expected_rate_hz": 60.0,
        "configuration_sha256": configuration_sha256,
        "configuration": configuration,
        "polar_recording_confirmed": request.polar_recording_confirmed,
        "performance_only_reason": request.performance_only_reason,
        "coordinate_units_validated": False,
    }


class LiftoffManager:
    def __init__(
        self,
        *,
        artifact_root: Path,
        receiver: Any,
        persistence: SQLModelLiftoffPersistence,
        hrv_client: Any | None = None,
    ) -> None:
        self.artifact_root = Path(artifact_root).resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.receiver = receiver
        self.persistence = persistence
        self.hrv_client = hrv_client
        self._active: dict[str, _ActiveLiftoffSession] = {}
        self._capture_task: asyncio.Task[None] | None = None

    def start_capture(self) -> None:
        if self._capture_task is None and hasattr(self.receiver, "next_packet"):
            self._capture_task = asyncio.create_task(self._capture_loop())

    async def _capture_loop(self) -> None:
        while True:
            received = await self.receiver.next_packet()
            if len(self._active) != 1:
                continue
            active = next(iter(self._active.values()))
            try:
                active.recorder.append_packet(
                    received.payload,
                    received_monotonic_ns=received.received_monotonic_ns,
                    received_utc=received.received_utc,
                )
            except SessionLifecycleError:
                continue

    async def create_session(self, request: CreateLiftoffSession) -> PreparedLiftoffSession:
        if self._active:
            raise LiftoffRuntimeError("liftoff_active_session")
        try:
            visit = self.persistence.require_visit(request.participant_id, request.visit_ordinal)
            assignment_context = self.persistence.admit_request(request, visit)
            if request.execution_purpose == "study":
                self.persistence.require_study_order(request.participant_id, visit.id, attempt_id=request.attempt_id)
        except KeyError as exc:
            raise LiftoffRuntimeError(str(exc.args[0])) from exc
        except ValueError as exc:
            raise LiftoffRuntimeError(str(exc)) from exc
        protocol = selected_protocol()
        if request.execution_purpose != "study" and not any(item.ordinal == request.visit_ordinal for item in protocol.visits):
            raise LiftoffRuntimeError("liftoff_visit_not_in_protocol")
        if not await self.receiver.wait_ready(min_valid=20, timeout_seconds=2.0):
            raise LiftoffRuntimeError("liftoff_telemetry_not_ready")

        session_id = str(uuid4())
        lease = secrets.token_urlsafe(32)
        lease_hash = hashlib.sha256(lease.encode("utf-8")).hexdigest()
        configuration_json = _canonical_json(request.configuration.model_dump(mode="json"))
        configuration_sha256 = hashlib.sha256(configuration_json.encode("utf-8")).hexdigest()
        run_dir = (self.artifact_root / session_id).resolve()
        if self.artifact_root not in run_dir.parents:
            raise LiftoffRuntimeError("liftoff_artifact_path")
        attempt_number = self.persistence.next_attempt_number(request.participant_id, visit.id)
        manifest = build_session_manifest(
            request=request,
            session_id=session_id,
            configuration_sha256=configuration_sha256,
            assignment_context=assignment_context,
        )
        manifest["attempt_number"] = attempt_number
        recorder = LiftoffSessionRecorder.prepare(run_dir, manifest=manifest)
        recorder.mark("recording_started", source="system")
        row = LiftoffSession(
            execution_purpose=request.execution_purpose,
            id=session_id,
            participant_id=request.participant_id,
            visit_id=visit.id,
            attempt_number=attempt_number,
            protocol_id=str(manifest["protocol_id"]),
            protocol_version=str(manifest["protocol_version"]),
            liftoff_build=request.configuration.liftoff_build,
            configuration_sha256=configuration_sha256,
            track_id=request.configuration.track_id,
            telemetry_profile=request.configuration.telemetry_profile,
            manifest_json=_canonical_json(manifest),
            status="PREPARED",
            validity="pending_review",
            artifact_root=str(run_dir),
            controller_lease_hash=lease_hash,
        )
        row = self.persistence.insert_session(row, attempt_id=request.attempt_id)
        self._active[session_id] = _ActiveLiftoffSession(
            recorder=recorder,
            lease_hash=lease_hash,
        )
        return PreparedLiftoffSession(
            **self._session_view(row).model_dump(),
            controller_lease=lease,
        )

    def session_view(self, session_id: str) -> LiftoffSessionView:
        row = self.persistence.load_session(session_id)
        if row is None:
            raise LiftoffRuntimeError("liftoff_session_not_found")
        return self._session_view(row)

    def _session_view(self, row: LiftoffSession) -> LiftoffSessionView:
        try:
            manifest = json.loads(row.manifest_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            manifest = {}
        visit_ordinal = int(manifest.get("visit_ordinal", 0))
        return LiftoffSessionView(
            execution_purpose=row.execution_purpose,
            purpose_provenance_id=row.purpose_provenance_id,
            locale=manifest.get("locale", "es-419"),
            id=row.id,
            participant_id=row.participant_id,
            visit_id=row.visit_id,
            visit_ordinal=visit_ordinal,
            visit_code=str(manifest.get("visit_code", "")),
            attempt_number=row.attempt_number,
            protocol_id=row.protocol_id,
            protocol_version=row.protocol_version,
            liftoff_build=row.liftoff_build,
            track_id=row.track_id,
            telemetry_profile=row.telemetry_profile,
            status=row.status,
            validity=row.validity,
            sync_quality=row.sync_quality,
            polar_recording_confirmed=bool(manifest.get("polar_recording_confirmed", False)),
            created_at=row.created_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            interrupted_at=row.interrupted_at,
        )

    async def transition(
        self,
        session_id: str,
        action: LiftoffAction,
        lease: str,
    ) -> LiftoffSessionView:
        active = self._require_controller(session_id, lease)
        self.persistence.guard_acquisition(session_id)
        if action == "task/start" and not await self.receiver.wait_ready(
            min_valid=20,
            timeout_seconds=2.0,
        ):
            raise LiftoffRuntimeError("liftoff_telemetry_not_ready")
        try:
            active.recorder.mark(_ACTION_MARKER[action])
            if action == "recovery/finish":
                active.recorder.mark("recording_finished", source="system")
        except SessionLifecycleError as exc:
            raise LiftoffRuntimeError("liftoff_phase_order") from exc
        fields: dict[str, object] = {"status": _ACTION_STATUS[action]}
        now = datetime.now(timezone.utc)
        if action == "baseline/start":
            fields["started_at"] = now
        if action == "recovery/finish":
            fields["finished_at"] = now
        self.persistence.update_session(session_id, **fields)
        return self.session_view(session_id)

    def submit_results(
        self,
        session_id: str,
        lease: str,
        request: VisibleResultsRequest,
        screenshot: bytes,
    ) -> None:
        active = self._require_controller(session_id, lease)
        if self.session_view(session_id).status != "FINISHED":
            raise LiftoffRuntimeError("liftoff_phase_order")
        visible = VisibleResults(
            valid_lap_times_s=tuple(request.valid_lap_times_s),
            invalid_laps=request.invalid_laps,
            observer_restart_count=request.observer_restart_count,
        )
        active.recorder.attach_results(visible, screenshot=screenshot)
        self.persistence.save_result(
            session_id,
            valid_lap_times_s=request.valid_lap_times_s,
            invalid_laps=request.invalid_laps,
            observer_restart_count=request.observer_restart_count,
            screenshot_sha256=request.screenshot_sha256,
            provenance={"source": "visible_result_screen"},
        )

    def submit_questionnaires(
        self,
        session_id: str,
        lease: str,
        request: QuestionnairesRequest,
    ) -> None:
        active = self._require_controller(session_id, lease)
        if self.session_view(session_id).status != "FINISHED":
            raise LiftoffRuntimeError("liftoff_phase_order")
        active.recorder.attach_questionnaires(request.model_dump(mode="json"))

    def attach_physiology(
        self,
        session_id: str,
        lease: str,
        request: PhysiologyLinkRequest,
    ) -> None:
        active = self._require_controller(session_id, lease)
        active.recorder.attach_physiology_link(request.model_dump(mode="json"))
        self.persistence.update_session(
            session_id,
            hrv_measurement_id=request.hrv_measurement_id,
            hrv_file_sha256=request.hrv_file_sha256,
            sync_quality=request.sync_quality,
        )

    async def analyze_physiology(
        self,
        session_id: str,
        lease: str,
        *,
        rr_content: str,
        metadata: dict[str, object],
    ) -> PhysiologyLinkView:
        active = self._require_controller(session_id, lease)
        row = self.persistence.load_session(session_id)
        if row is None:
            raise LiftoffRuntimeError("liftoff_session_not_found")
        try:
            timing = PolarRecordingMetadataRequest.model_validate(metadata)
        except ValueError as exc:
            raise LiftoffRuntimeError("liftoff_hrv_metadata_invalid") from exc
        rr_hash = hashlib.sha256(rr_content.encode("utf-8")).hexdigest()
        if (
            str(timing.external_session_id) != session_id
            or timing.participant_id != row.participant_id
            or timing.rr_file_sha256 != rr_hash
        ):
            raise LiftoffRuntimeError("liftoff_hrv_identity_mismatch")
        request = TaskSessionHrvRequest(
            external_session_id=timing.external_session_id,
            participant_id=row.participant_id,
            rr_filename="polar.txt",
            rr_content=rr_content,
            rr_file_sha256=rr_hash,
            timing=timing,
            segments=self._hrv_segments(active.recorder),
        )
        return await self._submit_hrv_request(session_id, active, request)

    async def retry_physiology(self, session_id: str, lease: str) -> PhysiologyLinkView:
        active = self._require_controller(session_id, lease)
        pending_path = active.recorder.run_dir / "pending-hrv-request.json"
        if not pending_path.is_file():
            raise LiftoffRuntimeError("liftoff_hrv_pending_not_found")
        try:
            request = TaskSessionHrvRequest.model_validate_json(
                pending_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise LiftoffRuntimeError("liftoff_hrv_pending_invalid") from exc
        return await self._submit_hrv_request(session_id, active, request)

    @staticmethod
    def _hrv_segments(recorder: LiftoffSessionRecorder) -> list[UtcSegment]:
        marker_path = recorder.run_dir / "markers.jsonl"
        try:
            markers = [json.loads(line) for line in marker_path.read_text(encoding="utf-8").splitlines() if line]
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise LiftoffRuntimeError("liftoff_markers_invalid") from exc
        by_kind = {str(marker.get("kind")): marker for marker in markers}
        pairs = (
            ("baseline", "baseline_started", "baseline_finished"),
            ("task", "task_started", "task_finished"),
            ("recovery", "recovery_started", "recovery_finished"),
        )
        try:
            return [
                UtcSegment(
                    label=label,
                    start_utc=by_kind[start_kind]["received_utc"],
                    end_utc=by_kind[end_kind]["received_utc"],
                )
                for label, start_kind, end_kind in pairs
            ]
        except (KeyError, ValueError) as exc:
            raise LiftoffRuntimeError("liftoff_phase_markers_incomplete") from exc

    async def _submit_hrv_request(
        self,
        session_id: str,
        active: _ActiveLiftoffSession,
        request: TaskSessionHrvRequest,
    ) -> PhysiologyLinkView:
        pending_path = active.recorder.run_dir / "pending-hrv-request.json"
        try:
            if self.hrv_client is None:
                raise HrvTaskTemporaryError("hrv_unavailable")
            response: TaskSessionHrvResponse = await self.hrv_client.analyze(request)
        except HrvTaskTemporaryError:
            write_json_artifact(pending_path, request.model_dump(mode="json"))
            os.chmod(pending_path, 0o600)
            return PhysiologyLinkView(status="pending", sync_quality="missing")
        except HrvTaskContractError as exc:
            raise LiftoffRuntimeError("liftoff_hrv_contract_rejected") from exc
        if (
            str(response.external_session_id) != session_id
            or response.participant_id != request.participant_id
            or response.rr_file_sha256 != request.rr_file_sha256
        ):
            raise LiftoffRuntimeError("liftoff_hrv_response_mismatch")
        sync_quality = self._grade_sync(response, request)
        link = {
            "status": "linked",
            "contract_version": response.contract_version,
            "contract_schema_sha256": HRV_SCHEMA_SHA256,
            "hrv_commit": HRV_COMMIT,
            "external_session_id": session_id,
            "hrv_measurement_id": response.measurement_id,
            "hrv_file_sha256": response.rr_file_sha256,
            "sync_quality": sync_quality,
            "quality": response.quality.model_dump(mode="json"),
            "segment_indices": [item.model_dump(mode="json") for item in response.segment_indices],
            "phase_metrics": {
                key: value.model_dump(mode="json")
                for key, value in response.phase_metrics.items()
            },
            "delta_lnrmssd_baseline_task": response.delta_lnrmssd_baseline_task,
            "delta_lnrmssd_task_recovery": response.delta_lnrmssd_task_recovery,
        }
        active.recorder.attach_physiology_link(link)
        self.persistence.update_session(
            session_id,
            hrv_measurement_id=response.measurement_id,
            hrv_file_sha256=response.rr_file_sha256,
            sync_quality=sync_quality,
        )
        if pending_path.exists():
            pending_path.unlink()
        return PhysiologyLinkView(
            status="linked",
            hrv_measurement_id=response.measurement_id,
            hrv_file_sha256=response.rr_file_sha256,
            sync_quality=sync_quality,
        )

    def _grade_sync(
        self,
        response: TaskSessionHrvResponse,
        request: TaskSessionHrvRequest,
    ) -> str:
        health = self.receiver.health()
        denominator = max(1, health.valid_packets + health.overflow_count)
        loss_pct = 100.0 * health.overflow_count / denominator
        common_monotonic = (
            request.timing.first_rr_received_monotonic_ns is not None
            and request.timing.last_rr_received_monotonic_ns is not None
        )
        uncertainty_ms = 0.0 if common_monotonic else 1_001.0
        if (
            uncertainty_ms <= 100.0
            and loss_pct < 1.0
            and not health.clock_step_detected
            and response.quality.status == "good"
        ):
            return "good"
        if (
            uncertainty_ms <= 1_000.0
            and loss_pct < 5.0
            and not health.clock_step_detected
            and response.quality.status != "poor"
        ):
            return "acceptable"
        return "poor"

    def seal(self, session_id: str, lease: str) -> LiftoffDebriefView:
        active = self._require_controller(session_id, lease)
        active.recorder.update_receiver_health(self.receiver.health())
        try:
            inventory = active.recorder.seal()
        except SessionLifecycleError as exc:
            code = str(exc)
            if code in {"visible_results_required", "questionnaires_required", "session_not_finished"}:
                raise LiftoffRuntimeError(f"liftoff_{code}") from exc
            raise LiftoffRuntimeError("liftoff_seal_failed") from exc
        quality = json.loads((active.recorder.run_dir / "telemetry-quality.json").read_text(encoding="utf-8"))
        metrics_text = (active.recorder.run_dir / "metrics.json").read_text(encoding="utf-8")
        physiology = json.loads((active.recorder.run_dir / "physiology-link.json").read_text(encoding="utf-8"))
        self.persistence.update_session(
            session_id,
            status="FINISHED",
            validity=quality["validity"],
            sync_quality=str(physiology.get("sync_quality", "missing")),
            metrics_json=metrics_text,
            finished_at=datetime.now(timezone.utc),
        )
        self.persistence.replace_artifacts(session_id, inventory)
        self._active.pop(session_id, None)
        return self.debrief_view(session_id)

    def abort(self, session_id: str, lease: str, reason_code: str) -> LiftoffSessionView:
        active = self._require_controller(session_id, lease)
        inventory = active.recorder.seal_partial(reason_code)
        self.persistence.update_session(
            session_id,
            status="ABORTED",
            validity="invalid",
            finished_at=datetime.now(timezone.utc),
        )
        self.persistence.add_deviation(
            session_id,
            phase="session",
            code=reason_code,
            severity="error",
        )
        self.persistence.replace_artifacts(session_id, inventory)
        self._active.pop(session_id, None)
        return self.session_view(session_id)

    def readiness_view(self) -> LiftoffReadinessView:
        health = self.receiver.health()
        return LiftoffReadinessView(
            ready=health.valid_packets >= 20,
            valid_packets=health.valid_packets,
            invalid_packet_count=health.invalid_packet_count,
            overflow_count=health.overflow_count,
            duplicate_time_count=health.duplicate_time_count,
            out_of_order_count=health.out_of_order_count,
            clock_step_detected=health.clock_step_detected,
        )

    def debrief_view(self, session_id: str) -> LiftoffDebriefView:
        row = self.persistence.load_session(session_id)
        if row is None:
            raise LiftoffRuntimeError("liftoff_session_not_found")
        root = Path(row.artifact_root)
        quality_path = root / "telemetry-quality.json"
        metrics_path = root / "metrics.json"
        if not quality_path.is_file() or not metrics_path.is_file():
            raise LiftoffRuntimeError("liftoff_debrief_unavailable")
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        return LiftoffDebriefView(
            id=row.id,
            status=row.status,
            validity=row.validity,
            sync_quality=row.sync_quality,
            quality=quality,
            primary=metrics["primary"],
        )

    def artifact_views(self, session_id: str) -> list[LiftoffArtifactView]:
        if self.persistence.load_session(session_id) is None:
            raise LiftoffRuntimeError("liftoff_session_not_found")
        return [
            LiftoffArtifactView(
                kind=row.kind,
                relative_path=row.relative_path,
                sha256=row.sha256,
                size_bytes=row.size_bytes,
                created_at=row.created_at,
            )
            for row in self.persistence.list_artifacts(session_id)
        ]

    def bundle_files(self, session_id: str) -> tuple[Path, tuple[LiftoffArtifactView, ...]]:
        row = self.persistence.load_session(session_id)
        if row is None:
            raise LiftoffRuntimeError("liftoff_session_not_found")
        artifacts = tuple(self.artifact_views(session_id))
        if not artifacts:
            raise LiftoffRuntimeError("liftoff_bundle_unavailable")
        return Path(row.artifact_root), artifacts

    def _require_controller(self, session_id: str, lease: str) -> _ActiveLiftoffSession:
        active = self._active.get(session_id)
        if active is None:
            raise LiftoffRuntimeError("liftoff_session_not_active")
        if not isinstance(lease, str):
            raise LiftoffRuntimeError("liftoff_invalid_lease")
        observed = hashlib.sha256(lease.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(observed, active.lease_hash):
            raise LiftoffRuntimeError("liftoff_invalid_lease")
        return active

    async def shutdown(self) -> None:
        if self._capture_task is not None:
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass
            self._capture_task = None
        for session_id, active in list(self._active.items()):
            try:
                inventory = active.recorder.seal_partial("backend_shutdown")
                self.persistence.replace_artifacts(session_id, inventory)
                self.persistence.update_session(
                    session_id,
                    status="INTERRUPTED",
                    interrupted_at=datetime.now(timezone.utc),
                )
            except Exception:
                pass
            self._active.pop(session_id, None)


__all__ = ["LiftoffManager", "LiftoffRuntimeError", "build_session_manifest"]
