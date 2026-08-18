"""Persisted binding between a MATB database and one study protocol."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel

from app.study_protocol import StudyProtocolDefinition


class StudyMetadata(SQLModel, table=True):
    singleton_id: int = Field(default=1, primary_key=True)
    protocol_id: str
    protocol_version: str
    schedule_sha256: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StudyParticipantContext(SQLModel, table=True):
    participant_id: str = Field(foreign_key="participant.id", primary_key=True)
    protocol_id: str
    task_sequence: str
    prior_fpv_hours: float = Field(ge=0)
    gaming_hours_per_week: float = Field(ge=0)
    created_at: datetime = Field(default_factory=_utcnow)


def ensure_study_binding(engine: Engine, protocol: StudyProtocolDefinition) -> None:
    expected = (
        protocol.protocol_id,
        protocol.protocol_version,
        protocol.schedule_sha256,
    )
    with Session(engine) as session:
        metadata = session.get(StudyMetadata, 1)
        if metadata is None:
            session.add(
                StudyMetadata(
                    protocol_id=expected[0],
                    protocol_version=expected[1],
                    schedule_sha256=expected[2],
                )
            )
            session.commit()
            return
        actual = (
            metadata.protocol_id,
            metadata.protocol_version,
            metadata.schedule_sha256,
        )
        if actual != expected:
            raise RuntimeError("study_protocol_mismatch")
