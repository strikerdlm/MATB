from __future__ import annotations

import pytest

from matb_integration.suas.adapters.synthetic import SyntheticVehicleBackend
from matb_integration.suas.domain.enums import Locale, WorkloadProfile
from matb_integration.suas.research.protocol import (
    ProtocolController,
    ProtocolError,
    ProtocolPhase,
)


def test_protocol_requires_practice_then_participant_order(loaded_scenario) -> None:
    controller = ProtocolController(
        loaded_scenario.definition,
        participant_id="P03",
        locale=Locale.EN,
    )
    assert controller.block_order == (
        WorkloadProfile.PRACTICE,
        WorkloadProfile.MEDIUM,
        WorkloadProfile.HIGH,
        WorkloadProfile.LOW,
    )
    assert controller.phase is ProtocolPhase.READY_FOR_BLOCK
    controller.start_block("PRACTICE")
    with pytest.raises(ProtocolError, match="block_order_violation"):
        controller.start_block("LOW")


def test_sagat_freeze_captures_truth_and_exposes_only_public_probe(loaded_scenario) -> None:
    scenario = loaded_scenario.definition
    controller = ProtocolController(scenario, participant_id="P01", locale=Locale.EN)
    controller.start_block("PRACTICE")
    state = SyntheticVehicleBackend().initialize(scenario, scenario.blocks["PRACTICE"])
    due = controller.on_tick(state, simulation_time_ms=controller.sagat_due_ms)
    assert due is not None
    assert due.kind == "SAGAT"
    assert controller.phase is ProtocolPhase.SAGAT_ACTIVE
    assert "correct_answer" not in due.public_payload
    assert controller.private_probe is not None
    assert controller.private_probe.correct_answer
    assert controller.conceal_operational_state


def test_sagat_answer_sequence_and_post_block_gate(loaded_scenario) -> None:
    scenario = loaded_scenario.definition
    controller = ProtocolController(scenario, participant_id="P01", locale=Locale.EN)
    controller.start_block("PRACTICE")
    state = SyntheticVehicleBackend().initialize(scenario, scenario.blocks["PRACTICE"])
    controller.on_tick(state, simulation_time_ms=controller.sagat_due_ms)
    while controller.phase is ProtocolPhase.SAGAT_ACTIVE:
        assert controller.active_probe is not None
        controller.submit_sagat(controller.active_probe.probe_id or "", "Unknown", latency_ms=0)
    assert controller.phase is ProtocolPhase.BLOCK_RUNNING
    # Duration enters the post-block gate; no implicit completion is allowed.
    controller.on_tick(state, simulation_time_ms=scenario.blocks["PRACTICE"].duration_ms)
    assert controller.phase is ProtocolPhase.POST_BLOCK_ACTIVE
    controller.submit_post_block(
        "NASA_TLX",
        {
            "mental_demand": 1,
            "physical_demand": 1,
            "temporal_demand": 1,
            "performance": 1,
            "effort": 1,
            "frustration": 1,
        },
    )
    assert controller.phase is ProtocolPhase.POST_BLOCK_ACTIVE
    controller.submit_post_block("BEDFORD", {"value": 5})
    assert controller.phase is ProtocolPhase.READY_FOR_BLOCK
    assert controller.next_block_id == "LOW"


def test_probe_gate_rejects_wrong_answers_and_interrupts_without_resume(loaded_scenario) -> None:
    scenario = loaded_scenario.definition
    controller = ProtocolController(scenario, participant_id="P01", locale=Locale.EN)
    controller.start_block("PRACTICE")
    state = SyntheticVehicleBackend().initialize(scenario, scenario.blocks["PRACTICE"])
    controller.on_tick(state, simulation_time_ms=controller.sagat_due_ms)
    with pytest.raises(ProtocolError, match="probe_id_mismatch"):
        controller.submit_sagat("wrong", "Unknown")
    controller.interrupt_probe()
    assert controller.phase is ProtocolPhase.ABORTED
    assert controller.validity == "valid_with_deviation"
