"""Short-lived, allowlisted SQLModel persistence for Liftoff metadata."""

from __future__ import annotations

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

    def insert_session(self, row: LiftoffSession) -> LiftoffSession:
        with Session(self.engine) as db:
            db.add(row)
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

    def require_study_order(self, participant_id: str, visit_id: int) -> None:
        from app.experiment_catalog import require_task_order
        with Session(self.engine) as db:
            require_task_order(db, participant_id, visit_id, "liftoff", require_context=True)

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


__all__ = ["SQLModelLiftoffPersistence"]
