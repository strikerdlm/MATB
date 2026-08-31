from __future__ import annotations

import pandas as pd
import pytest

from matb_integration.analysis.stats.data import (
    ALL_METRICS, CONFIRMATORY_METRICS, VISIT_CENTER,
    fingerprint, fits_frame, metrics_frame,
)


def _mrow(p="P01", v=1, lvl="LOW", metric="sysmon_hit_rate", value=0.2, **extra):
    return {"participant_id": p, "visit_ordinal": v, "workload_level": lvl,
            "metric": metric, "value": value, **extra}


def test_constants():
    assert CONFIRMATORY_METRICS == ("sysmon_hit_rate", "nasatlx_rtlx_mean_0_100", "bedford")
    assert len(ALL_METRICS) == 15 and set(CONFIRMATORY_METRICS) <= set(ALL_METRICS)
    assert VISIT_CENTER == 3.5


def test_metrics_frame_shape_and_centering():
    df = metrics_frame([_mrow(v=1), _mrow(v=6, lvl="HIGH", value=1.0)])
    assert list(df.columns) == [
        "participant_id", "visit_ordinal", "workload_level", "metric", "value",
        "metrics_schema_version", "metric_version", "confirmatory_eligible", "visit_c",
    ]
    assert df["visit_c"].tolist() == [-2.5, 2.5]
    assert df["value"].dtype.kind == "f"


def test_metrics_frame_drops_extras_and_null_values():
    df = metrics_frame([_mrow(scheduled_day=0), _mrow(p="P02", value=None)])
    assert "scheduled_day" not in df.columns
    assert len(df) == 1  # null value dropped


def test_metrics_frame_rejects_unknown_level_and_metric():
    with pytest.raises(ValueError, match="workload_level"):
        metrics_frame([_mrow(lvl="EXTREME")])
    with pytest.raises(ValueError, match="metric"):
        metrics_frame([_mrow(metric="made_up")])


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), float("-inf"), "1.0"])
def test_metrics_frame_rejects_nonfinite_or_non_numeric_values(value):
    with pytest.raises(ValueError, match="finite|number|boolean"):
        metrics_frame([_mrow(value=value)])


@pytest.mark.parametrize("visit", [True, 0, -1, 1.0, "1", None])
def test_metrics_frame_requires_exact_positive_visit_ordinals(visit):
    with pytest.raises(ValueError, match="exact positive integer"):
        metrics_frame([_mrow(v=visit)])


@pytest.mark.parametrize(
    ("metric", "value"),
    [
        ("sysmon_hit_rate", 1.01),
        ("track_percent_time_in_target", -0.1),
        ("nasatlx_rtlx_mean_0_100", 101.0),
        ("bedford", 0.0),
        ("isa_mean", 11.0),
    ],
)
def test_metrics_frame_enforces_metric_domains(metric, value):
    with pytest.raises(ValueError, match="must be"):
        metrics_frame([_mrow(metric=metric, value=value)])


def test_metrics_frame_rejects_duplicate_scientific_identity():
    with pytest.raises(ValueError, match="duplicate participant"):
        metrics_frame([_mrow(), _mrow(value=0.3)])


def test_metrics_frame_rejects_mixed_schema_versions_without_migration():
    with pytest.raises(ValueError, match="explicit migration"):
        metrics_frame([
            _mrow(metrics_schema_version="1.0"),
            _mrow(p="P02", metrics_schema_version="2.0"),
        ])


def test_metrics_frame_treats_missing_schema_as_legacy_when_checking_mixes():
    with pytest.raises(ValueError, match="explicit migration"):
        metrics_frame([
            _mrow(),
            _mrow(p="P02", metrics_schema_version="2.0"),
        ])


def test_metrics_frame_empty():
    df = metrics_frame([])
    assert df.empty and "visit_c" in df.columns


def test_metrics_frame_preserves_validated_confirmatory_metadata():
    df = metrics_frame([
        _mrow(
            metrics_schema_version="2.0",
            metric_version="2",
            confirmatory_eligible=True,
        )
    ])

    assert df.loc[0, "metrics_schema_version"] == "2.0"
    assert df.loc[0, "metric_version"] == "2"
    assert bool(df.loc[0, "confirmatory_eligible"]) is True


@pytest.mark.parametrize(
    "extra,match",
    [
        ({"metrics_schema_version": "3.0", "metric_version": "1", "confirmatory_eligible": True}, "unsupported"),
        ({"metrics_schema_version": "2.0", "metric_version": "999", "confirmatory_eligible": True}, "metric_version"),
        ({"metrics_schema_version": "2.0", "metric_version": "1"}, "confirmatory_eligible"),
        ({"metrics_schema_version": "2.0", "metric_version": "1", "confirmatory_eligible": "yes"}, "boolean"),
    ],
)
def test_metrics_frame_rejects_invalid_scientific_metadata(extra, match):
    with pytest.raises(ValueError, match=match):
        metrics_frame([_mrow(**extra)])


def test_fits_frame():
    df = fits_frame([{"participant_id": "P01", "visit_ordinal": 2,
                      "g0": 40.0, "p0": 0.99, "tau0": 12.0, "curve": [1, 2]}])
    assert "curve" not in df.columns
    assert df["visit_c"].tolist() == [-1.5]
    assert fits_frame([]).empty


def test_fits_frame_rejects_invalid_or_duplicate_rows():
    valid = {"participant_id": "P01", "visit_ordinal": 1,
             "g0": 40.0, "p0": 0.99, "tau0": 12.0}
    with pytest.raises(ValueError, match="finite"):
        fits_frame([{**valid, "g0": float("nan")}])
    with pytest.raises(ValueError, match="duplicate participant"):
        fits_frame([valid, valid])


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("g0", 0.0, "g0"),
        ("g0", -1.0, "g0"),
        ("p0", -0.001, "p0"),
        ("p0", 1.001, "p0"),
        ("tau0", 0.0, "tau0"),
        ("tau0", -1.0, "tau0"),
    ],
)
def test_fits_frame_rejects_out_of_domain_depdf_parameters(field, value, match):
    valid = {
        "participant_id": "P01",
        "visit_ordinal": 1,
        "g0": 40.0,
        "p0": 0.99,
        "tau0": 12.0,
    }
    with pytest.raises(ValueError, match=match):
        fits_frame([{**valid, field: value}])


@pytest.mark.parametrize("p0", [0.0, 1.0])
def test_fits_frame_accepts_closed_probability_boundaries(p0):
    row = {
        "participant_id": "P01",
        "visit_ordinal": 1,
        "g0": 40.0,
        "p0": p0,
        "tau0": 12.0,
    }
    assert fits_frame([row]).iloc[0]["p0"] == p0


def test_fingerprint_is_order_invariant_and_value_sensitive():
    a = [_mrow(), _mrow(p="P02")]
    f1 = fingerprint(a, [])
    f2 = fingerprint(list(reversed(a)), [])
    f3 = fingerprint([_mrow(), _mrow(p="P02", value=0.9)], [])
    assert f1 == f2 != f3
    assert len(f1) == 64

    eligible = [_mrow(
        metrics_schema_version="2.0",
        metric_version="2",
        confirmatory_eligible=True,
    )]
    ineligible = [dict(eligible[0], confirmatory_eligible=False)]
    assert fingerprint(eligible, []) != fingerprint(ineligible, [])
