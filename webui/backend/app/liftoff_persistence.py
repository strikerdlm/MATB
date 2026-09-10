"""Short-lived, allowlisted SQLModel persistence for Liftoff metadata."""

from __future__ import annotations

from app.purpose_service import declare_acquisition

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from app.models import Participant, Visit
from matb_integration.recording.records import ArtifactInfo

from .liftoff_models import (
    LiftoffArtifact,
    LiftoffDeviation,
    LiftoffResult,
    LiftoffSession,
)

_SESSION_FIELDS = frozenset({
    "status",
    "validity",
    "hrv_measurement_id",
    "hrv_file_sha256",
    "sync_quality",
    "metrics_json",
    "started_at",
    "finished_at",
    "interrupted_at",
})
_ACTIVE_STATUSES = ("PREPARED", "BASELINE", "TASK", "RECOVERY", "FINISHED")


class SQLModelLiftoffPersistence:
    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def insert_session(self, row: LiftoffSession, *, attempt_id: str | None = None) -> LiftoffSession:
        with Session(self.engine) as db:
            declare_acquisition(db, row, purpose=row.execution_purpose, attempt_id=attempt_id)
            db.commit()
            db.refresh(row)
            db.expunge(row)
            return row

    def load_session(self, session_id: str) -> LiftoffSession | None:
        with Session(self.engine) as db:
            row = db.get(LiftoffSession, session_id)
            if row is None:
                return None
            db.expunge(row)
            return row

    def load_result(self, session_id: str) -> LiftoffResult | None:
        with Session(self.engine) as db:
            row = db.get(LiftoffResult, session_id)
            if row is None:
                return None
            db.expunge(row)
            return row

    def list_artifacts(self, session_id: str) -> tuple[LiftoffArtifact, ...]:
        with Session(self.engine) as db:
            rows = db.exec(
                select(LiftoffArtifact)
                .where(LiftoffArtifact.session_id == session_id)
                .order_by(LiftoffArtifact.relative_path)
            ).all()
            for row in rows:
                db.expunge(row)
            return tuple(rows)

    def list_attempts(self, participant_id: str, visit_id: int) -> tuple[LiftoffSession, ...]:
        with Session(self.engine) as db:
            rows = db.exec(
                select(LiftoffSession)
                .where(
                    LiftoffSession.participant_id == participant_id,
                    LiftoffSession.visit_id == visit_id,
                )
                .order_by(LiftoffSession.attempt_number)
            ).all()
            for row in rows:
                db.expunge(row)
            return tuple(rows)

    def analysis_attempt(self, participant_id: str, *, visit_id: int) -> LiftoffSession | None:
        with Session(self.engine) as db:
            row = db.exec(
                select(LiftoffSession)
                .where(
                    LiftoffSession.participant_id == participant_id,
                    LiftoffSession.visit_id == visit_id,
                    LiftoffSession.validity == "valid",
                    LiftoffSession.execution_purpose == "study",
                )
                .order_by(LiftoffSession.attempt_number)
            ).first()
            if row is None:
                return None
            db.expunge(row)
            return row

    def require_visit(self, participant_id: str, visit_ordinal: int) -> Visit:
        with Session(self.engine) as db:
            if db.get(Participant, participant_id) is None:
                raise KeyError("participant_not_found")
            visit = db.exec(
                select(Visit).where(
                    Visit.participant_id == participant_id,
                    Visit.visit_ordinal == visit_ordinal,
                )
            ).one_or_none()
            if visit is None:
                raise KeyError("visit_not_found")
            db.expunge(visit)
            return visit

    def next_attempt_number(self, participant_id: str, visit_id: int) -> int:
        attempts = self.list_attempts(participant_id, visit_id)
        return (attempts[-1].attempt_number + 1) if attempts else 1

    def require_study_order(self, participant_id: str, visit_id: int, *, attempt_id: str | None = None) -> None:
        from app.experiment_catalog import require_task_order
        with Session(self.engine) as db:
            from .study_registry_models import StudyAttemptSelection
            from .assessment_models import AssessmentSourceLink
            selection = db.get(StudyAttemptSelection, attempt_id) if attempt_id else None
            selected = []
            for identity in json.loads(selection.selections_json).values() if selection else []:
                selected.extend(db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.attempt_id == identity, AssessmentSourceLink.source_table == 'openmatb_suite_session')).all())
            if attempt_id:
                for source in selected:
                    require_task_order(db, participant_id, visit_id, 'liftoff', source_session_id=source.source_id)
            else:
                require_task_order(db, participant_id, visit_id, 'liftoff', require_context=True)

    def require_retake_allowed(self, participant_id: str, visit_id: int) -> None:
        attempts = [row for row in self.list_attempts(participant_id, visit_id) if row.execution_purpose == "study"]
        if attempts and attempts[-1].validity != "invalid":
            raise ValueError("liftoff_retake_not_allowed")

    def update_session(self, session_id: str, **fields: object) -> None:
        unknown = set(fields) - _SESSION_FIELDS
        if unknown:
            raise ValueError(
                f"unsupported liftoff metadata fields: {', '.join(sorted(unknown))}"
            )
        with Session(self.engine) as db:
            row = db.get(LiftoffSession, session_id)
            if row is None:
                raise KeyError(session_id)
            for key, value in fields.items():
                setattr(row, key, value)
            from app.study_admission import sync_runtime_attempt
            status = fields.get('status')
            if status in {'BASELINE', 'TASK', 'RECOVERY'}: sync_runtime_attempt(db, row, state='started')
            elif status == 'FINISHED': sync_runtime_attempt(db, row, state='finished')
            elif status in {'INTERRUPTED', 'ABORTED'}: sync_runtime_attempt(db, row, state='interrupted')
            db.add(row)
            db.commit()

    def mark_orphaned_sessions(self) -> int:
        changed = 0
        with Session(self.engine) as db:
            rows = db.exec(
                select(LiftoffSession).where(LiftoffSession.status.in_(_ACTIVE_STATUSES))
            ).all()
            for row in rows:
                row.status = "INTERRUPTED"
                row.interrupted_at = datetime.now(timezone.utc)
                from app.study_admission import sync_runtime_attempt
                sync_runtime_attempt(db, row, state='interrupted')
                db.add(row)
                changed += 1
            if changed:
                db.commit()
        return changed

    def add_deviation(
        self,
        session_id: str,
        *,
        phase: str,
        code: str,
        severity: str,
        detail: Mapping[str, object] | None = None,
    ) -> None:
        with Session(self.engine) as db:
            db.add(
                LiftoffDeviation(
                    session_id=session_id,
                    phase=phase,
                    code=code,
                    severity=severity,
                    detail_json=json.dumps(
                        dict(detail or {}),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
            )
            db.commit()

    def save_result(
        self,
        session_id: str,
        *,
        valid_lap_times_s: Sequence[float],
        invalid_laps: int,
        observer_restart_count: int,
        screenshot_sha256: str | None,
        provenance: Mapping[str, object] | None = None,
    ) -> None:
        with Session(self.engine) as db:
            if db.get(LiftoffResult, session_id) is not None:
                raise ValueError("liftoff_result_immutable")
            db.add(
                LiftoffResult(
                    session_id=session_id,
                    valid_lap_times_json=json.dumps(list(valid_lap_times_s), separators=(",", ":")),
                    invalid_laps=invalid_laps,
                    observer_restart_count=observer_restart_count,
                    screenshot_sha256=screenshot_sha256,
                    provenance_json=json.dumps(
                        dict(provenance or {}),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
            )
            db.commit()

    def replace_artifacts(self, session_id: str, artifacts: Sequence[ArtifactInfo]) -> None:
        session = self.load_session(session_id)
        if session is None:
            raise KeyError(session_id)
        root = Path(session.artifact_root).resolve()
        rows: list[LiftoffArtifact] = []
        for artifact in artifacts:
            try:
                relative = artifact.path.resolve().relative_to(root).as_posix()
            except ValueError as exc:
                raise ValueError("liftoff_artifact_outside_root") from exc
            rows.append(
                LiftoffArtifact(
                    session_id=session_id,
                    kind=artifact.kind,
                    relative_path=relative,
                    sha256=artifact.sha256,
                    size_bytes=artifact.size_bytes,
                )
            )
        with Session(self.engine) as db:
            old = db.exec(
                select(LiftoffArtifact).where(LiftoffArtifact.session_id == session_id)
            ).all()
            for row in old:
                db.delete(row)
            for row in rows:
                db.add(row)
            db.commit()

    def admit_request(self, request, visit):
        from app.study_admission import resolve_assignment
        with Session(self.engine) as db:
            context = resolve_assignment(db, attempt_id=request.attempt_id, instrument='liftoff', participant_id=request.participant_id,
                visit_id=visit.id, purpose=request.execution_purpose, require_started=True,
                config=dict(binding_id='liftoff-telemetry-all-v1', input_mapping='liftoff-telemetry-all-v1', configuration=request.configuration.model_dump(), scoring='liftoff-current'))
            if context and context['locale'] != request.locale:
                from fastapi import HTTPException
                raise HTTPException(422, 'Liftoff locale differs from the frozen assignment.')
            return context

    def guard_acquisition(self, session_id):
        from app.study_admission import guard_source
        with Session(self.engine) as db:
            guard_source(db, db.get(LiftoffSession, session_id))
