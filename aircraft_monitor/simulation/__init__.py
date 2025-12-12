"""Simulation engine for aircraft monitoring."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aircraft_monitor.simulation.engine import SimulationEngine


def __getattr__(name: str) -> object:
    """Lazy attribute access to avoid circular imports."""
    if name == "SimulationEngine":
        from aircraft_monitor.simulation.engine import SimulationEngine as _SimulationEngine

        return _SimulationEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["SimulationEngine"]
