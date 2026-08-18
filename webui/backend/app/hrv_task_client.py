"""Backend-only client for HRV's versioned task-session contract."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

HRV_CONTRACT_VERSION = "task-session-hrv-v1"
HRV_SCHEMA_SHA256 = "d4b837800725d9071fe98d21f34539495ba02c26f785b92d75c504bb47e201a0"
HRV_COMMIT = "0fea35b7"
PhaseLabel = Literal["baseline", "task", "recovery"]


class HrvTaskTemporaryError(RuntimeError):
    pass


class HrvTaskContractError(RuntimeError):
    pass


class PolarRecordingMetadataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["polar-task-capture-v1"]
    recorder_version: str = Field(min_length=1, max_length=64)
    capture_id: UUID
    external_session_id: UUID
    participant_id: str = Field(pattern=r"^P[0-9]{2,6}$")
    recording_start_utc: AwareDatetime
    recording_end_utc: AwareDatetime
    start_monotonic_ns: int = Field(ge=0)
    end_monotonic_ns: int = Field(gt=0)
    first_rr_received_monotonic_ns: int | None = Field(default=None, ge=0)
    last_rr_received_monotonic_ns: int | None = Field(default=None, ge=0)
    device_identifier_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    rr_count: int = Field(ge=30)
    rr_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class UtcSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: PhaseLabel
    start_utc: AwareDatetime
    end_utc: AwareDatetime


class TaskSessionHrvRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["task-session-hrv-v1"] = HRV_CONTRACT_VERSION
    external_session_id: UUID
    participant_id: str = Field(pattern=r"^P[0-9]{2,6}$")
    rr_filename: str = Field(min_length=1, max_length=255)
    rr_content: str = Field(min_length=1, max_length=5_000_000)
    rr_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    timing: PolarRecordingMetadataRequest
    segments: list[UtcSegment] = Field(min_length=3, max_length=3)


class SegmentIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: PhaseLabel
    start_idx: int
    end_idx: int


class PhaseHrvMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mean_hr_bpm: float | None
    rmssd_ms: float | None
    lnrmssd: float | None
    artifact_percentage: float
    usable_coverage_pct: float


class HrvTaskQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["good", "moderate", "poor"]
    artifact_percentage: float
    usable_rr_count: int
    reason_codes: list[str]


class TaskSessionHrvResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["task-session-hrv-v1"]
    external_session_id: UUID
    participant_id: str
    measurement_id: str
    rr_file_sha256: str
    rr_count: int
    recording_start_utc: AwareDatetime
    segment_indices: list[SegmentIndex]
    phase_metrics: dict[PhaseLabel, PhaseHrvMetrics]
    delta_lnrmssd_baseline_task: float | None
    delta_lnrmssd_task_recovery: float | None
    quality: HrvTaskQuality


class HrvTaskClient:
    def __init__(self, *, base_url: str, token: str, timeout_seconds: float = 30.0) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("invalid_hrv_api_url")
        if not token or timeout_seconds <= 0:
            raise ValueError("invalid_hrv_client_configuration")
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout_seconds

    async def analyze(self, request: TaskSessionHrvRequest) -> TaskSessionHrvResponse:
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                response = await client.post(
                    "/api/research/hrv/task-sessions/analyze",
                    json=request.model_dump(mode="json"),
                    headers=headers,
                )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise HrvTaskTemporaryError("hrv_unavailable") from exc
        if response.status_code >= 500:
            raise HrvTaskTemporaryError("hrv_unavailable")
        if response.status_code != 200:
            raise HrvTaskContractError("hrv_contract_rejected")
        try:
            return TaskSessionHrvResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise HrvTaskContractError("hrv_contract_invalid_response") from exc


__all__ = [
    "HRV_COMMIT",
    "HRV_CONTRACT_VERSION",
    "HRV_SCHEMA_SHA256",
    "HrvTaskClient",
    "HrvTaskContractError",
    "HrvTaskTemporaryError",
    "PolarRecordingMetadataRequest",
    "TaskSessionHrvRequest",
    "TaskSessionHrvResponse",
    "UtcSegment",
]
