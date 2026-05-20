"""Unit tests for matb_integration.sagat.probe_bank.

Tests the pyglet-free probe-bank parser. No OpenMATB runtime required.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from matb_integration.sagat.probe_bank import (
    Probe,
    ProbeBankError,
    load_probes,
)


GOOD_BANK_EN = """\
# SAGAT bank | generic | en
PROBE_ID: gen_l1_lights
SA_LEVEL: 1
DOMAIN: perception
QUESTION: Which monitoring lights were active in the past 30 seconds?
OPTIONS: green only | red only | both | neither
CORRECT: red only
TIMEOUT_SEC: 15

PROBE_ID: gen_l2_ontrack
SA_LEVEL: 2
DOMAIN: comprehension
QUESTION: Is the current mission progressing on schedule?
OPTIONS: yes | no | unclear
CORRECT: yes
TIMEOUT_SEC: 15
"""


def test_well_formed_bank_loads(tmp_path: Path) -> None:
    bank = tmp_path / "sagat_test_en.txt"
    bank.write_text(GOOD_BANK_EN, encoding="utf-8")

    probes = load_probes(bank)

    assert len(probes) == 2
    assert probes[0].probe_id == "gen_l1_lights"
    assert probes[0].sa_level == 1
    assert probes[0].domain == "perception"
    assert probes[0].correct == "red only"
    assert probes[0].timeout_sec == 15
    # EN bank auto-appends "Unknown"
    assert "Unknown" in probes[0].options
    assert probes[1].probe_id == "gen_l2_ontrack"
    assert probes[1].sa_level == 2


def test_missing_field_raises(tmp_path: Path) -> None:
    bad = """\
PROBE_ID: x
SA_LEVEL: 1
DOMAIN: perception
QUESTION: Q?
OPTIONS: a | b
CORRECT: a
"""  # no TIMEOUT_SEC
    path = tmp_path / "bad_en.txt"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(ProbeBankError, match="missing required fields"):
        load_probes(path)


def test_options_too_few_raises(tmp_path: Path) -> None:
    bad = """\
PROBE_ID: x
SA_LEVEL: 1
DOMAIN: perception
QUESTION: Q?
OPTIONS: only_one
CORRECT: only_one
TIMEOUT_SEC: 15
"""
    path = tmp_path / "bad_en.txt"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(ProbeBankError, match="2-6 entries"):
        load_probes(path)


def test_options_too_many_raises(tmp_path: Path) -> None:
    bad = """\
PROBE_ID: x
SA_LEVEL: 1
DOMAIN: perception
QUESTION: Q?
OPTIONS: a | b | c | d | e | f | g
CORRECT: a
TIMEOUT_SEC: 15
"""
    path = tmp_path / "bad_en.txt"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(ProbeBankError, match="2-6 entries"):
        load_probes(path)


def test_correct_not_in_options_raises(tmp_path: Path) -> None:
    bad = """\
PROBE_ID: x
SA_LEVEL: 1
DOMAIN: perception
QUESTION: Q?
OPTIONS: a | b | c
CORRECT: zzz
TIMEOUT_SEC: 15
"""
    path = tmp_path / "bad_en.txt"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(ProbeBankError, match="not in OPTIONS"):
        load_probes(path)


def test_sa_level_domain_mismatch_raises(tmp_path: Path) -> None:
    bad = """\
PROBE_ID: x
SA_LEVEL: 1
DOMAIN: comprehension
QUESTION: Q?
OPTIONS: a | b
CORRECT: a
TIMEOUT_SEC: 15
"""
    path = tmp_path / "bad_en.txt"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(ProbeBankError, match="inconsistent with SA_LEVEL"):
        load_probes(path)


def test_duplicate_probe_id_raises(tmp_path: Path) -> None:
    bad = """\
PROBE_ID: dup
SA_LEVEL: 1
DOMAIN: perception
QUESTION: Q1?
OPTIONS: a | b
CORRECT: a
TIMEOUT_SEC: 15

PROBE_ID: dup
SA_LEVEL: 2
DOMAIN: comprehension
QUESTION: Q2?
OPTIONS: a | b
CORRECT: b
TIMEOUT_SEC: 15
"""
    path = tmp_path / "bad_en.txt"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(ProbeBankError, match="Duplicate probe_id"):
        load_probes(path)


def test_en_bank_auto_appends_unknown(tmp_path: Path) -> None:
    src = """\
PROBE_ID: x
SA_LEVEL: 1
DOMAIN: perception
QUESTION: Q?
OPTIONS: yes | no
CORRECT: yes
TIMEOUT_SEC: 15
"""
    path = tmp_path / "x_en.txt"
    path.write_text(src, encoding="utf-8")
    probes = load_probes(path)
    assert "Unknown" in probes[0].options
    assert probes[0].options[-1] == "Unknown"


def test_es_bank_auto_appends_no_se(tmp_path: Path) -> None:
    src = """\
PROBE_ID: x
SA_LEVEL: 1
DOMAIN: perception
QUESTION: ¿Q?
OPTIONS: sí | no
CORRECT: sí
TIMEOUT_SEC: 15
"""
    path = tmp_path / "x_es.txt"
    path.write_text(src, encoding="utf-8")
    probes = load_probes(path)
    assert "No sé" in probes[0].options
    assert "Unknown" not in probes[0].options


def test_anchor_already_present_not_duplicated(tmp_path: Path) -> None:
    src = """\
PROBE_ID: x
SA_LEVEL: 1
DOMAIN: perception
QUESTION: Q?
OPTIONS: yes | no | Unknown
CORRECT: yes
TIMEOUT_SEC: 15
"""
    path = tmp_path / "x_en.txt"
    path.write_text(src, encoding="utf-8")
    probes = load_probes(path)
    assert probes[0].options.count("Unknown") == 1


def test_timeout_out_of_range_raises(tmp_path: Path) -> None:
    bad = """\
PROBE_ID: x
SA_LEVEL: 1
DOMAIN: perception
QUESTION: Q?
OPTIONS: a | b
CORRECT: a
TIMEOUT_SEC: 99
"""
    path = tmp_path / "bad_en.txt"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(ProbeBankError, match="5-60"):
        load_probes(path)


def test_file_not_found_raises(tmp_path: Path) -> None:
    """load_probes() raises ProbeBankError, not FileNotFoundError, on missing file.

    Reason: callers (Sagat plugin, scenario_builder_ext) expect a single
    ProbeBankError exception class to handle, not OSError subclasses.
    """
    missing = tmp_path / "does_not_exist_en.txt"
    with pytest.raises(ProbeBankError, match="not found"):
        load_probes(missing)
