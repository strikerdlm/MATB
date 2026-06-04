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
    visit_ordinal: int                              # 1..6 (the timepoint)
    scheduled_day: int                              # 0/3/6/9/12/15 (target)
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
