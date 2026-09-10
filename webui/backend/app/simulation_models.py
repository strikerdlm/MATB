"""SQLModel metadata for persisted native simulation sessions.

The simulation runtime keeps high-rate state in append-only artifacts.  These
tables intentionally contain only low-rate session, block, artifact, and
protocol-deviation metadata so the existing research-console tables remain
unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel, UniqueConstraint


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp for metadata defaults."""

    return datetime.now(timezone.utc)


class SimulationSession(SQLModel, table=True):
    __tablename__ = "simulation_session"
    purpose_provenance_id: str | None = None

    id: str = Field(primary_key=True)
    participant_id: str = Field(foreign_key="participant.id", index=True)
    visit_id: int = Field(foreign_key="visit.id", index=True)
    scenario_id: str
    scenario_sha256: str = Field(index=True)
    manifest_json: str
    locale: str
    lifecycle: str = "PREPARED"
    active_block_id: str | None = None
    validity: str = "valid"
    artifact_root: str
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    interrupted_at: datetime | None = None


class TechnicalSimulationSession(SQLModel, table=True):
    """Durable metadata for operator-only interactive checks.

    This table is deliberately separate from ``simulation_session`` so a
    technical launch cannot acquire a participant/visit identity or enter a
    research query through an omitted filter.
    """

    __tablename__ = "technical_simulation_session"
    purpose_provenance_id: str | None = None

    id: str = Field(primary_key=True)
    scenario_id: str
    scenario_sha256: str = Field(index=True)
    selected_block_id: str
    manifest_json: str
    locale: str
    lifecycle: str = "PREPARED"
    active_block_id: str | None = None
    validity: str = "technical_only"
    record_class: str = "technical_only"
    artifact_root: str
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    interrupted_at: datetime | None = None


class SimulationBlock(SQLModel, table=True):
    __tablename__ = "simulation_block"
    __table_args__ = (UniqueConstraint("session_id", "block_id"),)

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="simulation_session.id", index=True)
    block_id: str
    profile: str
    order_index: int
    lifecycle: str = "PREPARED"
    validity: str = "valid"
    simulation_started_ms: int | None = None
    simulation_finished_ms: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    was_interrupted: bool = False
    recovered_from_checkpoint: int | None = None
    metrics_json: str | None = None


class TechnicalSimulationBlock(SQLModel, table=True):
    __tablename__ = "technical_simulation_block"
    __table_args__ = (UniqueConstraint("session_id", "block_id"),)

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="technical_simulation_session.id", index=True)
    block_id: str
    profile: str
    order_index: int = 0
    lifecycle: str = "PREPARED"
    validity: str = "technical_only"
    simulation_started_ms: int | None = None
    simulation_finished_ms: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    was_interrupted: bool = False
    recovered_from_checkpoint: int | None = None
    metrics_json: str | None = None


class SimulationArtifact(SQLModel, table=True):
    __tablename__ = "simulation_artifact"
    __table_args__ = (UniqueConstraint("session_id", "relative_path"),)

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="simulation_session.id", index=True)
    kind: str
    relative_path: str
    sha256: str
    size_bytes: int
    created_at: datetime = Field(default_factory=_utcnow)


class TechnicalSimulationArtifact(SQLModel, table=True):
    __tablename__ = "technical_simulation_artifact"
    __table_args__ = (UniqueConstraint("session_id", "relative_path"),)

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="technical_simulation_session.id", index=True)
    kind: str
    relative_path: str
    sha256: str
    size_bytes: int
    created_at: datetime = Field(default_factory=_utcnow)


class ProtocolDeviation(SQLModel, table=True):
    __tablename__ = "protocol_deviation"

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="simulation_session.id", index=True)
    block_id: str | None = None
    code: str
    severity: str
    simulation_time_ms: int
    detail_json: str
    disposition: str = "unreviewed"
    created_at: datetime = Field(default_factory=_utcnow)


class TechnicalProtocolDeviation(SQLModel, table=True):
    __tablename__ = "technical_protocol_deviation"

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="technical_simulation_session.id", index=True)
    block_id: str | None = None
    code: str
    severity: str
    simulation_time_ms: int
    detail_json: str
    disposition: str = "technical_only"
    created_at: datetime = Field(default_factory=_utcnow)
