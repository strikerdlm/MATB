from __future__ import annotations

from matb_integration.qualification.contracts import (
    evaluate_conformance,
    evaluate_release_eligibility,
    evaluate_timing_qualification,
    list_profiles,
    load_profile,
    validate_compatibility_profile,
)


def test_profiles_are_valid_and_documented_comparator_is_not_selectable() -> None:
    assert set(list_profiles()) == {
        "matb-extended-2.0",
        "matb-ii-2011-compat",
        "openmatb-1.4.5-derived",
    }
    profiles = [load_profile(profile_id) for profile_id in list_profiles()]
    assert all(not validate_compatibility_profile(profile) for profile in profiles)
    nasa = load_profile("matb-ii-2011-compat")
    assert nasa["selectable"] is False
    assert nasa["claims"]["human_equivalence"] == "NOT_TESTED"


def test_conformance_pass_does_not_upgrade_other_evidence_classes() -> None:
    profile = load_profile("openmatb-1.4.5-derived")
    report = evaluate_conformance(
        profile,
        [{"check_id": "hash", "expected": "abc", "observed": "abc"}],
        source_commit="deadbeef",
    )
    assert report["status"] == "PASS"
    assert profile["claims"]["physical_timing"] == "NOT_MEASURED"
    assert profile["claims"]["human_equivalence"] == "NOT_TESTED"


def test_timing_qualification_fails_closed_without_physical_measurement() -> None:
    result = evaluate_timing_qualification(
        {
            "use_tier": "block_plus_physiology",
            "rig": {
                "rig_id": "rig-a",
                "os": "Windows",
                "display": "display",
                "audio_device": "audio",
                "input_device": "joystick",
            },
            "physical_measurement": {"measured": False},
            "measurement_summaries": [],
            "representative_full_block_recorded": False,
        }
    )
    assert result["status"] == "NOT_MEASURED"


def test_release_requires_every_evidence_class() -> None:
    blocked = evaluate_release_eligibility({"release_id": "v1.0.0", "gates": {}})
    assert blocked["status"] == "BLOCKED"
    assert blocked["eligible"] is False
    passing = evaluate_release_eligibility(
        {
            "release_id": "v1.0.0",
            "gates": {
                "software_regression": "PASS",
                "deterministic_replay": "PASS",
                "licensing_review": "PASS",
                "privacy_review": "PASS",
                "timing_block_plus_physiology": "PASS",
                "workload_calibration": "VALIDATED",
                "test_retest_reliability": "CHARACTERIZED",
                "reference_dataset_reproducibility": "PASS",
                "matb_ii_comparator": "CHARACTERIZED_NOT_EQUIVALENT",
            },
        }
    )
    assert passing["eligible"] is True
