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


def test_adjacent_participants_get_distinct_schedules(tmp_path: Path) -> None:
    common = dict(
        block_num=1,
        block_duration_sec=900,
        isa_probe_times_sec=[90.0 * i for i in range(1, 10)],
        bank_path=EN_BANK,
        n_freezes=3,
        probes_per_freeze=3,
        min_post_isa_stagger_sec=30.0,
        min_inter_freeze_sec=120.0,
    )
    e_p3 = emit_freezes_for_block(
        participant_id="P03", output_dir=tmp_path / "p3", seed=42 + 3, **common
    )
    e_p4 = emit_freezes_for_block(
        participant_id="P04", output_dir=tmp_path / "p4", seed=42 + 4, **common
    )
    assert [e.scenario_time_sec for e in e_p3] != [e.scenario_time_sec for e in e_p4]


def test_post_isa_stagger_respected(tmp_path: Path) -> None:
    """Freeze must NOT fall in [isa_t, isa_t + min_post_isa_stagger_sec)."""
    isa_times = [90.0 * i for i in range(1, 10)]
    events = emit_freezes_for_block(
        participant_id="P03",
        block_num=1,
        block_duration_sec=900,
        isa_probe_times_sec=isa_times,
        bank_path=EN_BANK,
        output_dir=tmp_path,
        n_freezes=3,
        probes_per_freeze=3,
        min_post_isa_stagger_sec=30.0,
        min_inter_freeze_sec=120.0,
        seed=42,
    )
    for e in events:
        for isa_t in isa_times:
            assert not (isa_t <= e.scenario_time_sec < isa_t + 30.0), (
                f"Freeze at {e.scenario_time_sec} falls in post-ISA exclusion "
                f"[{isa_t}, {isa_t + 30.0}) around ISA at {isa_t}"
            )


def test_pre_isa_proximity_is_allowed(tmp_path: Path) -> None:
    """Asymmetric stagger: freezes can occur right BEFORE an ISA. This is by design.

    With ISA every 90 s and min_inter_freeze_sec=120, the only feasible freeze
    positions are tucked into the [isa+30, next_isa) gaps. Verify that at least
    one freeze lands close to the next ISA (within the 30 s pre-ISA window).
    """
    isa_times = [90.0 * i for i in range(1, 10)]
    events = emit_freezes_for_block(
        participant_id="P03",
        block_num=1,
        block_duration_sec=900,
        isa_probe_times_sec=isa_times,
        bank_path=EN_BANK,
        output_dir=tmp_path,
        n_freezes=3,
        probes_per_freeze=3,
        min_post_isa_stagger_sec=30.0,
        min_inter_freeze_sec=120.0,
        seed=42,
    )
    # Verify at least one freeze is within 30s BEFORE an ISA (proves asymmetry).
    found_pre = False
    for e in events:
        for isa_t in isa_times:
            if isa_t - 30.0 < e.scenario_time_sec < isa_t:
                found_pre = True
                break
        if found_pre:
            break
    assert found_pre, (
        f"Expected at least one freeze in [isa-30, isa) window proving asymmetric "
        f"stagger; got freezes {[e.scenario_time_sec for e in events]}"
    )


def test_inter_freeze_stagger_respected(tmp_path: Path) -> None:
    events = emit_freezes_for_block(
        participant_id="P03",
        block_num=1,
        block_duration_sec=900,
        isa_probe_times_sec=[],
        bank_path=EN_BANK,
        output_dir=tmp_path,
        n_freezes=3,
        probes_per_freeze=3,
        min_post_isa_stagger_sec=30.0,
        min_inter_freeze_sec=120.0,
        seed=42,
    )
    times = sorted(e.scenario_time_sec for e in events)
    for i in range(1, len(times)):
        assert times[i] - times[i - 1] >= 120.0


def test_stratification_one_per_level_per_freeze(tmp_path: Path) -> None:
    from matb_integration.sagat.probe_bank import load_probes
    events = emit_freezes_for_block(
        participant_id="P03",
        block_num=1,
        block_duration_sec=900,
        isa_probe_times_sec=[],
        bank_path=EN_BANK,
        output_dir=tmp_path,
        n_freezes=3,
        probes_per_freeze=3,
        min_post_isa_stagger_sec=30.0,
        min_inter_freeze_sec=120.0,
        seed=42,
    )
    for e in events:
        probes = load_probes(e.probe_file_path)
        levels = sorted(p.sa_level for p in probes)
        assert levels == [1, 2, 3]


def test_no_probe_repeats_within_block(tmp_path: Path) -> None:
    from matb_integration.sagat.probe_bank import load_probes
    events = emit_freezes_for_block(
        participant_id="P03",
        block_num=1,
        block_duration_sec=900,
        isa_probe_times_sec=[],
        bank_path=EN_BANK,
        output_dir=tmp_path,
        n_freezes=3,
        probes_per_freeze=3,
        min_post_isa_stagger_sec=30.0,
        min_inter_freeze_sec=120.0,
        seed=42,
    )
    all_ids: list[str] = []
    for e in events:
        all_ids.extend(p.probe_id for p in load_probes(e.probe_file_path))
    assert len(all_ids) == len(set(all_ids)), f"Duplicate probe IDs: {all_ids}"


def test_overflow_block_budget_raises(tmp_path: Path) -> None:
    """8 freezes × 120s inter-stagger requires > 960s clear time; 600s block can't fit."""
    with pytest.raises(FreezeSchedulingError, match="No valid schedule"):
        emit_freezes_for_block(
            participant_id="P03",
            block_num=1,
            block_duration_sec=600,
            isa_probe_times_sec=[60.0 * i for i in range(1, 10)],
            bank_path=EN_BANK,
            output_dir=tmp_path,
            n_freezes=8,
            probes_per_freeze=3,
            min_post_isa_stagger_sec=30.0,
            min_inter_freeze_sec=120.0,
            seed=42,
        )


def test_block_edge_buffer_respected(tmp_path: Path) -> None:
    events = emit_freezes_for_block(
        participant_id="P03",
        block_num=1,
        block_duration_sec=900,
        isa_probe_times_sec=[],
        bank_path=EN_BANK,
        output_dir=tmp_path,
        n_freezes=3,
        probes_per_freeze=3,
        min_post_isa_stagger_sec=30.0,
        min_inter_freeze_sec=120.0,
        seed=42,
    )
    for e in events:
        assert e.scenario_time_sec >= 60.0
        assert e.scenario_time_sec <= 900.0 - 60.0


def test_manifest_round_trip(tmp_path: Path) -> None:
    emit_freezes_for_block(
        participant_id="P03",
        block_num=1,
        block_duration_sec=900,
        isa_probe_times_sec=[],
        bank_path=EN_BANK,
        output_dir=tmp_path,
        n_freezes=3,
        probes_per_freeze=3,
        min_post_isa_stagger_sec=30.0,
        min_inter_freeze_sec=120.0,
        seed=42,
    )
    manifest_path = tmp_path / "P03_block1_sagat_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["participant_id"] == "P03"
    assert manifest["block_num"] == 1
    assert manifest["seed"] == 42
    assert manifest["bank"] == "sagat_generic_en.txt"
    assert len(manifest["freezes"]) == 3
    for f in manifest["freezes"]:
        assert "freeze_id" in f
        assert "scenario_time_sec" in f
        assert "probe_file" in f
        assert len(f["probe_ids"]) == 3


def test_es_bank_emits_es_freeze_files(tmp_path: Path) -> None:
    from matb_integration.sagat.probe_bank import load_probes
    es_bank = REPO_ROOT / "openmatb" / "includes" / "questionnaires" / "sagat_generic_es.txt"
    events = emit_freezes_for_block(
        participant_id="P03",
        block_num=1,
        block_duration_sec=900,
        isa_probe_times_sec=[],
        bank_path=es_bank,
        output_dir=tmp_path,
        n_freezes=3,
        probes_per_freeze=3,
        min_post_isa_stagger_sec=30.0,
        min_inter_freeze_sec=120.0,
        seed=42,
    )
    for e in events:
        assert e.probe_file_path.name.endswith("_es.txt")
        probes = load_probes(e.probe_file_path)
        for p in probes:
            assert "No sé" in p.options


def test_same_seed_byte_identical_output(tmp_path: Path) -> None:
    kwargs = dict(
        participant_id="P03",
        block_num=1,
        block_duration_sec=900,
        isa_probe_times_sec=[],
        bank_path=EN_BANK,
        n_freezes=3,
        probes_per_freeze=3,
        min_post_isa_stagger_sec=30.0,
        min_inter_freeze_sec=120.0,
        seed=42,
    )
    out1 = tmp_path / "a"
    out2 = tmp_path / "b"
    emit_freezes_for_block(output_dir=out1, **kwargs)
    emit_freezes_for_block(output_dir=out2, **kwargs)

    a_files = sorted(p.name for p in out1.iterdir())
    b_files = sorted(p.name for p in out2.iterdir())
    assert a_files == b_files
    for fname in a_files:
        assert (out1 / fname).read_bytes() == (out2 / fname).read_bytes()


def test_sync_guard_probe_dataclass_fields() -> None:
    """Fails loudly if Probe gains a required field without bumping format_version."""
    from dataclasses import fields
    from matb_integration.sagat.probe_bank import (
        PROBE_BANK_FORMAT_VERSION,
        Probe,
    )
    field_names = {f.name for f in fields(Probe)}
    assert field_names == {
        "probe_id", "sa_level", "domain", "question",
        "options", "correct", "timeout_sec",
    }, f"Probe fields changed: {field_names}"
    assert PROBE_BANK_FORMAT_VERSION == "1.0"
