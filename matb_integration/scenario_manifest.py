"""Scenario manifest generation and warning-mode validation.

The manifest is intentionally plain JSON so it can travel with scenario files,
uploads, and research bundles without importing OpenMATB.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MANIFEST_VERSION = 2
SUPPORTED_MANIFEST_VERSIONS = (1, 2)
METRICS_SCHEMA_VERSION = "2.0"
MANIFEST_GENERATOR = "matb_integration.scenario_builder"

ScenarioManifest = dict[str, Any]
ValidationIssue = dict[str, Any]


def canonical_json(payload: Any) -> str:
    """Return deterministic, human-readable JSON with a trailing newline."""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_manifest(path: Path, manifest: ScenarioManifest) -> None:
    path.write_text(canonical_json(manifest), encoding="utf-8")


def build_scenario_manifest(
    *,
    scenario_filename: str,
    scenario_text: str,
    workload_level: str,
    seed: int,
    block_duration_sec: int,
    parameters: dict[str, Any],
    questionnaires: dict[str, Any],
    expected: dict[str, Any],
    participant_id: str | None = None,
    block_num: int | None = None,
    visit_ordinal: int | None = None,
    sagat_manifest_path: Path | None = None,
) -> ScenarioManifest:
    """Build a versioned manifest for an OpenMATB scenario file."""
    manifest: ScenarioManifest = {
        "manifest_version": MANIFEST_VERSION,
        "metrics_schema_version": METRICS_SCHEMA_VERSION,
        "deprecations": {
            "LATIN_SQUARE_3": "use COMPLETE_COUNTERBALANCE_3; six orders are complete permutation counterbalancing"
        },
        "generated_by": MANIFEST_GENERATOR,
        "scenario": {
            "filename": scenario_filename,
            "sha256": sha256_text(scenario_text),
            "line_count": len(scenario_text.splitlines()),
        },
        "workload_level": workload_level.upper(),
        "workload_label_status": "engineering_preset_pending_human_calibration",
        "seed": seed,
        "block_duration_sec": block_duration_sec,
        "parameters": parameters,
        "questionnaires": questionnaires,
        "expected": expected,
    }
    if participant_id:
        manifest["participant_id"] = participant_id
    if block_num is not None:
        manifest["block_num"] = block_num
    if visit_ordinal is not None:
        manifest["visit_ordinal"] = visit_ordinal
    if sagat_manifest_path is not None and sagat_manifest_path.exists():
        manifest["sagat"] = {
            "manifest_filename": sagat_manifest_path.name,
            "sha256": sha256_file(sagat_manifest_path),
        }
    return manifest


def manifest_summary(manifest: ScenarioManifest | None) -> dict[str, Any] | None:
    if manifest is None:
        return None
    scenario = manifest.get("scenario") if isinstance(manifest.get("scenario"), dict) else {}
    expected = manifest.get("expected") if isinstance(manifest.get("expected"), dict) else {}
    return {
        "manifest_version": manifest.get("manifest_version"),
        "metrics_schema_version": manifest.get("metrics_schema_version"),
        "scenario_filename": scenario.get("filename"),
        "scenario_sha256": scenario.get("sha256"),
        "participant_id": manifest.get("participant_id"),
        "visit_ordinal": manifest.get("visit_ordinal"),
        "block_num": manifest.get("block_num"),
        "workload_level": manifest.get("workload_level"),
        "workload_label_status": manifest.get("workload_label_status"),
        "seed": manifest.get("seed"),
        "block_duration_sec": manifest.get("block_duration_sec"),
        "expected_isa_probes": len(expected.get("isa_probe_times_sec") or []),
        "expected_sagat_freezes": expected.get("sagat_freezes", 0),
    }


def issue(
    severity: str,
    code: str,
    message: str,
    *,
    expected: Any = None,
    observed: Any = None,
) -> ValidationIssue:
    out: ValidationIssue = {"severity": severity, "code": code, "message": message}
    if expected is not None:
        out["expected"] = expected
    if observed is not None:
        out["observed"] = observed
    return out


def validation_status(issues: list[ValidationIssue]) -> str:
    if any(i.get("severity") == "error" for i in issues):
        return "error"
    if issues:
        return "warning"
    return "ok"


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _scenario_path_names(rows: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for row in rows:
        if row.get("type") == "scenario_path" and row.get("value"):
            names.append(Path(str(row["value"])).name)
    return names


def validate_manifest_against_session(
    manifest: ScenarioManifest,
    *,
    csv_rows: list[dict[str, Any]],
    converted_record: dict[str, Any],
    participant_id: str,
    visit_ordinal: int,
    workload_level: str,
    source_csv_filename: str,
) -> list[ValidationIssue]:
    """Compare a manifest to an ingested CSV conversion.

    The validator records issues only; callers decide whether issues block a
    workflow. The web console deliberately uses warning mode for P0.
    """
    issues: list[ValidationIssue] = []

    version = manifest.get("manifest_version")
    if version not in SUPPORTED_MANIFEST_VERSIONS:
        issues.append(issue(
            "error", "unsupported_manifest_version",
            "Scenario manifest version is unsupported.",
            expected=list(SUPPORTED_MANIFEST_VERSIONS), observed=version,
        ))
    elif version < MANIFEST_VERSION:
        issues.append(issue(
            "warning", "legacy_manifest_version",
            "Scenario manifest predates the current scientific provenance schema.",
            expected=MANIFEST_VERSION, observed=version,
        ))

    expected_level = str(manifest.get("workload_level", "")).upper()
    observed_level = workload_level.upper()
    if expected_level and expected_level != observed_level:
        issues.append(issue(
            "error", "workload_mismatch",
            "Uploaded workload level does not match the manifest.",
            expected=expected_level, observed=observed_level,
        ))

    expected_participant = manifest.get("participant_id")
    if expected_participant and expected_participant != participant_id:
        issues.append(issue(
            "warning", "participant_mismatch",
            "Uploaded participant id does not match the manifest.",
            expected=expected_participant, observed=participant_id,
        ))

    expected_visit = manifest.get("visit_ordinal")
    if expected_visit is not None:
        try:
            expected_visit_int = int(expected_visit)
        except (TypeError, ValueError):
            issues.append(issue(
                "error", "invalid_visit_ordinal",
                "Manifest visit ordinal is not an integer.",
                expected="integer", observed=expected_visit,
            ))
        else:
            if expected_visit_int != visit_ordinal:
                issues.append(issue(
                    "warning", "visit_mismatch",
                    "Uploaded visit ordinal does not match the manifest.",
                    expected=expected_visit, observed=visit_ordinal,
                ))

    scenario = manifest.get("scenario") if isinstance(manifest.get("scenario"), dict) else {}
    expected_scenario_filename = scenario.get("filename")
    observed_scenarios = _scenario_path_names(csv_rows)
    if expected_scenario_filename and observed_scenarios and expected_scenario_filename not in observed_scenarios:
        issues.append(issue(
            "warning", "scenario_file_mismatch",
            "CSV scenario_path row does not reference the manifest scenario file.",
            expected=expected_scenario_filename, observed=observed_scenarios,
        ))

    duration = _float_or_none(manifest.get("block_duration_sec"))
    observed_tmax = _float_or_none(converted_record.get("scenario_time_max_s"))
    if duration is not None and observed_tmax is not None:
        if observed_tmax > duration + 2.0:
            issues.append(issue(
                "error", "duration_exceeds_manifest",
                "CSV scenario time exceeds the manifest block duration.",
                expected=duration, observed=observed_tmax,
            ))
        elif observed_tmax < duration * 0.8:
            issues.append(issue(
                "warning", "session_shorter_than_manifest",
                "CSV appears shorter than the planned scenario block.",
                expected=duration, observed=observed_tmax,
            ))

    expected = manifest.get("expected") if isinstance(manifest.get("expected"), dict) else {}
    expected_isa = len(expected.get("isa_probe_times_sec") or [])
    observed_isa = ((converted_record.get("isa") or {}).get("n_probes_completed") or 0)
    if expected_isa and observed_isa < expected_isa:
        issues.append(issue(
            "warning", "isa_probe_shortfall",
            "Fewer ISA probe responses were found than planned.",
            expected=expected_isa, observed=observed_isa,
        ))

    expected_sagat = expected.get("sagat_freezes") or 0
    observed_sagat = ((converted_record.get("sagat") or {}).get("n_freezes_executed") or 0)
    if expected_sagat and observed_sagat < expected_sagat:
        issues.append(issue(
            "warning", "sagat_freeze_shortfall",
            "Fewer SAGAT freezes were executed than planned.",
            expected=expected_sagat, observed=observed_sagat,
        ))

    questionnaires = manifest.get("questionnaires") if isinstance(manifest.get("questionnaires"), dict) else {}
    if questionnaires.get("include_nasatlx") and duration is not None and observed_tmax is not None:
        n_tlx = ((converted_record.get("nasatlx") or {}).get("n_subscales_completed") or 0)
        if observed_tmax >= duration - 2.0 and n_tlx == 0:
            issues.append(issue(
                "warning", "nasatlx_missing",
                "The manifest expected NASA-TLX at block end, but no NASA-TLX responses were found.",
                expected="NASA-TLX responses", observed=f"{source_csv_filename}: none",
            ))

    return issues
