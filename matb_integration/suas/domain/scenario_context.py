"""Non-public scenario lookup for checkpoint-compatible world projections."""

from __future__ import annotations

from .models import ScenarioDefinition, WorldState


_SCENARIOS_BY_SHA256: dict[str, ScenarioDefinition] = {}


def register_scenario(scenario: ScenarioDefinition) -> None:
    """Make a loaded immutable scenario available to matching restored worlds."""

    _SCENARIOS_BY_SHA256[scenario.scenario_sha256] = scenario


def bind_world_scenario(state: WorldState, scenario: ScenarioDefinition) -> None:
    """Persist and register the canonical scenario identity without retaining worlds."""

    if state.scenario_sha256 not in ("", scenario.scenario_sha256):
        raise ValueError("world scenario identity does not match the supplied scenario")
    state.scenario_sha256 = scenario.scenario_sha256
    register_scenario(scenario)


def scenario_for_world(state: WorldState) -> ScenarioDefinition | None:
    """Resolve a previously loaded scenario using checkpoint-persisted identity only."""

    return _SCENARIOS_BY_SHA256.get(state.scenario_sha256)
