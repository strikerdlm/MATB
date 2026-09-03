"""Research protocol and logging utilities for human-factors experiments."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aircraft_monitor.research.logger import ResearchLogger
from aircraft_monitor.research.protocol import (
    AutomationMode,
    DemandBlock,
    ResearchModality,
    ResearchProtocol,
    WorkloadLevel,
)

if TYPE_CHECKING:
    from aircraft_monitor.research.runner import ResearchExperimentRunner

__all__ = [
    "AutomationMode",
    "DemandBlock",
    "ResearchExperimentRunner",
    "ResearchLogger",
    "ResearchModality",
    "ResearchProtocol",
    "WorkloadLevel",
]


def __getattr__(name: str) -> object:
    """Load the terminal runner only when callers request it.

    Protocol and provenance consumers do not need the optional Rich terminal
    stack.  Keeping this export lazy lets those consumers import the lightweight
    protocol module while preserving the public package-level runner import.
    """
    if name == "ResearchExperimentRunner":
        from aircraft_monitor.research.runner import ResearchExperimentRunner

        return ResearchExperimentRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
