"""A deliberately small, deterministic fixed-step simulation clock."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SimulationClock:
    """Advance simulation time in exact 100 ms steps, never wall-clock time."""

    tick_ms: int = 100
    simulation_time_ms: int = 0
    paused: bool = False

    def __post_init__(self) -> None:
        if self.tick_ms != 100:
            raise ValueError("SimulationClock tick_ms must be exactly 100")
        if self.simulation_time_ms < 0 or self.simulation_time_ms % self.tick_ms:
            raise ValueError("simulation_time_ms must be a non-negative whole tick")

    @property
    def tick(self) -> int:
        return self.simulation_time_ms // self.tick_ms

    def advance(self) -> int:
        """Advance one fixed tick unless paused, and return current time."""

        if not self.paused:
            self.simulation_time_ms += self.tick_ms
        return self.simulation_time_ms

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False
