"""Versioned, fail-closed MATB qualification contracts.

These helpers intentionally distinguish software conformance, physical timing,
human calibration, cross-implementation equivalence, and release eligibility.
No status is inferred from a different evidence class.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

PROFILE_SCHEMA_VERSION = "1.0"
CONFORMANCE_SCHEMA_VERSION = "1.0"
TIMING_QUALIFICATION_SCHEMA_VERSION = "1.0"
SCIENTIFIC_QUALIFICATION_SCHEMA_VERSION = "1.0"

PROFILE_DIR = Path(__file__).with_name("profiles")
PROFILE_STATUSES = {
    "software_verified",
    "candidate_pending_direct_test",
    "documented_not_selectable",
}
TIMING_TIERS = {"block_level", "block_plus_physiology", "erp_event_related"}
RESULT_STATUSES = {"PASS", "FAIL", "NOT_MEASURED", "NOT_TESTED"}


def canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _require_mapping(payload: Mapping[str, Any], key: str, issues: list[str]) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        issues.append(f"missing_or_invalid:{key}")
        return {}
    return value


def validate_compatibility_profile(profile: Mapping[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    if profile.get("schema_version") != PROFILE_SCHEMA_VERSION:
        issues.append("unsupported:schema_version")
    profile_id = profile.get("profile_id")
    if not isinstance(profile_id, str) or not profile_id.strip():
        issues.append("missing_or_invalid:profile_id")
    status = profile.get("status")
    if status not in PROFILE_STATUSES:
        issues.append("invalid:status")
    selectable = profile.get("selectable")
    if not isinstance(selectable, bool):
        issues.append("missing_or_invalid:selectable")
    if selectable and status == "documented_not_selectable":
        issues.append("inconsistent:documented_profile_selectable")
    implementation = _require_mapping(profile, "implementation", issues)
    if not implementation.get("name") or not implementation.get("version"):
        issues.append("missing:implementation_identity")
    tasks = profile.get("canonical_tasks")
    if not isinstance(tasks, list) or set(tasks) != {"SYSMON", "TRACK", "COMM", "RESMAN"}:
        issues.append("invalid:canonical_tasks")
    for key in ("behavior", "scoring", "logging", "provenance", "claims"):
        _require_mapping(profile, key, issues)
    claims = profile.get("claims") if isinstance(profile.get("claims"), Mapping) else {}
    if claims.get("human_equivalence") not in {"NOT_TESTED", "EQUIVALENT_WITHIN_MARGIN", "CHARACTERIZED_NOT_EQUIVALENT"}:
        issues.append("invalid:claims.human_equivalence")
    return tuple(sorted(set(issues)))


def list_profiles() -> tuple[str, ...]:
    return tuple(sorted(path.stem for path in PROFILE_DIR.glob("*.json")))


def load_profile(profile_id: str) -> dict[str, Any]:
    path = PROFILE_DIR / f"{profile_id}.json"
    if not path.is_file():
        raise KeyError(f"unknown compatibility profile: {profile_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    issues = validate_compatibility_profile(payload)
    if issues:
        raise ValueError(f"invalid compatibility profile {profile_id}: {', '.join(issues)}")
    return payload


def _check_passes(check: Mapping[str, Any]) -> bool:
    expected = check.get("expected")
    observed = check.get("observed")
    tolerance = check.get("absolute_tolerance")
    if tolerance is None:
        return expected == observed
    if isinstance(expected, bool) or isinstance(observed, bool):
        return False
    if not isinstance(expected, (int, float)) or not isinstance(observed, (int, float)):
        return False
    if not isinstance(tolerance, (int, float)) or tolerance < 0:
        return False
    return abs(float(expected) - float(observed)) <= float(tolerance)


def evaluate_conformance(
    profile: Mapping[str, Any],
    checks: Iterable[Mapping[str, Any]],
    *,
    source_commit: str,
) -> dict[str, Any]:
    profile_issues = validate_compatibility_profile(profile)
    normalized: list[dict[str, Any]] = []
    for index, check in enumerate(checks):
        item = dict(check)
        item.setdefault("check_id", f"check-{index + 1}")
        item["status"] = "PASS" if _check_passes(item) else "FAIL"
        normalized.append(item)
    status = "PASS" if not profile_issues and normalized and all(
        item["status"] == "PASS" for item in normalized
    ) else "FAIL"
    report = {
        "schema_version": CONFORMANCE_SCHEMA_VERSION,
        "profile_id": profile.get("profile_id"),
        "profile_sha256": sha256_payload(profile),
        "source_commit": source_commit,
        "status": status,
        "profile_validation_issues": list(profile_issues),
        "checks": normalized,
        "claim_boundary": (
            "Software conformance does not establish human equivalence or physical timing."
        ),
    }
    report["report_sha256"] = sha256_payload(report)
    return report


def evaluate_timing_qualification(payload: Mapping[str, Any]) -> dict[str, Any]:
    tier = payload.get("use_tier")
    issues: list[str] = []
    if tier not in TIMING_TIERS:
        issues.append("invalid:use_tier")
    rig = payload.get("rig")
    if not isinstance(rig, Mapping) or not all(
        rig.get(key) for key in ("rig_id", "os", "display", "audio_device", "input_device")
    ):
        issues.append("missing:rig_identity")
    physical = payload.get("physical_measurement")
    if not isinstance(physical, Mapping) or physical.get("measured") is not True:
        issues.append("not_measured:physical_onset")
    summaries = payload.get("measurement_summaries")
    if not isinstance(summaries, list) or not summaries:
        issues.append("missing:measurement_summaries")
        summaries = []
    required = {"visual", "audio", "input"}
    seen: set[str] = set()
    for item in summaries:
        if not isinstance(item, Mapping):
            issues.append("invalid:measurement_summary")
            continue
        modality = str(item.get("modality") or "")
        seen.add(modality)
        if modality in required and int(item.get("n") or 0) < 200:
            issues.append(f"insufficient_n:{modality}")
        if int(item.get("run_count") or 0) < 3:
            issues.append(f"insufficient_runs:{modality or 'unknown'}")
        if int(item.get("unmatched_count") or 0) > 0:
            issues.append(f"unmatched_events:{modality or 'unknown'}")
        if item.get("limits_passed") is not True:
            issues.append(f"limits_not_passed:{modality or 'unknown'}")
    for missing in sorted(required - seen):
        issues.append(f"missing_modality:{missing}")
    if payload.get("representative_full_block_recorded") is not True:
        issues.append("missing:representative_full_block")
    if tier == "erp_event_related" and not payload.get("erp_protocol_version"):
        issues.append("not_qualified:erp_protocol")
    if any(issue.startswith("not_measured:") for issue in issues):
        status = "NOT_MEASURED"
    else:
        status = "PASS" if not issues else "FAIL"
    result = dict(payload)
    result.update(
        {
            "schema_version": TIMING_QUALIFICATION_SCHEMA_VERSION,
            "status": status,
            "issues": sorted(set(issues)),
            "claim_boundary": (
                "This report applies only to the exact rig and use tier identified here; "
                "it does not replace session-specific timing QC."
            ),
        }
    )
    result["report_sha256"] = sha256_payload(result)
    return result


def evaluate_release_eligibility(payload: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "software_regression": "PASS",
        "deterministic_replay": "PASS",
        "licensing_review": "PASS",
        "privacy_review": "PASS",
        "timing_block_plus_physiology": "PASS",
        "workload_calibration": "VALIDATED",
        "test_retest_reliability": "CHARACTERIZED",
        "reference_dataset_reproducibility": "PASS",
    }
    gates = payload.get("gates") if isinstance(payload.get("gates"), Mapping) else {}
    blockers = [
        f"{key}:expected_{expected}:observed_{gates.get(key, 'MISSING')}"
        for key, expected in required.items()
        if gates.get(key) != expected
    ]
    comparator = gates.get("matb_ii_comparator")
    if comparator not in {"EQUIVALENT_WITHIN_MARGIN", "CHARACTERIZED_NOT_EQUIVALENT"}:
        blockers.append(f"matb_ii_comparator:observed_{comparator or 'MISSING'}")
    result = dict(payload)
    result.update(
        {
            "schema_version": SCIENTIFIC_QUALIFICATION_SCHEMA_VERSION,
            "release_id": payload.get("release_id", "v1.0.0"),
            "eligible": not blockers,
            "status": "PASS" if not blockers else "BLOCKED",
            "blockers": blockers,
            "claim_boundary": (
                "Release eligibility is evidence-class specific and does not imply diagnosis, "
                "fatigue assessment, or aeromedical fitness validity."
            ),
        }
    )
    result["report_sha256"] = sha256_payload(result)
    return result
