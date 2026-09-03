"""
Unit + regression tests for matb_integration.scenario_builder.

Sync-guard tests (test_openmatb_sync_*) assert that local constants still
mirror OpenMATB v1.4.5 defaults. They require:
  - A running X display (DISPLAY env var) or xvfb-run
  - OpenMATB installed at /root/repos/openmatb
These tests are skipped automatically when OpenMATB is not importable.
"""

from __future__ import annotations

import json
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
    OPENMATB_COMM_MAX_RESPONSE_DELAY_MS,
    OPENMATB_SYSMON_LIGHTS,
    OPENMATB_SYSMON_SCALES,
    RESMAN_LOSS_PER_MIN,
    TRACK_TARGET_PROPORTION,
    _comm_event_count,
    _COMM_MIN_ONSET_SEPARATION_SEC,
    _COMM_RESPONSE_AVAILABILITY_SEC,
    _fmt_time,
    _scenario_density_details,
    _separated_whole_second_times,
    _sysmon_event_count,
    build_block_scenario,
)
from matb_integration.scenario_manifest import sha256_file

# ── Helpers ───────────────────────────────────────────────────────────────────

_SCENARIO_LINE_RE = re.compile(r"^\d+:\d{2}:\d{2};")
_BLOCK_DURATION_SEC = 900
_LEVELS = list(WorkloadLevel)


def _non_comment_lines(scenario: str) -> list[str]:
    return [l for l in scenario.splitlines() if l.strip() and not l.startswith("#")]


def _scenario_seconds(value: str) -> int:
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    return hours * 3600 + minutes * 60 + seconds


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


def test_density_summary_counts_explicit_nontarget_windows() -> None:
    scenario = "\n".join((
        "0:00:05;sysmon;open_nontarget_opportunity",
        "0:00:06;communications;radioprompt;own.wav",
        "0:00:08;genericscales;start",
    ))

    details = _scenario_density_details(scenario)

    assert details["concurrent_event_overlap_pairs"] == 1
    assert details["task_events_within_5s_of_probe"] == 2


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
    # Every target has a protocol-defined target-absent comparison window.
    total  = sysmon * 2 + comm
    rate   = total / (_BLOCK_DURATION_SEC / 60)
    assert 2.0 <= rate <= 4.5, f"LOW rate {rate:.2f}/min out of expected range [2.0, 4.5]"


def test_sysmon_count_positive_for_all_levels():
    for level in _LEVELS:
        assert _sysmon_event_count(level, _BLOCK_DURATION_SEC) > 0


def test_comm_count_positive_for_all_levels():
    for level in _LEVELS:
        assert _comm_event_count(level, _BLOCK_DURATION_SEC) > 0


@pytest.mark.parametrize("level", _LEVELS)
def test_communications_prompts_are_physically_serial_and_close_before_stop(level):
    """Every audible prompt keeps its full response window and refractory guard."""
    scenario = build_block_scenario(level, block_duration_sec=900, seed=42)
    onsets = sorted(
        _scenario_seconds(line.split(";", 1)[0])
        for line in _non_comment_lines(scenario)
        if ";communications;radioprompt;" in line
    )

    assert all(
        second - first >= _COMM_MIN_ONSET_SEPARATION_SEC
        for first, second in zip(onsets, onsets[1:])
    )
    assert not onsets or onsets[-1] + _COMM_RESPONSE_AVAILABILITY_SEC < 900


def test_scenario_pins_the_verified_communications_profile() -> None:
    scenario = build_block_scenario(WorkloadLevel.LOW)
    assert "communications;voiceidiom;english" in scenario
    assert "communications;voicegender;male" in scenario
    assert "communications;maxresponsedelay;20000" in scenario


def test_communications_scheduler_rejects_an_infeasible_window() -> None:
    with pytest.raises(ValueError, match="COMM prompts"):
        _separated_whole_second_times(
            5,
            38,
            2,
            __import__("random").Random(42),
            minimum_separation_sec=34,
        )


def test_short_modal_block_reduces_communications_to_observable_capacity() -> None:
    scenario = build_block_scenario(
        WorkloadLevel.HIGH,
        block_duration_sec=60,
        seed=42,
    )

    # The 45-second ISA freeze leaves no complete 44-second COMM evidence
    # window.  The generator reports zero prompts instead of truncating one.
    assert ";communications;radioprompt;" not in scenario
    assert "COMM=0 total=" in scenario


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
def test_scenario_defines_explicit_sysmon_non_target_opportunities(level):
    """Observed d-prime denominators must come from protocol windows, not idle time."""
    scenario = build_block_scenario(level)
    assert "sysmon;nontargetduration;2000" in scenario
    assert ";sysmon;open_nontarget_opportunity" in scenario


@pytest.mark.parametrize("level", _LEVELS)
def test_non_target_windows_never_overlap_possible_target_response_windows(level):
    scenario = build_block_scenario(level, block_duration_sec=900, seed=42)
    target_onsets: list[float] = []
    nontarget_onsets: list[float] = []
    for line in _non_comment_lines(scenario):
        time_text, plugin, command, *_rest = line.split(";")
        hours, minutes, seconds = (float(part) for part in time_text.split(":"))
        onset = hours * 3600 + minutes * 60 + seconds
        if plugin == "sysmon" and command.endswith("-failure"):
            target_onsets.append(onset)
        elif plugin == "sysmon" and command == "open_nontarget_opportunity":
            nontarget_onsets.append(onset)

    assert len(nontarget_onsets) >= 12
    for nontarget in nontarget_onsets:
        assert all(
            nontarget + 2 <= target or nontarget >= target + 11
            for target in target_onsets
        )


@pytest.mark.parametrize("level", _LEVELS)
def test_primary_response_windows_never_cross_modal_probe_onsets(level):
    scenario = build_block_scenario(level, block_duration_sec=900, seed=42)
    probes: list[int] = []
    targets: list[int] = []
    prompts: list[int] = []
    for line in _non_comment_lines(scenario):
        time_text, plugin, command, *_rest = line.split(";")
        onset = _scenario_seconds(time_text)
        if plugin == "genericscales" and command == "start" and onset < 900:
            probes.append(onset)
        elif plugin == "sysmon" and command.endswith("-failure"):
            targets.append(onset)
        elif plugin == "communications" and command == "radioprompt":
            prompts.append(onset)

    assert all(not (target <= probe < target + 11) for target in targets for probe in probes)
    assert all(
        not (prompt <= probe < prompt + _COMM_RESPONSE_AVAILABILITY_SEC)
        for prompt in prompts
        for probe in probes
    )


@pytest.mark.parametrize("level", _LEVELS)
def test_each_scheduled_sysmon_failure_opens_a_distinct_task_wide_target_opportunity(level):
    """The runtime owns one task-wide target window, so all gauges must be serial."""
    scenario = build_block_scenario(level, block_duration_sec=900, seed=42)
    onsets: list[int] = []
    for line in _non_comment_lines(scenario):
        time_text, plugin, command, *_rest = line.split(";")
        if plugin != "sysmon" or not command.endswith("-failure"):
            continue
        onsets.append(_scenario_seconds(time_text))

    ordered = sorted(onsets)
    assert ordered
    assert all(
        second - first >= 11 for first, second in zip(ordered, ordered[1:])
    ), f"task-wide target windows overlap: {ordered}"
    assert len(ordered) == _sysmon_event_count(level, 900)


@pytest.mark.parametrize("level", _LEVELS)
def test_short_training_scenarios_keep_an_observed_non_target_denominator(level):
    """Short training runs keep explicit evidence without inventing 15-minute density."""
    scenario = build_block_scenario(level, block_duration_sec=60, seed=42)
    opportunities = [
        line
        for line in _non_comment_lines(scenario)
        if ";sysmon;open_nontarget_opportunity" in line
    ]

    assert opportunities
    assert len(opportunities) <= 12


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


@pytest.mark.parametrize("index,level", list(enumerate(_LEVELS)))
def test_committed_reference_scenarios_are_exact_generated_v3_artifacts(index, level):
    """The installed examples must never drift behind the scientific compiler."""
    scenario_path = (
        Path(__file__).resolve().parents[1]
        / "scenarios" / "military_aviation" / f"{level.value}_workload.txt"
    )
    manifest_path = scenario_path.with_suffix(".txt.manifest.json")
    expected_text = build_block_scenario(
        level,
        block_duration_sec=_BLOCK_DURATION_SEC,
        seed=42 + index,
    )

    assert scenario_path.read_bytes() == expected_text.encode("utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert manifest["scenario"]["sha256"] == sha256_file(scenario_path)
    assert manifest["artifact_scope"] == "exploratory_template"
    assert manifest["generated_by"]["provenance_status"] == "provisional_dirty_source_tree"
    assert manifest["expected"]["sysmon_target_opportunities"] > 0
    assert manifest["expected"]["sysmon_nontarget_opportunities"] > 0
    assert manifest["expected"]["comm_events"] > 0
    isa_header = next(
        line for line in expected_text.splitlines() if line.startswith("# ISA:")
    )
    assert f"({len(manifest['expected']['isa_probe_times_sec'])} probes)" in isa_header


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


def _is_accessible_directory(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


_HAS_OPENMATB = _is_accessible_directory(_OPENMATB_PATH)

_sync_skip = pytest.mark.skipif(
    not (_HAS_DISPLAY and _HAS_OPENMATB),
    reason="Requires DISPLAY env var and /root/repos/openmatb",
)


def test_inaccessible_openmatb_sync_path_is_treated_as_unavailable(monkeypatch):
    def deny_access(_path: Path) -> bool:
        raise PermissionError("inaccessible optional checkout")

    monkeypatch.setattr(Path, "is_dir", deny_access)
    assert _is_accessible_directory(_OPENMATB_PATH) is False


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
    manifest_path = tmp_path / "P03_block1_sagat_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    freeze_times = [int(item["scenario_time_sec"]) for item in manifest["freezes"]]
    nontarget_times = [
        _scenario_seconds(line.split(";", 1)[0])
        for line in _non_comment_lines(text)
        if ";sysmon;open_nontarget_opportunity" in line
    ]
    assert all(
        not (nontarget < freeze + 1 and freeze - 1 < nontarget + 2)
        for nontarget in nontarget_times
        for freeze in freeze_times
    )
