"""Immutable descriptive derivations and bytes; only exploratory pointers may move."""
from datetime import datetime, timezone
from sqlalchemy import Column, DDL, LargeBinary, event
from sqlmodel import Field, SQLModel


def now(): return datetime.now(timezone.utc)


class HcfDerivation(SQLModel, table=True):
    __tablename__ = 'hcf_derivation'
    id: str = Field(primary_key=True)
    snapshot_json: str
    created_at: datetime = Field(default_factory=now)


class HcfExploratoryPointer(SQLModel, table=True):
    __tablename__ = 'hcf_exploratory_pointer'
    id: str = Field(default='legacy-unambiguous', primary_key=True)
    derivation_id: str = Field(foreign_key='hcf_derivation.id')


class StudyAnalysisExecution(SQLModel, table=True):
    __tablename__ = 'study_analysis_execution'
    id: str = Field(primary_key=True)
    version_id: str = Field(foreign_key='study_version.id', index=True)
    plan_sha256: str
    data_sha256: str
    implementation_sha256: str
    request_json: str
    snapshot_json: str
    result_json: str
    actor: str
    reason: str
    created_at: datetime = Field(default_factory=now)


class StudyAnalysisArtifact(SQLModel, table=True):
    __tablename__ = 'study_analysis_artifact'
    execution_id: str = Field(primary_key=True, foreign_key='study_analysis_execution.id')
    path: str = Field(primary_key=True)
    sha256: str
    content: bytes = Field(sa_column=Column(LargeBinary, nullable=False))


for model in (HcfDerivation, StudyAnalysisExecution, StudyAnalysisArtifact):
    for operation in ('UPDATE', 'DELETE'):
        event.listen(model.__table__, 'after_create', DDL(
            f'CREATE TRIGGER IF NOT EXISTS {model.__tablename__}_no_{operation.lower()} '
            f'BEFORE {operation} ON {model.__tablename__} BEGIN '
            "SELECT RAISE(ABORT, 'analysis derivation is immutable'); END"))


class HcfFitSnapshot(SQLModel, table=True):
    __tablename__ = 'hcf_fit_snapshot'
    id: str = Field(primary_key=True)
    derivation_id: str = Field(foreign_key='hcf_derivation.id')
    fit_json: str
    created_at: datetime = Field(default_factory=now)


for operation in ('UPDATE','DELETE'):
    event.listen(HcfFitSnapshot.__table__,'after_create',DDL(
        f'CREATE TRIGGER IF NOT EXISTS hcf_fit_snapshot_no_{operation.lower()} BEFORE {operation} ON hcf_fit_snapshot BEGIN '
        "SELECT RAISE(ABORT, 'fit snapshot is immutable'); END"))


class StudyAnalysisInput(SQLModel, table=True):
    """Frozen job input; execution consumes this snapshot without selecting again."""
    __tablename__ = 'study_analysis_input'
    id: str = Field(primary_key=True)
    version_id: str = Field(foreign_key='study_version.id', index=True)
    snapshot_json: str
    request_json: str
    actor: str
    reason: str
    created_at: datetime = Field(default_factory=now)


for operation in ('UPDATE','DELETE'):
    event.listen(StudyAnalysisInput.__table__,'after_create',DDL(
        f'CREATE TRIGGER IF NOT EXISTS study_analysis_input_no_{operation.lower()} BEFORE {operation} ON study_analysis_input BEGIN '
        "SELECT RAISE(ABORT, 'analysis input is immutable'); END"))
