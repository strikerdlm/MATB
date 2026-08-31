"""Immutable scientific event and timing-observation contracts.

An event states what happened in experiment order. Timing observations state
when a linked event was observed in a named clock domain. Keeping these as
separate records prevents a software dispatch timestamp from being presented
as physical stimulus onset.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, ClassVar, Literal, Mapping
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

from ._immutability import deep_freeze_json, deep_thaw_json
from .components import COMPONENT_ID_PATTERN


ScientificTimingKind = Literal[
    "scheduled",
    "dispatch_start",
    "dispatch_end",
    "physical_onset",
    "physical_input",
    "software_receipt",
    "lsl_timestamp",
    "external_trigger",
]
TimingEvidenceSource = Literal["software", "physical"]
TimingUnit = Literal["ns", "s"]
TimingMethod = Literal[
    "experiment_clock",
    "software_clock",
    "photodiode",
    "audio_loopback",
    "actuated_input",
    "device_sensor",
    "lsl_clock",
    "parallel_port",
    "serial_trigger",
]
SourceProvenanceStatus = Literal[
    "complete",
    "provisional_dirty_source_tree",
    "provisional_unverified_source_tree",
    "provisional_missing_source_commit",
]
_FULL_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_MISSING_SOURCE_COMMITS = frozenset({"unknown", "unavailable"})


def _non_empty(value: str, *, field_name: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not have surrounding whitespace")
    return value


class ScientificEventV3(BaseModel):
    """Authoritative, session-ordered scientific event envelope."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    SCHEMA_VERSION: ClassVar[str] = "3.0"

    schema_version: Literal["3.0"] = "3.0"
    session_id: UUID
    event_id: UUID
    sequence: int = Field(ge=0)
    component_id: str = Field(pattern=COMPONENT_ID_PATTERN)
    component_version: str
    task: str | None
    event_type: str
    scenario_time_ns: int = Field(ge=0)
    scenario_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_id: str
    source_commit: str = Field(
        pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64}|unknown|unavailable)$"
    )
    source_dirty: bool | None
    provenance_status: SourceProvenanceStatus
    causation_id: UUID | None = None
    correlation_id: UUID | None = None
    opportunity_id: UUID | None = None
    payload: Mapping[str, JsonValue]

    @model_validator(mode="before")
    @classmethod
    def normalize_json_schema_integer_numbers(cls, value: object) -> object:
        """Accept JSON numbers that are mathematically schema-valid integers."""

        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        for field_name in ("sequence", "scenario_time_ns"):
            raw = normalized.get(field_name)
            if type(raw) is float and math.isfinite(raw) and raw.is_integer():
                normalized[field_name] = int(raw)
        return normalized

    @field_validator(
        "session_id",
        "event_id",
        "causation_id",
        "correlation_id",
        "opportunity_id",
        mode="before",
    )
    @classmethod
    def parse_json_uuid(cls, value: object) -> object:
        if isinstance(value, str):
            return UUID(value)
        return value

    @field_validator(
        "component_id",
        "component_version",
        "event_type",
        "profile_id",
    )
    @classmethod
    def validate_required_text(cls, value: str, info: Any) -> str:
        return _non_empty(value, field_name=info.field_name)

    @field_validator("task")
    @classmethod
    def validate_optional_task(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _non_empty(value, field_name="task")

    @field_validator("payload")
    @classmethod
    def validate_json_payload(
        cls, value: Mapping[str, JsonValue]
    ) -> Mapping[str, JsonValue]:
        try:
            json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("payload must contain only finite JSON values") from exc
        return deep_freeze_json(value)

    @field_serializer("payload")
    def serialize_payload(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        return deep_thaw_json(value)

    @model_validator(mode="after")
    def validate_deterministic_identity(self) -> "ScientificEventV3":
        if self.source_commit in _MISSING_SOURCE_COMMITS:
            expected_provenance = "provisional_missing_source_commit"
            if self.source_dirty is not None:
                raise ValueError(
                    "source_dirty must be null when the source commit is unavailable"
                )
        elif _FULL_GIT_OID.fullmatch(self.source_commit) is not None:
            expected_provenance = (
                "provisional_dirty_source_tree"
                if self.source_dirty is True
                else (
                    "complete"
                    if self.source_dirty is False
                    else "provisional_unverified_source_tree"
                )
            )
        else:  # Field pattern normally catches this; keep model semantics explicit.
            raise ValueError("source_commit must be a full lowercase Git object ID or sentinel")
        if self.provenance_status != expected_provenance:
            raise ValueError(
                "provenance_status is inconsistent with source_commit/source_dirty"
            )
        expected = self.expected_event_id(
            session_id=self.session_id,
            component_id=self.component_id,
            sequence=self.sequence,
            event_type=self.event_type,
        )
        if self.event_id != expected:
            raise ValueError("event_id does not match deterministic event identity")
        return self

    @classmethod
    def expected_event_id(
        cls,
        *,
        session_id: UUID | str,
        component_id: str,
        sequence: object,
        event_type: str,
    ) -> UUID:
        normalized_session = UUID(str(session_id))
        identity = json.dumps(
            [
                "matb.science",
                "scientific-event",
                cls.SCHEMA_VERSION,
                str(normalized_session),
                str(component_id),
                sequence,
                str(event_type),
            ],
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        return uuid5(NAMESPACE_URL, identity)

    @classmethod
    def create(
        cls,
        *,
        session_id: UUID | str,
        sequence: int,
        component_id: str,
        component_version: str,
        task: str | None,
        event_type: str,
        scenario_time_ns: int,
        scenario_sha256: str,
        profile_id: str,
        source_commit: str,
        source_dirty: bool | None,
        payload: dict[str, JsonValue],
        causation_id: UUID | str | None = None,
        correlation_id: UUID | str | None = None,
        opportunity_id: UUID | str | None = None,
    ) -> "ScientificEventV3":
        event_id = cls.expected_event_id(
            session_id=session_id,
            component_id=component_id,
            sequence=sequence,
            event_type=event_type,
        )
        normalized_sentinel = source_commit.strip().lower()
        if normalized_sentinel in _MISSING_SOURCE_COMMITS:
            normalized_source_commit = normalized_sentinel
            provenance_status: SourceProvenanceStatus = "provisional_missing_source_commit"
        elif _FULL_GIT_OID.fullmatch(source_commit) is not None:
            normalized_source_commit = source_commit
            provenance_status = (
                "provisional_dirty_source_tree"
                if source_dirty is True
                else (
                    "complete"
                    if source_dirty is False
                    else "provisional_unverified_source_tree"
                )
            )
        else:
            raise ValueError("source_commit must be a full lowercase Git object ID or sentinel")
        return cls(
            session_id=session_id,
            event_id=event_id,
            sequence=sequence,
            component_id=component_id,
            component_version=component_version,
            task=task,
            event_type=event_type,
            scenario_time_ns=scenario_time_ns,
            scenario_sha256=scenario_sha256,
            profile_id=profile_id,
            source_commit=normalized_source_commit,
            source_dirty=source_dirty,
            provenance_status=provenance_status,
            causation_id=causation_id,
            correlation_id=correlation_id,
            opportunity_id=opportunity_id,
            payload=payload,
        )

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "ScientificEventV3":
        return cls.model_validate(dict(record))

    def to_record(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class TimingObservationV1(BaseModel):
    """One clock-domain observation linked to a scientific event."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    SCHEMA_VERSION: ClassVar[str] = "1.0"
    PHYSICAL_KINDS: ClassVar[frozenset[str]] = frozenset(
        {"physical_onset", "physical_input"}
    )
    PHYSICAL_METHODS: ClassVar[frozenset[str]] = frozenset(
        {"photodiode", "audio_loopback", "actuated_input", "device_sensor"}
    )
    SEMANTIC_MATRIX: ClassVar[dict[str, tuple[str, frozenset[str], str]]] = {
        "scheduled": ("software", frozenset({"experiment_clock"}), "ns"),
        "dispatch_start": ("software", frozenset({"software_clock"}), "ns"),
        "dispatch_end": ("software", frozenset({"software_clock"}), "ns"),
        "software_receipt": ("software", frozenset({"software_clock"}), "ns"),
        "physical_onset": (
            "physical",
            frozenset({"photodiode", "audio_loopback", "device_sensor"}),
            "ns",
        ),
        "physical_input": (
            "physical",
            frozenset({"actuated_input", "device_sensor"}),
            "ns",
        ),
        "lsl_timestamp": ("software", frozenset({"lsl_clock"}), "s"),
        "external_trigger": (
            "software",
            frozenset({"parallel_port", "serial_trigger"}),
            "ns",
        ),
    }

    schema_version: Literal["1.0"] = "1.0"
    session_id: UUID
    event_id: UUID
    observation_id: UUID
    observation_index: int = Field(ge=0)
    kind: ScientificTimingKind
    clock_id: str
    value: int | float
    unit: TimingUnit
    evidence_source: TimingEvidenceSource
    method: TimingMethod
    rig_id: str | None = None
    uncertainty_ns: int | None = Field(default=None, ge=0)
    details: Mapping[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_json_schema_integer_numbers(cls, value: object) -> object:
        """Align Python decoding with JSON Schema's mathematical integers.

        JSON Schema intentionally considers ``1`` and ``1.0`` the same integer
        value. Strict Pydantic models retain the decoder's lexical Python type,
        so normalize only finite, mathematically integral floats for fields the
        wire schema declares as integers.
        """

        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        integer_fields = ["observation_index", "uncertainty_ns"]
        if normalized.get("unit") == "ns":
            integer_fields.append("value")
        for field_name in integer_fields:
            raw = normalized.get(field_name)
            if type(raw) is float and math.isfinite(raw) and raw.is_integer():
                normalized[field_name] = int(raw)
        return normalized

    @field_validator("session_id", "event_id", "observation_id", mode="before")
    @classmethod
    def parse_json_uuid(cls, value: object) -> object:
        if isinstance(value, str):
            return UUID(value)
        return value

    @field_validator("clock_id")
    @classmethod
    def validate_clock_id(cls, value: str) -> str:
        return _non_empty(value, field_name="clock_id")

    @field_validator("rig_id")
    @classmethod
    def validate_rig_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _non_empty(value, field_name="rig_id")

    @field_validator("value")
    @classmethod
    def validate_clock_value(cls, value: int | float) -> int | float:
        if isinstance(value, bool) or (
            isinstance(value, float) and not math.isfinite(value)
        ):
            raise ValueError("timing value must be a finite number")
        return value

    @field_validator("details")
    @classmethod
    def validate_json_details(
        cls, value: Mapping[str, JsonValue]
    ) -> Mapping[str, JsonValue]:
        try:
            json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("details must contain only finite JSON values") from exc
        return deep_freeze_json(value)

    @field_serializer("details")
    def serialize_details(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        return deep_thaw_json(value)

    @model_validator(mode="after")
    def validate_semantics_and_identity(self) -> "TimingObservationV1":
        if self.unit == "ns" and (isinstance(self.value, bool) or not isinstance(self.value, int)):
            raise ValueError("nanosecond timing values must be integers")

        expected_source, allowed_methods, expected_unit = self.SEMANTIC_MATRIX[self.kind]
        if (
            self.evidence_source != expected_source
            or self.method not in allowed_methods
            or self.unit != expected_unit
        ):
            methods = ", ".join(sorted(allowed_methods))
            label = "physical timing" if self.kind in self.PHYSICAL_KINDS else self.kind
            raise ValueError(
                f"{label} {self.kind} requires {expected_source} evidence, measurement method "
                f"{methods}, and {expected_unit} units"
            )
        if self.kind in self.PHYSICAL_KINDS and self.rig_id is None:
            raise ValueError("physical timing requires a named rig_id")
        if self.kind not in self.PHYSICAL_KINDS and self.rig_id is not None:
            raise ValueError(f"{self.kind} must not claim a physical rig_id")

        expected = self.expected_observation_id(
            session_id=self.session_id,
            event_id=self.event_id,
            observation_index=self.observation_index,
            kind=self.kind,
            clock_id=self.clock_id,
        )
        if self.observation_id != expected:
            raise ValueError("observation_id does not match deterministic timing identity")
        return self

    @classmethod
    def expected_observation_id(
        cls,
        *,
        session_id: UUID | str,
        event_id: UUID | str,
        observation_index: object,
        kind: str,
        clock_id: str,
    ) -> UUID:
        identity = json.dumps(
            [
                "matb.science",
                "timing-observation",
                cls.SCHEMA_VERSION,
                str(UUID(str(session_id))),
                str(UUID(str(event_id))),
                observation_index,
                str(kind),
                str(clock_id),
            ],
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        return uuid5(NAMESPACE_URL, identity)

    @classmethod
    def create(
        cls,
        *,
        session_id: UUID | str,
        event_id: UUID | str,
        observation_index: int,
        kind: ScientificTimingKind,
        clock_id: str,
        value: int | float,
        unit: TimingUnit,
        evidence_source: TimingEvidenceSource,
        method: TimingMethod,
        rig_id: str | None = None,
        uncertainty_ns: int | None = None,
        details: dict[str, JsonValue] | None = None,
    ) -> "TimingObservationV1":
        observation_id = cls.expected_observation_id(
            session_id=session_id,
            event_id=event_id,
            observation_index=observation_index,
            kind=kind,
            clock_id=clock_id,
        )
        return cls(
            session_id=session_id,
            event_id=event_id,
            observation_id=observation_id,
            observation_index=observation_index,
            kind=kind,
            clock_id=clock_id,
            value=value,
            unit=unit,
            evidence_source=evidence_source,
            method=method,
            rig_id=rig_id,
            uncertainty_ns=uncertainty_ns,
            details={} if details is None else details,
        )

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "TimingObservationV1":
        return cls.model_validate(dict(record))

    def to_record(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
