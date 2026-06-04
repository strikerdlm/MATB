from __future__ import annotations

import pandas as pd
import pytest

from matb_integration.analysis.stats.data import (
    ALL_METRICS, CONFIRMATORY_METRICS, VISIT_CENTER,
    fingerprint, fits_frame, metrics_frame,
)


def _mrow(p="P01", v=1, lvl="LOW", metric="sysmon_d_prime", value=2.0, **extra):
    return {"participant_id": p, "visit_ordinal": v, "workload_level": lvl,
            "metric": metric, "value": value, **extra}


def test_constants():
    assert CONFIRMATORY_METRICS == ("sysmon_d_prime", "nasatlx_raw_tlx", "bedford")
    assert len(ALL_METRICS) == 7 and set(CONFIRMATORY_METRICS) <= set(ALL_METRICS)
    assert VISIT_CENTER == 3.5


def test_metrics_frame_shape_and_centering():
    df = metrics_frame([_mrow(v=1), _mrow(v=6, lvl="HIGH", value=1.0)])
    assert list(df.columns) == ["participant_id", "visit_ordinal", "workload_level",
                                "metric", "value", "visit_c"]
    assert df["visit_c"].tolist() == [-2.5, 2.5]
    assert df["value"].dtype.kind == "f"


def test_metrics_frame_drops_extras_and_null_values():
    df = metrics_frame([_mrow(scheduled_day=0), _mrow(value=None)])
    assert "scheduled_day" not in df.columns
    assert len(df) == 1  # null value dropped


def test_metrics_frame_rejects_unknown_level_and_metric():
    with pytest.raises(ValueError, match="workload_level"):
        metrics_frame([_mrow(lvl="EXTREME")])
    with pytest.raises(ValueError, match="metric"):
        metrics_frame([_mrow(metric="made_up")])


def test_metrics_frame_empty():
    df = metrics_frame([])
    assert df.empty and "visit_c" in df.columns


def test_fits_frame():
    df = fits_frame([{"participant_id": "P01", "visit_ordinal": 2,
                      "g0": 40.0, "p0": 0.99, "tau0": 12.0, "curve": [1, 2]}])
    assert "curve" not in df.columns
    assert df["visit_c"].tolist() == [-1.5]
    assert fits_frame([]).empty


def test_fingerprint_is_order_invariant_and_value_sensitive():
    a = [_mrow(), _mrow(p="P02")]
    f1 = fingerprint(a, [])
    f2 = fingerprint(list(reversed(a)), [])
    f3 = fingerprint([_mrow(), _mrow(p="P02", value=9.9)], [])
    assert f1 == f2 != f3
    assert len(f1) == 64
