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


def test_empty_bank_raises(tmp_path: Path) -> None:
    """A file containing only comments or whitespace is malformed (zero probes)."""
    path = tmp_path / "empty_en.txt"
    path.write_text("# only a comment\n\n# another\n", encoding="utf-8")
    with pytest.raises(ProbeBankError, match="empty"):
        load_probes(path)


def test_completely_blank_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "blank_en.txt"
    path.write_text("\n\n", encoding="utf-8")
    with pytest.raises(ProbeBankError, match="empty"):
        load_probes(path)


def test_validate_bank_rejects_caller_assembled_duplicates() -> None:
    """validate_bank guards against duplicate IDs in caller-assembled lists.

    load_probes already catches duplicates during parsing, but validate_bank is
    exposed publicly for code paths that construct Probe objects directly
    (e.g., scenario_builder_ext.py merging probes from multiple sources).
    """
    from matb_integration.sagat.probe_bank import Probe, validate_bank

    a = Probe(probe_id="x", sa_level=1, domain="perception", question="Q?",
              options=("a", "b", "Unknown"), correct="a", timeout_sec=15)
    b = Probe(probe_id="x", sa_level=2, domain="comprehension", question="Q2?",
              options=("a", "b", "Unknown"), correct="b", timeout_sec=15)
    with pytest.raises(ProbeBankError, match="Duplicate"):
        validate_bank([a, b])


def test_validate_bank_accepts_unique_ids() -> None:
    from matb_integration.sagat.probe_bank import Probe, validate_bank

    a = Probe(probe_id="x", sa_level=1, domain="perception", question="Q?",
              options=("a", "b", "Unknown"), correct="a", timeout_sec=15)
    b = Probe(probe_id="y", sa_level=2, domain="comprehension", question="Q2?",
              options=("a", "b", "Unknown"), correct="b", timeout_sec=15)
    validate_bank([a, b])  # no exception


from matb_integration.sagat.probe_bank import write_freeze_file


def test_write_then_load_round_trip(tmp_path: Path) -> None:
    src = """\
PROBE_ID: gen_l1_a
SA_LEVEL: 1
DOMAIN: perception
QUESTION: Q1?
OPTIONS: yes | no
CORRECT: yes
TIMEOUT_SEC: 15

PROBE_ID: gen_l2_b
SA_LEVEL: 2
DOMAIN: comprehension
QUESTION: Q2?
OPTIONS: a | b | c
CORRECT: c
TIMEOUT_SEC: 20
"""
    src_path = tmp_path / "src_en.txt"
    src_path.write_text(src, encoding="utf-8")
    probes_in = load_probes(src_path)

    out_path = tmp_path / "out_en.txt"
    write_freeze_file(out_path, probes_in, header={"freeze_id": "P03_b1_f1"})

    probes_out = load_probes(out_path)
    assert probes_in == probes_out


def test_write_preserves_es_anchor_inference(tmp_path: Path) -> None:
    src = """\
PROBE_ID: x
SA_LEVEL: 1
DOMAIN: perception
QUESTION: ¿Q?
OPTIONS: sí | no
CORRECT: sí
TIMEOUT_SEC: 15
"""
    src_path = tmp_path / "src_es.txt"
    src_path.write_text(src, encoding="utf-8")
    probes_in = load_probes(src_path)

    out_path = tmp_path / "out_es.txt"
    write_freeze_file(out_path, probes_in, header={})
    probes_out = load_probes(out_path)
    assert "No sé" in probes_out[0].options
    assert probes_in == probes_out


def test_generic_en_bank_loads_and_is_balanced() -> None:
    """The shipped EN bank parses and has 3 probes at each SA level."""
    repo_root = Path(__file__).resolve().parents[1]
    bank = repo_root / "matb_integration" / "questionnaires" / "sagat_generic_en.txt"
    probes = load_probes(bank)
    assert len(probes) == 9
    levels = [p.sa_level for p in probes]
    assert levels.count(1) == 3
    assert levels.count(2) == 3
    assert levels.count(3) == 3
    # IDs are namespaced
    for p in probes:
        assert p.probe_id.startswith("gen_l")


def test_generic_es_bank_loads_with_no_se_anchor() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    bank = repo_root / "matb_integration" / "questionnaires" / "sagat_generic_es.txt"
    probes = load_probes(bank)
    assert len(probes) == 9
    # ES anchor present, EN anchor absent
    for p in probes:
        assert "No sé" in p.options
        assert "Unknown" not in p.options


def test_en_and_es_banks_share_probe_ids() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    questionnaire_dir = repo_root / "matb_integration" / "questionnaires"
    en = load_probes(questionnaire_dir / "sagat_generic_en.txt")
    es = load_probes(questionnaire_dir / "sagat_generic_es.txt")
    assert {p.probe_id for p in en} == {p.probe_id for p in es}
