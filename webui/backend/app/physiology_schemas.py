"""Strict HTTP contracts for the optional Polar H10 component."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from matb_integration.physiology.contracts import (
    PolarArtifactManifestV1,
    PolarCaptureV1,
    PolarDeviceCapabilitiesV1,
)


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScanRequest(StrictBody):
    timeout_seconds: float = Field(default=5.0, ge=0.25, le=30.0)


class PolarDeviceView(StrictBody):
    device_token: str
    alias: str
    connectable: bool | None
    rssi: int | None
    broadcast_hr_bpm: int | None
    broadcast_contact: bool | None
    token_expires_in_seconds: int


class ConnectRequest(StrictBody):
    device_token: str = Field(min_length=20, max_length=200)


class ConnectionView(StrictBody):
    connected: bool
    device_alias: str | None
    capabilities: PolarDeviceCapabilitiesV1 | None


class CaptureSettings(StrictBody):
    ecg_sample_rate_hz: Literal[130] = 130
    ecg_resolution_bits: Literal[14] = 14
    acc_sample_rate_hz: Literal[25, 50, 100, 200] = 50
    acc_resolution_bits: Literal[16] = 16
    acc_range_g: Literal[2, 4, 8] = 2


class CreateCaptureRequest(StrictBody):
    attempt_id: str | None = None
    execution_purpose: Literal["practice", "study"]
    participant_pseudonym: str = Field(pattern=r"^P[0-9]{2,6}$")
    matb_session_kind: Literal["openmatb", "liftoff", "suas", "generic"]
    matb_session_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    settings: CaptureSettings = Field(default_factory=CaptureSettings)


class PreparedCapture(StrictBody):
    capture: PolarCaptureV1
    controller_lease: str


class EmptyRequest(StrictBody):
    pass


class MarkerRequest(StrictBody):
    label: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def bounded_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        import json
        if len(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")) > 4096:
            raise ValueError("marker payload exceeds 4096 UTF-8 bytes")
        return value


class ArtifactInventory(StrictBody):
    capture_id: str
    state: Literal["none", "partial", "finalized", "incomplete"]
    manifest: PolarArtifactManifestV1 | None
    partial_files: list[str]


class PhysiologyAnalysisView(StrictBody):
    capture_id: str
    valid: bool
    reason: str | None
    phase_window_seconds: Literal[300] = 300
    phases: list[dict[str, Any]]
    workload_responses: list[dict[str, Any]]
    interpretation: Literal["descriptive_only_no_workload_classification"] = "descriptive_only_no_workload_classification"


class InternalRecordingGate(StrictBody):
    qualified: Literal[False] = False
    code: Literal["polar_internal_recording_not_qualified"] = "polar_internal_recording_not_qualified"
    message: str = "Internal H10 recording is gated pending license and physical-hardware qualification."
