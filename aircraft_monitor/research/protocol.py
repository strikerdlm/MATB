"""Deterministic research protocol definitions.

The protocol mirrors the easiest near-term MATB-derived features to implement:
seeded demand blocks, workload probes, automation state, and bounded event counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


class WorkloadLevel(Enum):
    """Research block demand levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AutomationMode(Enum):
    """Automation behavior used during a research block."""

    MANUAL = "manual"
    ADVISORY = "advisory"
    FORCED_HANDOFF = "forced_handoff"


class ResearchModality(Enum):
    """Supported experimental platform families."""

    UAS = "uas"
    FIGHTER = "fighter"
    COMBINED = "combined"


@dataclass(frozen=True, slots=True)
class DemandBlock:
    """Single bounded experimental block.

    Attributes:
        name: Human-readable block name.
        workload: Demand level being induced.
        max_events: Hard cap on source scenario events for this block.
        workload_probe_interval_events: Inject one ISA-style probe every N events.
        response_window_sec: Suggested response window for operator probes.
        automation_mode: Automation support or handoff mode.
        automation_reliability: Probability-like reliability setting in [0, 1].
    """

    name: str
    workload: WorkloadLevel
    max_events: int
    workload_probe_interval_events: int
    response_window_sec: float
    automation_mode: AutomationMode
    automation_reliability: float

    def __post_init__(self) -> None:
        """Validate demand block parameters."""
        if not self.name.strip():
            raise ValueError("Demand block name must not be empty.")
        if self.max_events < 1:
            raise ValueError("max_events must be >= 1.")
        if self.workload_probe_interval_events < 1:
            raise ValueError("workload_probe_interval_events must be >= 1.")
        if self.response_window_sec <= 0.0:
            raise ValueError("response_window_sec must be positive.")
        if self.automation_reliability < 0.0 or self.automation_reliability > 1.0:
            raise ValueError("automation_reliability must be in [0, 1].")


DEFAULT_PROTOCOL_NAME: Final[str] = "matb_research_mvp"


@dataclass(frozen=True, slots=True)
class ResearchProtocol:
    """Bounded experimental protocol.

    Attributes:
        name: Protocol identifier written to output logs.
        modality: Scenario family under study.
        seed: Base seed for deterministic event generation.
        blocks: Ordered demand blocks.
    """

    name: str
    modality: ResearchModality
    seed: int
    blocks: tuple[DemandBlock, ...]

    def __post_init__(self) -> None:
        """Validate protocol structure."""
        if not self.name.strip():
            raise ValueError("Protocol name must not be empty.")
        if len(self.blocks) == 0:
            raise ValueError("Protocol must contain at least one demand block.")

    @classmethod
    def default(cls, *, modality: ResearchModality, seed: int) -> "ResearchProtocol":
        """Create the short-term publishable MVP protocol.

        The three blocks intentionally map to MATB-style low, medium, and high
        workload by increasing event density and decreasing probe response time.
        """
        blocks = (
            DemandBlock(
                name="low_demand",
                workload=WorkloadLevel.LOW,
                max_events=10,
                workload_probe_interval_events=5,
                response_window_sec=10.0,
                automation_mode=AutomationMode.MANUAL,
                automation_reliability=1.0,
            ),
            DemandBlock(
                name="medium_demand",
                workload=WorkloadLevel.MEDIUM,
                max_events=18,
                workload_probe_interval_events=4,
                response_window_sec=8.0,
                automation_mode=AutomationMode.ADVISORY,
                automation_reliability=0.85,
            ),
            DemandBlock(
                name="high_demand",
                workload=WorkloadLevel.HIGH,
                max_events=28,
                workload_probe_interval_events=3,
                response_window_sec=6.0,
                automation_mode=AutomationMode.FORCED_HANDOFF,
                automation_reliability=0.65,
            ),
        )
        return cls(
            name=DEFAULT_PROTOCOL_NAME,
            modality=modality,
            seed=seed,
            blocks=blocks,
        )
