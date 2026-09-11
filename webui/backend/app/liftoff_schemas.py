"""Strict public transport contracts for Liftoff collection."""

from __future__ import annotations

from datetime import datetime
import math
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.participant_ids import PARTICIPANT_ID_PATTERN

LiftoffAction: TypeAlias = Literal[
    "baseline/start",
    "baseline/finish",
    "task/start",
    "task/finish",
    "recovery/start",
    "recovery/finish",
]


class LiftoffConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    liftoff_build: str = Field(min_length=1, max_length=64)
    track_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
    drone_id: str = Field(min_length=1, max_length=128)
    flight_mode: str = Field(min_length=1, max_length=32)
    camera_angle_deg: float = Field(ge=0, le=90, allow_inf_nan=False)
    fov_deg: float = Field(gt=0, le=180, allow_inf_nan=False)
    rates_profile: str = Field(min_length=1, max_length=64)
    controller_model: str = Field(min_length=1, max_length=128)
    controller_firmware: str = Field(min_length=1, max_length=64)
    resolution: str = Field(pattern=r"^[0-9]{3,5}x[0-9]{3,5}$")
    refresh_rate_hz: int = Field(ge=30, le=500)
    graphics_preset: str = Field(min_length=1, max_length=32)
    damage_enabled: bool
    battery_enabled: bool
    telemetry_profile: Literal["liftoff-telemetry-all-v1"]


class CreateLiftoffSession(BaseModel):
    attempt_id: str | None = None
    model_config = ConfigDict(extra="forbid")
    execution_purpose: Literal["practice", "study"]
    locale: Literal["es-419", "en"] = "es-419"

    participant_id: str = Field(pattern=PARTICIPANT_ID_PATTERN)
    visit_ordinal: int = Field(ge=1, le=16)
    configuration: LiftoffConfiguration
    polar_recording_confirmed: bool
    performance_only_reason: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")

    @model_validator(mode="after")
    def require_performance_only_reason(self) -> "CreateLiftoffSession":
        if not self.polar_recording_confirmed and self.performance_only_reason is None:
            raise ValueError("performance_only_reason is required when Polar is not confirmed")
        if self.polar_recording_confirmed and self.performance_only_reason is not None:
            raise ValueError("performance_only_reason is only valid without Polar")
        return self


class LiftoffSessionView(BaseModel):
    purpose_provenance_id: str | None = None
    model_config = ConfigDict(extra="forbid")
    execution_purpose: Literal["practice", "study"] = "study"
    locale: Literal["es-419", "en"] = "es-419"

    id: str
    participant_id: str
    visit_id: int
    visit_ordinal: int
    visit_code: str
    attempt_number: int
    protocol_id: str
    protocol_version: str
    liftoff_build: str
    track_id: str
    telemetry_profile: str
    status: str
    validity: str
    sync_quality: str
    polar_recording_confirmed: bool
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    interrupted_at: datetime | None = None


class PreparedLiftoffSession(LiftoffSessionView):
    controller_lease: str


class LiftoffReadinessView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready: bool
    valid_packets: int = Field(ge=0)
    invalid_packet_count: int = Field(ge=0)
    overflow_count: int = Field(ge=0)
    duplicate_time_count: int = Field(ge=0)
    out_of_order_count: int = Field(ge=0)
    clock_step_detected: bool


class VisibleResultsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid_lap_times_s: list[float] = Field(max_length=100)
    invalid_laps: int = Field(ge=0, le=1000)
    observer_restart_count: int = Field(ge=0, le=1000)
    screenshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_lap_times(self) -> "VisibleResultsRequest":
        if any(not math.isfinite(value) or value <= 0 for value in self.valid_lap_times_s):
            raise ValueError("valid lap times must be positive")
        return self


class QuestionnairesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kss: int = Field(ge=1, le=9)
    mental_demand: float = Field(ge=0, le=100, allow_inf_nan=False)
    physical_demand: float = Field(ge=0, le=100, allow_inf_nan=False)
    temporal_demand: float = Field(ge=0, le=100, allow_inf_nan=False)
    performance: float = Field(ge=0, le=100, allow_inf_nan=False)
    effort: float = Field(ge=0, le=100, allow_inf_nan=False)
    frustration: float = Field(ge=0, le=100, allow_inf_nan=False)


class PhysiologyLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["linked", "pending", "missing"]
    sync_quality: Literal["good", "acceptable", "poor", "missing"]
    hrv_measurement_id: str | None = Field(default=None, min_length=1, max_length=128)
    hrv_file_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class PhysiologyLinkView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["linked", "pending", "missing"]
    hrv_measurement_id: str | None = None
    hrv_file_sha256: str | None = None
    sync_quality: Literal["good", "acceptable", "poor", "missing"]
    contract_version: str = "task-session-hrv-v1"


class AbortRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TelemetryQualityView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packet_count: int
    expected_packet_count: int
    loss_pct: float
    observed_rate_hz: float
    maximum_gap_s: float
    invalid_packet_count: int
    overflow_count: int
    nonmonotonic_count: int
    clock_step_detected: bool
    validity: str
    reason_codes: tuple[str, ...]


class LiftoffDebriefView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: str
    validity: str
    sync_quality: str
    quality: TelemetryQualityView
    primary: dict[str, object]


class LiftoffArtifactView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    relative_path: str
    sha256: str
    size_bytes: int
    created_at: datetime | None = None


class LiftoffProtocolView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_id: str
    protocol_version: str
    schedule_sha256: str
    telemetry_profile: Literal["liftoff-telemetry-all-v1"]
    visits: list[dict[str, object]]


__all__ = [
    "AbortRequest",
    "CreateLiftoffSession",
    "EmptyRequest",
    "LiftoffAction",
    "LiftoffArtifactView",
    "LiftoffConfiguration",
    "LiftoffDebriefView",
    "LiftoffProtocolView",
    "LiftoffReadinessView",
    "LiftoffSessionView",
    "PhysiologyLinkRequest",
    "PhysiologyLinkView",
    "PreparedLiftoffSession",
    "QuestionnairesRequest",
    "TelemetryQualityView",
    "VisibleResultsRequest",
]
