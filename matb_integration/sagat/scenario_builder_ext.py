"""SAGAT freeze scheduling and per-freeze probe-file emission.

Pyglet-free. Called by matb_integration.scenario_builder when
include_sagat=True. Produces:
  - one .txt file per freeze in output_dir, named
    {participant_id}_block{N}_freeze{M}.txt
  - one .json manifest per block, named
    {participant_id}_block{N}_sagat_manifest.json
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from matb_integration.sagat.probe_bank import (
    Probe,
    ProbeBankError,
    load_probes,
    write_freeze_file,
)

MAX_SAMPLER_RETRIES: Final[int] = 200
BLOCK_EDGE_BUFFER_SEC: Final[float] = 60.0


class FreezeSchedulingError(RuntimeError):
    """Raised when no valid freeze schedule can be found within retry budget."""


@dataclass(frozen=True)
class FreezeEvent:
    scenario_time_sec: float
    freeze_id: str
    probe_file_path: Path


def emit_freezes_for_block(
    *,
    participant_id: str,
    block_num: int,
    block_duration_sec: int,
    isa_probe_times_sec: list[float],
    bank_path: Path,
    output_dir: Path,
    n_freezes: int = 3,
    probes_per_freeze: int = 3,
    min_post_isa_stagger_sec: float = 30.0,
    min_inter_freeze_sec: float = 120.0,
    seed: int,
) -> list[FreezeEvent]:
    """Schedule freezes, sample probes, write per-freeze files + manifest.

    Raises FreezeSchedulingError if no valid schedule found after MAX_SAMPLER_RETRIES.
    Raises ProbeBankError (re-raised from load_probes) if bank_path invalid.
    """
    if probes_per_freeze != 3:
        raise ValueError("probes_per_freeze must be 3 (1 per SA level)")

    output_dir.mkdir(parents=True, exist_ok=True)
    bank = load_probes(bank_path)

    rng = random.Random(seed)
    freeze_times = _schedule_freezes(
        block_duration_sec=block_duration_sec,
        isa_probe_times_sec=isa_probe_times_sec,
        n_freezes=n_freezes,
        min_post_isa_stagger_sec=min_post_isa_stagger_sec,
        min_inter_freeze_sec=min_inter_freeze_sec,
        rng=rng,
    )

    probes_by_level = _group_by_level(bank)
    selected_per_freeze = _sample_probes_per_block(
        probes_by_level=probes_by_level,
        n_freezes=n_freezes,
        rng=rng,
    )

    events: list[FreezeEvent] = []
    manifest_freezes: list[dict] = []
    for m, (ts, probes) in enumerate(zip(freeze_times, selected_per_freeze), start=1):
        freeze_id = f"{participant_id}_b{block_num}_f{m}"
        probe_file_name = f"{participant_id}_block{block_num}_freeze{m}.txt"
        # Match the bank file's language suffix so write_freeze_file infers the
        # correct uncertainty anchor when round-tripped.
        if bank_path.name.endswith("_es.txt"):
            probe_file_name = probe_file_name.replace(".txt", "_es.txt")
        else:
            probe_file_name = probe_file_name.replace(".txt", "_en.txt")
        probe_file_path = output_dir / probe_file_name

        header = {
            "participant": participant_id,
            "block": block_num,
            "freeze": m,
            "scenario_time": ts,
            "seed": seed,
        }
        write_freeze_file(probe_file_path, probes, header=header)

        events.append(FreezeEvent(
            scenario_time_sec=ts,
            freeze_id=freeze_id,
            probe_file_path=probe_file_path,
        ))
        manifest_freezes.append({
            "freeze_id": freeze_id,
            "scenario_time_sec": ts,
            "probe_file": probe_file_name,
            "probe_ids": [p.probe_id for p in probes],
        })

    manifest = {
        "participant_id": participant_id,
        "block_num": block_num,
        "seed": seed,
        "bank": bank_path.name,
        "freezes": manifest_freezes,
    }
    manifest_path = output_dir / f"{participant_id}_block{block_num}_sagat_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return events


def _schedule_freezes(
    *,
    block_duration_sec: int,
    isa_probe_times_sec: list[float],
    n_freezes: int,
    min_post_isa_stagger_sec: float,
    min_inter_freeze_sec: float,
    rng: random.Random,
) -> list[float]:
    lo = BLOCK_EDGE_BUFFER_SEC
    hi = block_duration_sec - BLOCK_EDGE_BUFFER_SEC
    if hi <= lo:
        raise FreezeSchedulingError(
            f"Block too short ({block_duration_sec}s) for edge buffers"
        )

    for _ in range(MAX_SAMPLER_RETRIES):
        candidate = sorted(rng.uniform(lo, hi) for _ in range(n_freezes))
        if _all_staggered(
            candidate,
            isa_probe_times_sec,
            min_post_isa_stagger_sec,
            min_inter_freeze_sec,
        ):
            return candidate

    raise FreezeSchedulingError(
        f"No valid schedule after {MAX_SAMPLER_RETRIES} retries — "
        f"likely cause: n_freezes={n_freezes} with given ISA timing "
        f"leaves no stagger room. Reduce n_freezes, shorten "
        f"min_inter_freeze_sec, or lengthen the block."
    )


def _all_staggered(
    candidate: list[float],
    isa_times: list[float],
    min_post_isa_stagger_sec: float,
    min_inter_freeze_sec: float,
) -> bool:
    # Inter-freeze stagger (symmetric)
    for i in range(1, len(candidate)):
        if candidate[i] - candidate[i - 1] < min_inter_freeze_sec:
            return False
    # Post-ISA stagger (asymmetric — freeze must be ≥ stagger AFTER any ISA)
    for t in candidate:
        for isa_t in isa_times:
            if isa_t <= t < isa_t + min_post_isa_stagger_sec:
                return False
    return True


def _group_by_level(bank: list[Probe]) -> dict[int, list[Probe]]:
    by_level: dict[int, list[Probe]] = {1: [], 2: [], 3: []}
    for p in bank:
        by_level[p.sa_level].append(p)
    return by_level


def _sample_probes_per_block(
    *,
    probes_by_level: dict[int, list[Probe]],
    n_freezes: int,
    rng: random.Random,
) -> list[list[Probe]]:
    """Stratified random permutation: each freeze gets 1 probe per SA level,
    no probe repeats within the block. Requires len(probes_by_level[lvl]) >= n_freezes
    for every level (3, with the shipped bank of 3 probes per level and 3 freezes).
    """
    permuted: dict[int, list[Probe]] = {}
    for lvl, probes in probes_by_level.items():
        if len(probes) < n_freezes:
            raise FreezeSchedulingError(
                f"Bank has only {len(probes)} L{lvl} probes; need {n_freezes}"
            )
        copy = list(probes)
        rng.shuffle(copy)
        permuted[lvl] = copy[:n_freezes]

    per_freeze: list[list[Probe]] = []
    for m in range(n_freezes):
        per_freeze.append([permuted[1][m], permuted[2][m], permuted[3][m]])
    return per_freeze
