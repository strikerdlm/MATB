"""Durable metadata for optional Polar H10 physiology captures."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PolarCaptureRecord(SQLModel, table=True):
    __tablename__ = "polar_capture"

    id: str = Field(primary_key=True)
    participant_id: str = Field(foreign_key="participant.id", index=True)
    matb_session_kind: str = Field(index=True)
    matb_session_id: str = Field(index=True)
    device_alias: str
    lifecycle: str = Field(index=True)
    requested_settings_json: str
    resolved_settings_json: str | None = None
    stream_counters_json: str = "{}"
    incomplete_reasons_json: str = "[]"
    gap_count: int = 0
    connection_epoch: int = 0
    artifact_state: str = "none"
    artifact_root: str | None = None
    manifest_json: str | None = None
    manifest_sha256: str | None = None
    controller_lease_hash: str
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = None
    ended_at: datetime | None = None


class PolarCaptureMarkerRecord(SQLModel, table=True):
    __tablename__ = "polar_capture_marker"

    id: int | None = Field(default=None, primary_key=True)
    capture_id: str = Field(foreign_key="polar_capture.id", index=True)
    sequence: int
    label: str
    payload_json: str = "{}"
    host_monotonic_ns: int
    occurred_at_utc: datetime = Field(default_factory=_utcnow)
