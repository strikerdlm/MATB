"""SQLModel tables for the MATB Research Console (Phase 1A)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Index, literal_column, text
from sqlmodel import Field, SQLModel, UniqueConstraint


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Participant(SQLModel, table=True):
    id: str = Field(primary_key=True)               # "P01"â€¦ pseudonymized, no PII
    enrollment_date: date
    sex: str | None = None
    age_band: str | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class Visit(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("participant_id", "visit_ordinal"),)
    id: int | None = Field(default=None, primary_key=True)
    participant_id: str = Field(foreign_key="participant.id", index=True)
    visit_ordinal: int                              # deployment protocol timepoint
    scheduled_day: int                              # deployment protocol target day
    actual_date: date | None = None
    status: str = "planned"                         # planned|in_progress|complete


class Block(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("visit_id", "workload_level"),)
    id: int | None = Field(default=None, primary_key=True)
    visit_id: int = Field(foreign_key="visit.id", index=True)
    workload_level: str                             # LOW|MEDIUM|HIGH
    source_csv_filename: str
    source_csv_sha256: str = Field(index=True, unique=True)
    ingested_at: datetime = Field(default_factory=_utcnow)
    metrics_json: str                               # full log_converter record


class BlockProvenance(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("block_id"),)
    id: int | None = Field(default=None, primary_key=True)
    block_id: int = Field(foreign_key="block.id", index=True)
    manifest_filename: str | None = None
    manifest_sha256: str | None = Field(default=None, index=True)
    manifest_json: str | None = None
    validation_status: str = "missing_manifest"     # ok|warning|error|missing_manifest|invalid_manifest
    validation_issues_json: str = "[]"              # list[ValidationIssue]
    created_at: datetime = Field(default_factory=_utcnow)


class DepdfFit(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    participant_id: str = Field(foreign_key="participant.id", index=True)
    visit_id: int = Field(foreign_key="visit.id", unique=True)
    mwl_source: str                                 # MWL instrument used for the fit (provenance)
    g0: float
    p0: float
    tau0: float
    hcf_value: float
    hcf_source: str
    criteria_version: int
    per_level_json: str
    fitted_at: datetime = Field(default_factory=_utcnow)


class ScreenResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    participant_id: str = Field(foreign_key="participant.id", unique=True, index=True)
    administered_at: str                            # ISO timestamp from the browser
    screen_version: int
    raw_trials_json: str                            # full raw payload (re-derivable)
    scores_json: str                                # score_screen() output
    created_at: datetime = Field(default_factory=_utcnow)
    execution_purpose: str = "study"


class PvtAssessment(SQLModel, table=True):
    """Visit-linked Karolinska rating and psychomotor vigilance test.

    Legacy ``ScreenResult`` rows remain untouched because they represent a
    different four-task battery and must never be reinterpreted as PVT data.
    """

    __tablename__ = "pvt_assessment"
    __table_args__ = (
        UniqueConstraint("visit_id"),
        Index("ix_pvt_assessment_participant_visit", "participant_id", "visit_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    participant_id: str = Field(foreign_key="participant.id", index=True)
    visit_id: int = Field(foreign_key="visit.id", index=True)
    kss_score: int = Field(ge=1, le=9)
    administered_at: str
    duration_ms: int = Field(ge=1)
    protocol_valid: bool = True
    pvt_version: int = 1
    raw_trials_json: str
    metrics_json: str
    created_at: datetime = Field(default_factory=_utcnow)
    execution_purpose: str = "study"
    timing_evidence_json: str = "{}"


class PracticeResult(SQLModel, table=True):
    """Practice observations never share study uniqueness or analysis tables."""

    id: int | None = Field(default=None, primary_key=True)
    experiment_id: str = Field(index=True)
    participant_id: str | None = Field(default=None, foreign_key="participant.id")
    execution_purpose: str = "practice"
    payload_json: str
    result_json: str
    created_at: datetime = Field(default_factory=_utcnow)


class AnalysisResult(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("fingerprint", "engine_version"),)
    id: int | None = Field(default=None, primary_key=True)
    fingerprint: str = Field(index=True)            # sha256 of canonical input rows
    engine_version: str
    artifact_json: str                              # full engine artifact
    created_at: datetime = Field(default_factory=_utcnow)


class BayesResult(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("fingerprint", "bayes_version"),
        Index(
            "uq_bayesresult_one_active",
            literal_column("1"),
            unique=True,
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    fingerprint: str = Field(index=True)            # input rows at job creation
    bayes_version: str
    status: str = "queued"                          # queued|running|done|failed
    artifact_json: str | None = None
    error: str | None = None
    attempt_count: int = 1
    error_history_json: str = "[]"
    owner_token: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow)
    last_attempt_at: datetime = Field(default_factory=_utcnow, index=True)
    finished_at: datetime | None = None


class ArchivedAssessment(SQLModel, table=True):
    """Immutable observations retained when an explicitly requested retake replaces a result."""
    __tablename__ = "archived_assessment"
    id: int | None = Field(default=None, primary_key=True)
    experiment_id: str = Field(index=True)
    participant_id: str = Field(index=True)
    original_id: int
    snapshot_json: str
    reason: str = "explicit_overwrite"
