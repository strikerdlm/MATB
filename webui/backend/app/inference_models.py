"""Optional additive semantic ledger. Source artifacts are append-only."""
from sqlalchemy import Column, LargeBinary
from sqlmodel import Field, SQLModel, UniqueConstraint


class InferenceAnnotation(SQLModel, table=True):
    __tablename__ = 'inference_annotation'
    id: str = Field(primary_key=True)
    capture_id: str = Field(index=True)
    content_json: str
    content_hash: str


class InferenceArtifact(SQLModel, table=True):
    __tablename__ = 'inference_artifact'
    id: str = Field(primary_key=True)
    owner_id: str = Field(index=True)
    role: str
    sha256: str
    content: bytes = Field(sa_column=Column(LargeBinary, nullable=False))


class InferenceRun(SQLModel, table=True):
    __tablename__ = 'inference_run'
    __table_args__ = (UniqueConstraint('input_identity', 'attempt_number'),)
    id: str = Field(primary_key=True)
    input_identity: str = Field(index=True)
    attempt_number: int = 1
    preview_id: str
    authorization_id: str
    job_id: str | None = None
    status: str = 'queued'
    result_json: str | None = None
    prior_attempt_id: str | None = None


class InferenceReview(SQLModel, table=True):
    __tablename__ = 'inference_review'
    id: str = Field(primary_key=True)
    owner_id: str = Field(index=True)
    activity: str
    reviewer: str
    created_at_ns: str
    content_json: str
