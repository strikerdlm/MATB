"""Instrument-neutral identities; source artifacts stay in their original stores."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlmodel import Field, SQLModel, UniqueConstraint


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


class AssessmentOccasion(SQLModel, table=True):
    __tablename__ = 'assessment_occasion'
    id: str = Field(default_factory=uid, primary_key=True)
    participant_id: str | None = Field(default=None, foreign_key='participant.id', index=True)
    visit_id: int | None = Field(default=None, foreign_key='visit.id', index=True)
    instrument: str = Field(index=True)
    phase: str | None = None
    order: int | None = None
    condition: str | None = None
    version_ref: str | None = None
    origin: str
    collection_group_id: str | None = Field(default=None, index=True)
    accompanying_occasion_id: str | None = Field(default=None, foreign_key='assessment_occasion.id')


class AssessmentAttempt(SQLModel, table=True):
    __tablename__ = 'assessment_attempt'
    __table_args__ = (UniqueConstraint('occasion_id', 'ordinal'),)
    id: str = Field(default_factory=uid, primary_key=True)
    occasion_id: str = Field(foreign_key='assessment_occasion.id', index=True)
    ordinal: int
    purpose_provenance_id: str | None = None
    execution_purpose: str
    repeat_of: str | None = Field(default=None, foreign_key='assessment_attempt.id')
    repeat_reason: str | None = None
    target_attempt_id: str | None = Field(default=None, foreign_key='assessment_attempt.id')
    interruption_category: str | None = None
    acquisition_state: str = 'created'
    created_at: datetime | None = Field(default_factory=now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    final_payload_sha256: str | None = None
    raw_saving: str = 'unknown'
    ratings: str = 'unknown'
    processing: str = 'unknown'


class AssessmentSourceLink(SQLModel, table=True):
    __tablename__ = 'assessment_source_link'
    __table_args__ = (UniqueConstraint('source_table', 'source_id', 'role'),)
    id: str = Field(default_factory=uid, primary_key=True)
    attempt_id: str = Field(foreign_key='assessment_attempt.id', index=True)
    source_table: str
    source_id: str
    role: str = 'acquisition'
    purpose_provenance_id: str | None = None


class AssessmentOccasionClassification(SQLModel, table=True):
    """Named retrospective association; never overwrites the original occasion."""
    __tablename__ = 'assessment_occasion_classification'
    id: int | None = Field(default=None, primary_key=True)
    occasion_id: str = Field(foreign_key='assessment_occasion.id', index=True)
    visit_id: int = Field(foreign_key='visit.id')
    phase: str
    order: int
    condition: str | None = None
    version_ref: str | None = None
    reviewer: str
    reason: str
    supporting_references_json: str = '[]'
    recorded_at: datetime = Field(default_factory=now)


from sqlalchemy import DDL, event
for model in (AssessmentOccasion, AssessmentSourceLink, AssessmentOccasionClassification):
    for operation in ('UPDATE', 'DELETE'):
        event.listen(model.__table__, 'after_create', DDL(
            f'CREATE TRIGGER IF NOT EXISTS {model.__tablename__}_no_{operation.lower()} '
            f'BEFORE {operation} ON {model.__tablename__} BEGIN '
            "SELECT RAISE(ABORT, 'assessment association is append-only'); END"))
