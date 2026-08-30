from __future__ import annotations

import pytest

from matb_integration.suhir.mwl import absolute_mwl, mwl_ratio, isa_timeseries

LOW = {
    "nasatlx": {"rtlx_mean_0_100": 40.0, "raw_tlx": 24.0},
    "isa": {"mean": 2.0, "probes": [{"scenario_time": 0.0, "value": 2.0}]},
    "bedford": {"value": 3},
}
HIGH = {
    "nasatlx": {"rtlx_mean_0_100": 80.0, "raw_tlx": 48.0},
    "isa": {"mean": 4.0, "probes": [
        {"scenario_time": 0.0, "value": 3.0},
        {"scenario_time": 90.0, "value": 5.0},
    ]},
    "bedford": {"value": 7},
}


def test_absolute_mwl_sources():
    assert absolute_mwl(HIGH) == 80.0
    assert absolute_mwl(HIGH, source="raw_tlx") == 48.0
    assert absolute_mwl(HIGH, source="isa_mean") == 4.0
    assert absolute_mwl(HIGH, source="bedford") == 7.0


def test_mwl_ratio_anchored_to_low_block():
    assert mwl_ratio(HIGH, LOW) == pytest.approx(2.0)
    assert mwl_ratio(HIGH, LOW, source="raw_tlx") == pytest.approx(2.0)
    assert mwl_ratio(HIGH, LOW, source="isa_mean") == pytest.approx(2.0)


def test_mwl_ratio_unknown_source_raises():
    with pytest.raises(ValueError):
        absolute_mwl(HIGH, source="nonsense")


def test_isa_timeseries_returns_sorted_pairs():
    assert isa_timeseries(HIGH) == [(0.0, 3.0), (90.0, 5.0)]
