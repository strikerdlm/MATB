# tests/screen/test_hcf_mapping.py
from __future__ import annotations

import pytest

from matb_integration.screen.hcf_mapping import (
    CLAMP, K, MIN_COHORT, SCREEN_VERSION, compute_cohort_hcf,
)


def _scores(simple=300.0, choice=420.0, nback=2.0, tracking=0.3, valid=True):
    return {
        "simple_rt": {"median_ms": simple, "valid": valid},
        "choice_rt": {"median_ms": choice, "valid": valid, "accuracy": 0.9},
        "nback": {"d_prime": nback, "valid": valid},
        "tracking": {"rms_norm": tracking, "valid": valid},
    }


def test_gate_below_min_cohort():
    assert compute_cohort_hcf({"P01": _scores(), "P02": _scores()}) == {}


def test_signs_and_direction():
    # P01 faster RT, better d', lower tracking error -> F above 1; P03 opposite
    cohort = {"P01": _scores(simple=250, choice=380, nback=2.8, tracking=0.2),
              "P02": _scores(simple=300, choice=420, nback=2.0, tracking=0.3),
              "P03": _scores(simple=350, choice=460, nback=1.2, tracking=0.4)}
    store = compute_cohort_hcf(cohort)
    assert set(store) == {"P01", "P02", "P03"}
    assert store["P01"].value > 1.0 > store["P03"].value
    assert store["P02"].value == pytest.approx(1.0, abs=1e-9)  # cohort mean
    assert store["P01"].source == "screen"
    assert "composite_z" in store["P01"].components
    assert store["P01"].components["screen_version"] == SCREEN_VERSION


def test_clamping():
    # construct an extreme outlier; z magnitudes large -> clamp at bounds
    cohort = {"P01": _scores(simple=150, nback=4.5, choice=300, tracking=0.05),
              "P02": _scores(), "P03": _scores(), "P04": _scores(),
              "P05": _scores(simple=900, nback=0.1, choice=900, tracking=0.95)}
    store = compute_cohort_hcf(cohort)
    assert store["P01"].value <= CLAMP[1] and store["P05"].value >= CLAMP[0]
    assert min(s.value for s in store.values()) >= CLAMP[0]
    assert max(s.value for s in store.values()) <= CLAMP[1]


def test_invalid_subtest_excluded_per_participant():
    cohort = {"P01": _scores(), "P02": _scores(simple=350),
              "P03": {**_scores(simple=250),
                      "nback": {"d_prime": None, "valid": False}}}
    store = compute_cohort_hcf(cohort)
    # P03's composite uses only its 3 valid metrics; still produces an estimate
    assert "nback" not in store["P03"].components
    assert store["P03"].source == "screen"


def test_metric_needs_two_valid_values_and_zero_sd():
    # all identical -> sd 0 -> z 0 -> F exactly 1.0 for everyone
    cohort = {f"P{i:02d}": _scores() for i in range(1, 4)}
    store = compute_cohort_hcf(cohort)
    assert all(s.value == pytest.approx(1.0) for s in store.values())
    # a metric valid for only one participant is excluded cohort-wide
    cohort["P01"]["tracking"]["valid"] = False
    cohort["P02"]["tracking"]["valid"] = False
    store = compute_cohort_hcf(cohort)
    assert all("tracking" not in s.components for s in store.values())


def test_constants_are_prereg_values():
    assert K == 0.05 and CLAMP == (0.85, 1.15) and MIN_COHORT == 3
