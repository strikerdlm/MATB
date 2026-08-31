"""Canonical, deterministic experiment specifications."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, ClassVar, Literal, Mapping

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


_IDENTIFIER_PATTERN = r"^[a-z0-9][a-z0-9._-]*$"
_COMPONENT_ID_PATTERN = r"^[a-z][a-z0-9]*(?:[-.][a-z0-9]+)*$"
_EVENT_TYPE_PATTERN = r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$"
MAX_EXPERIMENT_DURATION_NS = 86_400_000_000_000  # 24 hours
MAX_EXPERIMENT_TIMELINE_EVENTS = 10_000
MAX_EXPERIMENT_COMPONENTS = 64
MAX_EXPERIMENT_BODY_BYTES = 4 * 1024 * 1024
MAX_EXPERIMENT_TEXT_LENGTH = 256
MAX_EVENT_TEXT_LENGTH = 128


def _validate_json(value: object, *, label: str) -> None:
    try:
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain only finite JSON values") from exc


class TimelineEventV1(BaseModel):
    """One deterministic item in an experiment timeline."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    event_key: str = Field(pattern=_IDENTIFIER_PATTERN, max_length=MAX_EVENT_TEXT_LENGTH)
    at_ns: int = Field(ge=0, le=MAX_EXPERIMENT_DURATION_NS)
    duration_ns: int | None = Field(
        default=None, ge=1, le=MAX_EXPERIMENT_DURATION_NS
    )
    component_id: str = Field(
        pattern=_COMPONENT_ID_PATTERN, max_length=MAX_EVENT_TEXT_LENGTH
    )
    task: str | None = Field(max_length=MAX_EVENT_TEXT_LENGTH)
    event_type: str = Field(pattern=_EVENT_TYPE_PATTERN, max_length=MAX_EVENT_TEXT_LENGTH)
    parameters: Mapping[str, JsonValue]

    @model_validator(mode="before")
    @classmethod
    def normalize_json_schema_integer_numbers(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        for field_name in ("at_ns", "duration_ns"):
            raw = normalized.get(field_name)
            if type(raw) is float and math.isfinite(raw) and raw.is_integer():
                normalized[field_name] = int(raw)
        return normalized

    @field_validator("task")
    @classmethod
    def validate_optional_task(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or value != value.strip()):
            raise ValueError("task must be null or non-empty without surrounding whitespace")
        return value

    @field_validator("parameters")
    @classmethod
    def validate_parameters(
        cls, value: Mapping[str, JsonValue]
    ) -> Mapping[str, JsonValue]:
        _validate_json(value, label="parameters JSON")
        return deep_freeze_json(value)

    @field_serializer("parameters")
    def serialize_parameters(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        return deep_thaw_json(value)

    @classmethod
    def create(
        cls,
        *,
        event_key: str,
        at_ns: int,
        duration_ns: int | None,
        component_id: str,
        task: str | None,
        event_type: str,
        parameters: dict[str, JsonValue],
    ) -> "TimelineEventV1":
        return cls(
            event_key=event_key,
            at_ns=at_ns,
            duration_ns=duration_ns,
            component_id=component_id,
            task=task,
            event_type=event_type,
            parameters=parameters,
        )


class ExperimentSpecV1(BaseModel):
    """Canonical source specification compiled into runtime scenarios."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    SCHEMA_VERSION: ClassVar[str] = "1.0"

    schema_version: Literal["1.0"] = "1.0"
    experiment_id: str = Field(pattern=_IDENTIFIER_PATTERN, max_length=MAX_EVENT_TEXT_LENGTH)
    revision: int = Field(ge=1, le=2_147_483_647)
    title: str = Field(max_length=MAX_EXPERIMENT_TEXT_LENGTH)
    seed: int = Field(ge=0, le=9_223_372_036_854_775_807)
    profile_id: str = Field(max_length=MAX_EXPERIMENT_TEXT_LENGTH)
    duration_ns: int = Field(ge=1, le=MAX_EXPERIMENT_DURATION_NS)
    components: tuple[str, ...] = Field(
        min_length=1, max_length=MAX_EXPERIMENT_COMPONENTS
    )
    timeline: tuple[TimelineEventV1, ...] = Field(
        min_length=1, max_length=MAX_EXPERIMENT_TIMELINE_EVENTS
    )
    metadata: Mapping[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_json_schema_integer_numbers(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        for field_name in ("revision", "seed", "duration_ns"):
            raw = normalized.get(field_name)
            if type(raw) is float and math.isfinite(raw) and raw.is_integer():
                normalized[field_name] = int(raw)
        return normalized

    @field_validator("components", "timeline", mode="before")
    @classmethod
    def parse_wire_sequences(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("title", "profile_id")
    @classmethod
    def validate_text(cls, value: str, info: Any) -> str:
        if not value or not value.strip() or value != value.strip():
            raise ValueError(f"{info.field_name} must be non-empty without surrounding whitespace")
        return value

    @field_validator("components")
    @classmethod
    def normalize_components(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        import re

        if len(value) != len(set(value)):
            raise ValueError("components must not contain duplicates")
        if any(re.fullmatch(_COMPONENT_ID_PATTERN, item) is None for item in value):
            raise ValueError("components contains an invalid component identifier")
        return tuple(sorted(value))

    @field_validator("timeline")
    @classmethod
    def normalize_timeline(cls, value: tuple[TimelineEventV1, ...]) -> tuple[TimelineEventV1, ...]:
        keys = [event.event_key for event in value]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate timeline event_key")
        return tuple(sorted(value, key=lambda event: (event.at_ns, event.event_key)))

    @field_validator("metadata")
    @classmethod
    def validate_metadata(
        cls, value: Mapping[str, JsonValue]
    ) -> Mapping[str, JsonValue]:
        _validate_json(value, label="metadata JSON")
        return deep_freeze_json(value)

    @field_serializer("metadata")
    def serialize_metadata(self, value: Mapping[str, JsonValue]) -> dict[str, Any]:
        return deep_thaw_json(value)

    @model_validator(mode="after")
    def validate_timeline_boundary(self) -> "ExperimentSpecV1":
        available = set(self.components)
        for event in self.timeline:
            if event.component_id not in available:
                raise ValueError(
                    f"timeline event {event.event_key} uses undeclared component {event.component_id}"
                )
            event_end = event.at_ns + (event.duration_ns or 0)
            if event.at_ns >= self.duration_ns or event_end > self.duration_ns:
                raise ValueError(
                    f"timeline event {event.event_key} is outside experiment duration"
                )
        return self

    @classmethod
    def create(
        cls,
        *,
        experiment_id: str,
        revision: int,
        title: str,
        seed: int,
        profile_id: str,
        duration_ns: int,
        components: tuple[str, ...] | list[str],
        timeline: tuple[TimelineEventV1, ...] | list[TimelineEventV1],
        metadata: dict[str, JsonValue] | None = None,
    ) -> "ExperimentSpecV1":
        return cls(
            experiment_id=experiment_id,
            revision=revision,
            title=title,
            seed=seed,
            profile_id=profile_id,
            duration_ns=duration_ns,
            components=tuple(components),
            timeline=tuple(timeline),
            metadata={} if metadata is None else metadata,
        )

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "ExperimentSpecV1":
        return cls.model_validate(dict(record))

    def to_record(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_record(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
