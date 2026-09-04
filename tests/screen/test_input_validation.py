"""Independent boundary cases for browser-supplied cognitive observations."""
import math

import pytest

from matb_integration.screen.scoring import (
    score_choice_rt, score_nback, score_simple_rt, score_tracking,
)


@pytest.mark.parametrize("value", [-20, math.inf, math.nan, True])
def test_choice_rejects_invalid_rt(value):
    with pytest.raises(ValueError):
        score_choice_rt([{"responded": True, "correct": True, "rt_ms": value}])


def test_simple_rejects_infinite_rt():
    with pytest.raises(ValueError):
        score_simple_rt([{"responded": True, "rt_ms": math.inf}])


def test_tracking_rejects_duplicate_timestamps():
    with pytest.raises(ValueError):
        score_tracking({"samples": [[0, 0, 0, 0, 0]] * 20,
                        "n_expected_samples": 10, "path_amplitude_px": 1})


def test_nback_rejects_inconsistent_stimulus_truth():
    with pytest.raises(ValueError):
        score_nback([
            {"letter": "C", "is_target": False, "responded": False},
            {"letter": "G", "is_target": False, "responded": False},
            {"letter": "C", "is_target": False, "responded": True},
        ])


def test_tracking_time_coverage_is_independent_of_display_refresh():
    for hz in (30, 60, 120):
        samples = [[i * 1000 / hz, 30, 40, 0, 0] for i in range(hz + 1)]
        result = score_tracking({"samples": samples, "duration_ms": 1000,
                                "n_expected_samples": 60, "path_amplitude_px": 100})
        assert result["valid"] is True
        assert result["rms_norm"] == pytest.approx(0.5)
