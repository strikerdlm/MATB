"""Deterministic automation quality and failure-mode realizations."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from matb_integration.contracts._immutability import deep_freeze_json, deep_thaw_json
from .models import _IDENTIFIER, _SEMVER


def _validate_realization_identity(*, seed: int, identity: str, field_name: str) -> None:
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be an exact non-negative integer")
    if not isinstance(identity, str) or not identity:
        raise ValueError(f"{field_name} must be a non-empty string")


def _uniform(*, seed: int, identity: str, channel: str) -> float:
    material = f"matb.automation|{seed}|{identity}|{channel}".encode("utf-8")
    integer = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    return (integer + 0.5) / (2**64)


def _normal(*, seed: int, identity: str, channel: str) -> tuple[float, float, float]:
    u1 = _uniform(seed=seed, identity=identity, channel=f"{channel}:u1")
    u2 = _uniform(seed=seed, identity=identity, channel=f"{channel}:u2")
    z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    return z, u1, u2


class DiscreteAutomationRealization(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)

    model_id: str
    model_version: str
    opportunity_id: str
    target_present: bool
    available: bool
    responded: bool | None
    outcome: Literal["detected", "miss", "false_alarm", "correct_rejection", "unavailable"]
    latency_ms: float | None
    draws: Mapping[str, float]
    model_parameters: Mapping[str, float]

    @field_validator("draws", "model_parameters")
    @classmethod
    def freeze_evidence(cls, value: Mapping[str, float]) -> Mapping[str, float]:
        return deep_freeze_json(value)

    @field_serializer("draws", "model_parameters")
    def serialize_evidence(self, value: Mapping[str, float]) -> dict[str, float]:
        return deep_thaw_json(value)

    @model_validator(mode="after")
    def validate_state(self) -> "DiscreteAutomationRealization":
        if not self.available:
            if self.responded is not None or self.outcome != "unavailable" or self.latency_ms is not None:
                raise ValueError(
                    "unavailable realization requires responded=None, outcome='unavailable', and no latency"
                )
            return self
        if self.responded is None or self.outcome == "unavailable":
            raise ValueError("available realization requires a response decision and available outcome")
        if self.target_present:
            expected_outcome = "detected" if self.responded else "miss"
        else:
            expected_outcome = "false_alarm" if self.responded else "correct_rejection"
        if self.outcome != expected_outcome:
            raise ValueError("outcome contradicts target_present/responded state")
        if self.responded and self.latency_ms is None:
            raise ValueError("responded realization requires latency_ms")
        if not self.responded and self.latency_ms is not None:
            raise ValueError("non-response realization cannot contain latency_ms")
        return self


class DiscreteAutomationModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)

    model_id: str = Field(pattern=_IDENTIFIER)
    model_version: str = Field(pattern=_SEMVER)
    detection_probability: float = Field(ge=0.0, le=1.0)
    false_alarm_probability: float = Field(ge=0.0, le=1.0)
    latency_mean_ms: float = Field(ge=0.0)
    latency_sd_ms: float = Field(ge=0.0)
    availability_probability: float = Field(ge=0.0, le=1.0)

    def realize(
        self,
        *,
        seed: int,
        opportunity_id: str,
        target_present: bool,
    ) -> DiscreteAutomationRealization:
        _validate_realization_identity(
            seed=seed, identity=opportunity_id, field_name="opportunity_id"
        )
        availability_draw = _uniform(seed=seed, identity=opportunity_id, channel="availability")
        response_draw = _uniform(seed=seed, identity=opportunity_id, channel="response")
        z, latency_u1, latency_u2 = _normal(seed=seed, identity=opportunity_id, channel="latency")
        available = availability_draw < self.availability_probability
        draws = {
            "availability": availability_draw,
            "response": response_draw,
            "latency_u1": latency_u1,
            "latency_u2": latency_u2,
        }
        parameters = {
            "detection_probability": self.detection_probability,
            "false_alarm_probability": self.false_alarm_probability,
            "latency_mean_ms": self.latency_mean_ms,
            "latency_sd_ms": self.latency_sd_ms,
            "availability_probability": self.availability_probability,
        }
        if not available:
            return DiscreteAutomationRealization(
                model_id=self.model_id,
                model_version=self.model_version,
                opportunity_id=opportunity_id,
                target_present=target_present,
                available=False,
                responded=None,
                outcome="unavailable",
                latency_ms=None,
                draws=draws,
                model_parameters=parameters,
            )

        response_probability = (
            self.detection_probability if target_present else self.false_alarm_probability
        )
        responded = response_draw < response_probability
        if target_present:
            outcome = "detected" if responded else "miss"
        else:
            outcome = "false_alarm" if responded else "correct_rejection"
        latency = None
        if responded:
            latency = max(0.0, self.latency_mean_ms + z * self.latency_sd_ms)
        return DiscreteAutomationRealization(
            model_id=self.model_id,
            model_version=self.model_version,
            opportunity_id=opportunity_id,
            target_present=target_present,
            available=True,
            responded=responded,
            outcome=outcome,
            latency_ms=latency,
            draws=draws,
            model_parameters=parameters,
        )


class ContinuousAutomationRealization(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)

    model_id: str
    model_version: str
    event_id: str
    available: bool
    output_error: float | None
    response_delay_ms: float
    draws: Mapping[str, float]
    model_parameters: Mapping[str, float]

    @field_validator("draws", "model_parameters")
    @classmethod
    def freeze_evidence(cls, value: Mapping[str, float]) -> Mapping[str, float]:
        return deep_freeze_json(value)

    @field_serializer("draws", "model_parameters")
    def serialize_evidence(self, value: Mapping[str, float]) -> dict[str, float]:
        return deep_thaw_json(value)

    @model_validator(mode="after")
    def validate_state(self) -> "ContinuousAutomationRealization":
        if self.available and self.output_error is None:
            raise ValueError("available realization requires output_error")
        if not self.available and self.output_error is not None:
            raise ValueError("unavailable realization cannot contain output_error")
        return self


class ContinuousAutomationModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)

    model_id: str = Field(pattern=_IDENTIFIER)
    model_version: str = Field(pattern=_SEMVER)
    bias: float
    noise_sd: float = Field(ge=0.0)
    response_delay_ms: float = Field(ge=0.0)
    availability_probability: float = Field(ge=0.0, le=1.0)

    def realize(self, *, seed: int, event_id: str) -> ContinuousAutomationRealization:
        _validate_realization_identity(seed=seed, identity=event_id, field_name="event_id")
        availability_draw = _uniform(seed=seed, identity=event_id, channel="availability")
        z, noise_u1, noise_u2 = _normal(seed=seed, identity=event_id, channel="noise")
        available = availability_draw < self.availability_probability
        parameters = {
            "bias": self.bias,
            "noise_sd": self.noise_sd,
            "response_delay_ms": self.response_delay_ms,
            "availability_probability": self.availability_probability,
        }
        return ContinuousAutomationRealization(
            model_id=self.model_id,
            model_version=self.model_version,
            event_id=event_id,
            available=available,
            output_error=self.bias + z * self.noise_sd if available else None,
            response_delay_ms=self.response_delay_ms,
            draws={
                "availability": availability_draw,
                "noise_u1": noise_u1,
                "noise_u2": noise_u2,
            },
            model_parameters=parameters,
        )
