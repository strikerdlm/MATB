"""Strict API contracts for the MATB-FAC OpenMATB controller."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.participant_ids import PARTICIPANT_ID_PATTERN

Lifecycle = Literal[
    "INSTRUCTIONS", "READY", "STARTING", "RUNNING", "PAUSED",
    "AWAITING_SCALE", "BETWEEN_BLOCKS", "COMPLETE", "ABORTED", "FAILED", "INTERRUPTED",
]
Profile = Literal["PRACTICE", "LOW", "MEDIUM", "HIGH"]
HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]


class VisualProfilePalette(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_background: HexColor
    panel_background: HexColor
    instrument_background: HexColor
    panel_header: HexColor
    panel_header_text: HexColor
    control_background: HexColor
    control_foreground: HexColor
    text: HexColor
    muted_text: HexColor
    border: HexColor
    grid: HexColor
    accent: HexColor
    safe: HexColor
    warning: HexColor
    critical: HexColor
    disabled: HexColor


class VisualProfileMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_width: float = Field(ge=1, le=6)
    panel_radius: float = Field(ge=0, le=24)
    corner_mark_ratio: float = Field(ge=0, le=0.2)


class TrackingAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    panel: HexColor
    axis: HexColor
    grid: HexColor
    target: HexColor
    target_fill: HexColor
    cursor: HexColor
    cursor_outside: HexColor
    show_panel: bool
    show_grid: bool
    closed_target_border: bool


class SystemMonitoringAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    panel: HexColor
    lamp_1: HexColor
    lamp_2: HexColor
    lamp_3: HexColor
    lamp_4: HexColor
    lamp_off: HexColor
    lamp_border: HexColor
    lamp_shape: Literal["rectangle", "circle"]
    scale: HexColor
    pointer: HexColor
    feedback_positive: HexColor
    feedback_negative: HexColor


class CommunicationsAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    panel: HexColor
    display_background: HexColor
    display_border: HexColor
    active: HexColor
    inactive: HexColor
    positive: HexColor
    negative: HexColor
    show_display_bezel: bool


class ResourceManagementAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    panel: HexColor
    tank_1: HexColor
    tank_2: HexColor
    tank_3: HexColor
    tank_4: HexColor
    tank_5: HexColor
    tank_6: HexColor
    fluid: HexColor
    pipe_on: HexColor
    pipe_off: HexColor
    pump_on: HexColor
    pump_off: HexColor
    pump_failure: HexColor
    tolerance: HexColor
    meter: HexColor
    show_pump_ring: bool


class WorkloadAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    panel: HexColor
    scale: HexColor
    marker: HexColor


class VisualProfileModules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracking: TrackingAppearance
    system_monitoring: SystemMonitoringAppearance
    communications: CommunicationsAppearance
    resource_management: ResourceManagementAppearance
    workload: WorkloadAppearance


class VisualProfileDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["openmatb-visual-profile-v1"]
    profile_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    label: str = Field(min_length=3, max_length=100)
    geometry_policy: Literal["preserve_openmatb_v1"]
    palette: VisualProfilePalette
    metrics: VisualProfileMetrics
    modules: VisualProfileModules


class VisualProfileIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    paths: list[str]
    ratio: float
    minimum: float


class VisualProfileValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    publishable: bool
    errors: list[VisualProfileIssue]
    warnings: list[VisualProfileIssue]
    unacknowledged_warning_codes: list[str]


class OpenMatbVisualProfileView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    version: str
    label: str
    status: Literal["draft", "published"]
    schema_version: Literal["openmatb-visual-profile-v1"]
    sha256: str
    payload: VisualProfileDocument
    validation: VisualProfileValidation
    warning_acknowledgements: list[str]
    bundled: bool
    created_at: datetime
    published_at: datetime | None


class CloneVisualProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    label: str = Field(min_length=3, max_length=100)


class UpdateVisualProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: VisualProfileDocument
    warning_acknowledgements: list[str] = Field(default_factory=list, max_length=32)


class PublishVisualProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warning_acknowledgements: list[str] = Field(default_factory=list, max_length=32)


class ImportVisualProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: VisualProfileDocument


class VisualProfilePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_index: int = Field(default=1, ge=0, le=15)
    windowed: bool = True


class VisualProfilePreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lifecycle: Literal["IDLE", "STARTING", "RUNNING", "FAILED"]
    profile_id: str | None = None
    profile_version: str | None = None
    profile_sha256: str | None = None
    pid: int | None = None
    artifact_root: str | None = None
    last_error: str | None = None


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
    attempt_id: str | None = None
    model_config = ConfigDict(extra="forbid")
    execution_purpose: Literal["practice", "study"]
    participant_id: str = Field(pattern=PARTICIPANT_ID_PATTERN)
    visit_ordinal: int = Field(ge=1, le=16)
    preset_id: str = "matb-fac-standard"
    preset_version: str = "1.0.0"
    instruction_protocol_id: str = "matb-fac-es-419"
    instruction_version: str = "1.0.0"
    visual_theme: Literal["classic", "cockpit", "fac_modern"] | None = None
    visual_profile_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")
    visual_profile_version: str | None = Field(default=None, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    display_index: int = Field(default=1, ge=0, le=15)

    @model_validator(mode="after")
    def visual_selection_is_unambiguous(self):
        has_profile_id = self.visual_profile_id is not None
        has_profile_version = self.visual_profile_version is not None
        if has_profile_id != has_profile_version:
            raise ValueError("visual_profile_id and visual_profile_version must be provided together")
        if self.visual_theme is not None and has_profile_id:
            raise ValueError("visual_theme and visual profile selection are mutually exclusive")
        return self


class PreparedOpenMatbSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session: "OpenMatbSessionView"
    controller_lease: str
    participant_token: str


class OpenMatbSessionView(BaseModel):
    study_assignment_id: str | None = None
    purpose_provenance_id: str | None = None
    model_config = ConfigDict(extra="forbid")
    execution_purpose: Literal["practice", "study"] = "study"
    locale: str = "es-419"
    id: str
    participant_id: str = Field(pattern=PARTICIPANT_ID_PATTERN)
    visit_ordinal: int
    visit_code: str
    scheduled_day: int
    lifecycle: Lifecycle
    block_order: list[Profile]
    current_block_index: int = Field(ge=0)
    active_block: Profile | None
    active_block_instance_id: str | None = None
    evidence_processing: bool = False
    native_recovery_required: bool = False
    preset_id: str
    preset_version: str
    preset_sha256: str
    instruction_protocol: InstructionProtocolView
    visit_instruction: str
    visual_theme: str
    visual_profile_id: str | None
    visual_profile_version: str | None
    visual_profile_schema_version: str | None
    visual_profile_sha256: str | None
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
    questionnaire_attempt_id: str | None = None
    model_config = ConfigDict(extra="forbid")
    # Optional only for historical sessions created before attempt binding.
    block_instance_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
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
