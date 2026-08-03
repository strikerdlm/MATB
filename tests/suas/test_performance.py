from __future__ import annotations

import statistics
import time

import pytest

from matb_integration.suas.engine.runtime import SimulationEngine

from .test_soak import _eight_aircraft_scenario


@pytest.mark.performance
def test_high_profile_tick_budget(loaded_scenario) -> None:
    engine = SimulationEngine(loaded_scenario.definition, "HIGH")
    durations: list[float] = []
    for _ in range(300):
        started = time.perf_counter()
        engine.step()
        durations.append((time.perf_counter() - started) * 1_000)
    p50 = statistics.median(durations)
    p95 = sorted(durations)[int(len(durations) * 0.95) - 1]
    assert p95 < 100, f"HIGH tick budget exceeded: p50={p50:.3f}ms p95={p95:.3f}ms"


@pytest.mark.performance
def test_eight_aircraft_high_profile_tick_budget(loaded_scenario) -> None:
    """The one-tick wall budget holds for the maximum schema fleet size."""

    scenario = _eight_aircraft_scenario(loaded_scenario.definition)
    left = SimulationEngine(scenario, "HIGH")
    right = SimulationEngine(scenario, "HIGH")
    durations: list[float] = []
    for _ in range(6_000):
        started = time.perf_counter()
        left_result = left.step()
        durations.append((time.perf_counter() - started) * 1_000)
        right_result = right.step()
        assert left_result == right_result
    p50 = statistics.median(durations)
    p95 = sorted(durations)[int(len(durations) * 0.95) - 1]
    assert left.state_hash == right.state_hash
    assert p95 < 100, f"8-aircraft HIGH tick budget exceeded: p50={p50:.3f}ms p95={p95:.3f}ms"
