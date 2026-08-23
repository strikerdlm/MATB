"""Durable metadata for Polar-synchronized classic OpenMATB attempts."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel, UniqueConstraint


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClassicSessionAttempt(SQLModel, table=True):
    __tablename__ = "classic_session_attempt"
    __table_args__ = (
        UniqueConstraint("visit_id", "workload_level", "attempt_number"),
    )

    id: str = Field(primary_key=True)
    visit_id: int = Field(foreign_key="visit.id", index=True)
    workload_level: str = Field(index=True)
    attempt_number: int = Field(ge=1)
    scenario_name: str
    scenario_sha256: str | None = None
    openmatb_source_sha256: str | None = None
    test_mode: bool = False
    wall_time_scale: float = 1.0
    schema_version: str = "matb-classic-session-v1"
    status: str = "PREPARED"
    task_validity: str = "pending"
    physiology_quality: str = "pending"
    performance_only_override: bool = False
    override_reason_code: str | None = None
    artifact_root: str = Field(unique=True)
    controller_lease_hash: str | None = Field(default=None, repr=False)
    source_csv_filename: str | None = None
    source_csv_sha256: str | None = Field(default=None, index=True)
    metrics_json: str | None = None
    hrv_json: str | None = None
    failure_reason_code: str | None = None
    terminal_intent_status: str | None = None
    terminal_intent_reason_code: str | None = None
    battery_level_at_start: int | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    baseline_started_at: datetime | None = None
    task_started_at: datetime | None = None
    task_finished_at: datetime | None = None
    recovery_started_at: datetime | None = None
    recovery_finished_at: datetime | None = None
    finished_at: datetime | None = None


class ClassicSessionArtifact(SQLModel, table=True):
    __tablename__ = "classic_session_artifact"
    __table_args__ = (UniqueConstraint("session_id", "relative_path"),)

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="classic_session_attempt.id", index=True)
    kind: str
    relative_path: str
    sha256: str
    size_bytes: int = Field(ge=0)
    created_at: datetime = Field(default_factory=_utcnow)


class ClassicSessionSelection(SQLModel, table=True):
    __tablename__ = "classic_session_selection"
    __table_args__ = (UniqueConstraint("visit_id", "workload_level"),)

    id: int | None = Field(default=None, primary_key=True)
    visit_id: int = Field(foreign_key="visit.id", index=True)
    workload_level: str
    attempt_id: str = Field(
        foreign_key="classic_session_attempt.id",
        unique=True,
        index=True,
    )
    block_id: int | None = Field(default=None, foreign_key="block.id", index=True)
    selected_at: datetime = Field(default_factory=_utcnow)


class ClassicSessionSelectionAudit(SQLModel, table=True):
    __tablename__ = "classic_session_selection_audit"

    id: int | None = Field(default=None, primary_key=True)
    visit_id: int = Field(foreign_key="visit.id", index=True)
    workload_level: str
    previous_attempt_id: str | None = Field(
        default=None,
        foreign_key="classic_session_attempt.id",
    )
    new_attempt_id: str = Field(foreign_key="classic_session_attempt.id")
    reason_code: str
    actor: str = "researcher"
    changed_at: datetime = Field(default_factory=_utcnow)


__all__ = [
    "ClassicSessionArtifact",
    "ClassicSessionAttempt",
    "ClassicSessionSelection",
    "ClassicSessionSelectionAudit",
]
