"""
Generates OpenMATB-compatible scenario files (.txt) from ResearchProtocol
demand blocks. Does NOT import OpenMATB — outputs plain text.

Scenario line format: HH:MM:SS;plugin;command[;value]
Compatible with OpenMATB v1.4+.

Calibration against Pontiggia et al. (2024) combined event rates
(LOW ≈ 3/min, HIGH ≈ 23.5/min) using alerttimeout=10000 ms, block=900 s.
COMM density is constrained by a verified 24 s upper bound for the pinned
audio profile + 20 s response window + one-second refractory guard, so no
prompt can supersede another:

  Level   Targets   Non-targets   COMM   Total   /min
  LOW        16          16          4      36     2.4
  MEDIUM     40          40         10      90     6.0
  HIGH       65          65         16     146     9.7   ← before feasibility reductions

Monotonic ISA/NASA-TLX increase is the primary validity criterion;
exact event rates are secondary.

Sync guard: OPENMATB_* constants below mirror OpenMATB v1.4.5 plugin
defaults. If upstream changes them, tests/test_scenario_builder.py will
fail at the sync-guard assertions — update here to match.
"""

from __future__ import annotations

import random
import re
import os
import subprocess
import sys
from bisect import bisect_left
from math import ceil, floor
from pathlib import Path
from typing import Any, Final, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aircraft_monitor.research.protocol import ResearchProtocol, WorkloadLevel
from matb_integration.communications_profile import (
    COMM_AUDIO_INVENTORY_SHA256,
    COMM_AUDIO_PROFILE_ID,
    COMM_MAX_RESPONSE_DELAY_MS,
    COMM_MIN_ONSET_SEPARATION_SEC,
    COMM_PROMPT_UPPER_BOUND_SEC,
    COMM_RESPONSE_AVAILABILITY_SEC,
    COMM_VOICE_GENDER,
    COMM_VOICE_IDIOM,
    verify_communications_audio_profile,
)
from matb_integration.scenario_manifest import build_scenario_manifest, write_manifest
from matb_integration.sagat.scenario_builder_ext import emit_freezes_for_block

# ── OpenMATB sync-guard constants ─────────────────────────────────────────────
# Mirror openmatb/plugins/sysmon.py defaults — kept in sync by test assertions.
OPENMATB_ALERTTIMEOUT_MS: Final[int] = 10_000   # sysmon default alerttimeout
OPENMATB_NONTARGET_DURATION_MS: Final[int] = 2_000
OPENMATB_COMM_MAX_RESPONSE_DELAY_MS: Final[int] = COMM_MAX_RESPONSE_DELAY_MS
OPENMATB_SYSMON_LIGHTS: Final[tuple[str, ...]] = ("1", "2")
OPENMATB_SYSMON_SCALES: Final[tuple[str, ...]] = ("1", "2", "3", "4")

# ── Workload-level parameters ─────────────────────────────────────────────────
# difficulty: 0-1 fraction driving event density (replicates OpenMATB formula)
DIFFICULTY: Final[dict[WorkloadLevel, float]] = {
    WorkloadLevel.LOW: 0.20,
    WorkloadLevel.MEDIUM: 0.50,
    WorkloadLevel.HIGH: 0.80,
}

# TRACK targetproportion — larger zone = easier cursor control
TRACK_TARGET_PROPORTION: Final[dict[WorkloadLevel, float]] = {
    WorkloadLevel.LOW: 0.80,
    WorkloadLevel.MEDIUM: 0.50,
    WorkloadLevel.HIGH: 0.20,
}

# RESMAN tank A+B drain (L/min); default tank target = 2500 L
RESMAN_LOSS_PER_MIN: Final[dict[WorkloadLevel, int]] = {
    WorkloadLevel.LOW: 200,
    WorkloadLevel.MEDIUM: 600,
    WorkloadLevel.HIGH: 1_000,
}

# ISA probe interval (seconds) — probe fires, tasks auto-pause (BlockingPlugin)
ISA_PROBE_INTERVAL_SEC: Final[dict[WorkloadLevel, int]] = {
    WorkloadLevel.LOW: 90,
    WorkloadLevel.MEDIUM: 60,
    WorkloadLevel.HIGH: 45,
}

# Fixed OpenMATB timing parameters
_EVENTS_REFRACTORY_SEC: Final[float] = 1.0
_COMM_PROMPT_SEC: Final[float] = float(COMM_PROMPT_UPPER_BOUND_SEC)
_COMM_RESPONSE_AVAILABILITY_SEC: Final[int] = COMM_RESPONSE_AVAILABILITY_SEC
_COMM_MIN_ONSET_SEPARATION_SEC: Final[int] = COMM_MIN_ONSET_SEPARATION_SEC
_COMM_OWN_RATIO: Final[float] = 0.50    # fraction that are own-callsign

# Questionnaire filenames (relative to OpenMATB includes/questionnaires/)
ISA_QUESTIONNAIRE: Final[str] = "isa_en.txt"
NASATLX_QUESTIONNAIRE: Final[str] = "nasatlx_en.txt"
BEDFORD_QUESTIONNAIRE: Final[str] = "bedford_en.txt"

# Spanish equivalents — validated translations (see docs/research/scale_validation_es.md)
ISA_QUESTIONNAIRE_ES: Final[str] = "isa_es.txt"
NASATLX_QUESTIONNAIRE_ES: Final[str] = "nasatlx_es.txt"
BEDFORD_QUESTIONNAIRE_ES: Final[str] = "bedford_es.txt"

# ── Complete counterbalancing ─────────────────────────────────────────────────
# All 6 permutations of 3 workload levels. Participant N → row N % 6.
# This is complete permutation counterbalancing, not a 3-row Latin square.
COMPLETE_COUNTERBALANCE_3: Final[tuple[tuple[WorkloadLevel, ...], ...]] = (
    (WorkloadLevel.LOW,    WorkloadLevel.MEDIUM, WorkloadLevel.HIGH),
    (WorkloadLevel.LOW,    WorkloadLevel.HIGH,   WorkloadLevel.MEDIUM),
    (WorkloadLevel.MEDIUM, WorkloadLevel.LOW,    WorkloadLevel.HIGH),
    (WorkloadLevel.MEDIUM, WorkloadLevel.HIGH,   WorkloadLevel.LOW),
    (WorkloadLevel.HIGH,   WorkloadLevel.LOW,    WorkloadLevel.MEDIUM),
    (WorkloadLevel.HIGH,   WorkloadLevel.MEDIUM, WorkloadLevel.LOW),
)

# Deprecated compatibility alias. New code and manuscripts must use the
# scientifically precise COMPLETE_COUNTERBALANCE_3 name.
LATIN_SQUARE_3 = COMPLETE_COUNTERBALANCE_3


def block_order_for_participant(participant_id: str) -> tuple[WorkloadLevel, ...]:
    """Return the complete-counterbalancing order for a participant.

    Extracts the leading integer from `participant_id` (e.g. "P03" → 3).
    Participants with the same numeric suffix get the same order — use
    unique IDs. Groups of 6 consecutive participants are fully balanced.
    """
    digits = "".join(c for c in participant_id if c.isdigit())
    n = int(digits) if digits else 0
    return COMPLETE_COUNTERBALANCE_3[n % len(COMPLETE_COUNTERBALANCE_3)]


def _parse_scenario_time(value: str) -> float:
    hours, minutes, seconds = (float(part) for part in value.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def _scenario_density_details(scenario_text: str) -> dict[str, Any]:
    """Describe generated event density/overlap from the compiled scenario."""
    task_events: list[tuple[str, float, float]] = []
    probe_times: list[float] = []
    for raw_line in scenario_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split(";")
        if len(fields) < 3:
            continue
        onset = _parse_scenario_time(fields[0])
        plugin, command = fields[1], fields[2]
        if plugin == "sysmon" and command.endswith("-failure"):
            task_events.append(("sysmon", onset, onset + OPENMATB_ALERTTIMEOUT_MS / 1000))
        elif plugin == "sysmon" and command == "open_nontarget_opportunity":
            task_events.append((
                "sysmon",
                onset,
                onset + OPENMATB_NONTARGET_DURATION_MS / 1000,
            ))
        elif plugin == "communications" and command == "radioprompt":
            task_events.append((
                "communications",
                onset,
                onset + _COMM_PROMPT_SEC + OPENMATB_COMM_MAX_RESPONSE_DELAY_MS / 1000,
            ))
        elif plugin == "genericscales" and command == "start":
            probe_times.append(onset)

    overlap_pairs = 0
    for index, (_, start, end) in enumerate(task_events):
        for _, other_start, other_end in task_events[index + 1:]:
            if start < other_end and other_start < end:
                overlap_pairs += 1
    task_onsets = [start for _, start, _ in task_events]
    return {
        "overlap_definition": "pairwise overlap of task response-availability intervals",
        "concurrent_event_overlap_pairs": overlap_pairs,
        "task_events_within_5s_of_probe": sum(
            1 for onset in task_onsets if any(abs(onset - probe) <= 5 for probe in probe_times)
        ),
        "expected_active_primary_tasks": 4,
    }


# ── Time formatting ───────────────────────────────────────────────────────────

def _fmt_time(sec: float) -> str:
    """Format seconds as H:MM:SS for OpenMATB scenario files."""
    s = int(sec)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _nontarget_opportunity_times(
    *,
    target_onsets_sec: list[float],
    block_duration_sec: int,
    requested: int,
    probe_times_sec: list[float],
) -> list[int]:
    """Schedule explicit target-absent windows outside every possible target window.

    OpenMATB scenario times have whole-second resolution. Target onsets are therefore
    floored exactly as they are when written, and the alert timeout receives a
    one-second guard before a non-target window may begin.
    """
    duration_sec = OPENMATB_NONTARGET_DURATION_MS // 1000
    target_intervals = [
        (int(onset), int(onset) + OPENMATB_ALERTTIMEOUT_MS // 1000 + 1)
        for onset in target_onsets_sec
    ]
    probe_intervals = [(int(probe) - 1, int(probe) + 1) for probe in probe_times_sec]
    reserved = target_intervals + probe_intervals

    candidates: list[int] = []
    previous = -10_000
    for onset in range(5, block_duration_sec - duration_sec - 5):
        end = onset + duration_sec
        if onset < previous + duration_sec + 1:
            continue
        if any(onset < reserved_end and reserved_start < end for reserved_start, reserved_end in reserved):
            continue
        candidates.append(onset)
        previous = onset

    if not candidates:
        raise ValueError(
            "scenario cannot provide any explicit SYSMON non-target opportunity "
            "without overlapping target response windows"
        )
    target_count = min(requested, len(candidates))
    if len(candidates) == target_count:
        return candidates

    # Select across the complete block rather than taking an early-session cluster.
    return [
        candidates[int((index + 0.5) * len(candidates) / target_count)]
        for index in range(target_count)
    ]


# ── Event count calculations (mirror OpenMATB scenario_generation.py) ─────────

def _sysmon_event_count(
    level: WorkloadLevel,
    block_duration_sec: int,
    alerttimeout_sec: float = OPENMATB_ALERTTIMEOUT_MS / 1000,
    difficulty: float | None = None,
) -> int:
    """Return the task-wide target-opportunity count.

    The legacy generator applied this count independently to light and scale
    classes. The runtime, however, owns one task-wide target evidence window.
    Applying the demand ratio once preserves physically observable windows;
    an equal target-absent denominator supplies the paired SYSMON demand.
    """
    failure_duration = alerttimeout_sec + _EVENTS_REFRACTORY_SEC
    single_ratio = failure_duration / block_duration_sec
    max_n = int(1 / single_ratio)
    target_n = int((DIFFICULTY[level] if difficulty is None else difficulty) / single_ratio)
    return min(max_n, target_n)


def _comm_event_count(
    level: WorkloadLevel,
    block_duration_sec: int,
    difficulty: float | None = None,
) -> int:
    """Return total COMM (communications) event count for the block.

    Scale the requested demand by the full physical opportunity boundary.
    Unlike upstream's prompt-only estimate, this reserves the complete audio,
    response, and refractory interval so every target remains observable.
    """
    single_duration = _COMM_MIN_ONSET_SEPARATION_SEC
    single_ratio = single_duration / block_duration_sec
    return int((DIFFICULTY[level] if difficulty is None else difficulty) / single_ratio)


# ── Event distribution ────────────────────────────────────────────────────────

def _separated_whole_second_times(
    start_sec: float,
    end_sec: float,
    n: int,
    rng: random.Random,
    *,
    minimum_separation_sec: int,
    blocked_times_sec: tuple[float, ...] = (),
    response_availability_sec: int = 0,
    schedule_label: str = "COMM prompts",
    reduce_to_capacity: bool = False,
) -> list[int]:
    """Return deterministic whole-second onsets with a hard separation.

    OpenMATB text has whole-second resolution, so feasibility is checked after
    applying that exact resolution. Random slack is distributed across the
    complete feasible range without ever allowing a rendered collision.
    """
    if n <= 0:
        return []
    start = ceil(start_sec)
    end = floor(end_sec)
    blockers = tuple(int(value) for value in blocked_times_sec)
    candidates = [
        onset
        for onset in range(start, end + 1)
        if not any(
            onset <= blocker < onset + response_availability_sec
            for blocker in blockers
        )
    ]
    next_index = [
        bisect_left(candidates, onset + minimum_separation_sec)
        for onset in candidates
    ]
    capacity = [0] * (len(candidates) + 1)
    for index in range(len(candidates) - 1, -1, -1):
        capacity[index] = max(
            capacity[index + 1],
            1 + capacity[next_index[index]],
        )
    if capacity[0] < n and not reduce_to_capacity:
        raise ValueError(
            f"unable to schedule {n} {schedule_label} between {start}s and {end}s "
            f"with {minimum_separation_sec}s minimum onset separation outside modal freezes"
        )
    if reduce_to_capacity:
        # Short training blocks can contain modal ISA/SAGAT freezes that leave
        # no complete physical response window for the requested demand.  A
        # smaller, observable denominator is scientifically preferable to an
        # impossible prompt whose evidence window is silently truncated.
        n = min(n, capacity[0])
    selected: list[int] = []
    cursor = 0
    remaining = n
    while remaining:
        choices = [
            index
            for index in range(cursor, len(candidates))
            if 1 + capacity[next_index[index]] >= remaining
        ]
        chosen = rng.choice(choices)
        selected.append(candidates[chosen])
        cursor = next_index[chosen]
        remaining -= 1
    return selected


def _sysmon_failure_schedule(
    *,
    start_sec: float,
    end_sec: float,
    count: int,
    indicators: tuple[str, ...],
    rng: random.Random,
    minimum_indicator_separation_sec: int = 11,
    blocked_times_sec: tuple[float, ...] = (),
    reduce_to_capacity: bool = False,
) -> list[tuple[float, str]]:
    """Schedule failures so every event opens a distinct task-wide opportunity."""
    if not indicators:
        raise ValueError("SYSMON failure scheduling requires at least one indicator")
    times = _separated_whole_second_times(
        start_sec,
        end_sec,
        count,
        rng,
        minimum_separation_sec=minimum_indicator_separation_sec,
        blocked_times_sec=blocked_times_sec,
        response_availability_sec=minimum_indicator_separation_sec,
        schedule_label="SYSMON target opportunities",
        reduce_to_capacity=reduce_to_capacity,
    )
    assignments: list[str] = []
    while len(assignments) < len(times):
        batch = list(indicators)
        rng.shuffle(batch)
        assignments.extend(batch)
    return list(zip(times, assignments[:len(times)]))


def _comm_prompts(n: int, own_ratio: float, rng: random.Random) -> list[str]:
    """Return a list of n 'own'/'other' prompts at the given own-callsign ratio."""
    n_own = round(n * own_ratio)
    prompts = ["own"] * n_own + ["other"] * (n - n_own)
    rng.shuffle(prompts)
    return prompts


# ── Scenario generation ───────────────────────────────────────────────────────

def build_block_scenario(
    level: WorkloadLevel,
    block_duration_sec: int = 900,
    seed: int = 42,
    isa_questionnaire: str = ISA_QUESTIONNAIRE,
    nasatlx_questionnaire: str = NASATLX_QUESTIONNAIRE,
    bedford_questionnaire: str = BEDFORD_QUESTIONNAIRE,
    include_nasatlx: bool = True,
    include_bedford: bool = False,
    # SAGAT freeze-probe params
    include_sagat: bool = False,
    sagat_bank: Path | None = None,
    sagat_output_dir: Path | None = None,
    sagat_n_freezes: int = 3,
    participant_id: str = "P00",
    block_num: int = 1,
    workload_settings: Mapping[str, float | int] | None = None,
) -> str:
    """Generate a single-block OpenMATB scenario as a string.

    Args:
        level: Demand level (LOW / MEDIUM / HIGH).
        block_duration_sec: Block length in seconds (default 900 = 15 min).
        seed: RNG seed — same seed always produces identical output.
        isa_questionnaire: Questionnaire filename for ISA probes.
        nasatlx_questionnaire: Questionnaire filename for end-of-block TLX.
        bedford_questionnaire: Questionnaire filename for Bedford scale.
        include_nasatlx: Append NASA-TLX at block end (default True).
        include_bedford: Append Bedford scale at block end (default False).

    Returns:
        Scenario file content as a string.
    """
    rng = random.Random(seed)
    verify_communications_audio_profile()
    lines: list[str] = []

    settings = workload_settings or {}
    difficulty = float(settings.get("difficulty", DIFFICULTY[level]))
    track_prop = float(settings.get("track_target_proportion", TRACK_TARGET_PROPORTION[level]))
    resman_loss = int(settings.get("resman_loss_per_min", RESMAN_LOSS_PER_MIN[level]))
    isa_interval = int(settings.get("isa_probe_interval_sec", min(ISA_PROBE_INTERVAL_SEC[level], block_duration_sec)))
    if not 0 <= difficulty <= 1 or not 0.05 <= track_prop <= 1 or not 0 <= resman_loss <= 2_000:
        raise ValueError("workload settings are outside the supported range")
    if not 15 <= isa_interval <= block_duration_sec:
        raise ValueError("ISA interval must be between 15 seconds and the block duration")
    end_time = _fmt_time(block_duration_sec)

    sysmon_n = _sysmon_event_count(level, block_duration_sec, difficulty=difficulty)
    comm_n = _comm_event_count(level, block_duration_sec, difficulty=difficulty)
    n_isa = block_duration_sec // isa_interval
    isa_times = [
        isa_interval * (i + 1)
        for i in range(n_isa)
        if isa_interval * (i + 1) < block_duration_sec
    ]
    sagat_events = []
    if include_sagat:
        if sagat_bank is None or sagat_output_dir is None:
            raise ValueError(
                "include_sagat=True requires sagat_bank and sagat_output_dir"
            )
        sagat_events = emit_freezes_for_block(
            participant_id=participant_id,
            block_num=block_num,
            block_duration_sec=block_duration_sec,
            isa_probe_times_sec=isa_times,
            bank_path=sagat_bank,
            output_dir=sagat_output_dir,
            n_freezes=sagat_n_freezes,
            probes_per_freeze=3,
            min_post_isa_stagger_sec=30.0,
            min_inter_freeze_sec=120.0,
            seed=seed + block_num * 100 + 7,
        )
    blocker_times = tuple([
        *isa_times,
        *(event.scenario_time_sec for event in sagat_events),
    ])
    comm_times = _separated_whole_second_times(
        5.0,
        block_duration_sec - (_COMM_RESPONSE_AVAILABILITY_SEC + 1),
        comm_n,
        rng,
        minimum_separation_sec=_COMM_MIN_ONSET_SEPARATION_SEC,
        blocked_times_sec=blocker_times,
        response_availability_sec=_COMM_RESPONSE_AVAILABILITY_SEC,
        reduce_to_capacity=True,
    )
    comm_n = len(comm_times)
    prompts = _comm_prompts(comm_n, _COMM_OWN_RATIO, rng)
    indicators = tuple(
        [f"lights-{indicator}" for indicator in OPENMATB_SYSMON_LIGHTS]
        + [f"scales-{indicator}" for indicator in OPENMATB_SYSMON_SCALES]
    )
    target_schedule = _sysmon_failure_schedule(
        start_sec=5.0,
        end_sec=block_duration_sec - 15.0,
        count=sysmon_n,
        indicators=indicators,
        rng=rng,
        blocked_times_sec=blocker_times,
        reduce_to_capacity=True,
    )
    target_times = [time for time, _indicator in target_schedule]
    nontarget_times = _nontarget_opportunity_times(
        target_onsets_sec=target_times,
        block_duration_sec=block_duration_sec,
        requested=max(12, sysmon_n),
        probe_times_sec=list(blocker_times),
    )
    total_task_events = len(target_schedule) + len(nontarget_times) + comm_n
    rate = total_task_events / (block_duration_sec / 60)

    # ── Header ────────────────────────────────────────────────────────────────
    lines += [
        f"# OpenMATB military aviation scenario — {level.value.upper()} workload",
        f"# Generated by matb_integration.scenario_builder (seed={seed})",
        f"# Block: {block_duration_sec}s ({block_duration_sec // 60} min) | "
        f"difficulty={difficulty} | SYSMON={len(target_schedule)} target+"
        f"{len(nontarget_times)} non-target COMM={comm_n} "
        f"total={total_task_events} ({rate:.1f}/min)",
        f"# ISA: every {isa_interval}s ({len(isa_times)} probes) | "
        f"TRACK targetproportion={track_prop} | "
        f"RESMAN losspermin={resman_loss}",
        "",
    ]

    # ── Task start ────────────────────────────────────────────────────────────
    lines.append("# Task initialisation")
    for task in ("sysmon", "track", "resman", "communications"):
        lines.append(f"0:00:00;{task};start")
    lines.append("")

    # ── Workload parameters at t=0 ────────────────────────────────────────────
    lines.append("# Workload parameters")
    lines.append(f"0:00:00;track;targetproportion;{track_prop}")
    lines.append(f"0:00:00;resman;tank-a-lossperminute;{resman_loss}")
    lines.append(f"0:00:00;resman;tank-b-lossperminute;{resman_loss}")
    lines.append(f"0:00:00;sysmon;nontargetduration;{OPENMATB_NONTARGET_DURATION_MS}")
    lines.append(f"0:00:00;communications;voiceidiom;{COMM_VOICE_IDIOM}")
    lines.append(f"0:00:00;communications;voicegender;{COMM_VOICE_GENDER}")
    lines.append(
        f"0:00:00;communications;maxresponsedelay;{OPENMATB_COMM_MAX_RESPONSE_DELAY_MS}"
    )
    lines.append("")

    # ── SYSMON failure events ─────────────────────────────────────────────────
    lines.append(
        f"# SYSMON failures — {len(target_schedule)} task-wide serial target opportunities"
    )
    for t, indicator in target_schedule:
        lines.append(f"{_fmt_time(t)};sysmon;{indicator}-failure;True")

    lines.append("")
    lines.append(
        f"# SYSMON explicit non-target opportunities — {len(nontarget_times)} "
        f"windows × {OPENMATB_NONTARGET_DURATION_MS} ms"
    )
    for t in nontarget_times:
        lines.append(f"{_fmt_time(t)};sysmon;open_nontarget_opportunity")

    lines.append("")

    # ── COMM events ───────────────────────────────────────────────────────────
    lines.append(f"# COMM events — {comm_n} total ({_COMM_OWN_RATIO*100:.0f}% own-callsign)")
    for t, prompt in sorted(zip(comm_times, prompts)):
        lines.append(f"{_fmt_time(t)};communications;radioprompt;{prompt}")

    lines.append("")

    # ── ISA probes ────────────────────────────────────────────────────────────
    lines.append(
        f"# ISA probes — every {isa_interval}s ({len(isa_times)} probes) "
        f"[tasks auto-pause via BlockingPlugin]"
    )
    for t in isa_times:
        ts = _fmt_time(t)
        lines.append(f"{ts};genericscales;filename;{isa_questionnaire}")
        lines.append(f"{ts};genericscales;start")

    lines.append("")

    # ── SAGAT freeze triggers ─────────────────────────────────────────────────
    if sagat_events:
        lines.append(f"# SAGAT freezes — {len(sagat_events)} total")
        for ev in sagat_events:
            ts = _fmt_time(ev.scenario_time_sec)
            lines.append(f"{ts};sagat;filename;{ev.probe_file_path.name}")
            lines.append(f"{ts};sagat;start")
        lines.append("")

    # ── Block end ─────────────────────────────────────────────────────────────
    scales_at_end = [q for flag, q in [
        (include_nasatlx, nasatlx_questionnaire),
        (include_bedford, bedford_questionnaire),
    ] if flag]
    label = ", ".join(scales_at_end) if scales_at_end else "no end-of-block scales"
    lines.append(f"# Block end — stop tasks, collect {label}")
    for task in ("sysmon", "track", "resman", "communications"):
        lines.append(f"{end_time};{task};stop")

    for questionnaire in scales_at_end:
        lines.append(f"{end_time};genericscales;filename;{questionnaire}")
        lines.append(f"{end_time};genericscales;start")

    return "\n".join(lines) + "\n"


def _manifest_payload(
    *,
    scenario_filename: str,
    scenario_text: str,
    level: WorkloadLevel,
    block_duration_sec: int,
    seed: int,
    isa_questionnaire: str,
    nasatlx_questionnaire: str,
    bedford_questionnaire: str,
    include_nasatlx: bool,
    include_bedford: bool,
    participant_id: str | None = None,
    block_num: int | None = None,
    visit_ordinal: int | None = None,
    sagat_manifest_path: Path | None = None,
    sagat_n_freezes: int = 0,
    source_commit: str = "unknown",
    source_dirty: bool | None = None,
    workload_settings: Mapping[str, float | int] | None = None,
    profile_name: str | None = None,
    visual_theme: str | None = None,
) -> dict[str, Any]:
    comm_n = scenario_text.count(";communications;radioprompt;")
    settings = workload_settings or {}
    difficulty = float(settings.get("difficulty", DIFFICULTY[level]))
    track_prop = float(settings.get("track_target_proportion", TRACK_TARGET_PROPORTION[level]))
    resman_loss = int(settings.get("resman_loss_per_min", RESMAN_LOSS_PER_MIN[level]))
    isa_interval = int(settings.get("isa_probe_interval_sec", ISA_PROBE_INTERVAL_SEC[level]))
    isa_times = [
        isa_interval * (i + 1)
        for i in range(block_duration_sec // isa_interval)
        if isa_interval * (i + 1) < block_duration_sec
    ]
    density_details = _scenario_density_details(scenario_text)
    sysmon_light_events = scenario_text.count(";sysmon;lights-")
    sysmon_scale_events = scenario_text.count(";sysmon;scales-")
    sysmon_targets = sysmon_light_events + sysmon_scale_events
    sysmon_nontargets = scenario_text.count(";sysmon;open_nontarget_opportunity")
    task_events_total = sysmon_targets + sysmon_nontargets + comm_n
    return build_scenario_manifest(
        scenario_filename=scenario_filename,
        scenario_text=scenario_text,
        workload_level=level.name,
        seed=seed,
        block_duration_sec=block_duration_sec,
        participant_id=participant_id,
        block_num=block_num,
        visit_ordinal=visit_ordinal,
        sagat_manifest_path=sagat_manifest_path,
        source_commit=source_commit,
        source_dirty=source_dirty,
        parameters={
            "difficulty": difficulty,
            "suite_profile_name": profile_name or level.name,
            "track_target_proportion": track_prop,
            "resman_loss_per_min": resman_loss,
            "isa_probe_interval_sec": isa_interval,
            "openmatb_alerttimeout_ms": OPENMATB_ALERTTIMEOUT_MS,
            "openmatb_nontarget_duration_ms": OPENMATB_NONTARGET_DURATION_MS,
            "openmatb_comm_max_response_delay_ms": OPENMATB_COMM_MAX_RESPONSE_DELAY_MS,
            "communications_prompt_duration_sec": _COMM_PROMPT_SEC,
            "communications_audio_profile_id": COMM_AUDIO_PROFILE_ID,
            "communications_audio_inventory_sha256": COMM_AUDIO_INVENTORY_SHA256,
            "communications_voice_idiom": COMM_VOICE_IDIOM,
            "communications_voice_gender": COMM_VOICE_GENDER,
            "communications_response_availability_sec": _COMM_RESPONSE_AVAILABILITY_SEC,
            "communications_minimum_onset_separation_sec": _COMM_MIN_ONSET_SEPARATION_SEC,
            "communications_own_callsign_ratio": _COMM_OWN_RATIO,
            "openmatb_sysmon_lights": list(OPENMATB_SYSMON_LIGHTS),
            "openmatb_sysmon_scales": list(OPENMATB_SYSMON_SCALES),
            **({"visual_theme": visual_theme} if visual_theme is not None else {}),
        },
        questionnaires={
            "isa": isa_questionnaire,
            "nasatlx": nasatlx_questionnaire,
            "bedford": bedford_questionnaire,
            "include_nasatlx": include_nasatlx,
            "include_bedford": include_bedford,
        },
        expected={
            "sysmon_light_events": sysmon_light_events,
            "sysmon_scale_events": sysmon_scale_events,
            "sysmon_target_opportunities": sysmon_targets,
            "sysmon_nontarget_opportunities": sysmon_nontargets,
            "comm_events": comm_n,
            "task_events_total": task_events_total,
            "event_rate_per_min": round(task_events_total / (block_duration_sec / 60), 3),
            "per_subtask_event_rate_per_min": {
                "sysmon": round((sysmon_targets + sysmon_nontargets) / (block_duration_sec / 60), 3),
                "communications": round(comm_n / (block_duration_sec / 60), 3),
            },
            "counterbalancing_method": "complete_permutation_counterbalancing_3_conditions",
            "workload_label_status": "engineering_preset_pending_human_calibration",
            "isa_probe_times_sec": isa_times,
            "sagat_freezes": sagat_n_freezes,
            **density_details,
        },
    )


def _write_scenario_with_manifest(
    out_path: Path,
    scenario_text: str,
    **manifest_kwargs: Any,
) -> None:
    # Hash and persisted bytes must be identical on every platform.  Without an
    # explicit newline policy, Windows translates LF to CRLF after the manifest
    # hash has already been computed from the in-memory LF text.
    out_path.write_text(scenario_text, encoding="utf-8", newline="\n")
    manifest = _manifest_payload(
        scenario_filename=out_path.name,
        scenario_text=scenario_text,
        **manifest_kwargs,
    )
    write_manifest(out_path.with_suffix(out_path.suffix + ".manifest.json"), manifest)


def build_protocol_scenarios(
    protocol: ResearchProtocol,
    output_dir: Path,
    block_duration_sec: int = 900,
    *,
    source_commit: str = "unknown",
    source_dirty: bool | None = None,
) -> dict[str, Path]:
    """Generate one scenario file per demand block in the protocol.

    Args:
        protocol: ResearchProtocol instance (defines workload levels and seed).
        output_dir: Directory to write scenario files into.
        block_duration_sec: Duration per block in seconds.

    Returns:
        Mapping of block name → output Path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for i, block in enumerate(protocol.blocks):
        seed = protocol.seed + i
        scenario_text = build_block_scenario(
            level=block.workload,
            block_duration_sec=block_duration_sec,
            seed=seed,
        )
        filename = f"{block.name}.txt"
        out_path = output_dir / filename
        _write_scenario_with_manifest(
            out_path,
            scenario_text,
            level=block.workload,
            block_duration_sec=block_duration_sec,
            seed=seed,
            isa_questionnaire=ISA_QUESTIONNAIRE,
            nasatlx_questionnaire=NASATLX_QUESTIONNAIRE,
            bedford_questionnaire=BEDFORD_QUESTIONNAIRE,
            include_nasatlx=True,
            include_bedford=False,
            source_commit=source_commit,
            source_dirty=source_dirty,
        )
        paths[block.name] = out_path
    return paths


def build_session_files(
    participant_id: str,
    output_dir: Path,
    *,
    visit_ordinal: int,
    source_commit: str,
    source_dirty: bool,
    block_duration_sec: int = 900,
    base_seed: int = 42,
    include_nasatlx: bool = True,
    include_bedford: bool = False,
) -> list[tuple[int, WorkloadLevel, Path]]:
    """Generate 3 counterbalanced scenario files for one participant.

    Block order is determined by complete permutation counterbalancing keyed on the numeric suffix
    of `participant_id`. Groups of 6 consecutive participant numbers are
    fully counterbalanced.

    Args:
        participant_id: e.g. "P03" — numeric part drives counterbalancing row.
        visit_ordinal: Visit bound into every adjacent manifest.
        source_commit: Full lowercase Git object id for the generator source.
        source_dirty: Whether that source checkout contained uncommitted changes.
        output_dir: Directory to write scenario files into.
        block_duration_sec: Duration per block in seconds (default 900).
        base_seed: RNG seed offset; each block gets `base_seed + block_index`.
        include_nasatlx: Append NASA-TLX at each block end (default True).
        include_bedford: Append Bedford scale at each block end (default False).

    Returns:
        List of (block_number, WorkloadLevel, file_path) in presentation order.
    """
    if (
        isinstance(visit_ordinal, bool)
        or not isinstance(visit_ordinal, int)
        or visit_ordinal < 1
    ):
        raise ValueError("visit_ordinal must be an exact positive integer")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", participant_id) is None:
        raise ValueError("participant_id must be a filesystem-safe research identifier")
    output_dir.mkdir(parents=True, exist_ok=True)
    order = block_order_for_participant(participant_id)
    results: list[tuple[int, WorkloadLevel, Path]] = []

    for block_num, level in enumerate(order, start=1):
        seed = base_seed + block_num - 1
        scenario_text = build_block_scenario(
            level=level,
            block_duration_sec=block_duration_sec,
            seed=seed,
            include_nasatlx=include_nasatlx,
            include_bedford=include_bedford,
        )
        filename = f"{participant_id}_block{block_num}_{level.value.upper()}.txt"
        out_path = output_dir / filename
        _write_scenario_with_manifest(
            out_path,
            scenario_text,
            level=level,
            block_duration_sec=block_duration_sec,
            seed=seed,
            isa_questionnaire=ISA_QUESTIONNAIRE,
            nasatlx_questionnaire=NASATLX_QUESTIONNAIRE,
            bedford_questionnaire=BEDFORD_QUESTIONNAIRE,
            include_nasatlx=include_nasatlx,
            include_bedford=include_bedford,
            participant_id=participant_id,
            block_num=block_num,
            visit_ordinal=visit_ordinal,
            source_commit=source_commit,
            source_dirty=source_dirty,
        )
        results.append((block_num, level, out_path))

    return results


def detect_generator_source_provenance(repo_root: Path) -> tuple[str, bool | None]:
    """Resolve a full Git source identity, or return an explicit missing sentinel."""
    configured_commit = os.getenv("MATB_SOURCE_COMMIT")
    configured_dirty = os.getenv("MATB_SOURCE_DIRTY")
    if configured_commit is not None:
        if configured_dirty is None or configured_dirty.strip().lower() == "unknown":
            dirty: bool | None = None
        elif configured_dirty.strip().lower() == "true":
            dirty = True
        elif configured_dirty.strip().lower() == "false":
            dirty = False
        else:
            raise ValueError("MATB_SOURCE_DIRTY must be true, false, unknown, or unset")
        return configured_commit, dirty
    commit = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if commit.returncode != 0:
        return "unknown", None
    status = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=normal"],
        capture_output=True,
        text=True,
        check=False,
    )
    return commit.stdout.strip(), None if status.returncode != 0 else bool(status.stdout)


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate military aviation OpenMATB scenario files."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "scenarios" / "military_aviation",
        help="Output directory for generated scenario files.",
    )
    parser.add_argument(
        "--block-duration",
        type=int,
        default=900,
        metavar="SEC",
        help="Block duration in seconds (default: 900).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Base RNG seed (default: 42).",
    )
    parser.add_argument("--participant-id", help="Optional participant binding (requires --visit-ordinal).")
    parser.add_argument("--visit-ordinal", type=int, help="Optional visit binding (requires --participant-id).")
    args = parser.parse_args()
    if (args.participant_id is None) != (args.visit_ordinal is None):
        parser.error("--participant-id and --visit-ordinal must be supplied together")
    source_commit, source_dirty = detect_generator_source_provenance(
        Path(__file__).resolve().parents[1]
    )

    for i, level in enumerate(WorkloadLevel):
        text = build_block_scenario(
            level=level,
            block_duration_sec=args.block_duration,
            seed=args.seed + i,
        )
        out = args.output_dir / f"{level.value}_workload.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        _write_scenario_with_manifest(
            out,
            text,
            level=level,
            block_duration_sec=args.block_duration,
            seed=args.seed + i,
            isa_questionnaire=ISA_QUESTIONNAIRE,
            nasatlx_questionnaire=NASATLX_QUESTIONNAIRE,
            bedford_questionnaire=BEDFORD_QUESTIONNAIRE,
            include_nasatlx=True,
            include_bedford=False,
            participant_id=args.participant_id,
            visit_ordinal=args.visit_ordinal,
            block_num=i + 1 if args.participant_id is not None else None,
            source_commit=source_commit,
            source_dirty=source_dirty,
        )
        print(f"Written: {out}")
