"""SQLModel tables for the MATB Research Console (Phase 1A)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlmodel import Field, SQLModel, UniqueConstraint


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Participant(SQLModel, table=True):
    id: str = Field(primary_key=True)               # "P01"… pseudonymized, no PII
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
    validation_status: str = "missing_manifest"     # scenario validation or classic_session_verified
    validation_issues_json: str = "[]"              # list[ValidationIssue]
    created_at: datetime = Field(default_factory=_utcnow)


class BlockBundle(SQLModel, table=True):
    """Metadata for one validated OpenMATB scientific bundle.

    High-rate samples remain in the immutable ZIP and are deliberately not
    expanded into relational rows.
    """

    __table_args__ = (UniqueConstraint("block_id"),)
    id: int | None = Field(default=None, primary_key=True)
    block_id: int = Field(foreign_key="block.id", index=True)
    bundle_sha256: str = Field(index=True, unique=True)
    original_filename: str
    stored_filename: str
    schema_version: str
    run_status: str
    quality_status: str
    session_id: str
    summary_json: str
    manifest_json: str
    quality_json: str
    ingested_at: datetime = Field(default_factory=_utcnow)


class BlockArtifact(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("bundle_id", "name"),)
    id: int | None = Field(default=None, primary_key=True)
    bundle_id: int = Field(foreign_key="blockbundle.id", index=True)
    name: str
    sha256: str
    size_bytes: int
    media_type: str


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


class AnalysisResult(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("fingerprint", "engine_version"),)
    id: int | None = Field(default=None, primary_key=True)
    fingerprint: str = Field(index=True)            # sha256 of canonical input rows
    engine_version: str
    artifact_json: str                              # full engine artifact
    created_at: datetime = Field(default_factory=_utcnow)


class BayesResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    fingerprint: str = Field(index=True)            # input rows at job creation
    bayes_version: str
    status: str = "queued"                          # queued|running|done|failed
    artifact_json: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None
