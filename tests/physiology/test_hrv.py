from __future__ import annotations

import math

import numpy as np
import pytest

from matb_integration.physiology.hrv import (
    analyze_rr_phase,
    clean_rr_intervals,
    compute_time_domain,
)


def test_time_domain_metrics_match_hand_calculated_values() -> None:
    metrics = compute_time_domain(np.asarray([1000.0, 1100.0, 900.0]))

    assert metrics["mean_nn_ms"] == pytest.approx(1000.0)
    assert metrics["sdnn_ms"] == pytest.approx(100.0)
    assert metrics["rmssd_ms"] == pytest.approx(math.sqrt(25_000.0))
    assert metrics["sdsd_ms"] == pytest.approx(math.sqrt(45_000.0))
    assert metrics["cvnn"] == pytest.approx(0.1)
    assert metrics["nn50"] == 2
    assert metrics["pnn50_pct"] == pytest.approx(100.0)
    assert metrics["mean_hr_bpm"] == pytest.approx(60.4040404)
    assert metrics["min_hr_bpm"] == pytest.approx(54.5454545)
    assert metrics["max_hr_bpm"] == pytest.approx(66.6666667)


def test_cleaning_preserves_length_and_interpolates_out_of_range_interval() -> None:
    cleaned, valid, quality = clean_rr_intervals(
        np.asarray([1000.0, 1000.0, 250.0, 1000.0, 1000.0])
    )

    assert valid.tolist() == [True, True, False, True, True]
    assert cleaned.tolist() == [1000.0] * 5
    assert quality["corrected_pct"] == pytest.approx(20.0)
    assert quality["out_of_bounds_pct"] == pytest.approx(20.0)
    assert quality["label"] == "unusable"


def test_five_minute_lf_modulation_produces_lf_dominant_welch_spectrum() -> None:
    seconds = np.arange(300, dtype=float)
    rr = 1000.0 + 50.0 * np.sin(2.0 * np.pi * 0.1 * seconds)

    result = analyze_rr_phase(
        rr,
        nominal_duration_s=300.0,
        coverage_fraction=1.0,
    )

    frequency = result["frequency_domain"]
    assert frequency["status"] == "ok"
    assert frequency["metrics"]["lf_power_ms2"] > frequency["metrics"]["hf_power_ms2"]
    assert frequency["metrics"]["lf_peak_hz"] == pytest.approx(0.1, abs=0.02)
    assert len(frequency["psd"]) > 10


def test_frequency_domain_reports_all_prespecified_gate_failures() -> None:
    rr = np.full(290, 1000.0)

    result = analyze_rr_phase(
        rr,
        nominal_duration_s=299.0,
        coverage_fraction=0.94,
        disconnect_count=1,
    )

    assert result["frequency_domain"] == {
        "status": "not_computable",
        "reason_codes": [
            "phase_duration_below_300s",
            "beat_coverage_below_95pct",
            "bluetooth_disconnect",
        ],
        "metrics": None,
        "psd": [],
    }


def test_frequency_integration_supports_numpy_1_26_without_trapezoid(monkeypatch) -> None:
    monkeypatch.delattr(np, "trapezoid", raising=False)
    seconds = np.arange(300, dtype=float)
    rr = 1000.0 + 25.0 * np.sin(2.0 * np.pi * 0.1 * seconds)

    result = analyze_rr_phase(
        rr,
        nominal_duration_s=300.0,
        coverage_fraction=1.0,
    )

    assert result["frequency_domain"]["status"] == "ok"


def test_tiny_phase_sample_is_not_labelled_excellent() -> None:
    result = analyze_rr_phase(
        np.asarray([1000.0, 1000.0]),
        nominal_duration_s=300.0,
        coverage_fraction=2.0 / 300.0,
    )

    assert result["quality"]["label"] == "insufficient_data"


def test_time_domain_does_not_bridge_a_bluetooth_disconnect() -> None:
    result = analyze_rr_phase(
        np.full(300, 1000.0),
        nominal_duration_s=300.0,
        coverage_fraction=1.0,
        disconnect_count=1,
    )

    assert result["time_domain"] == {
        "status": "not_computable",
        "reason_code": "discontinuous_rr_segments",
        "metrics": None,
    }
