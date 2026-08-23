"""Transactional persistence for immutable classic OpenMATB attempts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.classic_models import (
    ClassicSessionArtifact,
    ClassicSessionAttempt,
    ClassicSessionSelection,
    ClassicSessionSelectionAudit,
)
from app.ingestion import WORKLOAD_LEVELS
from app.models import Block, BlockProvenance, DepdfFit, Visit


class ClassicPersistenceError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ClassicAttemptContext:
    attempt: ClassicSessionAttempt
    participant_id: str
    visit_ordinal: int


class SQLModelClassicPersistence:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create_attempt(
        self,
        *,
        participant_id: str,
        visit_ordinal: int,
        workload_level: str,
        scenario_name: str,
        scenario_sha256: str | None = None,
        openmatb_source_sha256: str | None = None,
        test_mode: bool = False,
        wall_time_scale: float = 1.0,
        artifact_root: str,
        session_id: str | None = None,
        controller_lease_hash: str | None = None,
        performance_only_override: bool = False,
        override_reason_code: str | None = None,
    ) -> ClassicSessionAttempt:
        level = workload_level.upper()
        if level not in WORKLOAD_LEVELS:
            raise ClassicPersistenceError("invalid_workload_level")
        if scenario_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", scenario_sha256):
            raise ClassicPersistenceError("invalid_scenario_sha256")
        if openmatb_source_sha256 is not None and not re.fullmatch(
            r"[0-9a-f]{64}", openmatb_source_sha256
        ):
            raise ClassicPersistenceError("invalid_openmatb_source_sha256")
        if (
            isinstance(wall_time_scale, bool)
            or not isinstance(wall_time_scale, (int, float))
            or not math.isfinite(float(wall_time_scale))
            or not 0.001 <= float(wall_time_scale) <= 1.0
            or (not test_mode and float(wall_time_scale) != 1.0)
        ):
            raise ClassicPersistenceError("invalid_wall_time_scale")
        root = Path(artifact_root)
        if root.is_absolute() or ".." in root.parts or not root.parts:
            raise ClassicPersistenceError("invalid_artifact_root")
        with Session(self.engine) as db:
            visit = db.exec(
                select(Visit).where(
                    Visit.participant_id == participant_id,
                    Visit.visit_ordinal == visit_ordinal,
                )
            ).first()
            if visit is None or visit.id is None:
                raise ClassicPersistenceError("visit_not_found")
            existing = db.exec(
                select(ClassicSessionAttempt).where(
                    ClassicSessionAttempt.visit_id == visit.id,
                    ClassicSessionAttempt.workload_level == level,
                )
            ).all()
            attempt = ClassicSessionAttempt(
                id=session_id or str(uuid4()),
                visit_id=visit.id,
                workload_level=level,
                attempt_number=max((row.attempt_number for row in existing), default=0) + 1,
                scenario_name=scenario_name,
                scenario_sha256=scenario_sha256,
                openmatb_source_sha256=openmatb_source_sha256,
                test_mode=bool(test_mode),
                wall_time_scale=float(wall_time_scale),
                artifact_root=root.as_posix(),
                controller_lease_hash=controller_lease_hash,
                performance_only_override=performance_only_override,
                override_reason_code=override_reason_code,
            )
            db.add(attempt)
            db.commit()
            db.refresh(attempt)
            return attempt

    def get_attempt(self, session_id: str) -> ClassicSessionAttempt:
        with Session(self.engine) as db:
            attempt = db.get(ClassicSessionAttempt, session_id)
            if attempt is None:
                raise ClassicPersistenceError("session_not_found")
            db.expunge(attempt)
            return attempt

    def get_attempt_context(self, session_id: str) -> ClassicAttemptContext:
        with Session(self.engine) as db:
            attempt = db.get(ClassicSessionAttempt, session_id)
            if attempt is None:
                raise ClassicPersistenceError("session_not_found")
            visit = db.get(Visit, attempt.visit_id)
            if visit is None:
                raise ClassicPersistenceError("visit_not_found")
            context = ClassicAttemptContext(
                attempt=attempt,
                participant_id=visit.participant_id,
                visit_ordinal=visit.visit_ordinal,
            )
            db.expunge(attempt)
            return context

    def update_attempt_state(self, session_id: str, **fields: Any) -> ClassicSessionAttempt:
        allowed = {
            "status",
            "battery_level_at_start",
            "baseline_started_at",
            "task_started_at",
            "task_finished_at",
            "recovery_started_at",
            "recovery_finished_at",
            "failure_reason_code",
            "terminal_intent_status",
            "terminal_intent_reason_code",
        }
        if not fields or set(fields) - allowed:
            raise ClassicPersistenceError("invalid_attempt_update")
        with Session(self.engine) as db:
            attempt = db.get(ClassicSessionAttempt, session_id)
            if attempt is None:
                raise ClassicPersistenceError("session_not_found")
            if attempt.status in {"COMPLETE", "ABORTED", "INTERRUPTED"}:
                raise ClassicPersistenceError("session_immutable")
            for name, value in fields.items():
                setattr(attempt, name, value)
            db.add(attempt)
            db.commit()
            db.refresh(attempt)
            db.expunge(attempt)
            return attempt

    def terminate_attempt(
        self,
        session_id: str,
        *,
        status: str,
        reason_code: str,
        task_validity: str = "invalid",
        physiology_quality: str = "partial",
        source_csv_filename: str | None = None,
        source_csv_sha256: str | None = None,
        metrics: dict | None = None,
        hrv: dict | None = None,
    ) -> ClassicSessionAttempt:
        if status not in {"ABORTED", "INTERRUPTED"}:
            raise ClassicPersistenceError("invalid_terminal_status")
        with Session(self.engine) as db:
            attempt = db.get(ClassicSessionAttempt, session_id)
            if attempt is None:
                raise ClassicPersistenceError("session_not_found")
            if attempt.status in {"COMPLETE", "ABORTED", "INTERRUPTED"}:
                raise ClassicPersistenceError("session_immutable")
            attempt.status = status
            attempt.failure_reason_code = reason_code
            attempt.terminal_intent_status = None
            attempt.terminal_intent_reason_code = None
            attempt.task_validity = task_validity
            attempt.physiology_quality = physiology_quality
            attempt.source_csv_filename = source_csv_filename
            attempt.source_csv_sha256 = source_csv_sha256
            attempt.metrics_json = _canonical_json(metrics) if metrics is not None else None
            attempt.hrv_json = _canonical_json(hrv) if hrv is not None else None
            attempt.finished_at = _utcnow()
            db.add(attempt)
            db.commit()
            db.refresh(attempt)
            db.expunge(attempt)
            return attempt

    def mark_orphaned_attempts(self) -> int:
        with Session(self.engine) as db:
            attempts = db.exec(
                select(ClassicSessionAttempt).where(
                    ClassicSessionAttempt.status.in_(
                        {
                            "PREPARED",
                            "BASELINE",
                            "TASK",
                            "POST_TASK",
                            "RECOVERY",
                            "FINALIZING",
                        }
                    )
                )
            ).all()
            for attempt in attempts:
                attempt.status = "FINALIZING"
                attempt.failure_reason_code = "backend_process_restart"
                attempt.terminal_intent_status = "INTERRUPTED"
                attempt.terminal_intent_reason_code = "backend_process_restart"
                attempt.finished_at = None
                db.add(attempt)
            db.commit()
            return len(attempts)

    def list_attempts(
        self,
        *,
        participant_id: str | None = None,
        visit_ordinal: int | None = None,
    ) -> list[ClassicAttemptContext]:
        with Session(self.engine) as db:
            statement = select(ClassicSessionAttempt, Visit).join(
                Visit,
                Visit.id == ClassicSessionAttempt.visit_id,
            )
            if participant_id is not None:
                statement = statement.where(Visit.participant_id == participant_id)
            if visit_ordinal is not None:
                statement = statement.where(Visit.visit_ordinal == visit_ordinal)
            rows = db.exec(
                statement.order_by(
                    Visit.participant_id,
                    Visit.visit_ordinal,
                    ClassicSessionAttempt.workload_level,
                    ClassicSessionAttempt.attempt_number,
                )
            ).all()
            contexts = [
                ClassicAttemptContext(
                    attempt=attempt,
                    participant_id=visit.participant_id,
                    visit_ordinal=visit.visit_ordinal,
                )
                for attempt, visit in rows
            ]
            for context in contexts:
                db.expunge(context.attempt)
            return contexts

    def list_artifacts(self, session_id: str) -> list[ClassicSessionArtifact]:
        with Session(self.engine) as db:
            if db.get(ClassicSessionAttempt, session_id) is None:
                raise ClassicPersistenceError("session_not_found")
            artifacts = db.exec(
                select(ClassicSessionArtifact)
                .where(ClassicSessionArtifact.session_id == session_id)
                .order_by(ClassicSessionArtifact.relative_path)
            ).all()
            for artifact in artifacts:
                db.expunge(artifact)
            return list(artifacts)

    def selected_attempt_id(self, *, visit_id: int, workload_level: str) -> str | None:
        with Session(self.engine) as db:
            selection = db.exec(
                select(ClassicSessionSelection).where(
                    ClassicSessionSelection.visit_id == visit_id,
                    ClassicSessionSelection.workload_level == workload_level,
                )
            ).first()
            return selection.attempt_id if selection is not None else None

    def list_selection_audits(
        self,
        *,
        participant_id: str,
        visit_ordinal: int,
    ) -> list[ClassicSessionSelectionAudit]:
        with Session(self.engine) as db:
            visit = db.exec(
                select(Visit).where(
                    Visit.participant_id == participant_id,
                    Visit.visit_ordinal == visit_ordinal,
                )
            ).first()
            if visit is None or visit.id is None:
                raise ClassicPersistenceError("visit_not_found")
            rows = db.exec(
                select(ClassicSessionSelectionAudit)
                .where(ClassicSessionSelectionAudit.visit_id == visit.id)
                .order_by(ClassicSessionSelectionAudit.id)
            ).all()
            for row in rows:
                db.expunge(row)
            return list(rows)

    def finalize_attempt(
        self,
        session_id: str,
        *,
        task_validity: str,
        physiology_quality: str,
        source_csv_filename: str,
        source_csv_sha256: str,
        metrics: dict,
        hrv: dict,
        failure_reason_code: str | None = None,
    ) -> ClassicSessionAttempt:
        if task_validity not in {"valid", "invalid"}:
            raise ClassicPersistenceError("invalid_task_validity")
        with Session(self.engine) as db:
            attempt = db.get(ClassicSessionAttempt, session_id)
            if attempt is None:
                raise ClassicPersistenceError("session_not_found")
            if attempt.status in {"COMPLETE", "ABORTED", "INTERRUPTED"}:
                raise ClassicPersistenceError("session_immutable")
            attempt.status = "COMPLETE"
            attempt.task_validity = task_validity
            attempt.physiology_quality = physiology_quality
            attempt.source_csv_filename = source_csv_filename
            attempt.source_csv_sha256 = source_csv_sha256
            attempt.metrics_json = _canonical_json(metrics)
            attempt.hrv_json = _canonical_json(hrv)
            attempt.failure_reason_code = failure_reason_code
            attempt.terminal_intent_status = None
            attempt.terminal_intent_reason_code = None
            attempt.finished_at = _utcnow()
            db.add(attempt)
            if task_validity == "valid" and not attempt.test_mode:
                selection = db.exec(
                    select(ClassicSessionSelection).where(
                        ClassicSessionSelection.visit_id == attempt.visit_id,
                        ClassicSessionSelection.workload_level == attempt.workload_level,
                    )
                ).first()
                if selection is None:
                    self._select_in_session(
                        db,
                        attempt,
                        reason_code="first_valid_attempt",
                    )
            db.commit()
            db.refresh(attempt)
            return attempt

    def register_artifacts(
        self,
        session_id: str,
        inventory: Iterable[Mapping[str, Any] | Any],
    ) -> list[ClassicSessionArtifact]:
        """Register a finalized bundle exactly once without changing its files."""

        prepared = self._prepare_artifacts(session_id, inventory)
        with Session(self.engine) as db:
            attempt = db.get(ClassicSessionAttempt, session_id)
            if attempt is None:
                raise ClassicPersistenceError("session_not_found")
            if attempt.status not in {"COMPLETE", "ABORTED", "INTERRUPTED"}:
                raise ClassicPersistenceError("session_not_finalized")
            existing = db.exec(
                select(ClassicSessionArtifact).where(
                    ClassicSessionArtifact.session_id == session_id
                )
            ).first()
            if existing is not None:
                raise ClassicPersistenceError("artifacts_immutable")
            for artifact in prepared:
                db.add(artifact)
            db.commit()
            for artifact in prepared:
                db.refresh(artifact)
                db.expunge(artifact)
        return sorted(prepared, key=lambda artifact: artifact.relative_path)

    @staticmethod
    def _prepare_artifacts(
        session_id: str,
        inventory: Iterable[Mapping[str, Any] | Any],
    ) -> list[ClassicSessionArtifact]:
        prepared: list[ClassicSessionArtifact] = []
        relative_paths: set[str] = set()
        for item in inventory:
            def field(name: str) -> Any:
                return item.get(name) if isinstance(item, Mapping) else getattr(item, name)

            relative = str(field("relative_path"))
            path = Path(relative)
            digest = str(field("sha256"))
            size = field("size_bytes")
            kind = str(field("kind"))
            if not relative or path.is_absolute() or ".." in path.parts:
                raise ClassicPersistenceError("invalid_artifact_path")
            if relative in relative_paths:
                raise ClassicPersistenceError("duplicate_artifact_path")
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ClassicPersistenceError("invalid_artifact_sha256")
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise ClassicPersistenceError("invalid_artifact_size")
            if not kind:
                raise ClassicPersistenceError("invalid_artifact_kind")
            relative_paths.add(relative)
            prepared.append(
                ClassicSessionArtifact(
                    session_id=session_id,
                    kind=kind,
                    relative_path=path.as_posix(),
                    sha256=digest,
                    size_bytes=size,
                )
            )
        return prepared

    def finalize_attempt_with_artifacts(
        self,
        session_id: str,
        *,
        task_validity: str,
        physiology_quality: str,
        source_csv_filename: str,
        source_csv_sha256: str,
        metrics: dict,
        hrv: dict,
        inventory: Iterable[Mapping[str, Any] | Any],
        failure_reason_code: str | None = None,
        recovery_from_validated_bundle: bool = False,
    ) -> ClassicSessionAttempt:
        """Commit terminal metadata, artifacts, block, and selection together."""

        if task_validity not in {"valid", "invalid"}:
            raise ClassicPersistenceError("invalid_task_validity")
        prepared = self._prepare_artifacts(session_id, inventory)
        with Session(self.engine) as db:
            attempt = db.get(ClassicSessionAttempt, session_id)
            if attempt is None:
                raise ClassicPersistenceError("session_not_found")
            if (
                attempt.status in {"COMPLETE", "ABORTED", "INTERRUPTED"}
                and not recovery_from_validated_bundle
            ):
                raise ClassicPersistenceError("session_immutable")
            existing = db.exec(
                select(ClassicSessionArtifact).where(
                    ClassicSessionArtifact.session_id == session_id
                )
            ).first()
            if existing is not None:
                raise ClassicPersistenceError("artifacts_immutable")

            attempt.status = "COMPLETE"
            attempt.task_validity = task_validity
            attempt.physiology_quality = physiology_quality
            attempt.source_csv_filename = source_csv_filename
            attempt.source_csv_sha256 = source_csv_sha256
            attempt.metrics_json = _canonical_json(metrics)
            attempt.hrv_json = _canonical_json(hrv)
            attempt.failure_reason_code = failure_reason_code
            attempt.terminal_intent_status = None
            attempt.terminal_intent_reason_code = None
            attempt.finished_at = _utcnow()
            db.add(attempt)
            for artifact in prepared:
                db.add(artifact)
            if task_validity == "valid" and not attempt.test_mode:
                selection = db.exec(
                    select(ClassicSessionSelection).where(
                        ClassicSessionSelection.visit_id == attempt.visit_id,
                        ClassicSessionSelection.workload_level == attempt.workload_level,
                    )
                ).first()
                if selection is None:
                    self._select_in_session(
                        db,
                        attempt,
                        reason_code="first_valid_attempt",
                    )
            db.commit()
            db.refresh(attempt)
            db.expunge(attempt)
            return attempt

    def terminate_attempt_with_artifacts(
        self,
        session_id: str,
        *,
        status: str,
        reason_code: str,
        task_validity: str,
        physiology_quality: str,
        source_csv_filename: str,
        source_csv_sha256: str,
        metrics: dict,
        hrv: dict,
        inventory: Iterable[Mapping[str, Any] | Any],
        recovery_from_validated_bundle: bool = False,
    ) -> ClassicSessionAttempt:
        if status not in {"ABORTED", "INTERRUPTED"}:
            raise ClassicPersistenceError("invalid_terminal_status")
        prepared = self._prepare_artifacts(session_id, inventory)
        with Session(self.engine) as db:
            attempt = db.get(ClassicSessionAttempt, session_id)
            if attempt is None:
                raise ClassicPersistenceError("session_not_found")
            if (
                attempt.status in {"COMPLETE", "ABORTED", "INTERRUPTED"}
                and not recovery_from_validated_bundle
            ):
                raise ClassicPersistenceError("session_immutable")
            existing = db.exec(
                select(ClassicSessionArtifact).where(
                    ClassicSessionArtifact.session_id == session_id
                )
            ).first()
            if existing is not None:
                raise ClassicPersistenceError("artifacts_immutable")

            attempt.status = status
            attempt.failure_reason_code = reason_code
            attempt.terminal_intent_status = None
            attempt.terminal_intent_reason_code = None
            attempt.task_validity = task_validity
            attempt.physiology_quality = physiology_quality
            attempt.source_csv_filename = source_csv_filename
            attempt.source_csv_sha256 = source_csv_sha256
            attempt.metrics_json = _canonical_json(metrics)
            attempt.hrv_json = _canonical_json(hrv)
            attempt.finished_at = _utcnow()
            db.add(attempt)
            for artifact in prepared:
                db.add(artifact)
            db.commit()
            db.refresh(attempt)
            db.expunge(attempt)
            return attempt

    def select_attempt(self, session_id: str, *, reason_code: str) -> ClassicSessionSelection:
        if not reason_code.strip():
            raise ClassicPersistenceError("selection_reason_required")
        with Session(self.engine) as db:
            attempt = db.get(ClassicSessionAttempt, session_id)
            if attempt is None:
                raise ClassicPersistenceError("session_not_found")
            if (
                attempt.status != "COMPLETE"
                or attempt.task_validity != "valid"
                or attempt.test_mode
            ):
                raise ClassicPersistenceError("attempt_not_selectable")
            selection = self._select_in_session(db, attempt, reason_code=reason_code)
            db.commit()
            db.refresh(selection)
            return selection

    @staticmethod
    def _select_in_session(
        db: Session,
        attempt: ClassicSessionAttempt,
        *,
        reason_code: str,
    ) -> ClassicSessionSelection:
        if (
            attempt.source_csv_filename is None
            or attempt.source_csv_sha256 is None
            or attempt.metrics_json is None
        ):
            raise ClassicPersistenceError("attempt_results_missing")
        selection = db.exec(
            select(ClassicSessionSelection).where(
                ClassicSessionSelection.visit_id == attempt.visit_id,
                ClassicSessionSelection.workload_level == attempt.workload_level,
            )
        ).first()
        previous_attempt_id = selection.attempt_id if selection is not None else None
        block = db.exec(
            select(Block).where(
                Block.visit_id == attempt.visit_id,
                Block.workload_level == attempt.workload_level,
            )
        ).first()
        block_source_changed = bool(
            block is None
            or block.source_csv_filename != attempt.source_csv_filename
            or block.source_csv_sha256 != attempt.source_csv_sha256
            or block.metrics_json != attempt.metrics_json
        )
        if block is None:
            block = Block(
                visit_id=attempt.visit_id,
                workload_level=attempt.workload_level,
                source_csv_filename=attempt.source_csv_filename,
                source_csv_sha256=attempt.source_csv_sha256,
                metrics_json=attempt.metrics_json,
            )
        else:
            block.source_csv_filename = attempt.source_csv_filename
            block.source_csv_sha256 = attempt.source_csv_sha256
            block.metrics_json = attempt.metrics_json
            block.ingested_at = _utcnow()
        db.add(block)
        db.flush()
        if block.id is None:
            raise ClassicPersistenceError("block_persistence_failed")
        stale_provenance = db.exec(
            select(BlockProvenance).where(BlockProvenance.block_id == block.id)
        ).first()
        if stale_provenance is not None:
            db.delete(stale_provenance)
            db.flush()
        provenance_payload = {
            "manifest_version": "matb-classic-block-provenance-v1",
            "classic_session_id": attempt.id,
            "attempt_number": attempt.attempt_number,
            "workload_level": attempt.workload_level,
            "scenario": {
                "filename": attempt.scenario_name,
                "sha256": attempt.scenario_sha256,
            },
            "openmatb_source_sha256": attempt.openmatb_source_sha256,
            "source_csv_filename": attempt.source_csv_filename,
            "source_csv_sha256": attempt.source_csv_sha256,
            "test_mode": attempt.test_mode,
        }
        provenance_json = _canonical_json(provenance_payload)
        db.add(
            BlockProvenance(
                block_id=block.id,
                manifest_filename=None,
                manifest_sha256=hashlib.sha256(
                    provenance_json.encode("utf-8")
                ).hexdigest(),
                manifest_json=provenance_json,
                validation_status="classic_session_verified",
                validation_issues_json="[]",
            )
        )
        if block_source_changed:
            stale_fit = db.exec(
                select(DepdfFit).where(DepdfFit.visit_id == attempt.visit_id)
            ).first()
            if stale_fit is not None:
                db.delete(stale_fit)
        if selection is None:
            selection = ClassicSessionSelection(
                visit_id=attempt.visit_id,
                workload_level=attempt.workload_level,
                attempt_id=attempt.id,
                block_id=block.id,
            )
        else:
            selection.attempt_id = attempt.id
            selection.block_id = block.id
            selection.selected_at = _utcnow()
        db.add(selection)
        db.add(
            ClassicSessionSelectionAudit(
                visit_id=attempt.visit_id,
                workload_level=attempt.workload_level,
                previous_attempt_id=previous_attempt_id,
                new_attempt_id=attempt.id,
                reason_code=reason_code,
            )
        )
        return selection


__all__ = [
    "ClassicAttemptContext",
    "ClassicPersistenceError",
    "SQLModelClassicPersistence",
]
