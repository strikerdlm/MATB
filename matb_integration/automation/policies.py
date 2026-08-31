"""Pure allocation policies, intentionally independent of automation quality."""

from __future__ import annotations

import json
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import AllocationAction, AutomationProposal, TaskName, TaskSnapshot, _IDENTIFIER, _SEMVER


class AutomationPolicy(Protocol):
    policy_id: str
    policy_version: str

    def decide(self, snapshot: TaskSnapshot) -> tuple[AutomationProposal, ...]: ...


class ScheduledHandoff(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    rule_id: str = Field(min_length=1)
    task: TaskName
    at_scenario_time_ns: int = Field(ge=0)
    action: AllocationAction
    forced: bool = False


class ScheduledPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    policy_id: str = Field(pattern=_IDENTIFIER)
    policy_version: str = Field(pattern=_SEMVER)
    schedule: tuple[ScheduledHandoff, ...]

    @model_validator(mode="after")
    def unique_rules(self) -> "ScheduledPolicy":
        rules = [item.rule_id for item in self.schedule]
        if len(rules) != len(set(rules)):
            raise ValueError("scheduled policy rule_id values must be unique")
        return self

    def decide(self, snapshot: TaskSnapshot) -> tuple[AutomationProposal, ...]:
        proposals = []
        for item in self.schedule:
            if item.task != snapshot.task or snapshot.scenario_time_ns < item.at_scenario_time_ns:
                continue
            proposals.append(
                AutomationProposal.create(
                    policy_id=self.policy_id,
                    policy_version=self.policy_version,
                    rule_id=item.rule_id,
                    task=item.task,
                    action=item.action,
                    trigger="scheduled",
                    forced=item.forced,
                    reason=f"scheduled handoff at {item.at_scenario_time_ns} ns",
                    # Bind the proposal to the complete scheduled rule.  A rule
                    # edited in place must never retain an earlier proposal ID.
                    identity_key=json.dumps(
                        {
                            "action": item.action,
                            "at_scenario_time_ns": item.at_scenario_time_ns,
                            "forced": item.forced,
                            "reason": f"scheduled handoff at {item.at_scenario_time_ns} ns",
                            "rule_id": item.rule_id,
                            "task": item.task,
                        },
                        ensure_ascii=True,
                        allow_nan=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
            )
        return tuple(proposals)


class ThresholdPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    policy_id: str = Field(pattern=_IDENTIFIER)
    policy_version: str = Field(pattern=_SEMVER)
    task: TaskName
    engage_below: float = Field(ge=0.0, le=1.0)
    disengage_above: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_hysteresis(self) -> "ThresholdPolicy":
        if self.engage_below >= self.disengage_above:
            raise ValueError("engage_below must be lower than disengage_above")
        return self

    def decide(self, snapshot: TaskSnapshot) -> tuple[AutomationProposal, ...]:
        if snapshot.task != self.task or snapshot.performance is None:
            return ()
        action: AllocationAction | None = None
        rule_id = ""
        reason = ""
        if not snapshot.automation_active and snapshot.performance < self.engage_below:
            action = "engage"
            rule_id = "engage-below"
            reason = f"performance {snapshot.performance} below {self.engage_below}"
        elif snapshot.automation_active and snapshot.performance > self.disengage_above:
            action = "disengage"
            rule_id = "disengage-above"
            reason = f"performance {snapshot.performance} above {self.disengage_above}"
        if action is None:
            return ()
        return (
            AutomationProposal.create(
                policy_id=self.policy_id,
                policy_version=self.policy_version,
                rule_id=rule_id,
                task=self.task,
                action=action,
                trigger="threshold",
                forced=False,
                reason=reason,
                identity_key=(
                    f"threshold:{snapshot.source_event_id}:{snapshot.scenario_time_ns}:{action}"
                ),
            ),
        )
