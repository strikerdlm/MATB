"""Durable metadata for frontend-supervised classic OpenMATB suites."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel, UniqueConstraint


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OpenMatbPresetSet(SQLModel, table=True):
    __tablename__ = "openmatb_preset_set"
    __table_args__ = (UniqueConstraint("preset_id", "version"),)

    id: int | None = Field(default=None, primary_key=True)
    preset_id: str = Field(index=True)
    version: str
    label_es: str
    status: str = "draft"
    settings_json: str
    sha256: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow)
    published_at: datetime | None = None


class OpenMatbInstructionProtocol(SQLModel, table=True):
    __tablename__ = "openmatb_instruction_protocol"
    __table_args__ = (UniqueConstraint("protocol_id", "version"),)

    id: int | None = Field(default=None, primary_key=True)
    protocol_id: str = Field(index=True)
    version: str
    locale: str = "es-419"
    status: str = "draft"
    content_json: str
    sha256: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow)
    published_at: datetime | None = None


class OpenMatbVisualProfile(SQLModel, table=True):
    """Versioned, presentation-only OpenMATB profile."""

    __tablename__ = "openmatb_visual_profile"
    __table_args__ = (UniqueConstraint("profile_id", "version"),)

    id: int | None = Field(default=None, primary_key=True)
    profile_id: str = Field(index=True)
    version: str
    label: str
    status: str = "draft"
    schema_version: str
    payload_json: str
    sha256: str = Field(index=True)
    validation_json: str = "{\"errors\":[],\"warnings\":[]}"
    warning_acknowledgements_json: str = "[]"
    created_at: datetime = Field(default_factory=_utcnow)
    published_at: datetime | None = None


class OpenMatbSuiteSession(SQLModel, table=True):
    __tablename__ = "openmatb_suite_session"

    id: str = Field(primary_key=True)
    participant_id: str = Field(foreign_key="participant.id", index=True)
    visit_id: int = Field(foreign_key="visit.id", index=True)
    visit_ordinal: int
    preset_id: str
    preset_version: str
    preset_sha256: str
    instruction_protocol_id: str
    instruction_version: str
    instruction_sha256: str
    locale: str = "es-419"
    # Legacy bundled-theme selector is retained for historical sessions.
    visual_theme: str = "fac_modern"
    visual_profile_id: str | None = None
    visual_profile_version: str | None = None
    visual_profile_schema_version: str | None = None
    visual_profile_sha256: str | None = None
    execution_purpose: str = "study"
    display_index: int = 1
    lifecycle: str = "INSTRUCTIONS"
    current_block_index: int = 0
    block_order_json: str
    scenario_paths_json: str
    scores_json: str = "{}"
    controller_lease_hash: str
    participant_token_hash: str
    artifact_root: str
    active_pid: int | None = None
    active_session_csv: str | None = None
    last_error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
