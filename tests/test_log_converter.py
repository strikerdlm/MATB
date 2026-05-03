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
    convert_session,
    convert_to_jsonl,
    parse_csv,
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
    assert m["raw_tlx"] == pytest.approx(31.0, abs=0.01)
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
