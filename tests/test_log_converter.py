"""
Tests for matb_integration.log_converter.

Covers:
- CSV parsing robustness (whitespace, empty values, nan)
- SYSMON metrics: n_hits/misses/FA, hit_rate, d', mean_rt
- ISA metrics: probes list, mean, sd
- NASA-TLX metrics: subscales, raw_tlx
- COMM metrics: sdt_value→ n_hits/FA/CR, d'
- convert_session on the synthetic smoke-test CSV (regression guard)
"""

from __future__ import annotations

import csv
import io
import json
import math
import textwrap
from pathlib import Path

import pytest

from matb_integration.log_converter import (
    _d_prime,
    _norm_ppf,
    _sysmon_metrics,
    _isa_metrics,
    _nasatlx_metrics,
    _bedford_metric,
    _comm_metrics,
    _track_metrics,
    _resman_metrics,
    convert_session,
    convert_to_jsonl,
    parse_csv,
    NASA_TLX_SUBSCALES,
    NASA_TLX_SUBSCALES_ES,
    ISA_TITLE_ES,
)

# ── helpers ────────────────────────────────────────────────────────────────────

SMOKE_CSV = Path(__file__).resolve().parent / 'fixtures' / 'synthetic_legacy_smoke.csv'


def _csv_rows(text: str) -> list[dict[str, str]]:
    """Parse CSV text to list of row dicts (mirrors parse_csv internals)."""
    reader = csv.DictReader(io.StringIO(textwrap.dedent(text).strip()))
    return [{k.strip(): v.strip() for k, v in row.items()} for row in reader]


# ── unit: probit / d' ─────────────────────────────────────────────────────────

def test_norm_ppf_midpoint():
    assert abs(_norm_ppf(0.5)) < 1e-10


def test_norm_ppf_symmetry():
    assert abs(_norm_ppf(0.84134) - 1.0) < 0.001


def test_d_prime_equal_rates():
    # Hit rate == FA rate → d' ≈ 0 (Hautus corrected, so not exactly 0 unless equal)
    dp = _d_prime(10, 10, 10, 10)
    assert dp is not None
    assert abs(dp) < 0.2


def test_d_prime_high_performance():
    dp = _d_prime(18, 2, 1, 19)
    assert dp is not None and dp > 2.0


def test_d_prime_undefined_no_signals():
    assert _d_prime(0, 0, 0, 0) is None


def test_d_prime_undefined_no_noise():
    assert _d_prime(5, 5, 0, 0) is None


def test_track_metrics_ignore_nonfinite_numeric_samples():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,1.0,performance,track,center_deviation,inf
        2.0,2.0,performance,track,center_deviation,-inf
        3.0,3.0,performance,track,center_deviation,nan
        4.0,4.0,performance,track,center_deviation,0.25
        5.0,5.0,performance,track,cursor_in_target,true
    """)

    metrics = _track_metrics(rows)
    assert metrics["n_samples"] == 1
    assert metrics["mean_absolute_deviation"] == 0.25
    assert metrics["rmse_deviation"] == 0.25


def test_jsonl_conversion_never_emits_nonstandard_nonfinite_constants(tmp_path: Path):
    source = tmp_path / "nonfinite.csv"
    source.write_text(
        "logtime,scenario_time,type,module,address,value\n"
        "1,1,performance,track,center_deviation,inf\n"
        "2,2,performance,track,center_deviation,nan\n"
        "3,3,performance,sysmon,signal_detection,HIT\n",
        encoding="utf-8",
    )

    line = convert_to_jsonl(source)

    assert "Infinity" not in line
    assert "NaN" not in line
    json.loads(line, parse_constant=lambda value: pytest.fail(value))


@pytest.mark.parametrize(
    "header",
    [
        "logtime,scenario_time,type,module,address,address",
        "logtime,scenario_time,type,module,address",
    ],
)
def test_parse_csv_rejects_duplicate_or_missing_required_headers(
    tmp_path: Path, header: str
) -> None:
    source = tmp_path / "malformed.csv"
    source.write_text(header + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="CSV header"):
        parse_csv(source)


def test_parse_csv_rejects_rows_with_extra_fields(tmp_path: Path) -> None:
    source = tmp_path / "malformed.csv"
    source.write_text(
        "logtime,scenario_time,type,module,address,value\n"
        "1,1,performance,sysmon,signal_detection,HIT,unexpected\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="row 2"):
        parse_csv(source)


# ── unit: SYSMON ──────────────────────────────────────────────────────────────

def test_sysmon_basic_counts():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,10.0,performance,sysmon,signal_detection,HIT
        1.1,10.1,performance,sysmon,response_time,1200.5
        1.2,20.0,performance,sysmon,signal_detection,MISS
        1.3,20.0,performance,sysmon,response_time,nan
        1.4,30.0,performance,sysmon,signal_detection,FA
    """)
    m = _sysmon_metrics(rows)
    assert m["n_hits"] == 1
    assert m["n_misses"] == 1
    assert m["n_false_alarms"] == 1
    assert m["n_signals"] == 2
    assert m["hit_rate"] is None
    assert m["hit_rate_legacy_v1"] == pytest.approx(0.5, abs=1e-4)
    assert m["mean_rt_ms"] is None
    assert m["mean_rt_ms_legacy_v1"] == pytest.approx(1200.5, abs=0.1)
    assert m["d_prime"] is None  # no duration provided
    assert m["dprime_observed_v2"] is None
    assert m["observed_opportunity_status"] == "unavailable"


def test_sysmon_d_prime_with_duration():
    # 10 signals over 900s, n_indicators=6, alerttimeout=10s → 540 total intervals → 530 non-signal
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,10.0,performance,sysmon,signal_detection,HIT
        1.1,20.0,performance,sysmon,signal_detection,HIT
        1.2,30.0,performance,sysmon,signal_detection,HIT
        1.3,40.0,performance,sysmon,signal_detection,HIT
        1.4,50.0,performance,sysmon,signal_detection,HIT
        1.5,60.0,performance,sysmon,signal_detection,HIT
        1.6,70.0,performance,sysmon,signal_detection,HIT
        1.7,80.0,performance,sysmon,signal_detection,HIT
        1.8,90.0,performance,sysmon,signal_detection,MISS
        1.9,100.0,performance,sysmon,signal_detection,MISS
    """)
    m = _sysmon_metrics(rows, alerttimeout_sec=10.0, n_indicators=6, scenario_duration_sec=900.0)
    assert m["d_prime"] is not None
    assert m["d_prime"] > 1.5  # high hit rate, 0 FA
    assert m["dprime_estimated_v1"] == m["d_prime"]
    assert m["estimated_confirmatory_eligible"] is False


def test_sysmon_observed_dprime_requires_unique_target_and_nontarget_opportunities():
    closed_payloads = [
        {"opportunity_id": "t1", "phase": "closed", "target": True, "outcome": "HIT", "response_time_ms": 500.0},
        {"opportunity_id": "t2", "phase": "closed", "target": True, "outcome": "MISS"},
        {"opportunity_id": "n1", "phase": "closed", "target": False, "outcome": "FA", "response_time_ms": 500.0},
        {"opportunity_id": "n2", "phase": "closed", "target": False, "outcome": "CR"},
    ]
    payloads = [
        {"opportunity_id": payload["opportunity_id"], "phase": "opened", "target": payload["target"]}
        for payload in closed_payloads
    ] + closed_payloads
    rows = [
        {"logtime": str(i), "scenario_time": str(i), "type": "performance",
         "module": "sysmon", "address": "opportunity", "value": json.dumps(payload)}
        for i, payload in enumerate(payloads)
    ]
    metrics = _sysmon_metrics(
        rows,
        expected_target_opportunities=2,
        expected_nontarget_opportunities=2,
    )
    assert metrics["observed_opportunity_status"] == "complete"
    assert metrics["dprime_observed_v2"] == pytest.approx(0.0)
    assert metrics["observed_opportunity_reconciled"] is True
    assert metrics["observed_confirmatory_eligible"] is False


def test_sysmon_automation_is_reconciled_but_excluded_from_human_performance():
    payloads = [
        {
            "opportunity_id": "auto-target",
            "phase": "opened",
            "target": True,
            "response_actor": "automation",
            "automation_active": True,
            "duration_ms": 1000,
            "opened_scenario_time_s": 0.0,
            "deadline_s": 1.0,
        },
        {
            "opportunity_id": "human-target",
            "phase": "opened",
            "target": True,
            "response_actor": "participant",
            "automation_active": False,
        },
        {
            "opportunity_id": "human-noise",
            "phase": "opened",
            "target": False,
            "response_actor": "participant",
            "automation_active": False,
        },
        {
            "opportunity_id": "auto-target",
            "phase": "closed",
            "target": True,
            "outcome": "HIT",
            "response_time_ms": 500.0,
            "response_actor": "automation",
            "automation_active": True,
            "opened_scenario_time_s": 0.0,
            "scheduled_deadline_s": 1.0,
        },
        {
            "opportunity_id": "human-target",
            "phase": "closed",
            "target": True,
            "outcome": "MISS",
            "response_actor": "participant",
            "automation_active": False,
        },
        {
            "opportunity_id": "human-noise",
            "phase": "closed",
            "target": False,
            "outcome": "CR",
            "response_actor": "participant",
            "automation_active": False,
        },
    ]
    rows = [
        {
            "type": "performance",
            "module": "sysmon",
            "address": "opportunity",
            "value": json.dumps(payload),
        }
        for payload in payloads
    ]

    metrics = _sysmon_metrics(
        rows,
        expected_target_opportunities=2,
        expected_nontarget_opportunities=1,
    )

    assert metrics["observed_opportunity_status"] == "complete"
    assert metrics["observed_opportunity_reconciled"] is True
    assert metrics["n_automated_opportunities"] == 1
    assert metrics["n_human_target_opportunities"] == 1
    assert metrics["observed_n_hits"] == 0
    assert metrics["observed_n_misses"] == 1
    assert metrics["hit_rate"] == 0.0
    assert metrics["human_performance_eligible"] is False


def test_sysmon_corrected_rt_uses_only_reconciled_human_target_hits():
    payloads = [
        {
            "opportunity_id": "automated-target",
            "phase": "opened",
            "target": True,
            "automation_active": True,
            "allocation_actor": "automation",
        },
        {
            "opportunity_id": "human-target",
            "phase": "opened",
            "target": True,
            "automation_active": False,
            "allocation_actor": "participant",
        },
        {
            "opportunity_id": "human-noise",
            "phase": "opened",
            "target": False,
            "automation_active": False,
            "allocation_actor": "participant",
        },
        {
            "opportunity_id": "automated-target",
            "phase": "closed",
            "target": True,
            "outcome": "HIT",
            "response_time_ms": 100.0,
            "automation_active": True,
            "response_actor": "automation",
        },
        {
            "opportunity_id": "human-target",
            "phase": "closed",
            "target": True,
            "outcome": "HIT",
            "response_time_ms": 900.0,
            "automation_active": False,
            "response_actor": "participant",
        },
        {
            "opportunity_id": "human-noise",
            "phase": "closed",
            "target": False,
            "outcome": "FA",
            "response_time_ms": 200.0,
            "automation_active": False,
            "response_actor": "participant",
        },
    ]
    rows = [
        {
            "type": "performance",
            "module": "sysmon",
            "address": "opportunity",
            "value": json.dumps(payload),
        }
        for payload in payloads
    ] + _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1,1,performance,sysmon,response_time,100
        2,2,performance,sysmon,response_time,900
    """)

    metrics = _sysmon_metrics(
        rows,
        expected_target_opportunities=2,
        expected_nontarget_opportunities=1,
    )

    assert metrics["observed_opportunity_status"] == "complete"
    assert metrics["mean_rt_ms"] == pytest.approx(900.0)
    assert metrics["mean_rt_ms_legacy_v1"] == pytest.approx(500.0)
    assert metrics["human_performance_eligible"] is False


def test_sysmon_corrected_rt_is_null_when_lifecycle_is_invalid():
    payloads = [
        {
            "opportunity_id": "target",
            "phase": "opened",
            "target": True,
            "automation_active": False,
        },
        {
            "opportunity_id": "target",
            "phase": "closed",
            "target": True,
            "outcome": "HIT",
            "response_time_ms": 700.0,
            "automation_active": False,
            "response_actor": "participant",
        },
        {
            "opportunity_id": "target",
            "phase": "closed",
            "target": True,
            "outcome": "HIT",
            "response_time_ms": 700.0,
            "automation_active": False,
            "response_actor": "participant",
        },
    ]
    rows = [
        {
            "type": "performance",
            "module": "sysmon",
            "address": "opportunity",
            "value": json.dumps(payload),
        }
        for payload in payloads
    ]

    metrics = _sysmon_metrics(
        rows,
        expected_target_opportunities=1,
        expected_nontarget_opportunities=0,
    )


def test_sysmon_response_outcomes_require_finite_nonnegative_response_time():
    payloads = [
        {
            "opportunity_id": "target",
            "phase": "opened",
            "target": True,
            "automation_active": False,
        },
        {
            "opportunity_id": "target",
            "phase": "closed",
            "target": True,
            "outcome": "HIT",
            "response_time_ms": None,
            "automation_active": False,
            "response_actor": "participant",
        },
    ]
    rows = [
        {
            "type": "performance",
            "module": "sysmon",
            "address": "opportunity",
            "value": json.dumps(payload),
        }
        for payload in payloads
    ]

    metrics = _sysmon_metrics(
        rows,
        expected_target_opportunities=1,
        expected_nontarget_opportunities=0,
    )

    assert metrics["observed_opportunity_status"] == "invalid"
    assert "missing_response_time:target" in metrics["observed_opportunity_issues"]

    assert metrics["observed_opportunity_status"] == "invalid"
    assert metrics["mean_rt_ms"] is None


def test_sysmon_automated_cr_is_excluded_from_human_nontarget_denominator():
    payloads = [
        {
            "opportunity_id": "human-target",
            "phase": "opened",
            "target": True,
            "automation_active": False,
            "allocation_actor": "participant",
        },
        {
            "opportunity_id": "automated-noise",
            "phase": "opened",
            "target": False,
            "automation_active": True,
            "allocation_actor": "automation",
        },
        {
            "opportunity_id": "human-target",
            "phase": "closed",
            "target": True,
            "outcome": "HIT",
            "response_time_ms": 500.0,
            "automation_active": False,
            "response_actor": "participant",
        },
        {
            "opportunity_id": "automated-noise",
            "phase": "closed",
            "target": False,
            "outcome": "CR",
            "automation_active": True,
            "response_actor": "automation",
        },
    ]
    rows = [
        {
            "type": "performance",
            "module": "sysmon",
            "address": "opportunity",
            "value": json.dumps(payload),
        }
        for payload in payloads
    ]

    metrics = _sysmon_metrics(
        rows,
        expected_target_opportunities=1,
        expected_nontarget_opportunities=1,
    )

    assert metrics["observed_opportunity_reconciled"] is True
    assert metrics["n_human_target_opportunities"] == 1
    assert metrics["n_human_nontarget_opportunities"] == 0
    assert metrics["n_automation_exposed_opportunities"] == 1
    assert metrics["dprime_observed_v2"] is None
    assert metrics["human_performance_eligible"] is False


def test_sysmon_lifecycle_timing_mismatch_invalidates_observed_evidence():
    payloads = [
        {
            "opportunity_id": "t1",
            "phase": "opened",
            "target": True,
            "duration_ms": 1000,
            "opened_scenario_time_s": 0.0,
            "deadline_s": 1.0,
        },
        {
            "opportunity_id": "t1",
            "phase": "closed",
            "target": True,
            "outcome": "HIT",
            "opened_scenario_time_s": 0.0,
            "scheduled_deadline_s": 10.0,
        },
    ]
    rows = [
        {
            "type": "performance",
            "module": "sysmon",
            "address": "opportunity",
            "value": json.dumps(payload),
        }
        for payload in payloads
    ]

    metrics = _sysmon_metrics(rows, expected_target_opportunities=1)

    assert metrics["observed_opportunity_status"] == "invalid"
    assert "deadline_mismatch:t1" in metrics["observed_opportunity_issues"]


def test_sysmon_observed_dprime_fails_closed_on_duplicate_outcome():
    payload = {"opportunity_id": "t1", "phase": "closed", "target": True, "outcome": "HIT"}
    rows = [
        {"type": "performance", "module": "sysmon", "address": "opportunity", "value": json.dumps(
            {"opportunity_id": "t1", "phase": "opened", "target": True}
        )},
        {"type": "performance", "module": "sysmon", "address": "opportunity", "value": json.dumps(payload)},
        {"type": "performance", "module": "sysmon", "address": "opportunity", "value": json.dumps(payload)},
    ]
    metrics = _sysmon_metrics(rows)
    assert metrics["observed_opportunity_status"] == "invalid"
    assert metrics["dprime_observed_v2"] is None


def test_sysmon_hit_rate_is_derived_from_reconciled_opportunities_and_rejects_channel_tampering():
    payloads = [
        {"opportunity_id": "t1", "phase": "opened", "target": True},
        {"opportunity_id": "t2", "phase": "opened", "target": True},
        {"opportunity_id": "n1", "phase": "opened", "target": False},
        {"opportunity_id": "t1", "phase": "closed", "target": True, "outcome": "HIT", "response_time_ms": 500.0},
        {"opportunity_id": "t2", "phase": "closed", "target": True, "outcome": "MISS"},
        {"opportunity_id": "n1", "phase": "closed", "target": False, "outcome": "CR"},
    ]
    rows = [
        {"type": "performance", "module": "sysmon", "address": "opportunity", "value": json.dumps(payload)}
        for payload in payloads
    ] + [
        {"type": "performance", "module": "sysmon", "address": "signal_detection", "value": "HIT"},
        {"type": "performance", "module": "sysmon", "address": "signal_detection", "value": "HIT"},
    ]

    metrics = _sysmon_metrics(
        rows,
        expected_target_opportunities=2,
        expected_nontarget_opportunities=1,
    )

    assert metrics["hit_rate_legacy_v1"] == 1.0
    assert metrics["hit_rate"] is None
    assert metrics["observed_opportunity_status"] == "invalid"
    assert any("legacy_opportunity_channel_mismatch" in issue for issue in metrics["observed_opportunity_issues"])


def test_sysmon_stalled_nontarget_window_is_never_confirmatory_evidence():
    payloads = [
        {
            "opportunity_id": "n1",
            "phase": "opened",
            "target": False,
            "duration_ms": 2000,
            "opened_scenario_time_s": 0.0,
            "deadline_s": 2.0,
        },
        {
            "opportunity_id": "n1",
            "phase": "closed",
            "target": False,
            "outcome": "INVALID_STALLED_WINDOW",
            "opened_scenario_time_s": 0.0,
            "scheduled_deadline_s": 2.0,
            "closed_scenario_time_s": 5.0,
            "lateness_ms": 3000,
        },
    ]
    rows = [
        {
            "type": "performance",
            "module": "sysmon",
            "address": "opportunity",
            "value": json.dumps(payload),
        }
        for payload in payloads
    ]

    metrics = _sysmon_metrics(
        rows,
        expected_target_opportunities=0,
        expected_nontarget_opportunities=1,
    )

    assert metrics["observed_opportunity_status"] == "invalid"
    assert metrics["dprime_observed_v2"] is None
    assert metrics["observed_confirmatory_eligible"] is False
    assert "invalid_outcome:n1" in metrics["observed_opportunity_issues"]


def test_sysmon_observed_dprime_is_incomplete_for_unclosed_or_unplanned_gaps():
    payloads = [
        {"opportunity_id": "t1", "phase": "opened", "target": True},
        {"opportunity_id": "t1", "phase": "closed", "target": True, "outcome": "HIT", "response_time_ms": 500.0},
        {"opportunity_id": "n1", "phase": "opened", "target": False},
    ]
    rows = [
        {"type": "performance", "module": "sysmon", "address": "opportunity", "value": json.dumps(payload)}
        for payload in payloads
    ]

    metrics = _sysmon_metrics(
        rows,
        expected_target_opportunities=2,
        expected_nontarget_opportunities=1,
    )

    assert metrics["observed_opportunity_status"] == "incomplete"
    assert metrics["dprime_observed_v2"] is None
    assert metrics["observed_confirmatory_eligible"] is False
    assert "unclosed_opportunity:n1" in metrics["observed_opportunity_issues"]
    assert any(
        issue.startswith("expected_target_count_mismatch")
        for issue in metrics["observed_opportunity_issues"]
    )


def test_sysmon_no_rows():
    m = _sysmon_metrics([])
    assert m["n_hits"] == 0
    assert m["hit_rate"] is None
    assert m["d_prime"] is None


# ── unit: ISA ─────────────────────────────────────────────────────────────────

def test_isa_single_probe():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,90.0,performance,genericscales,Workload,3.0
    """)
    m = _isa_metrics(rows)
    assert m["n_probes_completed"] == 1
    assert m["mean"] == pytest.approx(3.0)
    assert m["sd"] is None  # need at least 2 for stdev


def test_isa_multiple_probes():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,90.0,performance,genericscales,Workload,2.0
        2.0,180.0,performance,genericscales,Workload,4.0
        3.0,270.0,performance,genericscales,Workload,3.0
    """)
    m = _isa_metrics(rows)
    assert m["n_probes_completed"] == 3
    assert m["mean"] == pytest.approx(3.0, abs=1e-3)
    assert m["sd"] is not None and m["sd"] > 0


def test_isa_ignores_other_modules():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,90.0,performance,sysmon,Workload,3.0
        2.0,90.0,performance,genericscales,Mental demand,5.0
    """)
    m = _isa_metrics(rows)
    assert m["n_probes_completed"] == 0


def test_isa_no_probes():
    m = _isa_metrics([])
    assert m["n_probes_completed"] == 0
    assert m["mean"] is None


def test_isa_out_of_range_values_are_retained_as_invalid_but_not_scored():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,90.0,performance,genericscales,Workload,999
        2.0,180.0,performance,genericscales,Workload,5
    """)
    metrics = _isa_metrics(rows)
    assert metrics["mean"] == 5.0
    assert metrics["n_invalid_probes"] == 1
    assert metrics["invalid_probes"][0]["value_raw"] == 999.0
    assert metrics["confirmatory_eligible"] is False


def test_questionnaires_record_nonfinite_or_missing_values_as_invalid():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,90.0,performance,genericscales,Workload,nan
        2.0,900.0,performance,genericscales,Mental demand,nan
        3.0,900.0,performance,genericscales,Bedford,
    """)

    isa = _isa_metrics(rows)
    tlx = _nasatlx_metrics(rows)
    bedford = _bedford_metric(rows)

    assert isa["n_invalid_probes"] == 1
    assert isa["invalid_probes"][0]["reason"] == "missing_or_nonfinite_isa_value"
    assert tlx["invalid_subscales"] == ["mental_demand"]
    assert tlx["invalid_observations"][0]["reason"] == "missing_or_nonfinite_value"
    assert bedford["invalid_values"][0]["reason"] == "missing_or_nonfinite_value"


# ── unit: NASA-TLX ────────────────────────────────────────────────────────────

def test_nasatlx_full():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,900.0,performance,genericscales,Mental demand,7.0
        1.1,900.0,performance,genericscales,Physical demand,3.0
        1.2,900.0,performance,genericscales,Time pressure,8.0
        1.3,900.0,performance,genericscales,Performance,5.0
        1.4,900.0,performance,genericscales,Effort,6.0
        1.5,900.0,performance,genericscales,Frustration,2.0
    """)
    m = _nasatlx_metrics(rows)
    assert m["n_subscales_completed"] == 6
    assert m["raw_tlx"] == pytest.approx(31.0, abs=0.01)
    assert m["legacy_subscale_sum_0_60"] == pytest.approx(31.0, abs=0.01)
    assert m["rtlx_mean_0_10"] == pytest.approx(31 / 6, abs=0.001)
    assert m["rtlx_mean_0_100"] == pytest.approx((31 / 6) * 10, abs=0.001)
    assert m["weighted_tlx_0_100"] is None
    assert m["complete"] is True
    assert m["mental_demand"] == pytest.approx(7.0)
    assert m["frustration"] == pytest.approx(2.0)


def test_nasatlx_partial():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,900.0,performance,genericscales,Mental demand,6.0
    """)
    m = _nasatlx_metrics(rows)
    assert m["n_subscales_completed"] == 1
    assert m["physical_demand"] is None
    assert m["rtlx_mean_0_100"] is None
    assert m["confirmatory_eligible"] is False


def test_nasatlx_out_of_range_is_retained_for_legacy_but_v2_fails_closed():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,900.0,performance,genericscales,Mental demand,11.0
        1.1,900.0,performance,genericscales,Physical demand,3.0
        1.2,900.0,performance,genericscales,Temporal demand,8.0
        1.3,900.0,performance,genericscales,Performance,5.0
        1.4,900.0,performance,genericscales,Effort,6.0
        1.5,900.0,performance,genericscales,Frustration,2.0
    """)
    metrics = _nasatlx_metrics(rows)
    assert metrics["raw_tlx"] == pytest.approx(35.0)
    assert metrics["invalid_subscales"] == ["mental_demand"]
    assert metrics["rtlx_mean_0_100"] is None


def test_nasatlx_no_rows():
    m = _nasatlx_metrics([])
    assert m["n_subscales_completed"] == 0
    assert m["raw_tlx"] is None


def test_bedford_out_of_range_value_is_not_rounded_into_a_metric():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,900.0,performance,genericscales,Bedford,999
    """)
    metrics = _bedford_metric(rows)
    assert metrics["value"] is None
    assert metrics["value_raw"] == 999.0
    assert metrics["valid"] is False
    assert metrics["invalid_values"]


def test_duplicate_bedford_presentations_are_retained_but_ineligible():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,900.0,performance,genericscales,Bedford,4
        2.0,901.0,performance,genericscales,Bedford,6
    """)

    metrics = _bedford_metric(rows)

    assert metrics["value"] is None
    assert metrics["value_raw"] is None
    assert metrics["n_observations"] == 2
    assert [item["value_raw"] for item in metrics["observations"]] == [4.0, 6.0]
    assert metrics["valid"] is False
    assert metrics["confirmatory_eligible"] is False


def test_duplicate_tlx_subscale_invalidates_corrected_questionnaire():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1,900,performance,genericscales,Mental demand,4
        2,900,performance,genericscales,Mental demand,5
        3,900,performance,genericscales,Physical demand,2
        4,900,performance,genericscales,Time pressure,3
        5,900,performance,genericscales,Performance,6
        6,900,performance,genericscales,Effort,5
        7,900,performance,genericscales,Frustration,1
    """)

    metrics = _nasatlx_metrics(rows)

    assert metrics["n_rows_observed"] == 7
    assert metrics["duplicate_subscales"] == ["mental_demand"]
    assert metrics["complete"] is False
    assert metrics["rtlx_mean_0_100"] is None
    assert metrics["confirmatory_eligible"] is False


# ── unit: COMM ────────────────────────────────────────────────────────────────

def _comm_opportunity_row(
    logtime: float,
    scenario_time: float,
    opportunity_id: str,
    destination: str,
    phase: str,
    **details,
) -> str:
    payload = {
        "schema_version": "1.0",
        "opportunity_id": opportunity_id,
        "destination": destination,
        "phase": phase,
        **details,
    }
    return (
        f'{logtime},{scenario_time},performance,communications,comm_opportunity_v1,'
        f'"{json.dumps(payload, sort_keys=True).replace(chr(34), chr(34) * 2)}"'
    )


def test_comm_legacy_outcomes_are_preserved_but_not_promoted_to_observed_metrics():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,53.0,performance,communications,sdt_value,HIT
        2.0,62.0,performance,communications,sdt_value,MISS
        3.0,80.0,performance,communications,sdt_value,FA
        4.0,85.0,performance,communications,sdt_value,CR
        5.0,53.0,performance,communications,response_time,2500.0
    """)
    m = _comm_metrics(rows, expected_opportunities=4)
    assert m["n_hits"] == 0
    assert m["n_misses"] == 0
    assert m["n_false_alarms"] == 0
    assert m["n_correct_rejections"] == 0
    assert m["d_prime"] is None
    assert m["mean_rt_ms"] is None
    assert m["n_hits_legacy_v1"] == 1
    assert m["n_misses_legacy_v1"] == 1
    assert m["n_false_alarms_legacy_v1"] == 1
    assert m["n_correct_rejections_legacy_v1"] == 1
    assert m["d_prime_legacy_v1"] is not None
    assert m["mean_rt_ms_legacy_v1"] == pytest.approx(2500.0, abs=0.1)
    assert m["observed_opportunity_status"] == "unavailable"
    assert m["observed_opportunity_reconciled"] is False


def test_comm_complete_explicit_lifecycles_are_counted_and_reconciled():
    lines = ["logtime,scenario_time,type,module,address,value"]
    trial_specs = (
        ("comm-000001", "own", "HIT", 1250.0),
        ("comm-000002", "own", "MISS", None),
        ("comm-000003", "other", "FA", 800.0),
        ("comm-000004", "other", "CR", None),
    )
    now = 1.0
    for opportunity_id, destination, outcome, response_time_ms in trial_specs:
        lines.append(_comm_opportunity_row(now, now, opportunity_id, destination, "opened"))
        now += 0.1
        lines.append(_comm_opportunity_row(
            now, now, opportunity_id, destination, "presentation_started",
            software_play_invoked=True, physical_onset_measured=False,
        ))
        now += 0.1
        lines.append(_comm_opportunity_row(now, now, opportunity_id, destination, "response_window_opened"))
        now += 0.1
        lines.append(_comm_opportunity_row(
            now, now, opportunity_id, destination, "closed",
            outcome=outcome, response_time_ms=response_time_ms,
        ))
        now += 0.1
    rows = _csv_rows("\n".join(lines))

    m = _comm_metrics(rows, expected_opportunities=4)

    assert m["n_hits"] == 1
    assert m["n_misses"] == 1
    assert m["n_false_alarms"] == 1
    assert m["n_correct_rejections"] == 1
    assert m["hit_rate"] == pytest.approx(0.5, abs=1e-4)
    assert m["fa_rate"] == pytest.approx(0.5, abs=1e-4)
    assert m["d_prime"] is not None
    assert m["mean_rt_ms"] == pytest.approx(1025.0, abs=0.1)
    assert m["n_opened_opportunities"] == 4
    assert m["n_observed_opportunities"] == 4
    assert m["observed_opportunity_status"] == "complete"
    assert m["observed_opportunity_reconciled"] is True
    assert m["observed_confirmatory_eligible"] is False
    assert m["physical_onset_qualified"] is False


def test_comm_automation_is_reconciled_but_excluded_from_human_metrics():
    lines = ["logtime,scenario_time,type,module,address,value"]
    trials = (
        ("auto", "own", "HIT", 400.0, True, "automation"),
        ("human-signal", "own", "MISS", None, False, "participant"),
        ("human-noise", "other", "CR", None, False, "participant"),
    )
    now = 1.0
    for opportunity_id, destination, outcome, rt, automation_active, actor in trials:
        shared = {"automation_active": automation_active}
        lines.append(_comm_opportunity_row(
            now, now, opportunity_id, destination, "opened", **shared
        ))
        now += 0.1
        lines.append(_comm_opportunity_row(
            now, now, opportunity_id, destination, "presentation_started",
            software_play_invoked=True, physical_onset_measured=False, **shared,
        ))
        now += 0.1
        lines.append(_comm_opportunity_row(
            now, now, opportunity_id, destination, "response_window_opened", **shared
        ))
        now += 0.1
        lines.append(_comm_opportunity_row(
            now, now, opportunity_id, destination, "closed",
            outcome=outcome, response_time_ms=rt, response_actor=actor, **shared,
        ))
        now += 0.1

    metrics = _comm_metrics(_csv_rows("\n".join(lines)), expected_opportunities=3)

    assert metrics["observed_opportunity_status"] == "complete"
    assert metrics["observed_opportunity_reconciled"] is True
    assert metrics["n_automated_opportunities"] == 1
    assert metrics["n_observed_opportunities"] == 3
    assert metrics["n_human_observed_opportunities"] == 2
    assert metrics["n_hits"] == 0
    assert metrics["n_misses"] == 1
    assert metrics["n_correct_rejections"] == 1
    assert metrics["human_performance_eligible"] is False


def test_comm_participant_intervention_during_automation_is_not_pure_human_data():
    lines = ["logtime,scenario_time,type,module,address,value"]
    shared = {"automation_active": True}
    lines.extend([
        _comm_opportunity_row(1, 1, "mixed", "own", "opened", **shared),
        _comm_opportunity_row(
            2, 2, "mixed", "own", "presentation_started",
            software_play_invoked=True, physical_onset_measured=False, **shared,
        ),
        _comm_opportunity_row(
            3, 3, "mixed", "own", "response_window_opened", **shared,
        ),
        _comm_opportunity_row(
            4, 4, "mixed", "own", "closed", outcome="HIT",
            response_time_ms=500.0, response_actor="participant", **shared,
        ),
    ])

    metrics = _comm_metrics(_csv_rows("\n".join(lines)), expected_opportunities=1)

    assert metrics["observed_opportunity_reconciled"] is True
    assert metrics["n_observed_opportunities"] == 1
    assert metrics["n_human_observed_opportunities"] == 0
    assert metrics["n_automation_exposed_opportunities"] == 1
    assert metrics["n_participant_interventions_during_automation"] == 1
    assert metrics["n_hits"] == 0
    assert metrics["human_performance_eligible"] is False


def test_comm_expected_count_mismatch_nulls_corrected_aggregate():
    lines = ["logtime,scenario_time,type,module,address,value"]
    for index, (destination, outcome) in enumerate(
        (("own", "HIT"), ("own", "MISS"), ("other", "FA"), ("other", "CR")),
        start=1,
    ):
        opportunity_id = f"comm-{index:06d}"
        lines.extend([
            _comm_opportunity_row(index, index, opportunity_id, destination, "opened"),
            _comm_opportunity_row(
                index + 0.1, index + 0.1, opportunity_id, destination,
                "presentation_started", software_play_invoked=True,
                physical_onset_measured=False,
            ),
            _comm_opportunity_row(
                index + 0.2, index + 0.2, opportunity_id, destination,
                "response_window_opened",
            ),
            _comm_opportunity_row(
                index + 0.3, index + 0.3, opportunity_id, destination, "closed",
                outcome=outcome,
                response_time_ms=500.0 if outcome in {"HIT", "FA"} else None,
            ),
        ])

    metrics = _comm_metrics(_csv_rows("\n".join(lines)), expected_opportunities=5)

    assert metrics["observed_opportunity_status"] == "count_mismatch"
    assert metrics["n_opened_opportunities"] == 4
    assert metrics["n_observed_opportunities"] == 0
    assert metrics["n_hits"] == 0
    assert metrics["d_prime"] is None
    assert metrics["mean_rt_ms"] is None


def test_comm_invalid_or_incomplete_lifecycle_fails_closed():
    lines = [
        "logtime,scenario_time,type,module,address,value",
        _comm_opportunity_row(1, 1, "comm-000001", "own", "opened"),
        _comm_opportunity_row(2, 2, "comm-000001", "own", "presentation_started"),
        _comm_opportunity_row(3, 3, "comm-000001", "own", "invalidated", reason="task_stopped"),
    ]
    m = _comm_metrics(_csv_rows("\n".join(lines)), expected_opportunities=1)

    assert m["n_observed_opportunities"] == 0
    assert m["d_prime"] is None
    assert m["observed_opportunity_status"] == "invalid"
    assert m["observed_opportunity_reconciled"] is False
    assert any("invalidated" in issue for issue in m["observed_opportunity_issues"])


def test_comm_no_rows():
    m = _comm_metrics([], expected_opportunities=0)
    assert m["n_hits"] == 0
    assert m["d_prime"] is None


def test_track_metrics_propagate_deviation_target_time_and_recovery():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,1.0,performance,track,center_deviation,0.3
        1.1,1.1,performance,track,center_deviation,0.4
        1.2,1.2,performance,track,cursor_in_target,True
        1.3,1.3,performance,track,cursor_in_target,False
        1.4,1.4,performance,track,response_time,600
    """)
    metrics = _track_metrics(rows)
    assert metrics["rmse_deviation"] == pytest.approx(math.sqrt(0.125), abs=0.0001)
    assert metrics["mean_absolute_deviation"] == pytest.approx(0.35)
    assert metrics["percent_time_in_target"] == 50.0
    assert metrics["recovery_time_ms"]["mean"] == 600.0


def test_resman_metrics_propagate_target_deviation_tolerance_and_recovery():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,1.0,performance,resman,a_deviation,-100
        1.1,1.1,performance,resman,a_deviation,200
        1.2,1.2,performance,resman,a_in_tolerance,True
        1.3,1.3,performance,resman,a_in_tolerance,False
        1.4,1.4,performance,resman,a_response_time,2000
    """)
    metrics = _resman_metrics(rows)
    assert metrics["mean_absolute_deviation"] == 150.0
    assert metrics["percent_time_in_tolerance"] == 50.0
    assert metrics["recovery_time_ms"]["median"] == 2000.0
    assert metrics["by_tank"]["a"]["n_samples"] == 2


# ── integration: smoke-test CSV ───────────────────────────────────────────────

def test_csv_conversion_is_explicitly_marked_as_unreconciled_legacy_source(tmp_path):
    csv_path = tmp_path / "session.csv"
    csv_path.write_text(
        "logtime,scenario_time,type,module,address,value\n",
        encoding="utf-8",
    )

    record = convert_session(csv_path)

    assert record["scientific_source_status"] == (
        "legacy_csv_derived_not_reconciled_to_authoritative_event_stream"
    )


def test_extra_metadata_cannot_overwrite_scientific_contract_fields(tmp_path: Path):
    csv_path = tmp_path / "session.csv"
    csv_path.write_text(
        "logtime,scenario_time,type,module,address,value\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="reserved conversion fields"):
        convert_session(
            csv_path,
            extra_metadata={"scientific_source_status": "forged"},
        )


def test_smoke_csv_sysmon_counts():
    """Synthetic legacy fixture: 3 MISSes confirmed during smoke test, no HITs or FAs."""
    result = convert_session(
        SMOKE_CSV,
        participant_id="SMOKE",
        block_name="low_workload",
        workload_level="LOW",
    )
    s = result["sysmon"]
    assert s["n_misses"] == 3
    assert s["n_hits"] == 0
    assert s["n_false_alarms"] == 0
    assert s["hit_rate"] is None
    assert s["hit_rate_legacy_v1"] == pytest.approx(0.0)  # 0 / (0+3) = 0.0


def test_smoke_csv_comm_miss():
    """Synthetic legacy fixture: 1 COMM MISS at t=85.4s (own callsign, no response)."""
    result = convert_session(SMOKE_CSV)
    c = result["comm"]
    assert c["n_misses"] == 0
    assert c["n_hits"] == 0
    assert c["n_misses_legacy_v1"] == 1
    assert c["observed_opportunity_status"] == "unavailable"


def test_smoke_csv_isa_no_completed():
    """Synthetic legacy fixture: ISA probe fired at t=90s but session ended at t=90.05s (no response)."""
    result = convert_session(SMOKE_CSV)
    assert result["isa"]["n_probes_completed"] == 0


def test_smoke_csv_nasatlx_empty():
    """Synthetic legacy fixture: no NASA-TLX (90s run, end of block at 900s not reached)."""
    result = convert_session(SMOKE_CSV)
    assert result["nasatlx"]["n_subscales_completed"] == 0


def test_smoke_csv_jsonl_roundtrip(tmp_path):
    """JSONL output must be valid JSON with expected top-level keys."""
    out = tmp_path / "output.jsonl"
    line = convert_to_jsonl(
        SMOKE_CSV,
        output_path=out,
        participant_id="P00",
        block_name="low_workload",
        workload_level="LOW",
    )
    data = json.loads(line)
    assert data["metrics_schema_version"] == "2.0"
    assert data["scientific_source_status"] == (
        "legacy_csv_derived_not_reconciled_to_authoritative_event_stream"
    )
    assert data["participant_id"] == "P00"
    assert data["workload_level"] == "LOW"
    assert "sysmon" in data and "isa" in data and "nasatlx" in data and "comm" in data

    # Also verify the written file
    written = out.read_text().strip()
    assert json.loads(written) == data


# ── Spanish-language questionnaire support ────────────────────────────────────

def test_nasatlx_es_subscale_count():
    assert len(NASA_TLX_SUBSCALES_ES) == len(NASA_TLX_SUBSCALES)


def test_nasatlx_es_titles_recognised(tmp_path):
    """log_converter must parse Spanish NASA-TLX rows into English-keyed output."""
    csv_content = (
        "logtime,scenario_time,type,module,address,value\n"
        "1.0,900.0,performance,genericscales,Demanda mental,7.0\n"
        "1.1,900.0,performance,genericscales,Demanda física,3.0\n"
        "1.2,900.0,performance,genericscales,Demanda temporal,5.0\n"
        "1.3,900.0,performance,genericscales,Rendimiento,6.0\n"
        "1.4,900.0,performance,genericscales,Esfuerzo,8.0\n"
        "1.5,900.0,performance,genericscales,Frustración,4.0\n"
    )
    csv_path = tmp_path / "es_session.csv"
    csv_path.write_text(csv_content)
    result = convert_session(csv_path)
    t = result["nasatlx"]
    assert t["n_subscales_completed"] == 6
    assert t["mental_demand"] == pytest.approx(7.0)
    assert t["effort"] == pytest.approx(8.0)
    assert t["raw_tlx"] == pytest.approx(33.0)


def test_isa_es_title_recognised(tmp_path):
    """ISA Spanish title 'Carga de trabajo' must be parsed as an ISA probe."""
    csv_content = (
        "logtime,scenario_time,type,module,address,value\n"
        "1.0,90.0,performance,genericscales,Carga de trabajo,3.0\n"
        "1.1,180.0,performance,genericscales,Carga de trabajo,4.0\n"
    )
    csv_path = tmp_path / "es_isa.csv"
    csv_path.write_text(csv_content)
    result = convert_session(csv_path)
    isa = result["isa"]
    assert isa["n_probes_completed"] == 2
    assert isa["mean"] == pytest.approx(3.5)


def test_mixed_en_es_nasatlx_rows(tmp_path):
    """Mixed English and Spanish rows in the same session should both be parsed."""
    csv_content = (
        "logtime,scenario_time,type,module,address,value\n"
        "1.0,900.0,performance,genericscales,Mental demand,7.0\n"
        "1.1,900.0,performance,genericscales,Demanda física,3.0\n"
    )
    csv_path = tmp_path / "mixed.csv"
    csv_path.write_text(csv_content)
    result = convert_session(csv_path)
    t = result["nasatlx"]
    assert t["mental_demand"] == pytest.approx(7.0)
    assert t["physical_demand"] == pytest.approx(3.0)
    assert t["n_subscales_completed"] == 2


# ---------------------------------------------------------------------------
# SAGAT metric tests
# ---------------------------------------------------------------------------

def _make_sagat_csv_rows(rows: list[tuple[str, str, str]]) -> list[dict]:
    """Helper: convert (module, address, value) triples into log_converter row dicts."""
    out = []
    for i, (module, address, value) in enumerate(rows):
        out.append({
            "logtime": f"2026-05-20 12:00:{i:02d}",
            "scenario_time": str(i),
            "type": "performance",
            "module": module,
            "address": address,
            "value": value,
        })
    return out


def test_sagat_single_freeze_aggregation():
    from matb_integration.log_converter import _sagat_metric

    rows = _make_sagat_csv_rows([
        ("sagat", "probe_id", "gen_l1_a"),
        ("sagat", "sa_level", "1"),
        ("sagat", "domain", "perception"),
        ("sagat", "question_text", "Q1?"),
        ("sagat", "options_text", "a | b | Unknown"),
        ("sagat", "given_answer", "a"),
        ("sagat", "correct_answer", "a"),
        ("sagat", "is_correct", "True"),
        ("sagat", "latency_sec", "3.2"),
        ("sagat", "freeze_id", "P03_b1_f1"),

        ("sagat", "probe_id", "gen_l2_a"),
        ("sagat", "sa_level", "2"),
        ("sagat", "domain", "comprehension"),
        ("sagat", "question_text", "Q2?"),
        ("sagat", "options_text", "yes | no | Unknown"),
        ("sagat", "given_answer", "no"),
        ("sagat", "correct_answer", "yes"),
        ("sagat", "is_correct", "False"),
        ("sagat", "latency_sec", "5.1"),
        ("sagat", "freeze_id", "P03_b1_f1"),
    ])
    out = _sagat_metric(rows, manifest_path=None)
    assert out["n_probes_total"] == 2
    assert out["n_probes_answered"] == 2
    assert out["n_probes_timeout"] == 0
    assert out["sa_score_level_1_pct"] == 100.0
    assert out["sa_score_level_2_pct"] == 0.0
    assert out["sa_score_overall_pct"] == 50.0
    assert len(out["freeze_details"]) == 1
    assert out["freeze_details"][0]["probes"][0]["question"] == "Q1?"
    assert out["freeze_details"][0]["probes"][0]["options"] == ["a", "b", "Unknown"]


def test_sagat_per_level_aggregation():
    from matb_integration.log_converter import _sagat_metric

    def probe(pid, lvl, dom, given, correct, freeze):
        return [
            ("sagat", "probe_id", pid),
            ("sagat", "sa_level", str(lvl)),
            ("sagat", "domain", dom),
            ("sagat", "question_text", "Q?"),
            ("sagat", "options_text", "a | b"),
            ("sagat", "given_answer", given),
            ("sagat", "correct_answer", correct),
            ("sagat", "is_correct", str(given == correct)),
            ("sagat", "latency_sec", "1.0"),
            ("sagat", "freeze_id", freeze),
        ]

    triples: list[tuple[str, str, str]] = []
    # 3 L1: 2 correct, 1 wrong -> 66.7
    for i, ok in enumerate([True, True, False]):
        triples += probe(f"l1_{i}", 1, "perception", "a", "a" if ok else "b", "P03_b1_f1")
    # 3 L2: 1 correct, 2 wrong -> 33.3
    for i, ok in enumerate([True, False, False]):
        triples += probe(f"l2_{i}", 2, "comprehension", "a", "a" if ok else "b", "P03_b1_f2")
    # 3 L3: 0 correct -> 0.0
    for i in range(3):
        triples += probe(f"l3_{i}", 3, "projection", "a", "b", "P03_b1_f3")

    out = _sagat_metric(_make_sagat_csv_rows(triples), manifest_path=None)
    assert round(out["sa_score_level_1_pct"], 1) == 66.7
    assert round(out["sa_score_level_2_pct"], 1) == 33.3
    assert out["sa_score_level_3_pct"] == 0.0
    assert round(out["sa_score_overall_pct"], 1) == 33.3


def test_sagat_timeout_handling():
    from matb_integration.log_converter import _sagat_metric

    rows = _make_sagat_csv_rows([
        ("sagat", "probe_id", "g_a"),
        ("sagat", "sa_level", "1"),
        ("sagat", "domain", "perception"),
        ("sagat", "question_text", "Q?"),
        ("sagat", "options_text", "a | b"),
        ("sagat", "given_answer", "TIMEOUT"),
        ("sagat", "correct_answer", "a"),
        ("sagat", "is_correct", "False"),
        ("sagat", "latency_sec", "15.0"),
        ("sagat", "freeze_id", "P03_b1_f1"),
    ])
    out = _sagat_metric(rows, manifest_path=None)
    assert out["n_probes_total"] == 1
    assert out["n_probes_answered"] == 0
    assert out["n_probes_timeout"] == 1
    assert out["mean_latency_sec"] == 15.0


def test_sagat_manifest_cross_check(tmp_path):
    from matb_integration.log_converter import _sagat_metric
    import json as _json

    manifest = {
        "participant_id": "P03",
        "block_num": 1,
        "seed": 42,
        "bank": "sagat_generic_en.txt",
        "freezes": [
            {"freeze_id": "P03_b1_f1", "scenario_time_sec": 300.0,
             "probe_file": "x.txt", "probe_ids": ["g_a"]},
            {"freeze_id": "P03_b1_f2", "scenario_time_sec": 600.0,
             "probe_file": "y.txt", "probe_ids": ["g_b"]},
        ],
    }
    manifest_path = tmp_path / "P03_block1_sagat_manifest.json"
    manifest_path.write_text(_json.dumps(manifest), encoding="utf-8")

    # CSV only includes the FIRST freeze - second one never fired
    rows = _make_sagat_csv_rows([
        ("sagat", "probe_id", "g_a"),
        ("sagat", "sa_level", "1"),
        ("sagat", "domain", "perception"),
        ("sagat", "question_text", "Q?"),
        ("sagat", "options_text", "a | b"),
        ("sagat", "given_answer", "a"),
        ("sagat", "correct_answer", "a"),
        ("sagat", "is_correct", "True"),
        ("sagat", "latency_sec", "1.0"),
        ("sagat", "freeze_id", "P03_b1_f1"),
    ])
    out = _sagat_metric(rows, manifest_path=manifest_path)
    assert out["n_freezes_planned"] == 2
    assert out["n_freezes_executed"] == 1
    executed_flags = [f["executed"] for f in out["freeze_details"]]
    assert executed_flags == [True, False]


def test_convert_session_selects_only_the_exact_participant_block_sagat_manifest(
    tmp_path,
):
    csv_path = tmp_path / "session.csv"
    csv_path.write_text(
        "logtime,scenario_time,type,module,address,value\n", encoding="utf-8"
    )
    for participant in ("P01", "P02"):
        manifest = {
            "participant_id": participant,
            "block_num": 1,
            "seed": 42,
            "bank": "sagat_generic_en.txt",
            "freezes": [{
                "freeze_id": f"{participant}_b1_f1",
                "scenario_time_sec": 300.0,
                "probe_file": f"{participant}_freeze1.txt",
                "probe_ids": ["g_a"],
            }],
        }
        (tmp_path / f"{participant}_block1_sagat_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    record = convert_session(
        csv_path,
        participant_id="P01",
        block_name="block_1",
        sagat_manifest_dir=tmp_path,
    )

    assert record["sagat"]["manifest_status"] == "verified"
    assert record["sagat"]["n_freezes_planned"] == 1
    assert record["sagat"]["freeze_details"][0]["freeze_id"] == "P01_b1_f1"


def test_convert_session_rejects_wrong_identity_sagat_manifest_without_crashing(
    tmp_path,
):
    csv_path = tmp_path / "session.csv"
    csv_path.write_text(
        "logtime,scenario_time,type,module,address,value\n", encoding="utf-8"
    )
    wrong = {
        "participant_id": "P02",
        "block_num": 1,
        "seed": 42,
        "bank": "sagat_generic_en.txt",
        "freezes": [{
            "freeze_id": "P02_b1_f1",
            "scenario_time_sec": 300.0,
            "probe_file": "wrong.txt",
            "probe_ids": ["g_a"],
        }],
    }
    exact_name = tmp_path / "P01_block1_sagat_manifest.json"
    exact_name.write_text(json.dumps(wrong), encoding="utf-8")

    record = convert_session(
        csv_path,
        participant_id="P01",
        block_name="block_1",
        sagat_manifest_path=exact_name,
    )

    assert record["sagat"]["manifest_status"] == "invalid"
    assert record["sagat"]["n_freezes_planned"] is None
    assert "participant_id_mismatch" in record["sagat"]["manifest_issues"]


def test_sagat_snapshot_round_trip():
    from matb_integration.log_converter import _sagat_metric

    rows = _make_sagat_csv_rows([
        ("sagat", "snapshot_track_cursor_position", "[0.45, 0.51]"),
        ("sagat", "snapshot_sysmon_lights_failed", "{'1': True, '2': False}"),
        ("sagat", "probe_id", "g_a"),
        ("sagat", "sa_level", "1"),
        ("sagat", "domain", "perception"),
        ("sagat", "question_text", "Q?"),
        ("sagat", "options_text", "a | b"),
        ("sagat", "given_answer", "a"),
        ("sagat", "correct_answer", "a"),
        ("sagat", "is_correct", "True"),
        ("sagat", "latency_sec", "1.0"),
        ("sagat", "freeze_id", "P03_b1_f1"),
    ])
    out = _sagat_metric(rows, manifest_path=None)
    snap = out["freeze_details"][0]["snapshot"]
    assert "track_cursor_position" in snap
    assert "sysmon_lights_failed" in snap


def test_sagat_es_text_preserved_through_converter():
    from matb_integration.log_converter import _sagat_metric

    rows = _make_sagat_csv_rows([
        ("sagat", "probe_id", "g_a"),
        ("sagat", "sa_level", "1"),
        ("sagat", "domain", "perception"),
        ("sagat", "question_text", "¿Cuántas tareas?"),
        ("sagat", "options_text", "0 | 1 | No sé"),
        ("sagat", "given_answer", "1"),
        ("sagat", "correct_answer", "1"),
        ("sagat", "is_correct", "True"),
        ("sagat", "latency_sec", "1.0"),
        ("sagat", "freeze_id", "P03_b1_f1"),
    ])
    out = _sagat_metric(rows, manifest_path=None)
    p = out["freeze_details"][0]["probes"][0]
    assert p["question"] == "¿Cuántas tareas?"
    assert "No sé" in p["options"]
