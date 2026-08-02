"""Authoritative domain types for the sUAS simulator."""

from .events import AlertState, DomainEvent
from .commands import CommandEnvelope, CommandResult, CommandStatus
from .geometry import PointMM, PolygonMM, distance_mm, heading_mdeg
from .models import (
    AircraftDefinition,
    AircraftState,
    BlockDefinition,
    ContactDefinition,
    ContactState,
    Route,
    ScenarioDefinition,
    WorldState,
)
from .serialization import canonical_data, canonical_json, canonical_sha256

__all__ = [
    "AircraftDefinition",
    "AircraftState",
    "AlertState",
    "BlockDefinition",
    "ContactDefinition",
    "ContactState",
    "CommandEnvelope",
    "CommandResult",
    "CommandStatus",
    "DomainEvent",
    "PointMM",
    "PolygonMM",
    "Route",
    "ScenarioDefinition",
    "WorldState",
    "canonical_data",
    "canonical_json",
    "canonical_sha256",
    "distance_mm",
    "heading_mdeg",
]
