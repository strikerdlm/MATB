"""Capture packaging and task payloads; event/timing envelopes remain unchanged."""
from __future__ import annotations

import json
from typing import Any, Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

TASKS = ("sysmon", "track", "communications", "resman", "genericscales")
SHA = r"^[0-9a-f]{64}$"
DERIVATION_VERSION = "classic-evidence-1.1-preflight1"
MAX_JSONL_LINE_BYTES = 256 * 1024
MAX_STREAM_BYTES = 256 * 1024 * 1024
MAX_STREAM_RECORDS = 500_000


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def strict_json(content: bytes | str) -> Any:
    def invalid(value: str) -> None:
        raise ValueError(f"nonfinite JSON value: {value}")
    def pairs(items: list[tuple[str, Any]]) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(content, parse_constant=invalid, object_pairs_hook=pairs)


class ArtifactV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sha256: str = Field(pattern=SHA)
    size_bytes: int = Field(ge=0)
    records: int | None = Field(default=None, ge=0)


class CaptureManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["1.0"] = "1.0"
    capture_id: str
    session_id: str
    block_instance_id: str
    parent_session_id: str | None = None
    participant_id: str | None = None
    visit_ordinal: int | None = Field(default=None, ge=1)
    condition: str = "UNSPECIFIED"
    execution_purpose: Literal["study", "practice", "exploration"] = "exploration"
    scenario_sha256: str = Field(pattern=SHA)
    profile_id: str
    component_version: str
    source_commit: str
    source_dirty: bool | None
    scenario_manifest_status: str
    tasks: list[str]
    completion: Literal["recording", "completed", "interrupted", "failed"]
    failure_reason: str | None = None
    artifacts: dict[str, ArtifactV1]
    clocks: dict[str, str]

    @model_validator(mode="after")
    def identities(self) -> "CaptureManifestV1":
        for value in (self.capture_id, self.session_id, self.block_instance_id):
            if str(UUID(value)) != value:
                raise ValueError("capture, session and block IDs must be canonical UUIDs")
        if self.capture_id != str(uuid5(UUID(self.session_id), "classic-capture-1")):
            raise ValueError("capture ID does not match native session identity")
        if not self.profile_id or not self.component_version or not self.condition:
            raise ValueError("profile, component version and condition are required")
        if len(set(self.tasks)) != len(self.tasks) or any(t not in TASKS for t in self.tasks):
            raise ValueError("task list must contain unique classic task identifiers")
        if self.execution_purpose == "study" and (not self.participant_id or self.visit_ordinal is None):
            raise ValueError("study capture requires participant and visit identity")
        allowed = {"events", "timing", "scenario_manifest", "legacy_csv", "runtime_envelope"}
        if set(self.artifacts) - allowed:
            raise ValueError("unsupported evidence artifact role")
        if self.completion != "recording" and not {"events", "timing"} <= set(self.artifacts):
            raise ValueError("sealed capture requires event and timing integrity records")
        return self


class RuntimePayloadV1(BaseModel):
    """Lossless native row projection plus directly recorded task context.

    Values stay in native units. Decoded opportunity objects are validated and
    identified separately; they are not extracted from a compatibility CSV.
    """
    model_config = ConfigDict(extra="forbid", strict=True)
    payload_version: Literal["1.0"] = "1.0"
    block_instance_id: str
    record_type: str
    module: str
    address: str
    value: Any
    native_opportunity_id: str | None = None
    opportunity: dict[str, Any] | None = None
    automation_active: bool | None = None
    sample_interval_ms: float | int | None = None
    runtime_event_id: str | None = None
    completion: str | None = None
    compatibility_row: dict[str, str] | None = None

    @model_validator(mode="after")
    def validate_task_record(self) -> "RuntimePayloadV1":
        UUID(self.block_instance_id)
        canonical_bytes(self.value)
        if self.opportunity is not None:
            op = self.opportunity
            if (self.module, self.address) not in {("sysmon", "opportunity"), ("communications", "comm_opportunity_v1")}:
                raise ValueError("opportunity payload is attached to the wrong native record")
            if strict_json(self.value) != op:
                raise ValueError("decoded opportunity differs from the original native value")
            if not self.native_opportunity_id or op.get("opportunity_id") != self.native_opportunity_id:
                raise ValueError("opportunity identity is required")
            phases = {"opened", "closed", "rejected"} if self.module == "sysmon" else {
                "opened", "presentation_started", "response_window_opened", "closed", "invalidated"}
            if op.get("phase") not in phases:
                raise ValueError("unsupported opportunity phase")
            if self.module == "sysmon" and type(op.get("target")) is not bool:
                raise ValueError("SYSMON target flag is required")
            if self.module == "communications" and op.get("destination") not in {"own", "other"}:
                raise ValueError("COMM destination is required")
            canonical_bytes(op)
        return self


def opportunity_uuid(session_id: str, task: str, native_id: str) -> UUID:
    return uuid5(UUID(session_id), json.dumps(["classic-opportunity-1", task, native_id]))


def event_type(payload: RuntimePayloadV1) -> str:
    if payload.record_type == "capture_lifecycle":
        return f"block.{payload.value}"
    if payload.record_type == "task_lifecycle":
        return f"{payload.module}.task.{payload.value}"
    if payload.opportunity:
        return f"{payload.module}.opportunity.{payload.opportunity['phase']}"
    if payload.record_type in {"parameter", "event"} and payload.address == "automaticsolver":
        return f"{payload.module}.automation.changed"
    if payload.record_type == "input":
        return f"{payload.module or 'runtime'}.input"
    if payload.record_type == "performance":
        return f"{payload.module}.{'probe' if payload.module == 'genericscales' else 'sample'}"
    return "runtime.record"
