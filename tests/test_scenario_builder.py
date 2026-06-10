"""
Unit + regression tests for matb_integration.scenario_builder.

Sync-guard tests (test_openmatb_sync_*) assert that local constants still
mirror OpenMATB v1.4.5 defaults. They require:
  - A running X display (DISPLAY env var) or xvfb-run
  - OpenMATB installed at /root/repos/openmatb
These tests are skipped automatically when OpenMATB is not importable.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aircraft_monitor.research.protocol import WorkloadLevel
from matb_integration.scenario_builder import (
    DIFFICULTY,
    ISA_PROBE_INTERVAL_SEC,
    NASATLX_QUESTIONNAIRE,
    OPENMATB_ALERTTIMEOUT_MS,
    OPENMATB_SYSMON_LIGHTS,
    OPENMATB_SYSMON_SCALES,
    RESMAN_LOSS_PER_MIN,
    TRACK_TARGET_PROPORTION,
    _comm_event_count,
    _fmt_time,
    _sysmon_event_count,
    build_block_scenario,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

_SCENARIO_LINE_RE = re.compile(r"^\d+:\d{2}:\d{2};")
_BLOCK_DURATION_SEC = 900
_LEVELS = list(WorkloadLevel)


def _non_comment_lines(scenario: str) -> list[str]:
    return [l for l in scenario.splitlines() if l.strip() and not l.startswith("#")]


# ── Time formatting ───────────────────────────────────────────────────────────

def test_fmt_time_zero():
    assert _fmt_time(0) == "0:00:00"

def test_fmt_time_90():
    assert _fmt_time(90) == "0:01:30"

def test_fmt_time_3600():
    assert _fmt_time(3600) == "1:00:00"

def test_fmt_time_900():
    assert _fmt_time(900) == "0:15:00"

def test_fmt_time_truncates_float():
    assert _fmt_time(60.9) == "0:01:00"


# ── Event count formulas ──────────────────────────────────────────────────────

def test_sysmon_monotonic():
    low  = _sysmon_event_count(WorkloadLevel.LOW,    _BLOCK_DURATION_SEC)
    med  = _sysmon_event_count(WorkloadLevel.MEDIUM, _BLOCK_DURATION_SEC)
    high = _sysmon_event_count(WorkloadLevel.HIGH,   _BLOCK_DURATION_SEC)
    assert low < med < high


def test_comm_monotonic():
    low  = _comm_event_count(WorkloadLevel.LOW,    _BLOCK_DURATION_SEC)
    med  = _comm_event_count(WorkloadLevel.MEDIUM, _BLOCK_DURATION_SEC)
    high = _comm_event_count(WorkloadLevel.HIGH,   _BLOCK_DURATION_SEC)
    assert low < med < high


def test_low_rate_matches_pontiggia():
    """LOW workload combined rate should be near Pontiggia (2024) LOW ≈ 3/min."""
    sysmon = _sysmon_event_count(WorkloadLevel.LOW, _BLOCK_DURATION_SEC)
    comm   = _comm_event_count(WorkloadLevel.LOW,   _BLOCK_DURATION_SEC)
    total  = sysmon * 2 + comm
    rate   = total / (_BLOCK_DURATION_SEC / 60)
    assert 2.0 <= rate <= 4.5, f"LOW rate {rate:.2f}/min out of expected range [2.0, 4.5]"


def test_sysmon_count_positive_for_all_levels():
    for level in _LEVELS:
        assert _sysmon_event_count(level, _BLOCK_DURATION_SEC) > 0


def test_comm_count_positive_for_all_levels():
    for level in _LEVELS:
        assert _comm_event_count(level, _BLOCK_DURATION_SEC) > 0


# ── Scenario structure ────────────────────────────────────────────────────────

@pytest.mark.parametrize("level", _LEVELS)
def test_scenario_contains_required_tasks(level):
    s = build_block_scenario(level)
    assert "sysmon;start" in s
    assert "track;start" in s
    assert "resman;start" in s
    assert "communications;start" in s


@pytest.mark.parametrize("level", _LEVELS)
def test_scenario_tasks_are_stopped(level):
    s = build_block_scenario(level)
    assert "sysmon;stop" in s
    assert "track;stop" in s
    assert "resman;stop" in s
    assert "communications;stop" in s


@pytest.mark.parametrize("level", _LEVELS)
def test_scenario_has_nasatlx(level):
    s = build_block_scenario(level)
    assert NASATLX_QUESTIONNAIRE in s
    assert "genericscales;start" in s


@pytest.mark.parametrize("level", _LEVELS)
def test_scenario_has_isa_probes(level):
    s = build_block_scenario(level)
    assert "isa_en.txt" in s


@pytest.mark.parametrize("level", _LEVELS)
def test_scenario_line_time_format(level):
    s = build_block_scenario(level)
    for line in _non_comment_lines(s):
        assert _SCENARIO_LINE_RE.match(line), f"Bad time format: {line!r}"


@pytest.mark.parametrize("level", _LEVELS)
def test_scenario_end_time_is_block_duration(level):
    s = build_block_scenario(level, block_duration_sec=600)
    stop_lines = [l for l in s.splitlines() if ";stop" in l]
    assert all(l.startswith("0:10:00;") for l in stop_lines), \
        f"Stop lines don't all start at 0:10:00: {stop_lines}"


# ── Reproducibility ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("level", _LEVELS)
def test_same_seed_reproducible(level):
    assert build_block_scenario(level, seed=42) == build_block_scenario(level, seed=42)


def test_different_seeds_differ():
    s1 = build_block_scenario(WorkloadLevel.MEDIUM, seed=1)
    s2 = build_block_scenario(WorkloadLevel.MEDIUM, seed=2)
    assert s1 != s2


# ── Parameter ordering ────────────────────────────────────────────────────────

def test_difficulty_monotonic():
    assert DIFFICULTY[WorkloadLevel.LOW] < DIFFICULTY[WorkloadLevel.MEDIUM] < DIFFICULTY[WorkloadLevel.HIGH]


def test_track_proportion_decreasing():
    assert (TRACK_TARGET_PROPORTION[WorkloadLevel.LOW]
            > TRACK_TARGET_PROPORTION[WorkloadLevel.MEDIUM]
            > TRACK_TARGET_PROPORTION[WorkloadLevel.HIGH])


def test_resman_loss_monotonic():
    assert (RESMAN_LOSS_PER_MIN[WorkloadLevel.LOW]
            < RESMAN_LOSS_PER_MIN[WorkloadLevel.MEDIUM]
            < RESMAN_LOSS_PER_MIN[WorkloadLevel.HIGH])


def test_isa_interval_decreasing():
    assert (ISA_PROBE_INTERVAL_SEC[WorkloadLevel.LOW]
            > ISA_PROBE_INTERVAL_SEC[WorkloadLevel.MEDIUM]
            > ISA_PROBE_INTERVAL_SEC[WorkloadLevel.HIGH])


# ── Sync-guard (requires OpenMATB + DISPLAY) ──────────────────────────────────

_OPENMATB_PATH = Path("/root/repos/openmatb")
_HAS_DISPLAY = bool(os.environ.get("DISPLAY"))
_HAS_OPENMATB = _OPENMATB_PATH.is_dir()

_sync_skip = pytest.mark.skipif(
    not (_HAS_DISPLAY and _HAS_OPENMATB),
    reason="Requires DISPLAY env var and /root/repos/openmatb",
)


@_sync_skip
def test_openmatb_sync_alerttimeout():
    """Fail loudly if OpenMATB changes its sysmon alerttimeout default."""
    import gettext
    import builtins
    _orig = getattr(builtins, "_", None)
    builtins._ = lambda s: s  # noqa: E731  — stub gettext before import
    try:
        sys.path.insert(0, str(_OPENMATB_PATH))
        from plugins.sysmon import Sysmon  # type: ignore[import]
        actual = Sysmon().parameters["alerttimeout"]
        assert actual == OPENMATB_ALERTTIMEOUT_MS, (
            f"OpenMATB alerttimeout changed to {actual} — update "
            "OPENMATB_ALERTTIMEOUT_MS in scenario_builder.py"
        )
    finally:
        if _orig is None:
            delattr(builtins, "_")
        else:
            builtins._ = _orig


@_sync_skip
def test_openmatb_sync_lights():
    """Fail loudly if OpenMATB changes its sysmon light keys."""
    import builtins
    _orig = getattr(builtins, "_", None)
    builtins._ = lambda s: s  # noqa: E731
    try:
        sys.path.insert(0, str(_OPENMATB_PATH))
        from plugins.sysmon import Sysmon  # type: ignore[import]
        actual = tuple(Sysmon().parameters["lights"].keys())
        assert actual == OPENMATB_SYSMON_LIGHTS, (
            f"OpenMATB sysmon lights changed to {actual} — update "
            "OPENMATB_SYSMON_LIGHTS in scenario_builder.py"
        )
    finally:
        if _orig is None:
            delattr(builtins, "_")
        else:
            builtins._ = _orig


@_sync_skip
def test_openmatb_sync_scales():
    """Fail loudly if OpenMATB changes its sysmon scale keys."""
    import builtins
    _orig = getattr(builtins, "_", None)
    builtins._ = lambda s: s  # noqa: E731
    try:
        sys.path.insert(0, str(_OPENMATB_PATH))
        from plugins.sysmon import Sysmon  # type: ignore[import]
        actual = tuple(Sysmon().parameters["scales"].keys())
        assert actual == OPENMATB_SYSMON_SCALES, (
            f"OpenMATB sysmon scales changed to {actual} — update "
            "OPENMATB_SYSMON_SCALES in scenario_builder.py"
        )
    finally:
        if _orig is None:
            delattr(builtins, "_")
        else:
            builtins._ = _orig


def test_build_block_scenario_with_sagat_emits_two_lines_per_freeze(tmp_path):
    from matb_integration.scenario_builder import build_block_scenario
    from aircraft_monitor.research.protocol import WorkloadLevel

    repo_root = Path(__file__).resolve().parents[1]
    sagat_bank = repo_root / "matb_integration" / "questionnaires" / "sagat_generic_en.txt"

    text = build_block_scenario(
        level=WorkloadLevel.LOW,
        block_duration_sec=900,
        seed=42,
        include_sagat=True,
        sagat_bank=sagat_bank,
        sagat_output_dir=tmp_path,
        sagat_n_freezes=3,
        participant_id="P03",
        block_num=1,
    )
    # Three freezes → 3 × 2 lines (filename + start)
    assert text.count("sagat;filename;") == 3
    assert text.count("sagat;start") == 3
    # Manifest emitted
    assert (tmp_path / "P03_block1_sagat_manifest.json").exists()
