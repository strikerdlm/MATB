"""Additive evidence tables; legacy Block/CSV identities remain unchanged."""
from datetime import datetime, timezone

from sqlalchemy import Column, LargeBinary
from sqlmodel import Field, SQLModel, UniqueConstraint


def now() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceCapture(SQLModel, table=True):
    __tablename__ = "evidence_capture"
    id: str = Field(primary_key=True)
    manifest_sha256: str = Field(index=True)
    artifact_fingerprint: str
    session_id: str = Field(index=True)
    block_instance_id: str = Field(index=True)
    participant_id: str | None = Field(default=None, foreign_key="participant.id", index=True)
    visit_id: int | None = Field(default=None, foreign_key="visit.id", index=True)
    condition: str
    execution_purpose: str = Field(index=True)
    completion: str
    manifest_json: str
    created_at: datetime = Field(default_factory=now)


class EvidenceArtifact(SQLModel, table=True):
    __tablename__ = "evidence_artifact"
    __table_args__ = (UniqueConstraint("capture_id", "role"),)
    id: int | None = Field(default=None, primary_key=True)
    capture_id: str = Field(foreign_key="evidence_capture.id", index=True)
    role: str
    sha256: str
    content: bytes = Field(sa_column=Column(LargeBinary, nullable=False))


class EvidenceRecord(SQLModel, table=True):
    __tablename__ = "evidence_record"
    id: int | None = Field(default=None, primary_key=True)
    capture_id: str = Field(foreign_key="evidence_capture.id", index=True)
    stream: str = Field(index=True)
    ordinal: int
    record_id: str = Field(index=True)
    event_id: str = Field(index=True)
    task: str | None = Field(default=None, index=True)
    record_json: str


class EvidenceRun(SQLModel, table=True):
    __tablename__ = "evidence_run"
    id: str = Field(primary_key=True)
    capture_id: str = Field(foreign_key="evidence_capture.id", index=True)
    version: str
    status: str = "pending"
    reason: str | None = None
    result_json: str | None = None
    fingerprint: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=now)


class EvidenceMetric(SQLModel, table=True):
    __tablename__ = "evidence_metric"
    id: str = Field(primary_key=True)
    run_id: str = Field(foreign_key="evidence_run.id", index=True)
    capture_id: str = Field(foreign_key="evidence_capture.id", index=True)
    key: str = Field(index=True)
    version: str
    status: str
    value: float | None = None
    eligible: bool = False
    details_json: str


class EvidenceMetricSource(SQLModel, table=True):
    __tablename__ = "evidence_metric_source"
    id: int | None = Field(default=None, primary_key=True)
    metric_id: str = Field(foreign_key="evidence_metric.id", index=True)
    stream: str
    record_id: str = Field(index=True)


class EvidenceAnalysisInput(SQLModel, table=True):
    __tablename__ = "evidence_analysis_input"
    id: str = Field(primary_key=True)
    input_json: str
    created_at: datetime = Field(default_factory=now)


class EvidenceQualification(SQLModel, table=True):
    __tablename__ = "evidence_qualification"
    id: str = Field(primary_key=True)
    record_json: str
    created_at: datetime = Field(default_factory=now)


class EvidenceQualificationArtifact(SQLModel, table=True):
    __tablename__ = "evidence_qualification_artifact"
    __table_args__ = (UniqueConstraint("qualification_id", "name"),)
    id: int | None = Field(default=None, primary_key=True)
    qualification_id: str = Field(foreign_key="evidence_qualification.id", index=True)
    name: str
    content: bytes = Field(sa_column=Column(LargeBinary, nullable=False))


class EvidenceQualificationLink(SQLModel, table=True):
    __tablename__ = "evidence_qualification_link"
    id: str = Field(primary_key=True)
    capture_id: str = Field(foreign_key="evidence_capture.id", index=True)
    qualification_id: str = Field(foreign_key="evidence_qualification.id", index=True)
    binding_json: str
    created_at: datetime = Field(default_factory=now)


class EvidenceQualificationRevocation(SQLModel, table=True):
    __tablename__ = "evidence_qualification_revocation"
    id: str = Field(primary_key=True)
    qualification_id: str = Field(foreign_key="evidence_qualification.id", index=True)
    reviewer: str
    reason: str
    created_at: datetime = Field(default_factory=now)
