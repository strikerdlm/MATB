"""
Tests for:
  - block_order_for_participant (complete permutation counterbalancing)
  - build_session_files (generates 3 per-participant scenario files)
  - Bedford questionnaire file format
  - log_converter._bedford_metric
  - analysis.descriptive (pivot, Friedman, Spearman)
"""

from __future__ import annotations

import csv
import io
import json
import textwrap
from pathlib import Path

import pytest

from aircraft_monitor.research.protocol import WorkloadLevel
from matb_integration.scenario_builder import (
    COMPLETE_COUNTERBALANCE_3,
    LATIN_SQUARE_3,
    block_order_for_participant,
    build_session_files,
    BEDFORD_QUESTIONNAIRE,
)
from matb_integration.log_converter import _bedford_metric, convert_session
from matb_integration.analysis.descriptive import (
    _get,
    _pivot,
    analyse_metric,
    load_records,
    LEVEL_RANK,
)

BEDFORD_TXT = (
    Path(__file__).resolve().parents[1]
    / "matb_integration/questionnaires/bedford_en.txt"
)

# ── Complete permutation counterbalancing ────────────────────────────────────

def test_legacy_latin_square_name_is_an_alias():
    assert LATIN_SQUARE_3 is COMPLETE_COUNTERBALANCE_3

def test_latin_square_has_six_rows():
    assert len(COMPLETE_COUNTERBALANCE_3) == 6


def test_latin_square_each_row_is_permutation():
    levels = {WorkloadLevel.LOW, WorkloadLevel.MEDIUM, WorkloadLevel.HIGH}
    for row in LATIN_SQUARE_3:
        assert set(row) == levels


def test_latin_square_each_level_appears_once_per_row():
    for row in LATIN_SQUARE_3:
        assert len(row) == len(set(row)) == 3


def test_latin_square_all_rows_distinct():
    assert len(set(LATIN_SQUARE_3)) == 6


def test_block_order_numeric_suffix():
    assert block_order_for_participant("P00") == LATIN_SQUARE_3[0]
    assert block_order_for_participant("P05") == LATIN_SQUARE_3[5]
    assert block_order_for_participant("P06") == LATIN_SQUARE_3[0]  # wraps


def test_block_order_no_digits_defaults_to_row_0():
    assert block_order_for_participant("control") == LATIN_SQUARE_3[0]


def test_block_order_six_consecutive_participants_cover_all_orderings():
    orders = [block_order_for_participant(f"P{i:02d}") for i in range(6)]
    assert len(set(orders)) == 6


def test_block_order_24_participants_fully_balanced():
    from collections import Counter
    counts: Counter = Counter()
    for i in range(24):
        order = block_order_for_participant(f"P{i:02d}")
        counts[order] += 1
    # Each of the 6 orderings should appear exactly 4 times
    assert all(v == 4 for v in counts.values())


# ── build_session_files ───────────────────────────────────────────────────────

def test_build_session_files_creates_three_files(tmp_path):
    results = build_session_files("P02", tmp_path, block_duration_sec=60)
    assert len(results) == 3
    for block_num, level, path in results:
        assert path.exists()
        assert path.stat().st_size > 0


def test_build_session_files_naming(tmp_path):
    results = build_session_files("P02", tmp_path, block_duration_sec=60)
    for block_num, level, path in results:
        assert f"P02_block{block_num}_{level.value.upper()}" in path.name


def test_build_session_files_order_matches_latin_square(tmp_path):
    expected_order = block_order_for_participant("P02")
    results = build_session_files("P02", tmp_path, block_duration_sec=60)
    actual_order = tuple(level for _, level, _ in results)
    assert actual_order == expected_order


def test_build_session_files_reproducible(tmp_path):
    r1 = build_session_files("P00", tmp_path / "a", block_duration_sec=60)
    r2 = build_session_files("P00", tmp_path / "b", block_duration_sec=60)
    for (_, _, p1), (_, _, p2) in zip(r1, r2):
        assert p1.read_text() == p2.read_text()


# ── Bedford questionnaire ─────────────────────────────────────────────────────

def test_bedford_questionnaire_file_exists():
    assert BEDFORD_TXT.exists(), f"Missing: {BEDFORD_TXT}"


def test_bedford_questionnaire_format():
    line = BEDFORD_TXT.read_text().strip()
    parts = line.split(";")
    assert len(parts) == 4, "Expected title;label;min/max;min/max/default"
    title, _label, limit_labels, values = parts
    assert title == "Bedford"
    assert "/" in limit_labels
    val_parts = values.split("/")
    assert len(val_parts) == 3
    v_min, v_max, v_default = int(val_parts[0]), int(val_parts[1]), int(val_parts[2])
    assert v_min == 1
    assert v_max == 10
    assert 1 <= v_default <= 10


# ── Bedford metric parsing ────────────────────────────────────────────────────

def _csv_rows(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(textwrap.dedent(text).strip()))
    return [{k.strip(): v.strip() for k, v in row.items()} for row in reader]


def test_bedford_metric_parsed():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,900.0,performance,genericscales,Bedford,7.0
    """)
    m = _bedford_metric(rows)
    assert m["value"] == 7       # rounded integer
    assert m["value_raw"] == pytest.approx(7.0)


def test_bedford_metric_rounds_correctly():
    rows = _csv_rows("""
        logtime,scenario_time,type,module,address,value
        1.0,900.0,performance,genericscales,Bedford,5.45
    """)
    m = _bedford_metric(rows)
    assert m["value"] == 5  # round(5.45) == 5


def test_bedford_metric_absent():
    m = _bedford_metric([])
    assert m["value"] is None


def test_bedford_in_convert_session_output(tmp_path):
    """Bedford key must be present in convert_session output."""
    # Build a minimal CSV with a Bedford performance row
    csv_content = (
        "logtime,scenario_time,type,module,address,value\n"
        "1.0,0.0,version,,,1.4.5\n"
        "2.0,900.0,performance,genericscales,Bedford,6.0\n"
    )
    csv_path = tmp_path / "test_session.csv"
    csv_path.write_text(csv_content)
    result = convert_session(csv_path)
    assert "bedford" in result
    assert result["bedford"]["value"] == 6


# ── analysis.descriptive ──────────────────────────────────────────────────────

def _make_records(n_participants: int = 6) -> list[dict]:
    """Synthetic records: monotonic isa.mean (1<2<3) across LOW/MEDIUM/HIGH."""
    records = []
    for i in range(n_participants):
        for level, isa_val in [("LOW", 2.0 + i * 0.1), ("MEDIUM", 3.0 + i * 0.1), ("HIGH", 4.0 + i * 0.1)]:
            records.append({
                "participant_id": f"P{i:02d}",
                "workload_level": level,
                "isa": {"mean": isa_val, "sd": 0.5},
                "sysmon": {"hit_rate": None, "d_prime": None, "mean_rt_ms": None},
                "nasatlx": {"raw_tlx": None},
                "bedford": {"value": None},
                "comm": {"d_prime": None, "hit_rate": None},
            })
    return records


def test_get_nested_path():
    record = {"isa": {"mean": 3.2}}
    assert _get(record, "isa.mean") == pytest.approx(3.2)


def test_get_missing_returns_none():
    assert _get({}, "isa.mean") is None
    assert _get({"isa": {}}, "isa.mean") is None


def test_pivot_three_levels():
    records = _make_records(4)
    pivot = _pivot(records, "isa.mean")
    assert len(pivot) == 4
    for pid, levels in pivot.items():
        assert set(levels.keys()) == {"LOW", "MEDIUM", "HIGH"}


def test_pivot_excludes_incomplete_participants():
    records = _make_records(3)
    # Remove HIGH for participant P00
    records = [r for r in records if not (r["participant_id"] == "P00" and r["workload_level"] == "HIGH")]
    pivot = _pivot(records, "isa.mean")
    assert "P00" not in pivot
    assert len(pivot) == 2


def test_analyse_metric_monotonic_data():
    records = _make_records(6)
    res = analyse_metric(records, "isa.mean", "ISA mean")
    assert res is not None
    assert res["n_participants"] == 6
    d = res["descriptives"]
    assert d["LOW"]["mean"] < d["MEDIUM"]["mean"] < d["HIGH"]["mean"]


def test_analyse_metric_friedman_significant():
    """With perfectly monotonic data, Friedman should be significant."""
    pytest.importorskip("scipy")
    records = _make_records(8)
    res = analyse_metric(records, "isa.mean", "ISA mean")
    fr = res["friedman"]
    assert fr is not None
    assert fr["p_value"] < 0.05


def test_analyse_metric_spearman_all_positive():
    pytest.importorskip("scipy")
    records = _make_records(6)
    res = analyse_metric(records, "isa.mean", "ISA mean")
    sp = res["spearman_rho"]
    assert sp is not None
    assert sp["n_positive"] == sp["n_total"]
    assert sp["mean_rho"] == pytest.approx(1.0)


def test_load_records_from_jsonl(tmp_path):
    data = [
        {"participant_id": "P00", "workload_level": "LOW",    "isa": {"mean": 2.0}},
        {"participant_id": "P00", "workload_level": "MEDIUM", "isa": {"mean": 3.0}},
        {"participant_id": "P00", "workload_level": "HIGH",   "isa": {"mean": 4.0}},
    ]
    jsonl = tmp_path / "session.jsonl"
    jsonl.write_text("\n".join(json.dumps(r) for r in data))
    loaded = load_records(tmp_path)
    assert len(loaded) == 3


def test_analyse_metric_no_data_returns_none():
    res = analyse_metric([], "isa.mean", "ISA mean")
    assert res is None
