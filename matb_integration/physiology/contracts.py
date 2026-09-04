"""Versioned wire contracts for the optional MATB physiology component."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PolarDeviceCapabilitiesV1(_StrictContract):
    """Capabilities resolved from the connected device before capture."""

    SCHEMA_VERSION: ClassVar[str] = "1.0"
    schema_version: Literal["1.0"] = "1.0"
    device_alias: str
    firmware: str | None = None
    battery_percent: int | None = Field(default=None, ge=0, le=100)
    streams: tuple[Literal["hr_rr", "ecg", "acc"], ...]
    ecg_sample_rates_hz: tuple[int, ...] = ()
    ecg_resolutions_bits: tuple[int, ...] = ()
    acc_sample_rates_hz: tuple[int, ...] = ()
    acc_resolutions_bits: tuple[int, ...] = ()
    acc_ranges_g: tuple[int, ...] = ()
    internal_recording_qualified: bool = False

    @field_validator(
        "streams",
        "ecg_sample_rates_hz",
        "ecg_resolutions_bits",
        "acc_sample_rates_hz",
        "acc_resolutions_bits",
        "acc_ranges_g",
        mode="before",
    )
    @classmethod
    def _wire_list_to_tuple(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value


class PolarCaptureV1(_StrictContract):
    """Durable capture state without a Bluetooth address."""

    SCHEMA_VERSION: ClassVar[str] = "1.0"
    schema_version: Literal["1.0"] = "1.0"
    capture_id: str
    execution_purpose: Literal["practice", "study"] = "study"
    participant_pseudonym: str
    matb_session_kind: str
    matb_session_id: str
    device_alias: str
    lifecycle: Literal["created", "starting", "capturing", "stopping", "complete", "failed"]
    requested_settings: dict[str, Any]
    resolved_settings: dict[str, Any] | None = None
    stream_counters: dict[str, int] = Field(default_factory=dict)
    gap_count: int = 0
    connection_epoch: int = 0
    artifact_state: Literal["none", "partial", "finalized", "incomplete"] = "none"
    incomplete_reasons: tuple[str, ...] = ()
    started_at_utc: datetime | None = None
    ended_at_utc: datetime | None = None

    @field_validator("incomplete_reasons", mode="before")
    @classmethod
    def _reasons_to_tuple(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value


class PolarCaptureEventV1(_StrictContract):
    """Sequenced resumable monitor event. High-rate raw data is never included."""

    SCHEMA_VERSION: ClassVar[str] = "1.0"
    schema_version: Literal["1.0"] = "1.0"
    capture_id: str
    sequence: int = Field(ge=1)
    event_type: Literal["status", "hr", "quality", "preview", "marker", "gap", "error"]
    occurred_at_utc: datetime
    payload: dict[str, Any]


class PolarArtifactEntryV1(_StrictContract):
    relative_path: str
    schema_id: str
    row_count: int = Field(ge=0)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PolarArtifactManifestV1(_StrictContract):
    """Integrity and provenance record finalized after all writers close."""

    SCHEMA_VERSION: ClassVar[str] = "1.0"
    schema_version: Literal["1.0"] = "1.0"
    capture_id: str
    execution_purpose: Literal["practice", "study"] = "study"
    participant_pseudonym: str
    matb_session_kind: str
    matb_session_id: str
    started_at_utc: datetime
    ended_at_utc: datetime
    requested_settings: dict[str, Any]
    resolved_settings: dict[str, Any]
    clock_model: dict[str, Any]
    stream_counters: dict[str, int]
    algorithm_versions: dict[str, str]
    incomplete_reasons: tuple[str, ...] = ()
    artifacts: tuple[PolarArtifactEntryV1, ...]

    @field_validator("incomplete_reasons", "artifacts", mode="before")
    @classmethod
    def _manifest_tuples(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value
