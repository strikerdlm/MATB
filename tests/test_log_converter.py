"""
Tests for matb_integration.log_converter.

Covers:
- CSV parsing robustness (whitespace, empty values, nan)
- SYSMON metrics: n_hits/misses/FA, hit_rate, d', mean_rt
- ISA metrics: probes list, mean, sd
- NASA-TLX metrics: subscales, raw_tlx
- COMM metrics: sdt_value→ n_hits/FA/CR, d'
- convert_session on the real smoke-test CSV (regression guard)
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
    _comm_metrics,
    _tracking_metrics,
    _resman_metrics,
    _activity_metrics,
    convert_session,
    convert_to_jsonl,
    parse_csv,
    NASA_TLX_SUBSCALES,
    NASA_TLX_SUBSCALES_ES,
    ISA_TITLE_ES,
)

# ── helpers ────────────────────────────────────────────────────────────────────

SMOKE_CSV = Path(__file__).resolve().parents[1] / (
    "openmatb/sessions/2026-05-03/27_260503_174528.csv"
)


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
    assert m["hit_rate"] == pytest.approx(0.5, abs=1e-4)
    assert m["mean_rt_ms"] == pytest.approx(1200.5, abs=0.1)
    assert m["d_prime"] is None  # no duration provided


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


def test_isa_reads_concurrent_isa_10_plugin_rows() -> None:
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,90.0,performance,instantaneousworkload,workload,8
    """)

    m = _isa_metrics(rows)

    assert m["scale"] == "ISA_1_to_10"
    assert m["n_probes_completed"] == 1
    assert m["mean"] == 8.0


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
    assert m["raw_tlx"] == pytest.approx(31.0 / 6.0, abs=0.01)
    assert m["unweighted_sum_0_60"] == pytest.approx(31.0, abs=0.01)
    assert m["complete"] is True
    assert m["mental_demand"] == pytest.approx(7.0)
    assert m["frustration"] == pytest.approx(2.0)
    assert m["raw_tlx_legacy_sum_0_60"] == 31.0
    assert m["raw_tlx_mean_0_10"] == pytest.approx(31 / 6, abs=1e-4)
    assert m["raw_tlx_0_100"] == pytest.approx((31 / 6) * 10, abs=1e-3)


def test_nasatlx_accepts_questionnaire_temporal_demand_title() -> None:
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,900.0,performance,genericscales,Temporal demand,8.0
    """)

    assert _nasatlx_metrics(rows)["time_pressure"] == 8.0


def test_nasatlx_partial():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,900.0,performance,genericscales,Mental demand,6.0
    """)
    m = _nasatlx_metrics(rows)
    assert m["n_subscales_completed"] == 1
    assert m["physical_demand"] is None
    assert m["raw_tlx"] is None
    assert m["complete"] is False
    assert m["reason_code"] == "incomplete_nasa_tlx"


def test_nasatlx_no_rows():
    m = _nasatlx_metrics([])
    assert m["n_subscales_completed"] == 0
    assert m["raw_tlx"] is None


# ── unit: COMM ────────────────────────────────────────────────────────────────

def test_comm_sdt_counts():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,53.0,performance,communications,sdt_value,HIT
        2.0,62.0,performance,communications,sdt_value,MISS
        3.0,80.0,performance,communications,sdt_value,FA
        4.0,85.0,performance,communications,sdt_value,CR
        5.0,53.0,performance,communications,response_time,2500.0
    """)
    m = _comm_metrics(rows)
    assert m["n_hits"] == 1
    assert m["n_misses"] == 1
    assert m["n_false_alarms"] == 1
    assert m["n_correct_rejections"] == 1
    assert m["hit_rate"] == pytest.approx(0.5, abs=1e-4)
    assert m["fa_rate"] == pytest.approx(0.5, abs=1e-4)
    assert m["d_prime"] is not None
    assert m["mean_rt_ms"] == pytest.approx(2500.0, abs=0.1)


def test_comm_no_rows():
    m = _comm_metrics([])
    assert m["n_hits"] == 0
    assert m["d_prime"] is None


def test_tracking_and_resource_metrics_preserve_raw_performance() -> None:
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,1.0,performance,track,center_deviation,10
        1.1,1.0,performance,track,cursor_in_target,True
        2.0,2.0,performance,track,center_deviation,30
        2.1,2.0,performance,track,cursor_in_target,False
        3.0,1.0,performance,resman,a_deviation,-200
        3.1,1.0,performance,resman,a_in_tolerance,True
        4.0,2.0,performance,resman,a_deviation,400
        4.1,2.0,performance,resman,a_in_tolerance,False
    """)

    tracking = _tracking_metrics(rows)
    resman = _resman_metrics(rows)

    assert tracking["mean_deviation"] == 20.0
    assert tracking["rmse_deviation"] == pytest.approx(math.sqrt(500))
    assert tracking["in_target_pct"] == 50.0
    assert resman["tank_a"]["mean_signed_deviation"] == 100.0
    assert resman["tank_a"]["mean_absolute_deviation"] == 300.0
    assert resman["tank_a"]["in_tolerance_pct"] == 50.0


def test_tracking_metrics_include_target_coverage_deviation_and_recovery() -> None:
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,1.0,performance,track,cursor_in_target,True
        1.1,1.1,performance,track,center_deviation,0
        1.2,1.2,performance,track,cursor_in_target,False
        1.3,1.3,performance,track,center_deviation,3
        1.4,1.4,performance,track,cursor_in_target,1
        1.5,1.5,performance,track,center_deviation,4
        1.6,1.6,performance,track,response_time,1200
        1.7,1.7,performance,track,response_time,800
    """)

    metrics = _tracking_metrics(rows)

    assert metrics["n_samples"] == 3
    assert metrics["in_target_pct"] == pytest.approx(66.6667)
    assert metrics["mean_center_deviation"] == pytest.approx(7 / 3)
    assert metrics["rms_center_deviation"] == pytest.approx(math.sqrt(25 / 3))
    assert metrics["p95_center_deviation"] == pytest.approx(3.9)
    assert metrics["n_recoveries"] == 2
    assert metrics["mean_recovery_rt_ms"] == pytest.approx(1000.0)


def test_resource_management_metrics_report_each_tank_and_combined_samples() -> None:
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,1.0,performance,resman,a_in_tolerance,True
        1.1,1.1,performance,resman,a_deviation,-100
        1.2,1.2,performance,resman,a_in_tolerance,False
        1.3,1.3,performance,resman,a_deviation,200
        1.4,1.4,performance,resman,a_response_time,4000
        1.5,1.5,performance,resman,b_in_tolerance,1
        1.6,1.6,performance,resman,b_deviation,50
    """)

    metrics = _resman_metrics(rows)

    assert list(metrics["tanks"]) == ["a", "b"]
    assert metrics["tanks"]["a"]["in_tolerance_pct"] == pytest.approx(50.0)
    assert metrics["tanks"]["a"]["mean_abs_deviation"] == pytest.approx(150.0)
    assert metrics["tanks"]["a"]["rms_deviation"] == pytest.approx(math.sqrt(25_000))
    assert metrics["tanks"]["a"]["max_abs_deviation"] == pytest.approx(200.0)
    assert metrics["tanks"]["a"]["mean_recovery_rt_ms"] == pytest.approx(4000.0)
    assert metrics["combined"]["n_tolerance_samples"] == 3
    assert metrics["combined"]["in_tolerance_pct"] == pytest.approx(200 / 3)
    assert metrics["combined"]["mean_abs_deviation"] == pytest.approx(350 / 3)


def test_activity_metrics_preserve_event_and_input_counts_by_module() -> None:
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,1.0,event,sysmon,self,start
        1.1,1.1,event,track,self,start
        1.2,1.2,input,keyboard,ENTER,press
        1.3,1.3,performance,track,center_deviation,3
        1.4,1.4,state,resman,tank-a-level,2500
    """)

    metrics = _activity_metrics(rows)

    assert metrics == {
        "total_rows": 5,
        "event_count": 2,
        "input_count": 1,
        "performance_row_count": 1,
        "state_row_count": 1,
        "events_by_module": {"sysmon": 1, "track": 1},
        "inputs_by_module": {"keyboard": 1},
    }


def test_convert_session_exposes_tracking_resource_and_activity_metrics(tmp_path: Path) -> None:
    csv_path = tmp_path / "session.csv"
    csv_path.write_text(
        "logtime,scenario_time,type,module,address,value\n"
        "1.0,1.0,performance,track,cursor_in_target,True\n"
        "1.1,1.1,performance,resman,a_in_tolerance,True\n"
        "1.2,1.2,input,keyboard,ENTER,press\n",
        encoding="utf-8",
    )

    record = convert_session(csv_path)

    assert record["tracking"]["in_target_pct"] == 100.0
    assert record["resource_management"]["tanks"]["a"]["in_tolerance_pct"] == 100.0
    assert record["activity"]["input_count"] == 1


def test_converter_ignores_only_an_incomplete_final_csv_append(tmp_path: Path) -> None:
    csv_path = tmp_path / "interrupted.csv"
    csv_path.write_text(
        "logtime,scenario_time,type,module,address,value\n"
        "1.0,1.0,performance,track,cursor_in_target,True\n"
        "2.0,2.0,performance,sysmon",
        encoding="utf-8",
    )

    record = convert_session(csv_path)

    assert record["n_rows"] == 1
    assert record["source_recovery"] == {
        "incomplete_final_csv_rows_ignored": 1,
        "warning_codes": ["incomplete_final_csv_row_ignored"],
    }
    assert record["csv_path"] == "interrupted.csv"

    csv_path.write_text(
        "logtime,scenario_time,type,module,address,value\n"
        "2.0,2.0,performance,sysmon\n"
        "3.0,3.0,performance,track,cursor_in_target,True\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="malformed_csv_row"):
        parse_csv(csv_path)


def test_converter_rejects_malformed_middle_row_when_valid_final_row_has_no_newline(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "corrupt-middle.csv"
    csv_path.write_text(
        "logtime,scenario_time,type,module,address,value\n"
        "1.0,1.0,performance,sysmon\n"
        "2.0,2.0,performance,track,cursor_in_target,True",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="malformed_csv_row"):
        convert_session(csv_path)


# ── integration: smoke-test CSV ───────────────────────────────────────────────

@pytest.mark.skipif(not SMOKE_CSV.exists(), reason="Smoke-test CSV not present")
def test_smoke_csv_sysmon_counts():
    """Session 27: 3 MISSes confirmed during smoke test, no HITs or FAs."""
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
    assert s["hit_rate"] == pytest.approx(0.0)   # 0 / (0+3) = 0.0


@pytest.mark.skipif(not SMOKE_CSV.exists(), reason="Smoke-test CSV not present")
def test_smoke_csv_comm_miss():
    """Session 27: 1 COMM MISS at t=85.4s (own callsign, no response)."""
    result = convert_session(SMOKE_CSV)
    c = result["comm"]
    assert c["n_misses"] == 1
    assert c["n_hits"] == 0


@pytest.mark.skipif(not SMOKE_CSV.exists(), reason="Smoke-test CSV not present")
def test_smoke_csv_isa_no_completed():
    """Session 27: ISA probe fired at t=90s but session ended at t=90.05s (no response)."""
    result = convert_session(SMOKE_CSV)
    assert result["isa"]["n_probes_completed"] == 0


@pytest.mark.skipif(not SMOKE_CSV.exists(), reason="Smoke-test CSV not present")
def test_smoke_csv_nasatlx_empty():
    """Session 27: no NASA-TLX (90s run, end of block at 900s not reached)."""
    result = convert_session(SMOKE_CSV)
    assert result["nasatlx"]["n_subscales_completed"] == 0


@pytest.mark.skipif(not SMOKE_CSV.exists(), reason="Smoke-test CSV not present")
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
    assert t["raw_tlx"] == pytest.approx(5.5)


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
