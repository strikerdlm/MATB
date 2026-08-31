"""Hash-chained adaptive automation decision and handoff coordinator."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from .models import (
    AutomationAuditRecord,
    AutomationProposal,
    HandoffResult,
    HandoffTrigger,
    TaskSnapshot,
    _SEMVER,
)
from .policies import AutomationPolicy


class AdaptiveAutomationEngine:
    """Apply allocation proposals while retaining every scientific decision input."""

    def __init__(self, *, session_id: UUID, engine_version: str) -> None:
        self.session_id = UUID(str(session_id))
        if re.fullmatch(_SEMVER, engine_version) is None:
            raise ValueError("engine_version must be semantic versioning")
        self.engine_version = engine_version
        self._audit: list[AutomationAuditRecord] = []
        self._consumed_proposals: set[UUID] = set()
        self._handoffs: dict[UUID, HandoffResult] = {}

    @property
    def audit_head_sha256(self) -> str | None:
        return self._audit[-1].record_sha256 if self._audit else None

    def audit_records(self) -> tuple[AutomationAuditRecord, ...]:
        return tuple(self._audit)

    def create_proposal(
        self,
        *,
        snapshot: TaskSnapshot,
        policy_id: str,
        policy_version: str,
        rule_id: str,
        action: str,
        trigger: HandoffTrigger,
        forced: bool,
        reason: str,
    ) -> AutomationProposal:
        return AutomationProposal.create(
            policy_id=policy_id,
            policy_version=policy_version,
            rule_id=rule_id,
            task=snapshot.task,
            action=action,
            trigger=trigger,
            forced=forced,
            reason=reason,
            identity_key=(
                f"external:{snapshot.source_event_id}:{snapshot.scenario_time_ns}:{rule_id}"
            ),
        )

    def evaluate(
        self,
        snapshot: TaskSnapshot,
        policies: Iterable[AutomationPolicy],
    ) -> tuple[HandoffResult, ...]:
        results: list[HandoffResult] = []
        projected = snapshot
        transition_applied = False
        for policy in policies:
            for proposal in policy.decide(projected):
                if proposal.proposal_id in self._consumed_proposals:
                    self._append(
                        "policy_input",
                        projected.scenario_time_ns,
                        {"snapshot": projected.model_dump(mode="json")},
                    )
                    self._append(
                        "policy_decision",
                        projected.scenario_time_ns,
                        {
                            "outcome": "duplicate_suppressed",
                            "proposal": proposal.model_dump(mode="json"),
                        },
                    )
                    continue
                desired = proposal.action == "engage"
                if transition_applied and desired != projected.automation_active:
                    self._append(
                        "policy_input",
                        projected.scenario_time_ns,
                        {"snapshot": projected.model_dump(mode="json")},
                    )
                    self._append(
                        "policy_decision",
                        projected.scenario_time_ns,
                        {
                            "outcome": "conflict_suppressed",
                            "proposal": proposal.model_dump(mode="json"),
                        },
                    )
                    self._consumed_proposals.add(proposal.proposal_id)
                    continue
                result = self.apply(projected, proposal)
                results.append(result)
                transition_applied = transition_applied or result.applied
                projected = projected.model_copy(
                    update={"automation_active": result.automation_active_after}
                )
        return tuple(results)

    def apply(self, snapshot: TaskSnapshot, proposal: AutomationProposal) -> HandoffResult:
        if proposal.task != snapshot.task:
            raise ValueError("proposal task does not match policy input snapshot")
        if proposal.proposal_id in self._consumed_proposals:
            raise ValueError("proposal has already been consumed")

        self._append(
            "policy_input",
            snapshot.scenario_time_ns,
            {"snapshot": snapshot.model_dump(mode="json")},
        )
        self._append(
            "policy_decision",
            snapshot.scenario_time_ns,
            {"outcome": "proposed", "proposal": proposal.model_dump(mode="json")},
        )
        desired = proposal.action == "engage"
        applied = desired != snapshot.automation_active
        self._append(
            "automation_action",
            snapshot.scenario_time_ns,
            {
                "proposal_id": str(proposal.proposal_id),
                "action": proposal.action,
                "applied": applied,
                "forced": proposal.forced,
            },
        )
        handoff_id = uuid5(
            NAMESPACE_URL,
            f"matb.automation|handoff|{self.session_id}|{proposal.proposal_id}",
        )
        result = HandoffResult(
            handoff_id=handoff_id,
            proposal_id=proposal.proposal_id,
            task=proposal.task,
            trigger=proposal.trigger,
            forced=proposal.forced,
            action=proposal.action,
            applied=applied,
            automation_active_before=snapshot.automation_active,
            automation_active_after=desired if applied else snapshot.automation_active,
            scenario_time_ns=snapshot.scenario_time_ns,
            reason=proposal.reason,
        )
        self._consumed_proposals.add(proposal.proposal_id)
        self._handoffs[handoff_id] = result
        self._append("handoff", snapshot.scenario_time_ns, result.model_dump(mode="json"))
        return result

    def record_consequence(
        self,
        *,
        handoff_id: UUID,
        scenario_time_ns: int,
        performance_before: float,
        performance_after: float,
        notes: str,
    ) -> AutomationAuditRecord:
        normalized_id = UUID(str(handoff_id))
        if normalized_id not in self._handoffs:
            raise KeyError(f"unknown handoff_id: {normalized_id}")
        if scenario_time_ns < self._handoffs[normalized_id].scenario_time_ns:
            raise ValueError("handoff consequence cannot precede the handoff")
        return self._append(
            "handoff_consequence",
            scenario_time_ns,
            {
                "handoff_id": str(normalized_id),
                "performance_before": performance_before,
                "performance_after": performance_after,
                "performance_delta": performance_after - performance_before,
                "notes": notes,
            },
        )

    def _append(
        self,
        event_type: str,
        scenario_time_ns: int,
        payload: dict[str, Any],
    ) -> AutomationAuditRecord:
        if self._audit and scenario_time_ns < self._audit[-1].scenario_time_ns:
            raise ValueError(
                "automation audit scenario time cannot regress behind the chain head"
            )
        sequence = len(self._audit) + 1
        previous = self.audit_head_sha256
        record_id = AutomationAuditRecord.expected_record_id(
            engine_version=self.engine_version,
            session_id=self.session_id,
            sequence=sequence,
            event_type=event_type,
        )
        material = {
            "schema_version": "1.0",
            "engine_version": self.engine_version,
            "session_id": str(self.session_id),
            "record_id": str(record_id),
            "sequence": sequence,
            "event_type": event_type,
            "scenario_time_ns": scenario_time_ns,
            "payload": payload,
            "previous_record_sha256": previous,
        }
        digest = AutomationAuditRecord.expected_record_sha256(material)
        record = AutomationAuditRecord(
            **material,
            record_sha256=digest,
        )
        self._audit.append(record)
        return record
