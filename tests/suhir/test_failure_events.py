from __future__ import annotations

import pytest

from matb_integration.suhir.failure_events import (
    sysmon_failure_times,
    threshold_excursions,
    failure_metrics,
)


def _row(t, value, module="sysmon", address="signal_detection"):
    return {
        "scenario_time": str(t),
        "type": "performance",
        "module": module,
        "address": address,
        "value": value,
    }


def test_sysmon_failure_times_picks_misses_in_order():
    rows = [
        _row(10.0, "HIT"),
        _row(25.0, "MISS"),
        _row(5.0, "MISS"),
        _row(40.0, "FA"),
        _row(60.0, "MISS"),
    ]
    assert sysmon_failure_times(rows) == [5.0, 25.0, 60.0]


def test_threshold_excursions_requires_min_duration():
    # values outside [lo, hi]; only sustained breaches >= min_dur count.
    samples = [
        (0.0, 0.0), (1.0, 0.0),   # in band
        (2.0, 5.0), (2.5, 5.0),   # breach lasting 0.5 s
        (3.0, 0.0),               # back in band
        (4.0, 9.0),               # single-sample breach (0 s)
        (5.0, 0.0),
    ]
    out = threshold_excursions(samples, lo=-1.0, hi=1.0, min_dur=0.4)
    assert out == [2.0]  # only the 0.5 s breach; start time reported


def test_threshold_excursions_single_sample_excluded_by_design():
    # Pre-registered Phase-1 semantic: a breach of one out-of-band sample has
    # span 0 (last_out_of_band == first_out_of_band) and is excluded.
    samples = [(0.0, 5.0), (1.0, 0.0)]
    assert threshold_excursions(samples, lo=-1.0, hi=1.0, min_dur=0.5) == []


def test_threshold_excursions_open_ended_breach_to_session_end():
    # A breach that never returns in-band is flushed using the last sample.
    samples = [(0.0, 0.0), (1.0, 5.0), (2.0, 5.0), (3.0, 5.0)]
    assert threshold_excursions(samples, lo=-1.0, hi=1.0, min_dur=1.5) == [1.0]


def test_failure_metrics_mttf_and_rate():
    # failures at t = 10, 30, 60 over a 90 s block -> 3 failures.
    m = failure_metrics([10.0, 30.0, 60.0], duration_s=90.0)
    assert m["n_failures"] == 3
    # MTTF = mean inter-failure interval incl. time-to-first from t=0.
    # intervals: 10, 20, 30 -> mean 20.0
    assert m["mttf_s"] == pytest.approx(20.0)
    assert m["lambda_per_s"] == pytest.approx(1.0 / 20.0)


def test_failure_metrics_no_failures_is_censored():
    m = failure_metrics([], duration_s=90.0)
    assert m["n_failures"] == 0
    assert m["mttf_s"] is None
    assert m["lambda_per_s"] == pytest.approx(0.0)
