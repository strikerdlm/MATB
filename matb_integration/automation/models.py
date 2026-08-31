"""Strict contracts for adaptive task allocation and its audit trail."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, ClassVar, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_serializer,
    field_validator,
    model_validator,
)

from matb_integration.contracts._immutability import deep_freeze_json, deep_thaw_json


TaskName = Literal["sysmon", "communications", "track", "resman"]
AllocationAction = Literal["engage", "disengage"]
HandoffTrigger = Literal["offered", "requested", "threshold", "scheduled", "forced"]

_SEMVER = (
    r"^(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_IDENTIFIER = r"^[a-z][a-z0-9]*(?:[-.][a-z0-9]+)*$"


class TaskSnapshot(BaseModel):
    """Policy input captured before any allocation decision."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    task: TaskName
    scenario_time_ns: int = Field(ge=0)
    performance: float | None = Field(default=None, ge=0.0, le=1.0)
    workload_estimate: float | None = Field(default=None, ge=0.0, le=1.0)
    automation_active: bool
    source_event_id: UUID
    metrics: Mapping[str, float] = Field(default_factory=dict)

    @field_validator("source_event_id", mode="before")
    @classmethod
    def parse_uuid(cls, value: object) -> object:
        return UUID(value) if isinstance(value, str) else value

    @field_validator("metrics")
    @classmethod
    def finite_metrics(cls, value: Mapping[str, float]) -> Mapping[str, float]:
        import math

        if any(isinstance(item, bool) or not math.isfinite(item) for item in value.values()):
            raise ValueError("snapshot metrics must be finite numbers")
        return deep_freeze_json(value)

    @field_serializer("metrics")
    def serialize_metrics(self, value: Mapping[str, float]) -> dict[str, float]:
        return deep_thaw_json(value)


class AutomationProposal(BaseModel):
    """One allocation proposal; it contains no automation-quality parameters."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    proposal_id: UUID
    policy_id: str = Field(pattern=_IDENTIFIER)
    policy_version: str = Field(pattern=_SEMVER)
    rule_id: str = Field(min_length=1)
    task: TaskName
    action: AllocationAction
    trigger: HandoffTrigger
    forced: bool
    reason: str = Field(min_length=1)
    identity_key: str = Field(min_length=1)

    @field_validator("proposal_id", mode="before")
    @classmethod
    def parse_uuid(cls, value: object) -> object:
        return UUID(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_identity(self) -> "AutomationProposal":
        if self.trigger == "forced" and not self.forced:
            raise ValueError("forced trigger requires forced=True")
        expected = self.expected_id(
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            rule_id=self.rule_id,
            task=self.task,
            action=self.action,
            trigger=self.trigger,
            forced=self.forced,
            identity_key=self.identity_key,
        )
        if self.proposal_id != expected:
            raise ValueError("proposal_id does not match deterministic identity")
        return self

    @staticmethod
    def expected_id(
        *,
        policy_id: str,
        policy_version: str,
        rule_id: str,
        task: str,
        action: str,
        trigger: str,
        forced: bool,
        identity_key: str,
    ) -> UUID:
        identity = json.dumps(
            [
                "matb.automation",
                "proposal",
                policy_id,
                policy_version,
                rule_id,
                task,
                action,
                trigger,
                forced,
                identity_key,
            ],
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        return uuid5(NAMESPACE_URL, identity)

    @classmethod
    def create(cls, **values: Any) -> "AutomationProposal":
        proposal_id = cls.expected_id(
            policy_id=values["policy_id"],
            policy_version=values["policy_version"],
            rule_id=values["rule_id"],
            task=values["task"],
            action=values["action"],
            trigger=values["trigger"],
            forced=values["forced"],
            identity_key=values["identity_key"],
        )
        return cls(proposal_id=proposal_id, **values)


class HandoffResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    handoff_id: UUID
    proposal_id: UUID
    task: TaskName
    trigger: HandoffTrigger
    forced: bool
    action: AllocationAction
    applied: bool
    automation_active_before: bool
    automation_active_after: bool
    scenario_time_ns: int = Field(ge=0)
    reason: str

    @model_validator(mode="after")
    def validate_transition(self) -> "HandoffResult":
        desired = self.action == "engage"
        expected_applied = desired != self.automation_active_before
        expected_after = desired if expected_applied else self.automation_active_before
        if self.applied != expected_applied or self.automation_active_after != expected_after:
            raise ValueError(
                "handoff action, applied flag, and automation state are contradictory"
            )
        if self.trigger == "forced" and not self.forced:
            raise ValueError("forced trigger requires forced=True")
        return self


class AutomationAuditRecord(BaseModel):
    """Hash-chained audit event for policy inputs, decisions, and handoffs."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    SCHEMA_VERSION: ClassVar[str] = "1.0"

    schema_version: Literal["1.0"] = "1.0"
    engine_version: str = Field(pattern=_SEMVER)
    session_id: UUID
    record_id: UUID
    sequence: int = Field(ge=1)
    event_type: Literal[
        "policy_input",
        "policy_decision",
        "automation_action",
        "handoff",
        "handoff_consequence",
    ]
    scenario_time_ns: int = Field(ge=0)
    payload: Mapping[str, JsonValue]
    previous_record_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("session_id", "record_id", mode="before")
    @classmethod
    def parse_uuid(cls, value: object) -> object:
        return UUID(value) if isinstance(value, str) else value

    @field_validator("payload")
    @classmethod
    def freeze_payload(cls, value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        return deep_freeze_json(value)

    @field_serializer("payload")
    def serialize_payload(self, value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
        return deep_thaw_json(value)

    @staticmethod
    def expected_record_id(
        *,
        engine_version: str,
        session_id: UUID | str,
        sequence: int,
        event_type: str,
    ) -> UUID:
        identity = json.dumps(
            [
                "matb.automation",
                "audit",
                AutomationAuditRecord.SCHEMA_VERSION,
                engine_version,
                str(UUID(str(session_id))),
                sequence,
                event_type,
            ],
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        return uuid5(NAMESPACE_URL, identity)

    @staticmethod
    def expected_record_sha256(material: dict[str, Any]) -> str:
        encoded = json.dumps(
            material,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @model_validator(mode="after")
    def validate_identity_and_hash(self) -> "AutomationAuditRecord":
        expected_id = self.expected_record_id(
            engine_version=self.engine_version,
            session_id=self.session_id,
            sequence=self.sequence,
            event_type=self.event_type,
        )
        if self.record_id != expected_id:
            raise ValueError("record_id does not match deterministic audit identity")
        material = {
            "schema_version": self.schema_version,
            "engine_version": self.engine_version,
            "session_id": str(self.session_id),
            "record_id": str(self.record_id),
            "sequence": self.sequence,
            "event_type": self.event_type,
            "scenario_time_ns": self.scenario_time_ns,
            "payload": deep_thaw_json(self.payload),
            "previous_record_sha256": self.previous_record_sha256,
        }
        if self.record_sha256 != self.expected_record_sha256(material):
            raise ValueError("record_sha256 does not match canonical audit material")
        return self
