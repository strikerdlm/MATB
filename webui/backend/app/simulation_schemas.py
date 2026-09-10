"""Strict transport models for the native simulation API.

The runtime and browser share these names as a deliberately small contract.
All models reject unknown keys so accidental metadata or operator free text
cannot cross the API boundary.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import TypeAliasType

from app.participant_ids import PARTICIPANT_ID_PATTERN


Locale: TypeAlias = Literal["en", "es-CO"]
SessionMode: TypeAlias = Literal["research", "interactive_technical"]
RecordClass: TypeAlias = Literal["research", "technical_only"]
WorkloadProfile: TypeAlias = Literal["PRACTICE", "LOW", "MEDIUM", "HIGH"]
Lifecycle: TypeAlias = Literal[
    "PREPARED",
    "RUNNING",
    "PAUSED",
    "FINISHED",
    "ABORTED",
    "INTERRUPTED",
]
FinishDisposition: TypeAlias = Literal["complete", "abort"]

# Recursive JSON values are used for opaque, structured payloads such as
# manifests, metrics, and command results.  Free-form strings are still
# bounded by the surrounding contract; this alias only describes JSON shape.
# ``TypeAliasType`` gives Pydantic a named recursive definition.  A plain
# ``TypeAlias`` with a quoted self-reference recurses while Pydantic builds a
# schema on current Pydantic 2 releases.
JsonValue = TypeAliasType(
    "JsonValue",
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"],
)


class TrafficConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["off", "live", "recorded"] = "off"
    provider: Literal["adsb.lol", "opensky"] = "adsb.lol"
    recording_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    recording_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    @model_validator(mode="after")
    def require_recording(self):
        if self.mode == "recorded" and (not self.recording_id or not self.recording_sha256):
            raise ValueError("recorded traffic requires an immutable recording")
        return self


class PresentationControls(BaseModel):
    model_config = ConfigDict(extra="forbid")
    smooth_camera: bool = False
    contact_cycling: bool = False
    adjustable_layers: bool = False


class PresentationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1, 2] = 1
    interpolation_policy: Literal["linear-320-v1", "none-v1"] = "linear-320-v1"
    controls: PresentationControls = Field(default_factory=PresentationControls)
    layers: list[Literal["roads", "rivers", "settlements", "boundaries", "airports"]] = Field(default_factory=lambda: ["roads", "rivers", "settlements", "boundaries", "airports"])
    traffic: TrafficConfig = Field(default_factory=TrafficConfig)
    blocks: dict[WorkloadProfile, Literal["2d", "3d"]] = Field(default_factory=dict)
    scene_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    scene_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    camera: Literal["overview", "follow", "drone"] = "overview"

    @model_validator(mode="after")
    def require_scene(self):
        if self.traffic.mode != "off" and not self.scene_id:
            raise ValueError("traffic requires a georeferenced scene")
        if "3d" in self.blocks.values() and (not self.scene_id or not self.scene_sha256):
            raise ValueError("3D requires an immutable scene package")
        if bool(self.scene_id) != bool(self.scene_sha256):
            raise ValueError("scene id and checksum must be supplied together")
        return self


class PresentationEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["aircraft", "contact", "observed"]
    id: str = Field(min_length=1, max_length=80)


class PresentationPose(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    camera_position: tuple[float, float, float]
    camera_quaternion: tuple[float, float, float, float]
    fov: float = Field(default=55, gt=0, lt=180)
    aspect: float = Field(default=1, gt=0, le=100)
    controls_target: tuple[float, float, float] | None = None

    @model_validator(mode="after")
    def normalized_quaternion(self):
        if abs(sum(v * v for v in self.camera_quaternion) - 1) > 0.001:
            raise ValueError("camera quaternion must be normalized")
        return self


class OperationalLayers(BaseModel):
    model_config = ConfigDict(extra="forbid")
    routes: bool = True
    coverage: bool = True
    contacts: bool = True
    sensors: bool = True
    labels: bool = True


class PresentationPan(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    x: float
    y: float


class PresentationMapView(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    zoom: float = Field(ge=0.75, le=6)
    pan: PresentationPan


class PresentationViewport(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    width: int = Field(gt=0, le=32768)
    height: int = Field(gt=0, le=32768)
    dpr: float = Field(gt=0, le=16)


class ResolvedPresentation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    version: Literal[2]
    condition: Literal["2d", "3d"]
    camera: Literal["overview", "follow", "drone"]
    focus: PresentationEntity | None
    aircraft_id: str | None = Field(max_length=64)
    contact_id: str | None = Field(max_length=64)
    observed_id: str | None = Field(max_length=80)
    navigation_category: Literal["aircraft", "contact", "observed"] = "aircraft"
    operational_layers: OperationalLayers
    geographic_layers: list[Literal["roads", "rivers", "settlements", "boundaries", "airports"]] = Field(max_length=5)
    pose: PresentationPose | None
    map_view: PresentationMapView
    viewport: PresentationViewport | None
    visibility: Literal["visible", "hidden", "concealed", "unavailable"]
    transition_ms: Literal[0, 600]
    interpolation_policy: Literal["linear-320-v1", "none-v1"] | None = None
    interpolation_ms: Literal[0, 320] | None = None
    visual_profile: Literal["standard-v1"]
    model_version: Literal["schematic-drone-v1-scale12"]
    scene_sha256: str | None = Field(pattern=r"^[a-f0-9]{64}$")
    capture_sha256: str | None = Field(pattern=r"^[a-f0-9]{64}$")


class PresentationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    event_id: UUID
    block_id: WorkloadProfile
    version: Literal[1, 2] = 1
    kind: Literal["ready", "camera", "render", "failure", "fallback", "selection", "navigate", "navigation_filter", "layers", "geography", "resolved", "transition_start", "transition_end", "transition_cancel", "visibility", "resize", "map_view"]
    sequence: int | None = Field(default=None, ge=0)
    client_time_ms: float | None = Field(default=None, ge=0)
    resolved: ResolvedPresentation | None = None
    state_version: int = Field(default=0, ge=0)
    simulation_time_ms: int = Field(default=0, ge=0)
    camera: Literal["overview", "follow", "drone"] = "overview"
    traffic_frame_id: str | None = Field(default=None, max_length=80)
    layers: list[str] | None = Field(default=None, max_length=16)
    aircraft_id: str | None = Field(default=None, max_length=64)
    scene_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    camera_position: tuple[float, float, float] | None = None
    camera_quaternion: tuple[float, float, float, float] | None = None
    receipt_to_render_ms: float | None = Field(default=None, ge=0, le=3600000)

    @model_validator(mode="after")
    def versioned_exposure(self):
        if self.version == 2 and (self.resolved is None or self.sequence is None or self.client_time_ms is None):
            raise ValueError("v2 requires resolved exposure and ordering metadata")
        if self.version == 1 and (self.resolved is not None or self.kind not in {"ready", "camera", "render", "failure", "fallback"}):
            raise ValueError("v1 presentation semantics cannot be extended")
        return self


class CreateSimulationSession(BaseModel):
    attempt_id: str | None = None
    execution_purpose: Literal["study"]
    model_config = ConfigDict(extra="forbid")

    participant_id: str = Field(pattern=PARTICIPANT_ID_PATTERN)
    presentation: PresentationConfig | None = None
    visit_ordinal: int = Field(ge=1, le=16)
    scenario_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    locale: Locale


class CreateTechnicalSimulationSession(BaseModel):
    """Strict contract for a direct, non-participant interactive launch."""
    execution_purpose: Literal["practice"]

    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    block_id: WorkloadProfile
    presentation: PresentationConfig | None = None
    locale: Locale


class ConsoleProfile(BaseModel):
    """Recorded identity; unknown versions remain identifiable without upgrading."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(min_length=1, max_length=80)
    version: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class SessionView(BaseModel):
    purpose_provenance_id: str | None = None
    """Public session metadata that never includes a controller lease."""

    model_config = ConfigDict(extra="forbid")

    id: str
    console_profile: ConsoleProfile | None = None
    presentation: PresentationConfig | None = None
    participant_id: str | None = Field(default=None, pattern=PARTICIPANT_ID_PATTERN)
    visit_id: int | None = Field(default=None, ge=1)
    visit_ordinal: int | None = Field(default=None, ge=1, le=16)
    scenario_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    scenario_sha256: str | None = None
    locale: Locale
    lifecycle: Lifecycle
    active_block_id: str | None = None
    validity: str = "valid"
    session_mode: SessionMode = "research"
    execution_purpose: Literal["practice", "study"] = "study"
    record_class: RecordClass = "research"
    selected_block_id: WorkloadProfile | None = None
    block_order: list[str] = Field(default_factory=list)
    protocol_phase: str = "READY_FOR_BLOCK"
    current_block_index: int = Field(default=0, ge=0)
    active_probe: dict[str, JsonValue] | None = None
    next_block_id: str | None = None
    state_version: int = Field(default=0, ge=0)
    simulation_time_ms: int = Field(default=0, ge=0)
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    interrupted_at: datetime | None = None


class PreparedSession(SessionView):
    """Session returned by prepare, carrying the one-time plaintext lease."""

    model_config = ConfigDict(extra="forbid")

    controller_lease: str


class LifecycleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Start uses block_id, pause may carry a stable reason code, and resume
    # sends an empty object.  Keeping both optional lets each endpoint share a
    # strict request model without accepting arbitrary operator text.
    block_id: str | None = Field(default=None, min_length=1, max_length=64)
    reason: str | None = Field(default=None, min_length=1, max_length=64)


class FinishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disposition: FinishDisposition = "complete"
    reason: str | None = Field(default=None, min_length=1, max_length=64)


class RecoverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_version: int = Field(ge=0)
    confirm_process_restart: bool = False


class RecoveryView(SessionView):
    model_config = ConfigDict(extra="forbid")

    controller_lease: str | None = None


class CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: UUID
    expected_state_version: int = Field(ge=0)
    kind: Literal[
        "ASSIGN_SECTOR",
        "SET_WAYPOINT",
        "HOLD",
        "RESUME_MISSION",
        "RETURN_TO_BASE",
        "ACKNOWLEDGE_ALERT",
        "INSPECT_CONTACT",
        "CLASSIFY_CONTACT",
        "SET_CONTACT_PRIORITY",
        "REPORT_CONTACT",
        "SUBMIT_ISA",
        "SUBMIT_SAGAT",
        "SUBMIT_POST_BLOCK_SCALE",
    ]
    payload: dict[str, JsonValue]


class CommandResultView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: UUID
    status: Literal["accepted", "rejected", "duplicate"]
    code: str | None = None
    message: str | None = None
    expected_state_version: int | None = Field(default=None, ge=0)
    state_version: int = Field(default=0, ge=0)
    simulation_time_ms: int = Field(default=0, ge=0)
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class ArtifactView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    relative_path: str
    sha256: str
    size_bytes: int = Field(ge=0)
    created_at: datetime | None = None


class ScenarioSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    scenario_sha256: str | None = None
    title: str | None = None
    description: str | None = None
    titles: dict[Locale, str] = Field(default_factory=dict)
    descriptions: dict[Locale, str] = Field(default_factory=dict)
    aircraft_count: int | None = Field(default=None, ge=2, le=8)
    block_order: list[str] = Field(default_factory=list)
    locales: list[Locale] = Field(default_factory=list)
    profile_details: dict[WorkloadProfile, "ScenarioProfileSummary"] = Field(default_factory=dict)


class ScenarioProfileSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_seconds: int = Field(ge=1)
    aircraft_count: int = Field(ge=1, le=8)
    contact_count: int = Field(ge=0)
    calibration_status: Literal["engineering_preset_pending_human_calibration"]


class ScenarioValidationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    scenario_id: str | None = None
    scenario_sha256: str | None = None
    summary: ScenarioSummary | None = None
    errors: list["ErrorDetail"] = Field(default_factory=list)


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    context: dict[str, JsonValue] | None = None
