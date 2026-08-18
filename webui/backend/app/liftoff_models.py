"""Low-rate SQLModel metadata for Liftoff research sessions."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel, UniqueConstraint


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LiftoffSession(SQLModel, table=True):
    __tablename__ = "liftoff_session"
    __table_args__ = (
        UniqueConstraint("participant_id", "visit_id", "attempt_number"),
    )

    id: str = Field(primary_key=True)
    participant_id: str = Field(foreign_key="participant.id", index=True)
    visit_id: int = Field(foreign_key="visit.id", index=True)
    attempt_number: int = Field(ge=1)
    protocol_id: str
    protocol_version: str
    liftoff_build: str
    configuration_sha256: str = Field(index=True)
    track_id: str
    telemetry_profile: str
    manifest_json: str
    status: str = "PREPARED"
    validity: str = "pending_review"
    artifact_root: str
    controller_lease_hash: str = Field(repr=False)
    hrv_measurement_id: str | None = None
    hrv_file_sha256: str | None = None
    sync_quality: str = "missing"
    metrics_json: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    interrupted_at: datetime | None = None


class LiftoffArtifact(SQLModel, table=True):
    __tablename__ = "liftoff_artifact"
    __table_args__ = (UniqueConstraint("session_id", "relative_path"),)

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="liftoff_session.id", index=True)
    kind: str
    relative_path: str
    sha256: str
    size_bytes: int = Field(ge=0)
    created_at: datetime = Field(default_factory=_utcnow)


class LiftoffDeviation(SQLModel, table=True):
    __tablename__ = "liftoff_deviation"

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="liftoff_session.id", index=True)
    phase: str
    code: str
    severity: str
    received_utc: datetime = Field(default_factory=_utcnow)
    disposition: str = "unreviewed"
    detail_json: str = "{}"


class LiftoffResult(SQLModel, table=True):
    __tablename__ = "liftoff_result"

    session_id: str = Field(foreign_key="liftoff_session.id", primary_key=True)
    valid_lap_times_json: str
    invalid_laps: int = Field(ge=0)
    observer_restart_count: int = Field(ge=0)
    screenshot_sha256: str | None = Field(default=None, index=True)
    provenance_json: str = "{}"
    created_at: datetime = Field(default_factory=_utcnow)


__all__ = [
    "LiftoffArtifact",
    "LiftoffDeviation",
    "LiftoffResult",
    "LiftoffSession",
]
