# tests/screen/test_scoring.py
from __future__ import annotations

import pytest

from matb_integration.screen.scoring import (
    score_choice_rt, score_nback, score_screen, score_simple_rt, score_tracking,
)


def _rt_trials(rts, responded=True):
    return [{"rt_ms": r, "responded": responded} for r in rts]


def test_simple_rt_median_and_anticipation_discard():
    rts = [300, 320, 280, 140, 310]            # 140 ms -> anticipation, unusable
    out = score_simple_rt(_rt_trials(rts))
    assert out["median_ms"] == 305.0           # median of 280,300,310,320
    assert out["n_usable"] == 4 and out["n_trials"] == 5
    assert out["valid"] is True                # 4/5 = 80% usable


def test_simple_rt_invalid_when_too_few_usable():
    trials = _rt_trials([300] * 3) + _rt_trials([100] * 2)  # 3/5 = 60% < 80%
    assert score_simple_rt(trials)["valid"] is False


def test_choice_rt_correct_median_and_accuracy_gate():
    trials = [
        {"rt_ms": 400, "responded": True, "correct": True},
        {"rt_ms": 500, "responded": True, "correct": True},
        {"rt_ms": 450, "responded": True, "correct": False},
        {"rt_ms": 420, "responded": True, "correct": True},
    ]
    out = score_choice_rt(trials)
    assert out["median_ms"] == 420.0           # correct trials only: 400,420,500
    assert out["accuracy"] == pytest.approx(0.75)
    assert out["valid"] is True
    # accuracy below 0.6 invalidates even with full usability
    bad = [{"rt_ms": 400, "responded": True, "correct": i < 2} for i in range(10)]
    assert score_choice_rt(bad)["valid"] is False


def test_nback_d_prime_matches_sysmon_helper():
    # 20 targets (15 hits / 5 misses), 40 non-targets (4 FA / 36 CR)
    trials = (
        [{"is_target": True, "responded": True, "gap": False}] * 15
        + [{"is_target": True, "responded": False, "gap": False}] * 5
        + [{"is_target": False, "responded": True, "gap": False}] * 4
        + [{"is_target": False, "responded": False, "gap": False}] * 36
    )
    out = score_nback(trials)
    from matb_integration.log_converter import _d_prime
    assert out["d_prime"] == pytest.approx(_d_prime(15, 5, 4, 36))
    assert out["valid"] is True
    # >20% gap-flagged trials -> invalid
    gappy = [dict(t, gap=i < 15) for i, t in enumerate(trials)]
    assert score_nback(gappy)["valid"] is False


def test_tracking_rms_normalized():
    # constant 30 px error against amplitude 100 -> rms_norm 0.3
    # samples are [t_ms, mouse_x, mouse_y, target_x, target_y]
    out = score_tracking({"samples": [[i * 16, 30, 0, 0, 0] for i in range(100)],
                          "n_expected_samples": 100, "path_amplitude_px": 100.0})
    assert out["rms_norm"] == pytest.approx(0.3)
    assert out["valid"] is True
    sparse = {"samples": [[0, 30, 0, 0, 0]] * 50, "n_expected_samples": 100,
              "path_amplitude_px": 100.0}
    assert score_tracking(sparse)["valid"] is False  # 50% < 80% of expected


def test_nback_gap_derived_from_timestamps_when_present():
    # SOA nominal 2500 ms; trial 2 shown 2900 ms after trial 1 -> drift 400 > 250 -> gap
    trials = [
        {"is_target": False, "responded": False, "shown_at_ms": 0.0},
        {"is_target": False, "responded": False, "shown_at_ms": 2500.0},
        {"is_target": True, "responded": True, "shown_at_ms": 5400.0},
        {"is_target": False, "responded": False, "shown_at_ms": 7900.0},
    ]
    out = score_nback(trials, soa_ms=2500.0)
    assert out["n_usable"] == 3            # trial index 2 gap-flagged
    # browser flag is ignored when timestamps are present
    flagged = [dict(t, gap=True) for t in trials]
    assert score_nback(flagged, soa_ms=2500.0)["n_usable"] == 3


def test_nback_falls_back_to_browser_gap_flag():
    trials = [{"is_target": False, "responded": False, "gap": i == 1}
              for i in range(4)]
    assert score_nback(trials)["n_usable"] == 3


def test_score_screen_assembles_all_subtests():
    payload = {
        "simple_rt": {"trials": _rt_trials([300] * 30)},
        "choice_rt": {"trials": [{"rt_ms": 400, "responded": True, "correct": True}] * 30},
        "nback": {"trials": [{"is_target": i % 3 == 0, "responded": i % 3 == 0, "gap": False}
                              for i in range(60)]},
        "tracking": {"samples": [[i * 16, 10, 0, 0, 0] for i in range(5400)],
                     "n_expected_samples": 5400, "path_amplitude_px": 120.0},
    }
    scores = score_screen(payload)
    assert set(scores) == {"simple_rt", "choice_rt", "nback", "tracking"}
    assert all("valid" in s for s in scores.values())
