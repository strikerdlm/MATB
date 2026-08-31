from __future__ import annotations

import json
from pathlib import Path

import pytest

from aircraft_monitor.research.protocol import WorkloadLevel
from matb_integration.scenario_builder import build_session_files
from matb_integration.scenario_manifest import (
    canonical_json,
    sha256_file,
    sha256_text,
    validate_manifest_against_session,
    write_manifest,
)


def test_canonical_json_is_deterministic() -> None:
    a = {"b": 2, "a": {"d": 4, "c": 3}}
    b = {"a": {"c": 3, "d": 4}, "b": 2}
    assert canonical_json(a) == canonical_json(b)
    assert canonical_json(a).endswith("\n")


def test_canonical_json_rejects_nonfinite_numbers() -> None:
    with pytest.raises(ValueError, match="Out of range float"):
        canonical_json({"duration": float("nan")})


def test_manifest_persistence_matches_canonical_utf8_bytes(tmp_path: Path) -> None:
    payload = {"b": "line one\nline two", "a": 1}
    path = tmp_path / "manifest.json"

    write_manifest(path, payload)

    assert path.read_bytes() == canonical_json(payload).encode("utf-8")


def test_build_session_files_writes_adjacent_manifest(tmp_path: Path) -> None:
    files = build_session_files(
        "P03", tmp_path, visit_ordinal=2, source_commit="a" * 40,
        source_dirty=False, block_duration_sec=120, base_seed=42,
    )
    block_num, level, scenario_path = files[0]
    manifest_path = scenario_path.with_suffix(scenario_path.suffix + ".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert block_num == 1
    assert level in WorkloadLevel
    assert manifest["manifest_version"] == 3
    assert manifest["metrics_schema_version"] == "2.0"
    assert manifest["workload_label_status"] == "engineering_preset_pending_human_calibration"
    assert manifest["participant_id"] == "P03"
    assert manifest["visit_ordinal"] == 2
    assert manifest["block_num"] == 1
    assert manifest["workload_level"] == level.name
    assert manifest["scenario"]["filename"] == scenario_path.name
    assert manifest["scenario"]["sha256"] == sha256_file(scenario_path)
    assert manifest["expected"]["task_events_total"] > 0
    assert manifest["expected"]["counterbalancing_method"] == "complete_permutation_counterbalancing_3_conditions"
    assert "concurrent_event_overlap_pairs" in manifest["expected"]
    assert manifest["generated_by"] == {
        "component": "matb_integration.scenario_builder",
        "version": "3.0.0",
        "source_commit": "a" * 40,
        "source_dirty": False,
        "provenance_status": "complete",
    }


def test_manifest_hash_changes_with_scenario_text(tmp_path: Path) -> None:
    [(_, _, scenario_path)] = build_session_files(
        "P01", tmp_path, visit_ordinal=1, source_commit="b" * 40,
        source_dirty=False, block_duration_sec=90, base_seed=7,
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


def _v3_manifest() -> dict[str, object]:
    return {
        "manifest_version": 3,
        "metrics_schema_version": "2.0",
        "generated_by": {
            "component": "matb_integration.scenario_builder",
            "version": "3.0.0",
            "source_commit": "a" * 40,
            "source_dirty": False,
            "provenance_status": "complete",
        },
        "artifact_scope": "session_bound",
        "workload_label_status": "engineering_preset_pending_human_calibration",
        "participant_id": "P01",
        "visit_ordinal": 1,
        "workload_level": "LOW",
        "block_duration_sec": 120,
        "scenario": {"filename": "expected.txt", "sha256": "b" * 64},
        "questionnaires": {
            "isa": "isa_en.txt",
            "nasatlx": "nasatlx_en.txt",
            "bedford": "bedford_en.txt",
            "include_nasatlx": False,
            "include_bedford": False,
        },
        "expected": {
            "sysmon_target_opportunities": 0,
            "sysmon_nontarget_opportunities": 0,
            "comm_events": 0,
            "isa_probe_times_sec": [],
            "sagat_freezes": 0,
        },
    }


def _validate_v3(manifest: dict[str, object]) -> set[str]:
    issues = validate_manifest_against_session(
        manifest,
        csv_rows=[],
        converted_record={"scenario_time_max_s": 120, "sysmon": {}},
        participant_id="P01",
        visit_ordinal=1,
        workload_level="LOW",
        source_csv_filename="run.csv",
    )
    return {item["code"] for item in issues}


def test_v3_manifest_recomputes_generator_provenance_instead_of_trusting_status() -> None:
    manifest = _v3_manifest()
    generated = dict(manifest["generated_by"])
    generated.update({"source_commit": "junk", "source_dirty": True, "provenance_status": "complete"})
    manifest["generated_by"] = generated

    assert "invalid_generator_provenance" in _validate_v3(manifest)


def test_v3_manifest_enforces_workload_taxonomy_and_scope_binding() -> None:
    manifest = _v3_manifest()
    manifest["workload_label_status"] = "human_calibrated"
    manifest["artifact_scope"] = "exploratory_template"

    codes = _validate_v3(manifest)
    assert "unsupported_workload_label_status" in codes
    assert "artifact_scope_binding_mismatch" in codes


@pytest.mark.parametrize("visit", [True, 1.0, "1", 0])
def test_v3_manifest_requires_exact_positive_integer_visit_binding(visit: object) -> None:
    manifest = _v3_manifest()
    manifest["visit_ordinal"] = visit

    assert "invalid_visit_ordinal" in _validate_v3(manifest)


@pytest.mark.parametrize(
    ("metrics_schema_version", "expected_code"),
    [
        (None, "missing_metrics_schema_version"),
        ("1.0", "unsupported_metrics_schema_version"),
        ("3.0", "unsupported_metrics_schema_version"),
        (2.0, "unsupported_metrics_schema_version"),
    ],
)
def test_manifest_validator_requires_exact_supported_metrics_schema(
    metrics_schema_version: object,
    expected_code: str,
) -> None:
    manifest = {
        "manifest_version": 2,
        "participant_id": "P01",
        "visit_ordinal": 1,
        "workload_level": "LOW",
        "block_duration_sec": 120,
        "scenario": {"filename": "expected.txt", "sha256": "a" * 64},
        "questionnaires": {},
        "expected": {
            "sysmon_target_opportunities": 0,
            "sysmon_nontarget_opportunities": 0,
        },
    }
    if metrics_schema_version is not None:
        manifest["metrics_schema_version"] = metrics_schema_version

    issues = validate_manifest_against_session(
        manifest,
        csv_rows=[
            {"type": "scenario_path", "value": "expected.txt"},
            {"type": "scenario_sha256", "value": "a" * 64},
        ],
        converted_record={
            "scenario_time_max_s": 0,
            "sysmon": {
                "n_observed_target_opportunities": 0,
                "n_observed_nontarget_opportunities": 0,
            },
        },
        participant_id="P01",
        visit_ordinal=1,
        workload_level="LOW",
        source_csv_filename="run.csv",
    )

    assert any(
        item["code"] == expected_code and item["severity"] == "error"
        for item in issues
    )


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), float("-inf"), 0, -1])
def test_manifest_validator_rejects_nonfinite_or_nonpositive_duration(duration: float) -> None:
    manifest = {
        "manifest_version": 2,
        "participant_id": "P01",
        "visit_ordinal": 1,
        "workload_level": "LOW",
        "block_duration_sec": duration,
        "scenario": {"filename": "expected.txt", "sha256": "a" * 64},
        "questionnaires": {},
        "expected": {
            "sysmon_target_opportunities": 0,
            "sysmon_nontarget_opportunities": 0,
        },
    }

    issues = validate_manifest_against_session(
        manifest,
        csv_rows=[
            {"type": "scenario_path", "value": "expected.txt"},
            {"type": "scenario_sha256", "value": "a" * 64},
        ],
        converted_record={"scenario_time_max_s": 0},
        participant_id="P01",
        visit_ordinal=1,
        workload_level="LOW",
        source_csv_filename="run.csv",
    )

    assert any(i["code"] == "invalid_block_duration" for i in issues)


def test_manifest_validator_fails_on_sysmon_opportunity_count_mismatch() -> None:
    manifest = {
        "manifest_version": 2,
        "workload_level": "LOW",
        "block_duration_sec": 120,
        "scenario": {"filename": "expected.txt", "sha256": "abc"},
        "questionnaires": {},
        "expected": {
            "sysmon_target_opportunities": 4,
            "sysmon_nontarget_opportunities": 3,
        },
    }
    record = {
        "scenario_time_max_s": 120,
        "sysmon": {
            "n_observed_target_opportunities": 3,
            "n_observed_nontarget_opportunities": 3,
            "observed_opportunity_status": "incomplete",
        },
    }

    issues = validate_manifest_against_session(
        manifest,
        csv_rows=[],
        converted_record=record,
        participant_id="P01",
        visit_ordinal=1,
        workload_level="LOW",
        source_csv_filename="run.csv",
    )

    assert any(
        item["code"] == "sysmon_target_opportunity_count_mismatch"
        and item["severity"] == "error"
        for item in issues
    )


def test_manifest_validator_fails_on_comm_opportunity_count_or_lifecycle_mismatch() -> None:
    manifest = {
        "manifest_version": 2,
        "metrics_schema_version": "2.0",
        "workload_level": "LOW",
        "block_duration_sec": 120,
        "scenario": {"filename": "expected.txt", "sha256": "a" * 64},
        "questionnaires": {},
        "expected": {
            "sysmon_target_opportunities": 0,
            "sysmon_nontarget_opportunities": 0,
            "comm_events": 3,
        },
    }
    record = {
        "scenario_time_max_s": 120,
        "sysmon": {
            "n_observed_target_opportunities": 0,
            "n_observed_nontarget_opportunities": 0,
        },
        "comm": {
            "n_opened_opportunities": 2,
            "observed_opportunity_status": "invalid",
            "observed_opportunity_reconciled": False,
        },
    }

    issues = validate_manifest_against_session(
        manifest,
        csv_rows=[],
        converted_record=record,
        participant_id="P01",
        visit_ordinal=1,
        workload_level="LOW",
        source_csv_filename="run.csv",
    )
    codes = {item["code"] for item in issues}

    assert "comm_opportunity_count_mismatch" in codes
    assert "comm_opportunity_evidence_incomplete" in codes


def test_manifest_validator_requires_exact_isa_probe_count() -> None:
    manifest = _v3_manifest()
    manifest["expected"] = {
        **manifest["expected"],
        "isa_probe_times_sec": [30],
    }
    issues = validate_manifest_against_session(
        manifest,
        csv_rows=[],
        converted_record={
            "scenario_time_max_s": 120,
            "sysmon": {
                "n_observed_target_opportunities": 0,
                "n_observed_nontarget_opportunities": 0,
            },
            "comm": {"n_opened_opportunities": 0},
            "isa": {"n_rows_observed": 2, "n_probes_completed": 2},
        },
        participant_id="P01",
        visit_ordinal=1,
        workload_level="LOW",
        source_csv_filename="run.csv",
    )

    assert any(item["code"] == "isa_probe_count_mismatch" for item in issues)


def test_manifest_validator_rejects_duplicate_tlx_and_bedford_presentations() -> None:
    manifest = _v3_manifest()
    manifest["questionnaires"] = {
        "isa": "isa_en.txt",
        "nasatlx": "nasatlx_en.txt",
        "bedford": "bedford_en.txt",
        "include_nasatlx": True,
        "include_bedford": True,
    }
    issues = validate_manifest_against_session(
        manifest,
        csv_rows=[],
        converted_record={
            "scenario_time_max_s": 120,
            "sysmon": {
                "n_observed_target_opportunities": 0,
                "n_observed_nontarget_opportunities": 0,
            },
            "comm": {"n_opened_opportunities": 0},
            "nasatlx": {
                "n_rows_observed": 7,
                "n_subscales_completed": 6,
                "duplicate_subscales": ["mental_demand"],
            },
            "bedford": {"n_observations": 2},
            "isa": {"n_rows_observed": 0, "n_probes_completed": 0},
        },
        participant_id="P01",
        visit_ordinal=1,
        workload_level="LOW",
        source_csv_filename="run.csv",
    )
    codes = {item["code"] for item in issues}

    assert "nasatlx_presentation_mismatch" in codes
    assert "nasatlx_duplicate_subscales" in codes
    assert "bedford_presentation_mismatch" in codes


def test_manifest_validator_requires_completed_valid_questionnaires() -> None:
    manifest = _v3_manifest()
    manifest["questionnaires"] = {
        "isa": "isa_en.txt",
        "nasatlx": "nasatlx_en.txt",
        "bedford": "bedford_en.txt",
        "include_nasatlx": True,
        "include_bedford": True,
    }
    manifest["expected"] = {
        **manifest["expected"],
        "isa_probe_times_sec": [30],
    }
    issues = validate_manifest_against_session(
        manifest,
        csv_rows=[],
        converted_record={
            "scenario_time_max_s": 120,
            "sysmon": {
                "n_observed_target_opportunities": 0,
                "n_observed_nontarget_opportunities": 0,
            },
            "comm": {"n_opened_opportunities": 0},
            "isa": {
                "n_rows_observed": 1,
                "n_probes_completed": 0,
                "n_invalid_probes": 1,
            },
            "nasatlx": {
                "n_rows_observed": 6,
                "n_subscales_completed": 5,
                "complete": False,
                "invalid_subscales": ["mental_demand"],
            },
            "bedford": {
                "n_observations": 1,
                "valid": False,
                "invalid_values": [{"reason": "missing_or_nonfinite_value"}],
            },
        },
        participant_id="P01",
        visit_ordinal=1,
        workload_level="LOW",
        source_csv_filename="run.csv",
    )
    codes = {item["code"] for item in issues}

    assert {
        "isa_valid_completion_count_mismatch",
        "nasatlx_incomplete_or_invalid",
        "bedford_incomplete_or_invalid",
    } <= codes


def test_v3_manifest_cannot_omit_questionnaire_or_probe_plans() -> None:
    manifest = _v3_manifest()
    manifest["questionnaires"] = {}
    manifest["expected"] = {
        "sysmon_target_opportunities": 0,
        "sysmon_nontarget_opportunities": 0,
        "comm_events": 0,
    }

    codes = _validate_v3(manifest)

    assert "incomplete_questionnaire_plan" in codes
    assert "incomplete_expected_plan" in codes
    assert "invalid_isa_probe_schedule" in codes
    assert "invalid_sagat_freeze_count" in codes


def test_v3_false_questionnaire_flags_reconcile_to_zero_presentations() -> None:
    manifest = _v3_manifest()
    issues = validate_manifest_against_session(
        manifest,
        csv_rows=[],
        converted_record={
            "scenario_time_max_s": 120,
            "sysmon": {
                "n_observed_target_opportunities": 0,
                "n_observed_nontarget_opportunities": 0,
            },
            "comm": {"n_opened_opportunities": 0},
            "isa": {"n_rows_observed": 0},
            "sagat": {"n_freezes_executed": 0},
            "nasatlx": {"n_rows_observed": 6},
            "bedford": {"n_observations": 1},
        },
        participant_id="P01",
        visit_ordinal=1,
        workload_level="LOW",
        source_csv_filename="run.csv",
    )
    codes = {item["code"] for item in issues}

    assert "nasatlx_presentation_mismatch" in codes
    assert "bedford_presentation_mismatch" in codes
