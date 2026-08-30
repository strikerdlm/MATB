from __future__ import annotations

from matb_integration.qualification.study import (
    COMPLETE_ORDERS,
    build_calibration_study_manifest,
    calibration_orders,
    recruitment_target,
)


def test_each_session_balances_all_orders_for_six_consecutive_participants() -> None:
    assignments = [calibration_orders(index) for index in range(1, 7)]
    for session in range(3):
        assert {assignment[session] for assignment in assignments} == set(COMPLETE_ORDERS)
    assert all(len(set(assignment)) == 3 for assignment in assignments)


def test_recruitment_target_inflates_and_preserves_balance() -> None:
    assert recruitment_target(30, attrition_fraction=0.10) == 36


def test_calibration_manifest_preserves_scientific_boundaries() -> None:
    manifest = build_calibration_study_manifest(
        source_commit="deadbeef",
        compatibility_profile_id="MATB-EXTENDED-2.0",
        scenario_hashes={"LOW": "a" * 64, "MEDIUM": "b" * 64, "HIGH": "c" * 64},
    )
    assert manifest["pilot"]["n"] == 12
    assert manifest["pilot"]["included_in_confirmatory_inference"] is False
    assert manifest["claim_boundary"] == "non_diagnostic_non_fitness_research"
    assert manifest["prohibited_primary_endpoint"] == "universal_composite_score"
