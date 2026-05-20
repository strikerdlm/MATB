"""Unit tests for matb_integration.sagat.scenario_builder_ext.

Pure-Python tests, no pyglet, no OpenMATB runtime.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from matb_integration.sagat.scenario_builder_ext import (
    FreezeEvent,
    FreezeSchedulingError,
    emit_freezes_for_block,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EN_BANK = REPO_ROOT / "openmatb" / "includes" / "questionnaires" / "sagat_generic_en.txt"


def test_scheduling_is_deterministic_from_seed(tmp_path: Path) -> None:
    out1 = tmp_path / "p1"
    out2 = tmp_path / "p2"
    kwargs = dict(
        participant_id="P03",
        block_num=1,
        block_duration_sec=900,
        # Realistic LOW workload: ISA every 90 s
        isa_probe_times_sec=[90.0 * i for i in range(1, 10)],
        bank_path=EN_BANK,
        n_freezes=3,
        probes_per_freeze=3,
        min_post_isa_stagger_sec=30.0,
        min_inter_freeze_sec=120.0,
        seed=42,
    )
    events1 = emit_freezes_for_block(output_dir=out1, **kwargs)
    events2 = emit_freezes_for_block(output_dir=out2, **kwargs)

    assert [e.scenario_time_sec for e in events1] == [e.scenario_time_sec for e in events2]
    assert [e.freeze_id for e in events1] == [e.freeze_id for e in events2]
