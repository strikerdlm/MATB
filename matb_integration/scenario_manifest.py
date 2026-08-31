"""Scenario manifest generation and warning-mode validation.

The manifest is intentionally plain JSON so it can travel with scenario files,
uploads, and research bundles without importing OpenMATB.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from matb_integration.log_converter import NASA_TLX_SUBSCALES

MANIFEST_VERSION = 3
SUPPORTED_MANIFEST_VERSIONS = (1, 2, 3)
METRICS_SCHEMA_VERSION = "2.0"
MANIFEST_GENERATOR = "matb_integration.scenario_builder"
MANIFEST_GENERATOR_VERSION = "3.0.0"
_FULL_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")

ScenarioManifest = dict[str, Any]
ValidationIssue = dict[str, Any]


def canonical_json(payload: Any) -> str:
    """Return deterministic, human-readable JSON with a trailing newline."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def source_provenance(source_commit: str, source_dirty: bool | None) -> dict[str, Any]:
    """Classify generator source without upgrading missing evidence."""
    if not isinstance(source_commit, str):
        raise ValueError("source_commit must be a string")
    if source_dirty is not None and not isinstance(source_dirty, bool):
        raise ValueError("source_dirty must be boolean or null")
    normalized = source_commit.strip()
    if normalized.lower() in {"unknown", "unavailable"}:
        if source_dirty is not None:
            raise ValueError("source_dirty must be null when source_commit is unavailable")
        return {
            "source_commit": normalized.lower(),
            "source_dirty": None,
            "provenance_status": "provisional_missing_source_commit",
        }
    if _FULL_GIT_OID.fullmatch(normalized) is None:
        raise ValueError("source_commit must be a full lowercase SHA-1/SHA-256 Git object id")
    if source_dirty is None:
        status = "provisional_unverified_source_tree"
    elif source_dirty:
        status = "provisional_dirty_source_tree"
    else:
        status = "complete"
    return {
        "source_commit": normalized,
        "source_dirty": source_dirty,
        "provenance_status": status,
    }


def write_manifest(path: Path, manifest: ScenarioManifest) -> None:
    # Path.write_text otherwise applies platform newline translation on Windows,
    # changing archived manifest bytes and hashes for the same canonical payload.
    path.write_text(canonical_json(manifest), encoding="utf-8", newline="\n")


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
    source_commit: str = "unknown",
    source_dirty: bool | None = None,
) -> ScenarioManifest:
    """Build a versioned manifest for an OpenMATB scenario file."""
    manifest: ScenarioManifest = {
        "manifest_version": MANIFEST_VERSION,
        "metrics_schema_version": METRICS_SCHEMA_VERSION,
        "deprecations": {
            "LATIN_SQUARE_3": "use COMPLETE_COUNTERBALANCE_3; six orders are complete permutation counterbalancing"
        },
        "generated_by": {
            "component": MANIFEST_GENERATOR,
            "version": MANIFEST_GENERATOR_VERSION,
            **source_provenance(source_commit, source_dirty),
        },
        "artifact_scope": (
            "session_bound"
            if participant_id and visit_ordinal is not None
            else "exploratory_template"
        ),
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
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def _scenario_path_names(rows: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for row in rows:
        if row.get("type") == "scenario_path" and row.get("value"):
            names.append(Path(str(row["value"])).name)
    return names


def _observed_scenario_sha256(rows: list[dict[str, Any]]) -> list[str]:
    return [
        str(row.get("value"))
        for row in rows
        if row.get("type") == "scenario_sha256" and row.get("value")
    ]


def _runtime_manifest_evidence_issues(
    manifest: ScenarioManifest,
    *,
    csv_rows: list[dict[str, Any]],
    uploaded_manifest_sha256: str,
) -> list[ValidationIssue]:
    """Bind uploaded bytes to the manifest the runtime actually verified.

    A matching scenario hash alone is insufficient: an analyst could otherwise
    attach a newly authored manifest after data collection.  The runtime emits
    exactly one strict verification record before task execution; confirmatory
    ingestion requires that record to name these exact uploaded bytes.
    """

    evidence_rows = [
        row
        for row in csv_rows
        if row.get("type") == "scenario_manifest_evidence"
    ]
    if not evidence_rows:
        return [issue(
            "error",
            "missing_runtime_manifest_evidence",
            "CSV lacks the runtime-emitted scenario manifest verification record.",
        )]
    if len(evidence_rows) != 1:
        return [issue(
            "error",
            "ambiguous_runtime_manifest_evidence",
            "CSV must contain exactly one runtime manifest verification record.",
            expected=1,
            observed=len(evidence_rows),
        )]
    try:
        evidence = json.loads(
            str(evidence_rows[0].get("value", "")),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant: {value}")
            ),
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return [issue(
            "error",
            "invalid_runtime_manifest_evidence",
            "Runtime manifest evidence is not strict JSON.",
        )]
    required = {
        "schema_version",
        "status",
        "scenario_sha256",
        "adjacent_manifest_filename",
        "scenario_manifest_sha256",
        "manifest_identity",
    }
    if not isinstance(evidence, dict) or set(evidence) != required:
        return [issue(
            "error",
            "invalid_runtime_manifest_evidence",
            "Runtime manifest evidence has an unsupported structure.",
            expected=sorted(required),
            observed=sorted(evidence) if isinstance(evidence, dict) else None,
        )]

    evidence_issues: list[ValidationIssue] = []
    if evidence.get("schema_version") != "1.0":
        evidence_issues.append(issue(
            "error",
            "unsupported_runtime_manifest_evidence_schema",
            "Runtime manifest evidence schema is unsupported.",
            expected="1.0",
            observed=evidence.get("schema_version"),
        ))
    if evidence.get("status") != "verified":
        evidence_issues.append(issue(
            "error",
            "runtime_manifest_not_verified",
            "Runtime did not fully verify a clean, session-bound manifest.",
            expected="verified",
            observed=evidence.get("status"),
        ))
    if evidence.get("scenario_manifest_sha256") != uploaded_manifest_sha256:
        evidence_issues.append(issue(
            "error",
            "runtime_manifest_digest_mismatch",
            "Uploaded manifest bytes differ from the runtime-verified manifest.",
            expected=evidence.get("scenario_manifest_sha256"),
            observed=uploaded_manifest_sha256,
        ))
    scenario = manifest.get("scenario")
    scenario_sha256 = scenario.get("sha256") if isinstance(scenario, dict) else None
    if evidence.get("scenario_sha256") != scenario_sha256:
        evidence_issues.append(issue(
            "error",
            "runtime_manifest_scenario_mismatch",
            "Runtime evidence and uploaded manifest bind different scenarios.",
            expected=evidence.get("scenario_sha256"),
            observed=scenario_sha256,
        ))

    generated_by = manifest.get("generated_by")
    seed = manifest.get("seed")
    if (
        not isinstance(generated_by, dict)
        or isinstance(seed, bool)
        or not isinstance(seed, int)
        or seed < 0
    ):
        evidence_issues.append(issue(
            "error",
            "runtime_manifest_identity_unverifiable",
            "Uploaded manifest lacks the fields needed to verify runtime identity.",
        ))
    else:
        expected_identity = {
            "manifest_schema_version": str(manifest.get("manifest_version")),
            "metrics_schema_version": manifest.get("metrics_schema_version"),
            "experiment_spec_sha256": None,
            "experiment_seed": seed,
            "scenario_compiler_id": generated_by.get("component"),
            "scenario_compiler_version": generated_by.get("version"),
            "manifest_source_commit": generated_by.get("source_commit"),
            "manifest_source_dirty": generated_by.get("source_dirty"),
            "manifest_provenance_status": generated_by.get("provenance_status"),
        }
        if evidence.get("manifest_identity") != expected_identity:
            evidence_issues.append(issue(
                "error",
                "runtime_manifest_identity_mismatch",
                "Runtime-verified manifest identity differs from the uploaded manifest.",
                expected=evidence.get("manifest_identity"),
                observed=expected_identity,
            ))
    return evidence_issues


def validate_manifest_against_session(
    manifest: ScenarioManifest,
    *,
    csv_rows: list[dict[str, Any]],
    converted_record: dict[str, Any],
    participant_id: str,
    visit_ordinal: int,
    workload_level: str,
    source_csv_filename: str,
    uploaded_manifest_sha256: str | None = None,
) -> list[ValidationIssue]:
    """Compare a manifest to an ingested CSV conversion.

    The validator records issues only; callers decide whether issues block a
    workflow. The web console deliberately uses warning mode for P0.
    """
    issues: list[ValidationIssue] = []

    if uploaded_manifest_sha256 is not None:
        issues.extend(_runtime_manifest_evidence_issues(
            manifest,
            csv_rows=csv_rows,
            uploaded_manifest_sha256=uploaded_manifest_sha256,
        ))

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

    metrics_schema_version = manifest.get("metrics_schema_version")
    if metrics_schema_version is None:
        issues.append(issue(
            "error", "missing_metrics_schema_version",
            "Scenario manifest lacks the metrics schema required for confirmatory use.",
            expected=METRICS_SCHEMA_VERSION,
        ))
    elif metrics_schema_version != METRICS_SCHEMA_VERSION:
        issues.append(issue(
            "error", "unsupported_metrics_schema_version",
            "Scenario manifest metrics schema is unsupported.",
            expected=METRICS_SCHEMA_VERSION, observed=metrics_schema_version,
        ))

    generated_by = manifest.get("generated_by")
    if version == MANIFEST_VERSION:
        if not isinstance(generated_by, dict):
            issues.append(issue(
                "error", "invalid_generator_provenance",
                "Current manifests require structured generator provenance.",
            ))
        else:
            required_generator_keys = {
                "component", "version", "source_commit", "source_dirty", "provenance_status"
            }
            if set(generated_by) != required_generator_keys:
                issues.append(issue(
                    "error", "invalid_generator_provenance",
                    "Generator provenance must contain exactly the v3 fields.",
                    expected=sorted(required_generator_keys), observed=sorted(generated_by),
                ))
            if generated_by.get("component") != MANIFEST_GENERATOR:
                issues.append(issue(
                    "error", "invalid_generator_component",
                    "Manifest generator component is unsupported.",
                    expected=MANIFEST_GENERATOR, observed=generated_by.get("component"),
                ))
            if generated_by.get("version") != MANIFEST_GENERATOR_VERSION:
                issues.append(issue(
                    "error", "unsupported_generator_version",
                    "Manifest generator version is unsupported.",
                    expected=MANIFEST_GENERATOR_VERSION, observed=generated_by.get("version"),
                ))
            try:
                derived_provenance = source_provenance(
                    generated_by.get("source_commit"),
                    generated_by.get("source_dirty"),
                )
            except ValueError as exc:
                issues.append(issue(
                    "error", "invalid_generator_provenance",
                    "Generator source provenance is malformed.",
                    observed=str(exc),
                ))
            else:
                mismatches = {
                    field: {
                        "expected": derived_provenance[field],
                        "observed": generated_by.get(field),
                    }
                    for field in ("source_commit", "source_dirty", "provenance_status")
                    if generated_by.get(field) != derived_provenance[field]
                }
                if mismatches:
                    issues.append(issue(
                        "error", "invalid_generator_provenance",
                        "Generator provenance status is inconsistent with source evidence.",
                        expected=derived_provenance, observed=mismatches,
                    ))
                elif derived_provenance["provenance_status"] != "complete":
                    issues.append(issue(
                        "warning", "provisional_generator_provenance",
                        "Generator source provenance is incomplete; confirmatory use is ineligible.",
                        expected="complete", observed=derived_provenance["provenance_status"],
                    ))

        supported_workload_status = "engineering_preset_pending_human_calibration"
        if manifest.get("workload_label_status") != supported_workload_status:
            issues.append(issue(
                "error", "unsupported_workload_label_status",
                "This release does not accept self-asserted human workload calibration.",
                expected=supported_workload_status,
                observed=manifest.get("workload_label_status"),
            ))
    expected_level = str(manifest.get("workload_level", "")).upper()
    observed_level = workload_level.upper()
    if not expected_level:
        issues.append(issue(
            "error", "missing_workload_level", "Manifest lacks a workload-level binding."
        ))
    elif expected_level != observed_level:
        issues.append(issue(
            "error", "workload_mismatch",
            "Uploaded workload level does not match the manifest.",
            expected=expected_level, observed=observed_level,
        ))

    expected_participant = manifest.get("participant_id")
    if not expected_participant:
        issues.append(issue(
            "warning", "missing_participant_binding",
            "Manifest lacks a participant binding required for confirmatory use.",
        ))
    elif expected_participant != participant_id:
        issues.append(issue(
            "warning", "participant_mismatch",
            "Uploaded participant id does not match the manifest.",
            expected=expected_participant, observed=participant_id,
        ))

    expected_visit = manifest.get("visit_ordinal")
    if expected_visit is None:
        issues.append(issue(
            "warning", "missing_visit_binding",
            "Manifest lacks a visit binding required for confirmatory use.",
        ))
    elif (
        not isinstance(expected_visit, int)
        or isinstance(expected_visit, bool)
        or expected_visit < 1
    ):
        issues.append(issue(
            "error", "invalid_visit_ordinal",
            "Manifest visit ordinal must be an exact positive integer.",
            expected="positive integer", observed=expected_visit,
        ))
    elif expected_visit != visit_ordinal:
        issues.append(issue(
            "warning", "visit_mismatch",
            "Uploaded visit ordinal does not match the manifest.",
            expected=expected_visit, observed=visit_ordinal,
        ))

    if version == MANIFEST_VERSION:
        session_bound = bool(expected_participant) and (
            isinstance(expected_visit, int)
            and not isinstance(expected_visit, bool)
            and expected_visit >= 1
        )
        expected_scope = "session_bound" if session_bound else "exploratory_template"
        if manifest.get("artifact_scope") != expected_scope:
            issues.append(issue(
                "error", "artifact_scope_binding_mismatch",
                "Artifact scope must agree with participant and visit bindings.",
                expected=expected_scope, observed=manifest.get("artifact_scope"),
            ))

    scenario = manifest.get("scenario") if isinstance(manifest.get("scenario"), dict) else {}
    expected_scenario_filename = scenario.get("filename")
    expected_scenario_sha256 = scenario.get("sha256")
    observed_scenarios = _scenario_path_names(csv_rows)
    unique_observed_scenarios = sorted(set(observed_scenarios))
    if not expected_scenario_filename:
        issues.append(issue(
            "error", "missing_scenario_filename", "Manifest lacks a scenario filename."
        ))
    elif not observed_scenarios:
        issues.append(issue(
            "warning", "scenario_file_unobserved",
            "CSV contains no scenario_path row that can bind the manifest filename.",
        ))
    elif len(unique_observed_scenarios) > 1:
        issues.append(issue(
            "error", "scenario_file_binding_ambiguous",
            "CSV references multiple scenario basenames and cannot be bound to one manifest.",
            expected=expected_scenario_filename, observed=unique_observed_scenarios,
        ))
    elif unique_observed_scenarios[0] != expected_scenario_filename:
        issues.append(issue(
            "error", "scenario_file_mismatch",
            "CSV scenario basename does not match the manifest.",
            expected=expected_scenario_filename, observed=unique_observed_scenarios[0],
        ))
    if not isinstance(expected_scenario_sha256, str) or len(expected_scenario_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in expected_scenario_sha256
    ):
        issues.append(issue(
            "error", "invalid_scenario_sha256",
            "Manifest scenario SHA-256 must be a lowercase 64-character digest.",
            observed=expected_scenario_sha256,
        ))
    else:
        observed_hashes = _observed_scenario_sha256(csv_rows)
        unique_observed_hashes = sorted(set(observed_hashes))
        if not observed_hashes:
            issues.append(issue(
                "warning", "scenario_sha256_unobserved",
                "CSV lacks the runtime-observed scenario SHA-256 binding.",
            ))
        elif len(unique_observed_hashes) > 1:
            issues.append(issue(
                "error", "scenario_sha256_binding_ambiguous",
                "CSV contains multiple runtime scenario SHA-256 values and cannot bind one manifest.",
                expected=expected_scenario_sha256,
                observed=unique_observed_hashes,
            ))
        elif unique_observed_hashes[0] != expected_scenario_sha256:
            issues.append(issue(
                "error", "scenario_sha256_mismatch",
                "Runtime-observed scenario SHA-256 does not match the manifest.",
                expected=expected_scenario_sha256,
                observed=unique_observed_hashes[0],
            ))

    duration = _float_or_none(manifest.get("block_duration_sec"))
    observed_tmax = _float_or_none(converted_record.get("scenario_time_max_s"))
    if duration is None or duration <= 0:
        issues.append(issue(
            "error", "invalid_block_duration",
            "Manifest block_duration_sec must be a finite positive number.",
            observed=manifest.get("block_duration_sec"),
        ))
    elif observed_tmax is not None:
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

    raw_expected = manifest.get("expected")
    expected = raw_expected if isinstance(raw_expected, dict) else {}
    raw_questionnaires = manifest.get("questionnaires")
    questionnaires = raw_questionnaires if isinstance(raw_questionnaires, dict) else {}
    if version == MANIFEST_VERSION:
        required_questionnaire_keys = {
            "isa",
            "nasatlx",
            "bedford",
            "include_nasatlx",
            "include_bedford",
        }
        if not isinstance(raw_questionnaires, dict):
            issues.append(issue(
                "error",
                "invalid_questionnaire_plan",
                "Current manifests require a structured questionnaire plan.",
                expected=sorted(required_questionnaire_keys),
                observed=type(raw_questionnaires).__name__,
            ))
        else:
            if required_questionnaire_keys - set(questionnaires):
                issues.append(issue(
                    "error",
                    "incomplete_questionnaire_plan",
                    "Current manifests must declare every questionnaire and inclusion flag.",
                    expected=sorted(required_questionnaire_keys),
                    observed=sorted(questionnaires),
                ))
            for filename_key in ("isa", "nasatlx", "bedford"):
                filename = questionnaires.get(filename_key)
                if (
                    not isinstance(filename, str)
                    or not filename
                    or filename != Path(filename).name
                    or not filename.endswith(".txt")
                ):
                    issues.append(issue(
                        "error",
                        f"invalid_{filename_key}_questionnaire_filename",
                        f"Questionnaire {filename_key} must be a non-empty local .txt filename.",
                        observed=filename,
                    ))
            for flag_key in ("include_nasatlx", "include_bedford"):
                if type(questionnaires.get(flag_key)) is not bool:
                    issues.append(issue(
                        "error",
                        f"invalid_{flag_key}",
                        f"Questionnaire flag {flag_key} must be an exact boolean.",
                        observed=questionnaires.get(flag_key),
                    ))

        required_expected_keys = {
            "sysmon_target_opportunities",
            "sysmon_nontarget_opportunities",
            "comm_events",
            "isa_probe_times_sec",
            "sagat_freezes",
        }
        if not isinstance(raw_expected, dict):
            issues.append(issue(
                "error",
                "invalid_expected_plan",
                "Current manifests require a structured expected-observations plan.",
                expected=sorted(required_expected_keys),
                observed=type(raw_expected).__name__,
            ))
        elif required_expected_keys - set(expected):
            issues.append(issue(
                "error",
                "incomplete_expected_plan",
                "Current manifests must declare every required observation schedule.",
                expected=sorted(required_expected_keys),
                observed=sorted(expected),
            ))

        isa_schedule = expected.get("isa_probe_times_sec")
        if not (
            isinstance(isa_schedule, list)
            and all(
                isinstance(value, int)
                and not isinstance(value, bool)
                and value > 0
                and (duration is None or value < duration)
                for value in isa_schedule
            )
            and isa_schedule == sorted(set(isa_schedule))
        ):
            issues.append(issue(
                "error",
                "invalid_isa_probe_schedule",
                "ISA probe times must be unique, increasing positive integer seconds within the block.",
                observed=isa_schedule,
            ))

        sagat_plan = expected.get("sagat_freezes")
        if (
            not isinstance(sagat_plan, int)
            or isinstance(sagat_plan, bool)
            or sagat_plan < 0
        ):
            issues.append(issue(
                "error",
                "invalid_sagat_freeze_count",
                "SAGAT freeze count must be an exact non-negative integer.",
                observed=sagat_plan,
            ))
    sysmon_metrics = (
        converted_record.get("sysmon")
        if isinstance(converted_record.get("sysmon"), dict)
        else {}
    )
    for label in ("target", "nontarget"):
        expected_count = expected.get(f"sysmon_{label}_opportunities")
        observed_count = sysmon_metrics.get(f"n_observed_{label}_opportunities")
        if not isinstance(expected_count, int) or isinstance(expected_count, bool) or expected_count < 0:
            issues.append(issue(
                "error",
                f"invalid_sysmon_{label}_opportunity_count",
                f"Manifest must declare a non-negative SYSMON {label} opportunity count.",
                observed=expected_count,
            ))
        elif (
            isinstance(observed_count, int)
            and not isinstance(observed_count, bool)
            and expected_count != observed_count
        ):
            issues.append(issue(
                "error",
                f"sysmon_{label}_opportunity_count_mismatch",
                f"Observed SYSMON {label} opportunities do not match the manifest.",
                expected=expected_count,
                observed=observed_count,
            ))

    comm_metrics = (
        converted_record.get("comm")
        if isinstance(converted_record.get("comm"), dict)
        else {}
    )
    expected_comm = expected.get("comm_events")
    observed_comm = comm_metrics.get("n_opened_opportunities")
    if (
        not isinstance(expected_comm, int)
        or isinstance(expected_comm, bool)
        or expected_comm < 0
    ):
        issues.append(issue(
            "error",
            "invalid_comm_opportunity_count",
            "Manifest must declare a non-negative COMM opportunity count.",
            observed=expected_comm,
        ))
    else:
        if (
            not isinstance(observed_comm, int)
            or isinstance(observed_comm, bool)
            or observed_comm != expected_comm
        ):
            issues.append(issue(
                "error",
                "comm_opportunity_count_mismatch",
                "Observed COMM opportunity openings do not match the manifest.",
                expected=expected_comm,
                observed=observed_comm,
            ))
        if expected_comm > 0 and (
            comm_metrics.get("observed_opportunity_status") != "complete"
            or comm_metrics.get("observed_opportunity_reconciled") is not True
        ):
            issues.append(issue(
                "error",
                "comm_opportunity_evidence_incomplete",
                "COMM lifecycle evidence is incomplete, invalid, or unreconciled.",
                expected="complete",
                observed=comm_metrics.get("observed_opportunity_status"),
            ))

    isa_metrics = converted_record.get("isa") or {}
    isa_schedule = expected.get("isa_probe_times_sec")
    expected_isa = len(isa_schedule) if isinstance(isa_schedule, list) else 0
    observed_isa = isa_metrics.get("n_rows_observed")
    if not isinstance(observed_isa, int) or isinstance(observed_isa, bool):
        observed_isa = (
            (isa_metrics.get("n_probes_completed") or 0)
            + (isa_metrics.get("n_invalid_probes") or 0)
        )
    if "isa_probe_times_sec" in expected and observed_isa != expected_isa:
        issues.append(issue(
            "error", "isa_probe_count_mismatch",
            "Observed ISA presentations do not exactly match the planned probes.",
            expected=expected_isa, observed=observed_isa,
        ))
    completed_isa = isa_metrics.get("n_probes_completed")
    if (
        "isa_probe_times_sec" in expected
        and (
            not isinstance(completed_isa, int)
            or isinstance(completed_isa, bool)
            or completed_isa != expected_isa
        )
    ):
        issues.append(issue(
            "error",
            "isa_valid_completion_count_mismatch",
            "Valid completed ISA responses must exactly match the planned probes.",
            expected=expected_isa,
            observed=completed_isa,
        ))
    if expected_isa and observed_isa < expected_isa:
        issues.append(issue(
            "warning", "isa_probe_shortfall",
            "Fewer ISA probe responses were found than planned.",
            expected=expected_isa, observed=observed_isa,
        ))
    invalid_isa = ((converted_record.get("isa") or {}).get("n_invalid_probes") or 0)
    if invalid_isa:
        issues.append(issue(
            "error", "invalid_isa_values",
            "ISA responses outside the registered 1–10 domain were observed.",
            expected="all ISA values in [1, 10]", observed=invalid_isa,
        ))

    expected_sagat_value = expected.get("sagat_freezes")
    expected_sagat = (
        expected_sagat_value
        if isinstance(expected_sagat_value, int)
        and not isinstance(expected_sagat_value, bool)
        and expected_sagat_value >= 0
        else 0
    )
    observed_sagat = ((converted_record.get("sagat") or {}).get("n_freezes_executed") or 0)
    if "sagat_freezes" in expected and observed_sagat != expected_sagat:
        issues.append(issue(
            "error", "sagat_freeze_count_mismatch",
            "Observed SAGAT freezes do not exactly match the planned count.",
            expected=expected_sagat, observed=observed_sagat,
        ))
    if expected_sagat and observed_sagat < expected_sagat:
        issues.append(issue(
            "warning", "sagat_freeze_shortfall",
            "Fewer SAGAT freezes were executed than planned.",
            expected=expected_sagat, observed=observed_sagat,
        ))

    nasatlx_metrics = converted_record.get("nasatlx") or {}
    if "include_nasatlx" in questionnaires and type(questionnaires.get("include_nasatlx")) is bool:
        expected_tlx_rows = len(NASA_TLX_SUBSCALES) if questionnaires.get("include_nasatlx") else 0
        observed_tlx_rows = nasatlx_metrics.get("n_rows_observed")
        if not isinstance(observed_tlx_rows, int) or isinstance(observed_tlx_rows, bool):
            observed_tlx_rows = nasatlx_metrics.get("n_subscales_completed") or 0
        if observed_tlx_rows != expected_tlx_rows:
            issues.append(issue(
                "error", "nasatlx_presentation_mismatch",
                "NASA-TLX must contain exactly one observation for each planned subscale.",
                expected=expected_tlx_rows, observed=observed_tlx_rows,
            ))
        duplicate_subscales = nasatlx_metrics.get("duplicate_subscales") or []
        if duplicate_subscales:
            issues.append(issue(
                "error", "nasatlx_duplicate_subscales",
                "Duplicate NASA-TLX subscale presentations were observed.",
                expected="one observation per subscale", observed=duplicate_subscales,
            ))
        if questionnaires.get("include_nasatlx") and nasatlx_metrics.get("complete") is not True:
            issues.append(issue(
                "error",
                "nasatlx_incomplete_or_invalid",
                "Planned NASA-TLX evidence must contain six unique valid subscales.",
                expected="complete valid NASA-TLX",
                observed={
                    "complete": nasatlx_metrics.get("complete"),
                    "invalid_subscales": nasatlx_metrics.get("invalid_subscales") or [],
                },
            ))

    bedford_metrics = converted_record.get("bedford") or {}
    if "include_bedford" in questionnaires and type(questionnaires.get("include_bedford")) is bool:
        expected_bedford = 1 if questionnaires.get("include_bedford") else 0
        observed_bedford = bedford_metrics.get("n_observations")
        if not isinstance(observed_bedford, int) or isinstance(observed_bedford, bool):
            observed_bedford = 1 if bedford_metrics.get("value_raw") is not None else 0
        if observed_bedford != expected_bedford:
            issues.append(issue(
                "error", "bedford_presentation_mismatch",
                "Observed Bedford presentations do not exactly match the manifest.",
                expected=expected_bedford, observed=observed_bedford,
            ))
        if questionnaires.get("include_bedford") and bedford_metrics.get("valid") is not True:
            issues.append(issue(
                "error",
                "bedford_incomplete_or_invalid",
                "Planned Bedford evidence must contain exactly one valid 1–10 response.",
                expected="one valid Bedford response",
                observed={
                    "valid": bedford_metrics.get("valid"),
                    "n_observations": observed_bedford,
                },
            ))
    invalid_bedford = (converted_record.get("bedford") or {}).get("invalid_values") or []
    if invalid_bedford:
        issues.append(issue(
            "error", "invalid_bedford_values",
            "Bedford responses outside the registered 1–10 domain were observed.",
            expected="all Bedford values in [1, 10]", observed=invalid_bedford,
        ))
    if questionnaires.get("include_nasatlx") and duration is not None and observed_tmax is not None:
        n_tlx = (nasatlx_metrics.get("n_subscales_completed") or 0)
        if observed_tmax >= duration - 2.0 and n_tlx == 0:
            issues.append(issue(
                "warning", "nasatlx_missing",
                "The manifest expected NASA-TLX at block end, but no NASA-TLX responses were found.",
                expected="NASA-TLX responses", observed=f"{source_csv_filename}: none",
            ))

    return issues
