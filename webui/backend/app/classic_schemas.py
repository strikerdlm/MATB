"""Strict API contracts for classic OpenMATB + Polar H10 sessions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


WorkloadLevel = Literal["LOW", "MEDIUM", "HIGH"]
PARTICIPANT_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"


class CreateClassicSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_id: str = Field(pattern=PARTICIPANT_ID_PATTERN)
    visit_ordinal: int = Field(ge=1, le=32)
    workload_level: WorkloadLevel
    scenario_name: str = Field(
        pattern=r"^military_aviation/(low|medium|high)_workload\.txt$"
    )
    performance_only_override: bool = False
    override_reason_code: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$",
    )

    @model_validator(mode="after")
    def validate_override_and_scenario(self) -> "CreateClassicSession":
        expected = f"military_aviation/{self.workload_level.casefold()}_workload.txt"
        if self.scenario_name != expected:
            raise ValueError("scenario must match workload level")
        if self.performance_only_override and self.override_reason_code is None:
            raise ValueError("override_reason_code is required for performance-only mode")
        if not self.performance_only_override and self.override_reason_code is not None:
            raise ValueError("override_reason_code requires performance-only mode")
        return self


class ClassicSessionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    participant_id: str
    visit_id: int
    visit_ordinal: int
    workload_level: WorkloadLevel
    attempt_number: int
    scenario_name: str
    scenario_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    openmatb_source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    test_mode: bool
    wall_time_scale: float = Field(ge=0.001, le=1.0, allow_inf_nan=False)
    post_task_timeout_seconds: float = Field(gt=0, allow_inf_nan=False)
    status: str
    task_validity: str
    physiology_quality: str
    performance_only_override: bool
    failure_reason_code: str | None = None
    battery_level_at_start: int | None = None
    created_at: datetime
    baseline_started_at: datetime | None = None
    task_started_at: datetime | None = None
    task_finished_at: datetime | None = None
    recovery_started_at: datetime | None = None
    recovery_finished_at: datetime | None = None
    finished_at: datetime | None = None

    @field_validator(
        "created_at",
        "baseline_started_at",
        "task_started_at",
        "task_finished_at",
        "recovery_started_at",
        "recovery_finished_at",
        "finished_at",
        mode="after",
    )
    @classmethod
    def serialize_sqlite_timestamps_as_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class PreparedClassicSession(ClassicSessionView):
    controller_lease: str


class ClassicDebriefView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session: ClassicSessionView
    matb_metrics: dict[str, object]
    hrv: dict[str, object]
    selected_for_visit: bool


class ClassicArtifactView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    relative_path: str
    sha256: str
    size_bytes: int
    created_at: datetime | None = None

    @field_validator("created_at", mode="after")
    @classmethod
    def serialize_created_at_as_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class ClassicScenarioView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    workload_level: WorkloadLevel


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AbortClassicSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")


class SelectClassicAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")


class PolarScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: float = Field(default=5.0, ge=0.1, le=30.0, allow_inf_nan=False)


class PolarConnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_token: str = Field(min_length=1, max_length=256)


class PolarDeviceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_token: str
    display_name: str
    rssi: int | None
    is_polar_h10: bool
    heart_rate_service_advertised: bool
    token_expires_at_utc_ns: str

    @field_validator("token_expires_at_utc_ns", mode="before")
    @classmethod
    def stringify_expiry_nanoseconds(cls, value: int | str) -> str:
        return str(value)


class PolarStatusView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    backend_name: str
    connected_device_name: str | None
    device_identifier_sha256: str | None
    battery_level: int | None
    recording: bool
    reconnect_attempts: int
    last_error_code: str | None
    preflight_ready: bool
    last_rr_at_utc_ns: str | None
    sensor_contact_detected: bool | None

    @field_validator("last_rr_at_utc_ns", mode="before")
    @classmethod
    def stringify_last_rr_nanoseconds(cls, value: int | str | None) -> str | None:
        return None if value is None else str(value)


class PolarPreflightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: float = Field(default=8.0, ge=0.1, le=30.0, allow_inf_nan=False)


class PolarPreflightView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready: bool
    heart_rate_bpm: int | None
    rr_count: int
    sensor_contact_detected: bool | None
    battery_level: int | None
    measured_at_utc_ns: str
    reason_code: str | None

    @field_validator("measured_at_utc_ns", mode="before")
    @classmethod
    def stringify_measurement_nanoseconds(cls, value: int | str) -> str:
        return str(value)


class PolarCapabilitiesView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supported_os: bool
    platform: str
    backend_name: str
    bleak_version: str | None
    heart_rate_service_uuid: str
    heart_rate_measurement_uuid: str
    requirements: tuple[str, ...]


__all__ = [
    "AbortClassicSession",
    "ClassicArtifactView",
    "ClassicDebriefView",
    "ClassicScenarioView",
    "ClassicSessionView",
    "CreateClassicSession",
    "EmptyRequest",
    "PolarCapabilitiesView",
    "PolarConnectRequest",
    "PolarDeviceView",
    "PolarPreflightRequest",
    "PolarPreflightView",
    "PolarScanRequest",
    "PolarStatusView",
    "PreparedClassicSession",
    "SelectClassicAttempt",
    "WorkloadLevel",
]
