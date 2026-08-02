"""Protocol shared by real and synthetic vehicle integrations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from matb_integration.suas.domain.events import DomainEvent
from matb_integration.suas.domain.models import BlockDefinition, ScenarioDefinition, WorldState


@runtime_checkable
class VehicleBackend(Protocol):
    def initialize(self, scenario: ScenarioDefinition, block: BlockDefinition) -> WorldState:
        raise NotImplementedError

    def advance(
        self, state: WorldState, *, tick_ms: int,
    ) -> tuple[WorldState, tuple[DomainEvent, ...]]:
        raise NotImplementedError
