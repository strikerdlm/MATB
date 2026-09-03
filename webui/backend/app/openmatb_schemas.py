"""Strict API contracts for the MATB-FAC classic OpenMATB controller."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Lifecycle = Literal[
    "INSTRUCTIONS", "READY", "STARTING", "RUNNING", "PAUSED",
    "AWAITING_SCALE", "BETWEEN_BLOCKS", "COMPLETE", "ABORTED", "FAILED", "INTERRUPTED",
]
Profile = Literal["PRACTICE", "LOW", "MEDIUM", "HIGH"]


class ProfileSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_seconds: int = Field(ge=60, le=3600)
    difficulty: float = Field(ge=0, le=1)
    track_target_proportion: float = Field(ge=0.05, le=1)
    resman_loss_per_min: int = Field(ge=0, le=2000)
    isa_probe_interval_sec: int = Field(ge=15, le=600)

    @field_validator("isa_probe_interval_sec")
    @classmethod
    def interval_inside_block(cls, value: int, info):
        duration = info.data.get("duration_seconds")
        if isinstance(duration, int) and value > duration:
            raise ValueError("ISA interval cannot exceed block duration")
        return value


class PresetSetView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset_id: str
    version: str
    label_es: str
    status: Literal["draft", "published"]
    sha256: str
    profiles: dict[Profile, ProfileSettings]


class ClonePresetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    label_es: str = Field(min_length=3, max_length=100)


class UpdatePresetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profiles: dict[Profile, ProfileSettings]

    @field_validator("profiles")
    @classmethod
    def all_profiles(cls, value):
        required = {"PRACTICE", "LOW", "MEDIUM", "HIGH"}
        if set(value) != required:
            raise ValueError("all four profiles are required")
        return value


class CloneInstructionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")


class UpdateInstructionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=3, max_length=160)
    steps: list[str] = Field(min_length=1, max_length=20)
    task_instructions: dict[str, str]
    visit_instructions: dict[str, str]

    @field_validator("steps")
    @classmethod
    def bounded_steps(cls, value):
        if any(not step.strip() or len(step) > 500 for step in value):
            raise ValueError("instruction steps must contain 1..500 characters")
        return value

    @field_validator("task_instructions")
    @classmethod
    def classic_tasks(cls, value):
        if set(value) != {"TRACK", "COMM", "SYSMON", "RESMAN"} or any(not text.strip() or len(text) > 500 for text in value.values()):
            raise ValueError("instructions for TRACK, COMM, SYSMON, and RESMAN are required")
        return value

    @field_validator("visit_instructions")
    @classmethod
    def visit_steps(cls, value):
        if "DEFAULT" not in value or any(not code.strip() or not text.strip() or len(text) > 500 for code, text in value.items()):
            raise ValueError("visit instructions require a DEFAULT entry and 1..500 characters per entry")
        return value


class InstructionProtocolView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_id: str
    version: str
    locale: str
    status: Literal["draft", "published"]
    sha256: str
    title: str
    steps: list[str]
    task_instructions: dict[str, str]
    visit_instructions: dict[str, str]


class OpenMatbReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ready: bool
    platform: str
    python_executable: str
    openmatb_entrypoint: str
    display_index_default: int
    checks: dict[str, bool]
    warnings: list[str]


class CreateOpenMatbSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    participant_id: str = Field(pattern=r"^P[0-9]{2,6}$")
    visit_ordinal: int = Field(ge=1, le=16)
    preset_id: str = "matb-fac-standard"
    preset_version: str = "1.0.0"
    instruction_protocol_id: str = "matb-fac-es-419"
    instruction_version: str = "1.0.0"
    display_index: int = Field(default=1, ge=0, le=15)


class PreparedOpenMatbSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session: "OpenMatbSessionView"
    controller_lease: str
    participant_token: str


class OpenMatbSessionView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    participant_id: str
    visit_ordinal: int
    visit_code: str
    scheduled_day: int
    lifecycle: Lifecycle
    block_order: list[Profile]
    current_block_index: int = Field(ge=0)
    active_block: Profile | None
    preset_id: str
    preset_version: str
    preset_sha256: str
    instruction_protocol: InstructionProtocolView
    visit_instruction: str
    display_index: int
    scores: dict[str, dict[str, object]]
    active_pid: int | None
    last_error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AbortRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="operator_abort", pattern=r"^[a-z0-9_-]{3,64}$")


class WorkloadScaleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nasa_tlx: dict[str, int]
    bedford: int = Field(ge=1, le=10)

    @field_validator("nasa_tlx")
    @classmethod
    def valid_tlx(cls, value):
        expected = {"mental_demand", "physical_demand", "temporal_demand", "performance", "effort", "frustration"}
        if set(value) != expected or any(score < 0 or score > 100 or score % 5 for score in value.values()):
            raise ValueError("NASA-TLX requires six 0..100 ratings in steps of 5")
        return value


PreparedOpenMatbSession.model_rebuild()
