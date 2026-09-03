from __future__ import annotations

import math

import numpy as np

from matb_integration.physiology.analysis import analyze_rr_window, workload_response


def test_time_domain_equations_match_direct_hand_calculation() -> None:
    result = analyze_rr_window([1000.0, 1100.0, 900.0], minimum_duration_s=0.0)

    assert result["valid"] is True
    assert math.isclose(result["mean_instantaneous_hr_bpm"], (60 + 600 / 11 + 200 / 3) / 3)
    assert math.isclose(result["sdnn_ms"], 100.0)
    assert math.isclose(result["rmssd_ms"], math.sqrt((100**2 + 200**2) / 2))
    assert math.isclose(result["ln_rmssd"], math.log(result["rmssd_ms"]))
    assert result["pnn50_percent"] == 100.0


def test_continuity_break_is_not_bridged() -> None:
    result = analyze_rr_window(
        [1000.0, 1100.0, 900.0], continuity=[True, False], minimum_duration_s=0.0
    )
    assert result["n_contiguous_pairs"] == 1
    assert result["rmssd_ms"] == 100.0
    assert result["lf_power_ms2"] is None
    assert result["spectral_reason"] == "discontinuous_or_artifact_affected_window"


def test_short_window_returns_null_with_reason() -> None:
    result = analyze_rr_window([1000.0] * 30)
    assert result["valid"] is False
    assert result["reason"] == "duration_below_required_window"
    assert result["rmssd_ms"] is None


def test_contact_failure_invalidates_offline_window_without_changing_raw_rr() -> None:
    rr = [1000.0, 1010.0] * 151
    support = [True] * len(rr)
    support[100] = False
    result = analyze_rr_window(rr, external_valid=support)
    assert result["valid"] is False
    assert result["reason"] == "contact_requirement_failed"
    assert result["n_intervals"] == len(rr)


def test_welch_psd_resolves_known_lf_and_hf_tachogram_components() -> None:
    beat = np.arange(360, dtype=float)
    rr = 1000.0 + 35.0 * np.sin(2 * np.pi * 0.10 * beat) + 20.0 * np.sin(2 * np.pi * 0.25 * beat)
    result = analyze_rr_window(rr, minimum_duration_s=300.0)
    assert result["valid"] is True
    assert result["lf_power_ms2"] is not None and result["lf_power_ms2"] > 0
    assert result["hf_power_ms2"] is not None and result["hf_power_ms2"] > 0
    assert result["lf_hf_ratio"] is not None and result["lf_hf_ratio"] > 1
    assert result["lf_hf_interpretation"].startswith("neutral_mathematical_ratio")


def test_hf_is_available_at_60_seconds_while_lf_waits_for_120_seconds() -> None:
    beat = np.arange(80, dtype=float)
    rr = 1000.0 + 20.0 * np.sin(2 * np.pi * 0.25 * beat)
    result = analyze_rr_window(rr, minimum_duration_s=60.0)

    assert result["valid"] is True
    assert result["hf_power_ms2"] is not None
    assert result["lf_power_ms2"] is None
    assert result["lf_hf_ratio"] is None
    assert result["spectral_reason"] == "duration_below_120_s_for_lf"


def test_workload_response_is_descriptive_only() -> None:
    baseline = analyze_rr_window([1000.0, 1010.0] * 160, minimum_duration_s=0)
    task = analyze_rr_window([800.0, 820.0] * 200, minimum_duration_s=0)
    response = workload_response(baseline, task)
    assert response["valid"] is True
    assert "class" not in response and "probability" not in response
    assert response["interpretation"] == "descriptive_response_only_no_workload_classification"
