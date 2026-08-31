"""Deterministic, auditable adaptive automation."""

from .engine import AdaptiveAutomationEngine
from .models import (
    AutomationAuditRecord,
    AutomationProposal,
    HandoffResult,
    TaskSnapshot,
)
from .policies import AutomationPolicy, ScheduledHandoff, ScheduledPolicy, ThresholdPolicy
from .quality import (
    ContinuousAutomationModel,
    ContinuousAutomationRealization,
    DiscreteAutomationModel,
    DiscreteAutomationRealization,
)

__all__ = [
    "AdaptiveAutomationEngine",
    "AutomationAuditRecord",
    "AutomationPolicy",
    "AutomationProposal",
    "ContinuousAutomationModel",
    "ContinuousAutomationRealization",
    "DiscreteAutomationModel",
    "DiscreteAutomationRealization",
    "HandoffResult",
    "ScheduledHandoff",
    "ScheduledPolicy",
    "TaskSnapshot",
    "ThresholdPolicy",
]
