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
