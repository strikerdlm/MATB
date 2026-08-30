from __future__ import annotations

import json
from pathlib import Path

from aircraft_monitor.research.protocol import WorkloadLevel
from matb_integration.scenario_builder import build_session_files
from matb_integration.scenario_manifest import (
    canonical_json,
    sha256_file,
    sha256_text,
    validate_manifest_against_session,
)


def test_canonical_json_is_deterministic() -> None:
    a = {"b": 2, "a": {"d": 4, "c": 3}}
    b = {"a": {"c": 3, "d": 4}, "b": 2}
    assert canonical_json(a) == canonical_json(b)
    assert canonical_json(a).endswith("\n")


def test_build_session_files_writes_adjacent_manifest(tmp_path: Path) -> None:
    files = build_session_files("P03", tmp_path, block_duration_sec=120, base_seed=42)
    block_num, level, scenario_path = files[0]
    manifest_path = scenario_path.with_suffix(scenario_path.suffix + ".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert block_num == 1
    assert level in WorkloadLevel
    assert manifest["manifest_version"] == 2
    assert manifest["metrics_schema_version"] == "2.0"
    assert manifest["workload_label_status"] == "engineering_preset_pending_human_calibration"
    assert manifest["participant_id"] == "P03"
    assert manifest["block_num"] == 1
    assert manifest["workload_level"] == level.name
    assert manifest["scenario"]["filename"] == scenario_path.name
    assert manifest["scenario"]["sha256"] == sha256_file(scenario_path)
    assert manifest["expected"]["task_events_total"] > 0
    assert manifest["expected"]["counterbalancing_method"] == "complete_permutation_counterbalancing_3_conditions"
    assert "concurrent_event_overlap_pairs" in manifest["expected"]


def test_manifest_hash_changes_with_scenario_text(tmp_path: Path) -> None:
    [(_, _, scenario_path)] = build_session_files(
        "P01", tmp_path, block_duration_sec=90, base_seed=7,
    )[:1]
    manifest = json.loads(
        scenario_path.with_suffix(scenario_path.suffix + ".manifest.json").read_text(encoding="utf-8")
    )
    original_hash = manifest["scenario"]["sha256"]
    changed = scenario_path.read_text(encoding="utf-8") + "# changed\n"
    assert sha256_text(changed) != original_hash


def test_manifest_validator_reports_mismatches() -> None:
    manifest = {
        "manifest_version": 1,
        "participant_id": "P03",
        "visit_ordinal": 2,
        "workload_level": "HIGH",
        "block_duration_sec": 120,
        "scenario": {"filename": "expected.txt", "sha256": "abc"},
        "questionnaires": {"include_nasatlx": True},
        "expected": {"isa_probe_times_sec": [45, 90], "sagat_freezes": 1},
    }
    record = {
        "scenario_time_max_s": 150,
        "isa": {"n_probes_completed": 0},
        "nasatlx": {"n_subscales_completed": 0},
        "sagat": {"n_freezes_executed": 0},
    }
    rows = [{"type": "scenario_path", "value": "other.txt"}]

    issues = validate_manifest_against_session(
        manifest,
        csv_rows=rows,
        converted_record=record,
        participant_id="P01",
        visit_ordinal=1,
        workload_level="LOW",
        source_csv_filename="run.csv",
    )
    codes = {i["code"] for i in issues}
    assert {
        "workload_mismatch",
        "participant_mismatch",
        "visit_mismatch",
        "scenario_file_mismatch",
        "duration_exceeds_manifest",
        "isa_probe_shortfall",
        "sagat_freeze_shortfall",
        "nasatlx_missing",
    } <= codes


def test_manifest_validator_handles_non_numeric_visit() -> None:
    manifest = {
        "manifest_version": 1,
        "visit_ordinal": "visit-one",
        "workload_level": "LOW",
        "block_duration_sec": 120,
        "scenario": {"filename": "expected.txt", "sha256": "abc"},
        "questionnaires": {},
        "expected": {},
    }

    issues = validate_manifest_against_session(
        manifest,
        csv_rows=[],
        converted_record={"scenario_time_max_s": 120},
        participant_id="P01",
        visit_ordinal=1,
        workload_level="LOW",
        source_csv_filename="run.csv",
    )

    assert any(i["code"] == "invalid_visit_ordinal" for i in issues)
