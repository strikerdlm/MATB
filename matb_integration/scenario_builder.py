"""
Generates OpenMATB-compatible scenario files (.txt) from ResearchProtocol
demand blocks. Does NOT import OpenMATB — outputs plain text.

Scenario line format: HH:MM:SS;plugin;command[;value]
Compatible with OpenMATB v1.4+.

Calibration against Pontiggia et al. (2024) combined event rates
(LOW ≈ 3/min, HIGH ≈ 23.5/min) using alerttimeout=10000 ms, block=900 s:

  Level   SYSMON   COMM   Total   /min
  LOW       32      12     44     2.9   ← matches Pontiggia LOW
  MEDIUM    80      32    112     7.5
  HIGH     130      51    181    12.1   ← Pontiggia HIGH includes RESMAN pumps

Monotonic ISA/NASA-TLX increase is the primary validity criterion;
exact event rates are secondary.

Sync guard: OPENMATB_* constants below mirror OpenMATB v1.4.5 plugin
defaults. If upstream changes them, tests/test_scenario_builder.py will
fail at the sync-guard assertions — update here to match.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aircraft_monitor.research.protocol import ResearchProtocol, WorkloadLevel

# ── OpenMATB sync-guard constants ─────────────────────────────────────────────
# Mirror openmatb/plugins/sysmon.py defaults — kept in sync by test assertions.
OPENMATB_ALERTTIMEOUT_MS: Final[int] = 10_000   # sysmon default alerttimeout
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
_COMM_PROMPT_SEC: Final[float] = 13.0   # average_auditory_prompt_duration
_COMM_OWN_RATIO: Final[float] = 0.50    # fraction that are own-callsign

# Questionnaire filenames (relative to OpenMATB includes/questionnaires/)
ISA_QUESTIONNAIRE: Final[str] = "isa_en.txt"
NASATLX_QUESTIONNAIRE: Final[str] = "nasatlx_en.txt"
BEDFORD_QUESTIONNAIRE: Final[str] = "bedford_en.txt"

# Spanish equivalents — validated translations (see docs/research/scale_validation_es.md)
ISA_QUESTIONNAIRE_ES: Final[str] = "isa_es.txt"
NASATLX_QUESTIONNAIRE_ES: Final[str] = "nasatlx_es.txt"
BEDFORD_QUESTIONNAIRE_ES: Final[str] = "bedford_es.txt"

# ── Latin-square counterbalancing ─────────────────────────────────────────────
# All 6 permutations of 3 workload levels. Participant N → row N % 6.
# Covers up to N=6 orthogonal orderings; groups of 6 are fully balanced.
LATIN_SQUARE_3: Final[tuple[tuple[WorkloadLevel, ...], ...]] = (
    (WorkloadLevel.LOW,    WorkloadLevel.MEDIUM, WorkloadLevel.HIGH),
    (WorkloadLevel.LOW,    WorkloadLevel.HIGH,   WorkloadLevel.MEDIUM),
    (WorkloadLevel.MEDIUM, WorkloadLevel.LOW,    WorkloadLevel.HIGH),
    (WorkloadLevel.MEDIUM, WorkloadLevel.HIGH,   WorkloadLevel.LOW),
    (WorkloadLevel.HIGH,   WorkloadLevel.LOW,    WorkloadLevel.MEDIUM),
    (WorkloadLevel.HIGH,   WorkloadLevel.MEDIUM, WorkloadLevel.LOW),
)


def block_order_for_participant(participant_id: str) -> tuple[WorkloadLevel, ...]:
    """Return the Latin-square block order for a participant.

    Extracts the leading integer from `participant_id` (e.g. "P03" → 3).
    Participants with the same numeric suffix get the same order — use
    unique IDs. Groups of 6 consecutive participants are fully balanced.
    """
    digits = "".join(c for c in participant_id if c.isdigit())
    n = int(digits) if digits else 0
    return LATIN_SQUARE_3[n % len(LATIN_SQUARE_3)]


# ── Time formatting ───────────────────────────────────────────────────────────

def _fmt_time(sec: float) -> str:
    """Format seconds as H:MM:SS for OpenMATB scenario files."""
    s = int(sec)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


# ── Event count calculations (mirror OpenMATB scenario_generation.py) ─────────

def _sysmon_event_count(
    level: WorkloadLevel,
    block_duration_sec: int,
    alerttimeout_sec: float = OPENMATB_ALERTTIMEOUT_MS / 1000,
) -> int:
    """Return per-indicator-type failure count (lights count == scales count).

    Replicates OpenMATB add_scenario_phase() SYSMON branch logic.
    Total SYSMON events = result × (len(LIGHTS) + len(SCALES)).
    """
    failure_duration = alerttimeout_sec + _EVENTS_REFRACTORY_SEC
    single_ratio = failure_duration / block_duration_sec
    max_n = int(1 / single_ratio)
    target_n = int(DIFFICULTY[level] / single_ratio)
    return min(max_n, target_n)


def _comm_event_count(level: WorkloadLevel, block_duration_sec: int) -> int:
    """Return total COMM (communications) event count for the block.

    Replicates OpenMATB add_scenario_phase() COMMUNICATIONS branch logic.
    """
    single_duration = _COMM_PROMPT_SEC + _EVENTS_REFRACTORY_SEC
    single_ratio = single_duration / block_duration_sec
    return int(DIFFICULTY[level] / single_ratio)


# ── Event distribution ────────────────────────────────────────────────────────

def _uniform_times(
    start_sec: float,
    end_sec: float,
    n: int,
    rng: random.Random,
) -> list[float]:
    """Return n onset times uniformly distributed over [start_sec, end_sec]."""
    if n <= 0:
        return []
    return sorted(rng.uniform(start_sec, end_sec) for _ in range(n))


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
    lines: list[str] = []

    difficulty = DIFFICULTY[level]
    track_prop = TRACK_TARGET_PROPORTION[level]
    resman_loss = RESMAN_LOSS_PER_MIN[level]
    isa_interval = ISA_PROBE_INTERVAL_SEC[level]
    end_time = _fmt_time(block_duration_sec)

    sysmon_n = _sysmon_event_count(level, block_duration_sec)
    comm_n = _comm_event_count(level, block_duration_sec)
    n_isa = block_duration_sec // isa_interval

    # sysmon_n = events_N per indicator CLASS (lights and scales each get sysmon_n events)
    # Total SYSMON = sysmon_n (lights) + sysmon_n (scales) = 2 × sysmon_n
    # Mirrors OpenMATB add_scenario_phase(): light_list = choices(light_names, events_N)
    total_task_events = sysmon_n * 2 + comm_n
    rate = total_task_events / (block_duration_sec / 60)

    # ── Header ────────────────────────────────────────────────────────────────
    lines += [
        f"# OpenMATB military aviation scenario — {level.value.upper()} workload",
        f"# Generated by matb_integration.scenario_builder (seed={seed})",
        f"# Block: {block_duration_sec}s ({block_duration_sec // 60} min) | "
        f"difficulty={difficulty} | SYSMON={sysmon_n}+{sysmon_n} COMM={comm_n} "
        f"total={total_task_events} ({rate:.1f}/min)",
        f"# ISA: every {isa_interval}s ({n_isa} probes) | "
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
    lines.append("")

    # ── ISA probe times (reserved — events distributed around probes) ─────────
    isa_times = [isa_interval * (i + 1) for i in range(n_isa) if isa_interval * (i + 1) < block_duration_sec]

    # ── SYSMON failure events ─────────────────────────────────────────────────
    lines.append(
        f"# SYSMON failures — {sysmon_n} light events + {sysmon_n} scale events = {sysmon_n * 2} total"
    )
    # sysmon_n events chosen uniformly from available indicators (with replacement)
    light_times = _uniform_times(5.0, block_duration_sec - 15.0, sysmon_n, rng)
    light_indicators = [rng.choice(list(OPENMATB_SYSMON_LIGHTS)) for _ in light_times]
    for t, ind in sorted(zip(light_times, light_indicators)):
        lines.append(f"{_fmt_time(t)};sysmon;lights-{ind}-failure;True")

    lines.append("")
    scale_times = _uniform_times(5.0, block_duration_sec - 15.0, sysmon_n, rng)
    scale_indicators = [rng.choice(list(OPENMATB_SYSMON_SCALES)) for _ in scale_times]
    for t, ind in sorted(zip(scale_times, scale_indicators)):
        lines.append(f"{_fmt_time(t)};sysmon;scales-{ind}-failure;True")

    lines.append("")

    # ── COMM events ───────────────────────────────────────────────────────────
    lines.append(f"# COMM events — {comm_n} total ({_COMM_OWN_RATIO*100:.0f}% own-callsign)")
    comm_times = _uniform_times(5.0, block_duration_sec - 20.0, comm_n, rng)
    prompts = _comm_prompts(comm_n, _COMM_OWN_RATIO, rng)
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


def build_protocol_scenarios(
    protocol: ResearchProtocol,
    output_dir: Path,
    block_duration_sec: int = 900,
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
        scenario_text = build_block_scenario(
            level=block.workload,
            block_duration_sec=block_duration_sec,
            seed=protocol.seed + i,
        )
        filename = f"{block.name}.txt"
        out_path = output_dir / filename
        out_path.write_text(scenario_text, encoding="utf-8")
        paths[block.name] = out_path
    return paths


def build_session_files(
    participant_id: str,
    output_dir: Path,
    block_duration_sec: int = 900,
    base_seed: int = 42,
    include_nasatlx: bool = True,
    include_bedford: bool = False,
) -> list[tuple[int, WorkloadLevel, Path]]:
    """Generate 3 counterbalanced scenario files for one participant.

    Block order is determined by a Latin-square keyed on the numeric suffix
    of `participant_id`. Groups of 6 consecutive participant numbers are
    fully counterbalanced.

    Args:
        participant_id: e.g. "P03" — numeric part drives Latin-square row.
        output_dir: Directory to write scenario files into.
        block_duration_sec: Duration per block in seconds (default 900).
        base_seed: RNG seed offset; each block gets `base_seed + block_index`.
        include_nasatlx: Append NASA-TLX at each block end (default True).
        include_bedford: Append Bedford scale at each block end (default False).

    Returns:
        List of (block_number, WorkloadLevel, file_path) in presentation order.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    order = block_order_for_participant(participant_id)
    results: list[tuple[int, WorkloadLevel, Path]] = []

    for block_num, level in enumerate(order, start=1):
        scenario_text = build_block_scenario(
            level=level,
            block_duration_sec=block_duration_sec,
            seed=base_seed + block_num - 1,
            include_nasatlx=include_nasatlx,
            include_bedford=include_bedford,
        )
        filename = f"{participant_id}_block{block_num}_{level.value.upper()}.txt"
        out_path = output_dir / filename
        out_path.write_text(scenario_text, encoding="utf-8")
        results.append((block_num, level, out_path))

    return results


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
    args = parser.parse_args()

    for i, level in enumerate(WorkloadLevel):
        text = build_block_scenario(
            level=level,
            block_duration_sec=args.block_duration,
            seed=args.seed + i,
        )
        out = args.output_dir / f"{level.value}_workload.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Written: {out}")
