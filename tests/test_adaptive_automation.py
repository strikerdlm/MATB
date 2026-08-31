from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from matb_integration.automation import (
    AdaptiveAutomationEngine,
    AutomationAuditRecord,
    ContinuousAutomationModel,
    ContinuousAutomationRealization,
    DiscreteAutomationModel,
    DiscreteAutomationRealization,
    HandoffResult,
    ScheduledHandoff,
    ScheduledPolicy,
    TaskSnapshot,
    ThresholdPolicy,
)


SOURCE_EVENT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def snapshot(
    *,
    task: str = "sysmon",
    scenario_time_ns: int = 10_000_000_000,
    performance: float | None = 0.4,
    workload: float | None = 0.8,
    automation_active: bool = False,
) -> TaskSnapshot:
    return TaskSnapshot(
        task=task,
        scenario_time_ns=scenario_time_ns,
        performance=performance,
        workload_estimate=workload,
        automation_active=automation_active,
        source_event_id=SOURCE_EVENT_ID,
        metrics={"tracking.rmse": 0.25},
    )


def test_scheduled_policy_emits_one_stable_handoff_proposal():
    policy = ScheduledPolicy(
        policy_id="scheduled-allocation",
        policy_version="1.0.0",
        schedule=(
            ScheduledHandoff(
                rule_id="sysmon-at-10s",
                task="sysmon",
                at_scenario_time_ns=10_000_000_000,
                action="engage",
                forced=False,
            ),
        ),
    )

    proposals = policy.decide(snapshot())

    assert len(proposals) == 1
    assert proposals[0].trigger == "scheduled"
    assert proposals[0].action == "engage"
    assert proposals[0].forced is False
    assert policy.decide(snapshot())[0].proposal_id == proposals[0].proposal_id


def test_scheduled_proposal_identity_binds_the_exact_scheduled_time():
    def proposal(at_ns: int):
        policy = ScheduledPolicy(
            policy_id="scheduled-allocation",
            policy_version="1.0.0",
            schedule=(
                ScheduledHandoff(
                    rule_id="same-rule",
                    task="sysmon",
                    at_scenario_time_ns=at_ns,
                    action="engage",
                ),
            ),
        )
        return policy.decide(snapshot(scenario_time_ns=20_000_000_000))[0]

    assert proposal(10_000_000_000).proposal_id != proposal(11_000_000_000).proposal_id


def test_threshold_policy_has_hysteresis_and_never_embeds_quality_parameters():
    policy = ThresholdPolicy(
        policy_id="performance-guard",
        policy_version="1.0.0",
        task="sysmon",
        engage_below=0.5,
        disengage_above=0.8,
    )

    engage = policy.decide(snapshot(performance=0.4, automation_active=False))
    neutral = policy.decide(snapshot(performance=0.6, automation_active=False))
    disengage = policy.decide(snapshot(performance=0.9, automation_active=True))

    assert [proposal.action for proposal in engage] == ["engage"]
    assert neutral == ()
    assert [proposal.action for proposal in disengage] == ["disengage"]
    assert "detection_probability" not in policy.model_dump()
    assert "false_alarm_probability" not in policy.model_dump()


@pytest.mark.parametrize("trigger", ["offered", "requested", "threshold", "scheduled", "forced"])
def test_engine_supports_every_handoff_trigger_with_an_audit_chain(trigger: str):
    engine = AdaptiveAutomationEngine(
        session_id=UUID("11111111-1111-1111-1111-111111111111"),
        engine_version="1.0.0",
    )
    proposal = engine.create_proposal(
        snapshot=snapshot(),
        policy_id="manual-policy",
        policy_version="1.0.0",
        rule_id=f"{trigger}-rule",
        action="engage",
        trigger=trigger,
        forced=trigger == "forced",
        reason=f"{trigger} test",
    )

    result = engine.apply(snapshot(), proposal)

    assert result.applied is True
    assert result.automation_active_after is True
    assert result.trigger == trigger
    records = engine.audit_records()
    assert [record.event_type for record in records] == [
        "policy_input",
        "policy_decision",
        "automation_action",
        "handoff",
    ]
    assert all(record.previous_record_sha256 is not None for record in records[1:])
    assert records[-1].record_sha256 == engine.audit_head_sha256


def test_engine_deduplicates_a_scheduled_proposal_and_records_non_action_decision():
    engine = AdaptiveAutomationEngine(
        session_id=UUID("11111111-1111-1111-1111-111111111111"),
        engine_version="1.0.0",
    )
    policy = ScheduledPolicy(
        policy_id="scheduled-allocation",
        policy_version="1.0.0",
        schedule=(
            ScheduledHandoff(
                rule_id="one-shot",
                task="sysmon",
                at_scenario_time_ns=1,
                action="engage",
                forced=True,
            ),
        ),
    )

    first = engine.evaluate(snapshot(), (policy,))
    second = engine.evaluate(snapshot(automation_active=True), (policy,))

    assert len(first) == 1
    assert second == ()
    assert engine.audit_records()[-1].event_type == "policy_decision"
    assert engine.audit_records()[-1].payload["outcome"] == "duplicate_suppressed"


def test_handoff_consequence_is_a_separate_observation_not_a_policy_input():
    engine = AdaptiveAutomationEngine(
        session_id=UUID("11111111-1111-1111-1111-111111111111"),
        engine_version="1.0.0",
    )
    proposal = engine.create_proposal(
        snapshot=snapshot(),
        policy_id="manual-policy",
        policy_version="1.0.0",
        rule_id="participant-request",
        action="engage",
        trigger="requested",
        forced=False,
        reason="participant requested support",
    )
    handoff = engine.apply(snapshot(), proposal)

    consequence = engine.record_consequence(
        handoff_id=handoff.handoff_id,
        scenario_time_ns=12_000_000_000,
        performance_before=0.4,
        performance_after=0.7,
        notes="pre-registered 2 s observation window",
    )

    assert consequence.event_type == "handoff_consequence"
    assert consequence.payload["performance_delta"] == pytest.approx(0.3)


def test_discrete_quality_realization_is_order_independent_and_fully_auditable():
    model = DiscreteAutomationModel(
        model_id="slow-sensitive-detector",
        model_version="1.0.0",
        detection_probability=0.9,
        false_alarm_probability=0.2,
        latency_mean_ms=800.0,
        latency_sd_ms=100.0,
        availability_probability=0.95,
    )

    first = model.realize(seed=42, opportunity_id="sysmon-000001", target_present=True)
    model.realize(seed=42, opportunity_id="sysmon-000002", target_present=False)
    repeated = model.realize(seed=42, opportunity_id="sysmon-000001", target_present=True)

    assert repeated == first
    assert first.model_id == "slow-sensitive-detector"
    assert first.target_present is True
    assert set(first.draws) == {"availability", "response", "latency_u1", "latency_u2"}
    assert first.latency_ms is None or first.latency_ms >= 0


def test_continuous_quality_realization_separates_bias_noise_delay_and_availability():
    model = ContinuousAutomationModel(
        model_id="biased-tracker",
        model_version="1.0.0",
        bias=0.15,
        noise_sd=0.05,
        response_delay_ms=250.0,
        availability_probability=1.0,
    )

    result = model.realize(seed=7, event_id="track-sample-1")

    assert result.available is True
    assert result.response_delay_ms == 250.0
    assert result.output_error is not None
    assert result.model_parameters["bias"] == 0.15
    assert result.model_parameters["noise_sd"] == 0.05


@pytest.mark.parametrize("bad_seed", [True, 1.0, -1])
def test_quality_realization_rejects_non_exact_or_negative_seed(bad_seed):
    model = DiscreteAutomationModel(
        model_id="detector",
        model_version="1.0.0",
        detection_probability=0.9,
        false_alarm_probability=0.1,
        latency_mean_ms=100.0,
        latency_sd_ms=10.0,
        availability_probability=1.0,
    )

    with pytest.raises((TypeError, ValueError), match="seed"):
        model.realize(seed=bad_seed, opportunity_id="opportunity", target_present=True)


def test_quality_realization_rejects_empty_identity_and_contradictory_wire_state():
    model = ContinuousAutomationModel(
        model_id="tracker",
        model_version="1.0.0",
        bias=0.0,
        noise_sd=0.1,
        response_delay_ms=10.0,
        availability_probability=1.0,
    )
    with pytest.raises(ValueError, match="event_id"):
        model.realize(seed=1, event_id="")

    with pytest.raises(ValidationError, match="unavailable"):
        DiscreteAutomationRealization(
            model_id="detector",
            model_version="1.0.0",
            opportunity_id="opportunity",
            target_present=True,
            available=False,
            responded=True,
            outcome="detected",
            latency_ms=10.0,
            draws={},
            model_parameters={},
        )
    with pytest.raises(ValidationError, match="output_error"):
        ContinuousAutomationRealization(
            model_id="tracker",
            model_version="1.0.0",
            event_id="event",
            available=False,
            output_error=0.2,
            response_delay_ms=10.0,
            draws={},
            model_parameters={},
        )


def test_handoff_result_rejects_contradictory_action_state():
    with pytest.raises(ValidationError, match="action"):
        HandoffResult(
            handoff_id=UUID("11111111-1111-1111-1111-111111111111"),
            proposal_id=UUID("22222222-2222-2222-2222-222222222222"),
            task="sysmon",
            trigger="scheduled",
            forced=False,
            action="engage",
            applied=True,
            automation_active_before=False,
            automation_active_after=False,
            scenario_time_ns=1,
            reason="scheduled transition",
        )


def test_automation_evidence_is_deeply_immutable_and_hash_validated():
    engine = AdaptiveAutomationEngine(
        session_id=UUID("11111111-1111-1111-1111-111111111111"),
        engine_version="1.0.0",
    )
    proposal = engine.create_proposal(
        snapshot=snapshot(),
        policy_id="manual-policy",
        policy_version="1.0.0",
        rule_id="immutable-audit",
        action="engage",
        trigger="requested",
        forced=False,
        reason="audit mutation test",
    )
    engine.apply(snapshot(), proposal)
    record = engine.audit_records()[0]

    with pytest.raises(TypeError):
        record.payload["snapshot"]["metrics"]["tracking.rmse"] = 999  # type: ignore[index]
    assert record.record_sha256 == engine.audit_records()[0].record_sha256

    tampered = record.model_dump(mode="json")
    tampered["payload"]["snapshot"]["performance"] = 0.99
    with pytest.raises(ValidationError, match="record_sha256"):
        AutomationAuditRecord.model_validate(tampered)

    realization = DiscreteAutomationModel(
        model_id="immutable-detector",
        model_version="1.0.0",
        detection_probability=0.9,
        false_alarm_probability=0.1,
        latency_mean_ms=100.0,
        latency_sd_ms=10.0,
        availability_probability=1.0,
    ).realize(seed=1, opportunity_id="opportunity", target_present=True)
    with pytest.raises(TypeError):
        realization.draws["availability"] = 0.0


def test_automation_engine_rejects_unversioned_audit_chains():
    with pytest.raises(ValueError, match="semantic versioning"):
        AdaptiveAutomationEngine(session_id=SOURCE_EVENT_ID, engine_version="latest")


@pytest.mark.parametrize("field", ["bias", "noise_sd", "response_delay_ms"])
@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_continuous_model_rejects_nonfinite_parameters(field: str, bad_value: float):
    values = {
        "model_id": "finite-tracker",
        "model_version": "1.0.0",
        "bias": 0.0,
        "noise_sd": 0.1,
        "response_delay_ms": 50.0,
        "availability_probability": 1.0,
        field: bad_value,
    }
    with pytest.raises(ValidationError):
        ContinuousAutomationModel(**values)


def test_forced_semantics_are_part_of_proposal_identity():
    common = {
        "policy_id": "manual-policy",
        "policy_version": "1.0.0",
        "rule_id": "allocation",
        "task": "sysmon",
        "action": "engage",
        "trigger": "requested",
        "reason": "operator request",
        "identity_key": "request-1",
    }
    from matb_integration.automation import AutomationProposal

    offered = AutomationProposal.create(**common, forced=False)
    forced = AutomationProposal.create(**common, forced=True)

    assert offered.proposal_id != forced.proposal_id


def test_evaluate_applies_at_most_one_conflicting_transition_per_snapshot():
    from matb_integration.automation import AutomationProposal

    class ConflictingPolicy:
        def decide(self, current: TaskSnapshot):
            common = {
                "policy_id": "conflict-test",
                "policy_version": "1.0.0",
                "task": current.task,
                "trigger": "scheduled",
                "forced": False,
                "reason": "test conflict handling",
            }
            return (
                AutomationProposal.create(
                    **common,
                    rule_id="engage",
                    action="engage",
                    identity_key="engage",
                ),
                AutomationProposal.create(
                    **common,
                    rule_id="disengage",
                    action="disengage",
                    identity_key="disengage",
                ),
            )

    engine = AdaptiveAutomationEngine(session_id=SOURCE_EVENT_ID, engine_version="1.0.0")
    results = engine.evaluate(snapshot(), (ConflictingPolicy(),))

    assert len(results) == 1
    assert results[0].automation_active_after is True
    assert engine.audit_records()[-1].payload["outcome"] == "conflict_suppressed"


def test_duplicate_policy_audit_records_the_projected_input_the_policy_saw():
    from matb_integration.automation import AutomationProposal

    proposal = AutomationProposal.create(
        policy_id="duplicate-projection",
        policy_version="1.0.0",
        rule_id="engage",
        task="sysmon",
        action="engage",
        trigger="scheduled",
        forced=False,
        reason="projection integrity",
        identity_key="stable-proposal",
    )

    class FixedPolicy:
        def decide(self, current: TaskSnapshot):
            return (proposal,)

    engine = AdaptiveAutomationEngine(session_id=SOURCE_EVENT_ID, engine_version="1.0.0")
    engine.evaluate(snapshot(), (FixedPolicy(), FixedPolicy()))

    records = engine.audit_records()
    duplicate_input = records[-2]
    assert duplicate_input.event_type == "policy_input"
    assert duplicate_input.payload["snapshot"]["automation_active"] is True
    assert records[-1].payload["outcome"] == "duplicate_suppressed"


def test_automation_audit_rejects_scenario_time_regression():
    engine = AdaptiveAutomationEngine(session_id=SOURCE_EVENT_ID, engine_version="1.0.0")
    first_snapshot = snapshot(scenario_time_ns=10_000_000_000)
    first = engine.create_proposal(
        snapshot=first_snapshot,
        policy_id="time-integrity",
        policy_version="1.0.0",
        rule_id="engage",
        action="engage",
        trigger="scheduled",
        forced=False,
        reason="first transition",
    )
    engine.apply(first_snapshot, first)
    earlier_snapshot = snapshot(scenario_time_ns=9_000_000_000)
    earlier = engine.create_proposal(
        snapshot=earlier_snapshot,
        policy_id="time-integrity",
        policy_version="1.0.0",
        rule_id="late-arrival",
        action="disengage",
        trigger="scheduled",
        forced=False,
        reason="out-of-order transition",
    )

    with pytest.raises(ValueError, match="scenario time cannot regress"):
        engine.apply(earlier_snapshot, earlier)


@pytest.mark.parametrize(
    "changes",
    [
        {"detection_probability": 1.01},
        {"false_alarm_probability": -0.01},
        {"availability_probability": 2.0},
        {"latency_sd_ms": -1.0},
    ],
)
def test_discrete_model_rejects_invalid_failure_parameters(changes: dict[str, float]):
    values = {
        "model_id": "detector",
        "model_version": "1.0.0",
        "detection_probability": 0.9,
        "false_alarm_probability": 0.1,
        "latency_mean_ms": 200.0,
        "latency_sd_ms": 20.0,
        "availability_probability": 0.95,
        **changes,
    }
    with pytest.raises(ValidationError):
        DiscreteAutomationModel(**values)
