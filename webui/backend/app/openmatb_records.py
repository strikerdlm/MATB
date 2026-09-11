"""Durable native block receipts and immutable evidence registration.

The manager schedules processing only after suite termination. This module does
no task control, does not change the original files, and never merges browser
ratings into the native event stream.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from app.artifact_paths import resolve_artifact
from pathlib import Path
from uuid import uuid4

from sqlmodel import Session, select

from app.openmatb_models import OpenMatbBlockAttempt, OpenMatbSuiteSession

TERMINAL = {"COMPLETE", "ABORTED", "FAILED", "INTERRUPTED"}


class OpenMatbRecords:
    def __init__(self, engine, artifact_root: Path):
        self.engine = engine
        self.artifact_root = artifact_root.resolve()

    def begin(self, db: Session, suite: OpenMatbSuiteSession, profile: str, *, block_instance_id: str | None = None) -> OpenMatbBlockAttempt:
        attempt = OpenMatbBlockAttempt(id=block_instance_id or str(uuid4()), session_id=suite.id,
            block_index=suite.current_block_index, profile=profile,
            legacy_import_status="not_required" if profile == "PRACTICE" or suite.execution_purpose == "practice" else "pending")
        suite.active_block_instance_id = attempt.id
        suite.active_session_csv = None
        db.add(attempt)
        db.add(suite)
        db.flush()
        from app.assessment_adapters import attach_source
        from app.study_native import bind_block
        if not bind_block(db, suite, attempt):
            attach_source(db, "openmatb_block_attempt", attempt.model_dump(mode="json"), historical=False)
        return attempt

    def finish(self, db: Session, suite: OpenMatbSuiteSession, *, outcome: str, csv: Path | None, cause: str = "unknown") -> None:
        attempt = db.get(OpenMatbBlockAttempt, suite.active_block_instance_id) if suite.active_block_instance_id else None
        if attempt is None:
            return
        attempt.task_status = outcome
        attempt.finished_at = datetime.now(timezone.utc)
        attempt.session_csv = str(csv) if csv else None
        attempt.evidence_status = "queued"
        if csv is None or not csv.is_file():
            attempt.artifact_status = "missing"
            attempt.artifact_error = "native_artifacts_missing"
            attempt.evidence_status = "unavailable"
        else:
            # Existence is enough to report local files; integrity is reported
            # separately by registration, after acquisition has stopped.
            try:
                self._controlled_csv(suite, attempt)
                complete = all(path.is_file() for path in self._paths(csv).values())
                attempt.artifact_status = "saved" if complete else "partial"
                attempt.artifact_error = None if complete else "native_artifacts_incomplete"
                if not complete:
                    attempt.evidence_status = "unavailable"
            except ValueError:
                attempt.artifact_status = "invalid"
                attempt.artifact_error = "native_artifacts_outside_session"
                attempt.evidence_status = "unavailable"
        from app.study_native import finish_block
        finish_block(db, attempt, outcome, cause=cause)
        db.add(attempt)

    def recover(self) -> None:
        with Session(self.engine) as db:
            for attempt in db.exec(select(OpenMatbBlockAttempt)):
                if attempt.task_status in {"starting", "running"}:
                    attempt.task_status = "interrupted"
                    attempt.finished_at = attempt.finished_at or datetime.now(timezone.utc)
                    attempt.evidence_status = "queued" if attempt.session_csv else "unavailable"
                    attempt.artifact_status = "unknown"
                    from app.study_native import finish_block
                    finish_block(db, attempt, "interrupted")
                if attempt.evidence_status == "processing":
                    attempt.evidence_status = "failed"
                    attempt.evidence_error = "interrupted_processing"
                db.add(attempt)
            db.commit()

    def _controlled_csv(self, suite: OpenMatbSuiteSession, attempt: OpenMatbBlockAttempt) -> Path:
        with Session(self.engine) as db:
            from app.study_native import storage_key
            instance_key = storage_key(db, suite, attempt.profile)
        root = (self.artifact_root / suite.id / "sessions" / instance_key).resolve()
        if self.artifact_root not in root.parents:
            raise ValueError("native_artifacts_outside_session")
        csv = resolve_artifact(attempt.session_csv or "").resolve()
        if root not in csv.parents or not csv.is_file():
            raise ValueError("native_artifacts_outside_session")
        return csv

    @staticmethod
    def _paths(csv: Path) -> dict[str, Path]:
        return {"capture_manifest": csv.with_suffix(".capture.manifest.json"),
                 "scenario_manifest": csv.with_suffix(".scenario.manifest.json"),
                 "events": csv.with_suffix(".scientific.events.jsonl"),
                 "timing": csv.with_suffix(".timing.observations.jsonl"), "legacy_csv": csv}

    def _artifacts(self, suite: OpenMatbSuiteSession, attempt: OpenMatbBlockAttempt) -> dict[str, bytes]:
        from matb_integration.evidence.contracts import CaptureManifestV1, MAX_STREAM_BYTES, strict_json
        csv = self._controlled_csv(suite, attempt)
        artifacts = {}
        for role, path in self._paths(csv).items():
            if path.resolve().parent != csv.parent:
                raise ValueError("native_artifacts_outside_session")
            limit = 2 * 1024 * 1024 if "manifest" in role else 64 * 1024 * 1024 if role == "legacy_csv" else MAX_STREAM_BYTES
            with path.open("rb") as source:
                content = source.read(limit + 1)
            if len(content) > limit:
                raise ValueError("evidence_artifact_too_large")
            artifacts[role] = content
        manifest = CaptureManifestV1.model_validate(strict_json(artifacts["capture_manifest"]))
        purpose = "practice" if attempt.profile == "PRACTICE" else suite.execution_purpose
        if (manifest.parent_session_id != suite.id or manifest.block_instance_id != attempt.id
                or manifest.participant_id != suite.participant_id or manifest.visit_ordinal != suite.visit_ordinal
                or manifest.condition != attempt.profile or manifest.execution_purpose != purpose):
            raise ValueError("evidence_session_identity_mismatch")
        return artifacts

    def pending(self) -> list[str]:
        with Session(self.engine) as db:
            return list(db.exec(select(OpenMatbBlockAttempt.id).join(OpenMatbSuiteSession)
                .where(OpenMatbSuiteSession.lifecycle.in_(TERMINAL), OpenMatbBlockAttempt.evidence_status == "queued")
                .order_by(OpenMatbBlockAttempt.started_at, OpenMatbBlockAttempt.id)))

    def process(self, attempt_id: str) -> None:
        from app.evidence_service import ingest_evidence, capture_summary, run_derivation
        with Session(self.engine) as db:
            attempt = db.get(OpenMatbBlockAttempt, attempt_id)
            if attempt is None or attempt.evidence_status != "queued":
                return
            suite = db.get(OpenMatbSuiteSession, attempt.session_id)
            if suite is None or suite.lifecycle not in TERMINAL:
                return
            attempt.evidence_status = "processing"
            attempt.evidence_error = None
            db.add(attempt)
            db.commit()
            try:
                artifacts = self._artifacts(suite, attempt)
                capture_id, created = ingest_evidence(db, artifacts)
                summary = capture_summary(db, capture_id)
                if not created and summary["capture_status"] == "processing_failed":
                    run_derivation(db, capture_id)
                    summary = capture_summary(db, capture_id)
                attempt = db.get(OpenMatbBlockAttempt, attempt_id)
                attempt.capture_id = capture_id
                attempt.artifact_status = "saved"
                attempt.artifact_error = None
                attempt.evidence_status = "failed" if summary["capture_status"] == "processing_failed" else "processed"
                attempt.evidence_error = "evidence_processing_failed" if attempt.evidence_status == "failed" else None
            except Exception as exc:
                db.rollback()
                attempt = db.get(OpenMatbBlockAttempt, attempt_id)
                attempt.evidence_status = "failed"
                # Keep paths, exception details and credentials out of notices.
                known = {"evidence_session_identity_mismatch", "native_artifacts_outside_session", "evidence_artifact_too_large", "capture_identity_conflict"}
                attempt.evidence_error = str(exc) if str(exc) in known else "evidence_registration_failed"
            db.add(attempt)
            db.commit()

    def receipt(self, db: Session, suite: OpenMatbSuiteSession) -> dict:
        from app.evidence_models import EvidenceCapture
        from app.evidence_discovery import review_summary
        from app.assessment_adapters import source_identity
        rows = list(db.exec(select(OpenMatbBlockAttempt).where(OpenMatbBlockAttempt.session_id == suite.id)
                            .order_by(OpenMatbBlockAttempt.started_at, OpenMatbBlockAttempt.id)))
        attempts = []
        for attempt in rows:
            capture = db.get(EvidenceCapture, attempt.capture_id) if attempt.capture_id else None
            summary = review_summary(db, capture.id) if capture else None
            attempts.append({**source_identity(db, "openmatb_block_attempt", attempt.id),
                "rating_attempt_id": source_identity(db, "openmatb_block_attempt", attempt.id, "ratings")["assessment_attempt_id"],
                "block_instance_id": attempt.id, "block_index": attempt.block_index,
                "profile": attempt.profile, "task_status": attempt.task_status,
                "execution_purpose": "practice" if attempt.profile == "PRACTICE" else suite.execution_purpose,
                "started_at": attempt.started_at, "finished_at": attempt.finished_at,
                "artifact_status": attempt.artifact_status, "artifact_error": attempt.artifact_error,
                "ratings_status": "not_required" if attempt.profile == "PRACTICE" else "saved" if attempt.ratings_json else "pending",
                "ratings_saved_at": attempt.ratings_saved_at,
                "legacy_import_status": attempt.legacy_import_status, "legacy_import_error": attempt.legacy_import_error,
                "evidence_status": attempt.evidence_status, "evidence_error": attempt.evidence_error,
                "capture_id": attempt.capture_id, "capture_status": summary["capture_status"] if summary else None,
                "qualification": summary["qualification"] if summary else None})
        return {**source_identity(db, "openmatb_suite_session", suite.id), "session_id": suite.id, "participant_id": suite.participant_id,
                "visit_ordinal": suite.visit_ordinal, "execution_purpose": suite.execution_purpose,
                "lifecycle": suite.lifecycle, "historical": suite.receipt_version == 0,
                "block_order": json.loads(suite.block_order_json), "attempts": attempts}
