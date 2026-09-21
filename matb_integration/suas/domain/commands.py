"""Typed, replay-safe operator commands and their outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Mapping

from .enums import ContactClassification, ContactPriority
from .geometry import PointMM


@dataclass(frozen=True, slots=True)
class AssignSector:
    aircraft_id: str
    sector_id: str


@dataclass(frozen=True, slots=True)
class SetWaypoint:
    aircraft_id: str
    waypoint: PointMM


@dataclass(frozen=True, slots=True)
class Hold:
    aircraft_id: str


@dataclass(frozen=True, slots=True)
class ResumeMission:
    aircraft_id: str


@dataclass(frozen=True, slots=True)
class ReturnToBase:
    aircraft_id: str


@dataclass(frozen=True, slots=True)
class AcknowledgeAlert:
    alert_id: str


@dataclass(frozen=True, slots=True)
class InspectContact:
    contact_id: str


@dataclass(frozen=True, slots=True)
class ClassifyContact:
    contact_id: str
    classification: ContactClassification


@dataclass(frozen=True, slots=True)
class SetContactPriority:
    contact_id: str
    priority: ContactPriority


@dataclass(frozen=True, slots=True)
class ReportContact:
    contact_id: str
    note_code: str


@dataclass(frozen=True, slots=True)
class SubmitIsa:
    probe_id: str
    rating: int


@dataclass(frozen=True, slots=True)
class SubmitSagat:
    probe_id: str
    answer: str


@dataclass(frozen=True, slots=True)
class SubmitPostBlockScale:
    scale_id: Literal["NASA_TLX", "BEDFORD"]
    answers: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class SwarmTask:
    group_id: str
    action: str
    target_id: str


@dataclass(frozen=True, slots=True)
class SwarmWaypoint:
    group_id: str
    waypoint: PointMM
    formation: str


@dataclass(frozen=True, slots=True)
class SwarmMembership:
    group_id: str
    aircraft_id: str
    action: str


OperatorCommand = (
    SwarmTask | SwarmWaypoint | SwarmMembership |
    AssignSector | SetWaypoint | Hold | ResumeMission | ReturnToBase |
    AcknowledgeAlert | InspectContact | ClassifyContact |
    SetContactPriority | ReportContact | SubmitIsa | SubmitSagat |
    SubmitPostBlockScale
)


@dataclass(frozen=True, slots=True)
class CommandEnvelope:
    command_id: str
    expected_state_version: int
    command: OperatorCommand


class CommandStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class CommandResult:
    command_id: str
    status: CommandStatus
    code: str
    applied_tick: int | None
    state_version: int
