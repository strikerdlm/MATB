"""Immutable acquisition identities and append-only purpose attestations."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DDL, event
from sqlmodel import Field, SQLModel


class PurposeProvenance(SQLModel, table=True):
    __tablename__ = 'purpose_provenance'
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    source_table: str
    source_id: str
    source_snapshot_sha256: str
    recorded_purpose: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PurposeClassification(SQLModel, table=True):
    __tablename__ = 'purpose_classification'
    id: int | None = Field(default=None, primary_key=True)
    provenance_id: str = Field(foreign_key='purpose_provenance.id', index=True)
    purpose: str
    classification: str  # explicit | retrospective | unknown
    actor: str
    reason: str
    supporting_references_json: str = '[]'
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


for model in (PurposeProvenance, PurposeClassification):
    for operation in ('UPDATE', 'DELETE'):
        event.listen(model.__table__, 'after_create', DDL(
            f'CREATE TRIGGER IF NOT EXISTS {model.__tablename__}_no_{operation.lower()} '
            f'BEFORE {operation} ON {model.__tablename__} BEGIN '
            "SELECT RAISE(ABORT, 'purpose provenance is append-only'); END"
        ))
