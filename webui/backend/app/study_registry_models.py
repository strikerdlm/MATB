"""Additive study authoring ledger. Frozen records and assignment snapshots are immutable."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlmodel import SQLModel, Field


def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc)


class StudyWorkspace(SQLModel, table=True):
    __tablename__ = 'study_workspace'
    id: int = Field(default=1, primary_key=True)
    study_id: str
    template_family: str
    deployment_protocol_id: str
    deployment_schedule_sha256: str


class StudyDraft(SQLModel, table=True):
    __tablename__ = 'study_draft'
    id: str = Field(default_factory=uid, primary_key=True)
    payload_json: str
    sha256: str
    frozen_version_id: str | None = None
    created_at: datetime = Field(default_factory=now)


class StudyVersion(SQLModel, table=True):
    __tablename__ = 'study_version'
    id: str = Field(primary_key=True)
    analysis_plan_id: str = Field(unique=True)
    study_id: str
    template_family: str
    study_json: str
    analysis_json: str
    study_sha256: str
    analysis_sha256: str
    draft_sha256: str
    rehearsal_id: str
    actor: str
    reason: str
    created_at: datetime = Field(default_factory=now)


class StudyValidation(SQLModel, table=True):
    __tablename__ = 'study_validation'
    id: str = Field(default_factory=uid, primary_key=True)
    draft_id: str = Field(foreign_key='study_draft.id')
    draft_sha256: str
    issues_json: str
    created_at: datetime = Field(default_factory=now)


class StudyRehearsal(SQLModel, table=True):
    __tablename__ = 'study_rehearsal'
    id: str = Field(default_factory=uid, primary_key=True)
    draft_id: str = Field(foreign_key='study_draft.id')
    draft_sha256: str
    result_json: str
    created_at: datetime = Field(default_factory=now)


class StudyActivation(SQLModel, table=True):
    __tablename__ = 'study_activation'
    id: int | None = Field(default=None, primary_key=True)
    version_id: str = Field(foreign_key='study_version.id')
    actor: str
    reason: str
    created_at: datetime = Field(default_factory=now)


class StudyAssignment(SQLModel, table=True):
    __tablename__ = 'study_assignment'
    id: str = Field(default_factory=uid, primary_key=True)
    version_id: str = Field(foreign_key='study_version.id')
    participant_id: str = Field(foreign_key='participant.id')
    visit_id: int = Field(foreign_key='visit.id')
    arm: str
    occasions_json: str
    actor: str
    created_at: datetime = Field(default_factory=now)


class StudyAmendment(SQLModel, table=True):
    __tablename__ = 'study_amendment'
    id: str = Field(default_factory=uid, primary_key=True)
    prior_assignment_id: str = Field(foreign_key='study_assignment.id', unique=True)
    replacement_assignment_id: str = Field(foreign_key='study_assignment.id')
    actor: str
    reason: str
    diff_json: str
    created_at: datetime = Field(default_factory=now)


class StudyAttemptSelection(SQLModel, table=True):
    __tablename__ = 'study_attempt_selection'
    attempt_id: str = Field(foreign_key='assessment_attempt.id', primary_key=True)
    selections_json: str
    created_at: datetime = Field(default_factory=now)


class StudyRecoveryInterval(SQLModel, table=True):
    __tablename__ = 'study_recovery_interval'
    assignment_id: str = Field(foreign_key='study_assignment.id', primary_key=True)
    interval_key: str = Field(primary_key=True)
    anchor_attempt_id: str = Field(foreign_key='assessment_attempt.id')
    started_at: datetime = Field(default_factory=now)
    ended_at: datetime | None = None
    actor: str
    reason: str = ''
    finish_actor: str | None = None
    finish_reason: str | None = None


class StudyRegistryLock(SQLModel, table=True):
    __tablename__ = 'study_registry_lock'
    id: int = Field(default=1, primary_key=True)


class StudyNativeRating(SQLModel, table=True):
    __tablename__ = 'study_native_rating'
    id: str = Field(primary_key=True, foreign_key='assessment_attempt.id')
    target_attempt_id: str = Field(foreign_key='assessment_attempt.id')
    session_id: str
    block_instance_id: str
    payload_json: str
    payload_sha256: str
    created_at: datetime = Field(default_factory=now)


class StudyPreparation(SQLModel, table=True):
    """Immutable presentation and researcher criterion snapshot, before measurement."""
    __tablename__ = 'study_preparation'
    id: str = Field(default_factory=uid, primary_key=True)
    assignment_id: str = Field(foreign_key='study_assignment.id', index=True)
    participant_id: str = Field(foreign_key='participant.id', index=True)
    version_id: str = Field(foreign_key='study_version.id')
    occasion_key: str
    instrument: str
    identity_sha256: str = Field(index=True)
    config_sha256: str
    presentation_json: str
    requirement_json: str
    created_at: datetime = Field(default_factory=now)


class StudyPreparationEvent(SQLModel, table=True):
    __tablename__ = 'study_preparation_event'
    id: str = Field(default_factory=uid, primary_key=True)
    preparation_id: str = Field(foreign_key='study_preparation.id', index=True)
    stage: str
    payload_json: str
    passed: bool | None = None
    attempt_id: str | None = Field(default=None, foreign_key='assessment_attempt.id', index=True)
    duration_seconds: float | None = None
    created_at: datetime = Field(default_factory=now)


class StudyPreparationPractice(SQLModel, table=True):
    """Bind an actual practice attempt before acquisition; retrospective guesses cannot qualify."""
    __tablename__ = 'study_preparation_practice'
    attempt_id: str = Field(primary_key=True, foreign_key='assessment_attempt.id')
    preparation_id: str = Field(foreign_key='study_preparation.id')
    created_at: datetime = Field(default_factory=now)



class StudyPreparationAdmission(SQLModel, table=True):
    """Exact preparation decision at measurement admission; never inferred retrospectively."""
    __tablename__ = 'study_preparation_admission'
    attempt_id: str = Field(primary_key=True, foreign_key='assessment_attempt.id')
    assignment_id: str = Field(foreign_key='study_assignment.id', index=True)
    snapshot_json: str
    snapshot_sha256: str
    created_at: datetime = Field(default_factory=now)


from sqlalchemy import DDL, event
for _model in (StudyPreparation, StudyPreparationEvent, StudyPreparationPractice, StudyPreparationAdmission):
    for _operation in ('UPDATE', 'DELETE'):
        event.listen(_model.__table__, 'after_create', DDL(
            f'CREATE TRIGGER IF NOT EXISTS {_model.__tablename__}_no_{_operation.lower()} '
            f'BEFORE {_operation} ON {_model.__tablename__} BEGIN '
            "SELECT RAISE(ABORT, 'preparation evidence is immutable'); END"))


class StudyNativePreflight(SQLModel, table=True):
    """Exact process metadata, never an acquisition start timestamp."""
    __tablename__ = 'study_native_preflight'
    session_id: str = Field(primary_key=True)
    attempt_id: str = Field(foreign_key='assessment_attempt.id', index=True)
    block_instance_id: str
    snapshot_json: str
    session_csv: str
    created_at: datetime = Field(default_factory=now)


for _operation in ('UPDATE', 'DELETE'):
    event.listen(StudyNativePreflight.__table__, 'after_create', DDL(
        f'CREATE TRIGGER IF NOT EXISTS study_native_preflight_no_{_operation.lower()} '
        f'BEFORE {_operation} ON study_native_preflight BEGIN '
        "SELECT RAISE(ABORT, 'preflight snapshot is immutable'); END"))
