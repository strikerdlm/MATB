"""Strict transport models for the native simulation API.

The runtime and browser share these names as a deliberately small contract.
All models reject unknown keys so accidental metadata or operator free text
cannot cross the API boundary.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
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


class CreateSimulationSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_id: str = Field(pattern=PARTICIPANT_ID_PATTERN)
    visit_ordinal: int = Field(ge=1, le=16)
    scenario_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    locale: Locale


class CreateTechnicalSimulationSession(BaseModel):
    """Strict contract for a direct, non-participant interactive launch."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    block_id: WorkloadProfile
    locale: Locale


class SessionView(BaseModel):
    """Public session metadata that never includes a controller lease."""

    model_config = ConfigDict(extra="forbid")

    id: str
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
