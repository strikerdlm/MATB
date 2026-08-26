from __future__ import annotations

import pytest

from matb_integration.scientific_data.summary import summarize_rows


def test_summary_preserves_raw_metrics_and_names_score_directions() -> None:
    samples = [
        {
            "automation_sysmon": False,
            "automation_communications": False,
            "automation_tracking": False,
            "automation_resman": False,
            "discrete_load_count": 1,
            "tracking_deviation": 25.0,
            "tracking_in_target": True,
            "tank_a_level": 2_200.0,
            "tank_a_target": 2_000.0,
            "tank_a_in_tolerance": True,
            "tank_b_level": 2_600.0,
            "tank_b_target": 2_500.0,
            "tank_b_in_tolerance": True,
        },
        {
            "automation_sysmon": True,
            "automation_communications": False,
            "automation_tracking": False,
            "automation_resman": True,
            "discrete_load_count": 2,
            "tracking_deviation": 75.0,
            "tracking_in_target": False,
            "tank_a_level": 1_800.0,
            "tank_a_target": 2_000.0,
            "tank_a_in_tolerance": True,
            "tank_b_level": 2_400.0,
            "tank_b_target": 2_500.0,
            "tank_b_in_tolerance": True,
        },
    ]
    trials = [
        {"task": "sysmon", "outcome": "HIT", "rt_ms": 2_000.0, "onset_s": 0.0, "deadline_s": 10.0},
        {"task": "sysmon", "outcome": "MISS", "rt_ms": None, "onset_s": 20.0, "deadline_s": 30.0},
        {
            "task": "communications",
            "outcome": "HIT",
            "rt_ms": 5_000.0,
            "onset_s": 0.0,
            "deadline_s": 20.0,
            "elements_available": 2,
            "elements_correct": 2,
        },
        {"task": "workload", "outcome": "response", "raw_value": 7.0, "rt_ms": 1_200.0},
        {
            "task": "subjective_workload",
            "trial_type": "NASA-TLX",
            "stimulus_id": "Mental demand",
            "raw_value": 6.0,
            "rt_ms": 3_000.0,
        },
    ]

    summary = summarize_rows(
        samples=samples,
        trials=trials,
        score_config={"tracking_range": 100.0, "resource_range": 1_000.0},
    )

    assert summary["sysmon"]["raw"]["mean_hit_rt_ms"] == 2_000.0
    assert summary["sysmon"]["scores"]["canonical_rt_efficiency"]["value"] == 40.0
    assert summary["communications"]["raw"]["element_accuracy_pct"] == 100.0
    assert summary["communications"]["scores"]["usaarl_three_element_accuracy"]["value"] is None
    assert summary["communications"]["scores"]["usaarl_three_element_accuracy"]["status"] == "not_computable"
    assert summary["tracking"]["raw"]["mean_deviation"] == 50.0
    assert summary["tracking"]["scores"]["canonical_performance"]["value"] == 50.0
    assert summary["tracking"]["scores"]["usaarl_scaled_error"]["direction"] == "lower_is_better"
    assert summary["resource_management"]["tank_a"]["scores"]["canonical_performance"]["value"] == 80.0
    assert summary["resource_management"]["tank_a"]["scores"]["usaarl_signed_scaled"]["value"] == 0.0
    assert summary["resource_management"]["tank_b"]["scores"]["usaarl_signed_scaled"]["status"] == "incompatible_configuration"
    assert summary["workload"]["mean_isa_1_to_10"] == 7.0
    assert summary["subjective_workload"]["NASA-TLX"]["values"]["Mental demand"] == 6.0
    assert summary["subjective_workload"]["NASA-TLX"]["raw_tlx_0_100"] is None
    assert summary["task_load"]["mean_discrete_task_count"] == 1.5
    assert summary["automation_exposure_fraction"]["sysmon"] == 0.5
    assert "readiness_score" not in summary
    assert "global_score" not in summary


def test_summary_does_not_guess_experimenter_defined_ranges() -> None:
    summary = summarize_rows(
        samples=[{"tracking_deviation": 10.0, "tracking_in_target": True}],
        trials=[],
        score_config={},
    )

    assert summary["tracking"]["scores"]["canonical_performance"]["value"] is None
    assert summary["tracking"]["scores"]["canonical_performance"]["status"] == "missing_threshold"


def test_summary_does_not_treat_missing_tracking_samples_as_perfect_performance() -> None:
    summary = summarize_rows(
        samples=[],
        trials=[],
        score_config={"tracking_range": 100.0},
    )

    assert summary["tracking"]["raw"]["n_samples"] == 0
    assert summary["tracking"]["scores"]["canonical_performance"]["value"] is None
    assert summary["tracking"]["scores"]["canonical_performance"]["status"] == "no_samples"
    assert summary["tracking"]["scores"]["usaarl_scaled_error"]["value"] is None
    assert summary["tracking"]["scores"]["usaarl_scaled_error"]["status"] == "no_samples"


def test_summary_rejects_global_composite_score_configuration() -> None:
    with pytest.raises(ValueError, match="global composite"):
        summarize_rows(samples=[], trials=[], score_config={"global_weights": {"tracking": 1.0}})
