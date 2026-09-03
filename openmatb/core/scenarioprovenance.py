"""Fail-closed binding of an OpenMATB scenario to its adjacent manifest."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

SCENARIO_PROVENANCE_SCHEMA_VERSION = "1.0"
MAX_SCENARIO_MANIFEST_BYTES = 2 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_BUILDER_COMPONENT = "matb_integration.scenario_builder"
_BUILDER_VERSION = "3.0.0"
_COMPILED_COMPONENT = "matb-research"
_COMPILED_VERSION = "1.0.0"
_BUILDER_REQUIRED_TOP_LEVEL = {
    "manifest_version",
    "metrics_schema_version",
    "deprecations",
    "generated_by",
    "artifact_scope",
    "scenario",
    "workload_level",
    "workload_label_status",
    "seed",
    "block_duration_sec",
    "parameters",
    "questionnaires",
    "expected",
}
_BUILDER_OPTIONAL_TOP_LEVEL = {
    "participant_id",
    "block_num",
    "visit_ordinal",
    "sagat",
}
_BUILDER_PARAMETER_KEYS = {
    "difficulty",
    "track_target_proportion",
    "resman_loss_per_min",
    "isa_probe_interval_sec",
    "openmatb_alerttimeout_ms",
    "openmatb_nontarget_duration_ms",
    "openmatb_comm_max_response_delay_ms",
    "communications_prompt_duration_sec",
    "communications_audio_profile_id",
    "communications_audio_inventory_sha256",
    "communications_voice_idiom",
    "communications_voice_gender",
    "communications_response_availability_sec",
    "communications_minimum_onset_separation_sec",
    "communications_own_callsign_ratio",
    "openmatb_sysmon_lights",
    "openmatb_sysmon_scales",
}
_BUILDER_QUESTIONNAIRE_KEYS = {
    "isa",
    "nasatlx",
    "bedford",
    "include_nasatlx",
    "include_bedford",
}
_BUILDER_EXPECTED_KEYS = {
    "sysmon_light_events",
    "sysmon_scale_events",
    "sysmon_target_opportunities",
    "sysmon_nontarget_opportunities",
    "comm_events",
    "task_events_total",
    "event_rate_per_min",
    "per_subtask_event_rate_per_min",
    "counterbalancing_method",
    "workload_label_status",
    "isa_probe_times_sec",
    "sagat_freezes",
    "overlap_definition",
    "concurrent_event_overlap_pairs",
    "task_events_within_5s_of_probe",
    "expected_active_primary_tasks",
}


def _is_exact_int(value: object, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _is_finite_number(value: object, *, minimum: float | None = None) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    numeric = float(value)
    return math.isfinite(numeric) and (minimum is None or numeric >= minimum)


def _require_exact_keys(
    value: object,
    *,
    required: set[str],
    optional: set[str] | None = None,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ScenarioProvenanceError(f"{label} must be an object")
    allowed = required | (optional or set())
    missing = sorted(required - set(value))
    extra = sorted(set(value) - allowed)
    if missing or extra:
        raise ScenarioProvenanceError(
            f"{label} fields are malformed (missing={missing!r}, extra={extra!r})"
        )
    return value


def _scenario_seconds(value: str) -> int:
    try:
        parts = value.split(":")
        if len(parts) != 3:
            raise ValueError
        hours, minutes, seconds = (int(part) for part in parts)
    except (AttributeError, ValueError) as exc:
        raise ScenarioProvenanceError(
            f"scenario contains an invalid timestamp: {value!r}"
        ) from exc
    if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ScenarioProvenanceError(
            f"scenario contains an invalid timestamp: {value!r}"
        )
    return hours * 3600 + minutes * 60 + seconds


def _safe_questionnaire_filename(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or Path(value).name != value
        or not value.endswith(".txt")
    ):
        raise ScenarioProvenanceError(
            f"scenario-builder {label} questionnaire filename is malformed"
        )
    return value


class ScenarioProvenanceError(ValueError):
    """An adjacent manifest exists but cannot bind the executable scenario."""


@dataclass(frozen=True, slots=True)
class BoundScenarioManifest:
    evidence: dict[str, Any]
    content: bytes | None


def _validate_builder_payload(
    payload: dict[str, Any],
    *,
    scenario_content: bytes,
    scenario_path: Path,
) -> None:
    _require_exact_keys(
        payload,
        required=_BUILDER_REQUIRED_TOP_LEVEL,
        optional=_BUILDER_OPTIONAL_TOP_LEVEL,
        label="scenario-builder manifest",
    )
    deprecations = _require_exact_keys(
        payload.get("deprecations"),
        required={"LATIN_SQUARE_3"},
        label="scenario-builder deprecations",
    )
    if deprecations["LATIN_SQUARE_3"] != (
        "use COMPLETE_COUNTERBALANCE_3; six orders are complete permutation counterbalancing"
    ):
        raise ScenarioProvenanceError("scenario-builder deprecation contract is malformed")

    scenario = _require_exact_keys(
        payload.get("scenario"),
        required={"filename", "sha256", "line_count"},
        label="scenario-builder scenario",
    )
    if (
        not isinstance(scenario["filename"], str)
        or not scenario["filename"]
        or Path(scenario["filename"]).name != scenario["filename"]
        or scenario["filename"] != scenario_path.name
    ):
        raise ScenarioProvenanceError("scenario-builder filename binding is malformed")
    if not _is_exact_int(scenario["line_count"], minimum=1):
        raise ScenarioProvenanceError("scenario-builder line count is malformed")
    try:
        scenario_text = scenario_content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ScenarioProvenanceError("executable scenario is not UTF-8") from exc
    lines = scenario_text.splitlines()
    if scenario["line_count"] != len(lines):
        raise ScenarioProvenanceError(
            "scenario-builder line count does not match executable scenario"
        )

    workload_level = payload.get("workload_level")
    if workload_level not in {"LOW", "MEDIUM", "HIGH"}:
        raise ScenarioProvenanceError("scenario-builder workload level is malformed")
    seed = payload.get("seed")
    if not _is_exact_int(seed) or seed > 9_223_372_036_854_775_807:
        raise ScenarioProvenanceError("scenario-builder seed is malformed")
    duration = payload.get("block_duration_sec")
    if not _is_exact_int(duration, minimum=1):
        raise ScenarioProvenanceError("scenario-builder block duration is malformed")
    block_num = payload.get("block_num")
    if block_num is not None and not _is_exact_int(block_num, minimum=1):
        raise ScenarioProvenanceError("scenario-builder block number is malformed")

    parameters = _require_exact_keys(
        payload.get("parameters"),
        required=_BUILDER_PARAMETER_KEYS,
        optional={"suite_profile_name"},
        label="scenario-builder parameters",
    )
    if parameters.get("suite_profile_name", workload_level) not in {"PRACTICE", "LOW", "MEDIUM", "HIGH"}:
        raise ScenarioProvenanceError("scenario-builder suite profile name is malformed")
    for key in ("difficulty", "track_target_proportion", "communications_own_callsign_ratio"):
        if not _is_finite_number(parameters[key], minimum=0) or float(parameters[key]) > 1:
            raise ScenarioProvenanceError(f"scenario-builder parameter {key} is malformed")
    for key in (
        "resman_loss_per_min",
        "isa_probe_interval_sec",
        "openmatb_alerttimeout_ms",
        "openmatb_nontarget_duration_ms",
        "openmatb_comm_max_response_delay_ms",
        "communications_response_availability_sec",
        "communications_minimum_onset_separation_sec",
    ):
        if not _is_exact_int(parameters[key], minimum=1):
            raise ScenarioProvenanceError(f"scenario-builder parameter {key} is malformed")
    if not _is_finite_number(parameters["communications_prompt_duration_sec"], minimum=0):
        raise ScenarioProvenanceError(
            "scenario-builder communications prompt duration is malformed"
        )
    if float(parameters["communications_prompt_duration_sec"]) <= 0:
        raise ScenarioProvenanceError(
            "scenario-builder communications prompt duration must be positive"
        )
    if not isinstance(parameters["communications_audio_profile_id"], str) or not parameters[
        "communications_audio_profile_id"
    ]:
        raise ScenarioProvenanceError("scenario-builder audio profile is malformed")
    if (
        not isinstance(parameters["communications_audio_inventory_sha256"], str)
        or _SHA256.fullmatch(parameters["communications_audio_inventory_sha256"]) is None
    ):
        raise ScenarioProvenanceError("scenario-builder audio inventory hash is malformed")
    for key in ("communications_voice_idiom", "communications_voice_gender"):
        if not isinstance(parameters[key], str) or not parameters[key].strip():
            raise ScenarioProvenanceError(f"scenario-builder parameter {key} is malformed")
    for key in ("openmatb_sysmon_lights", "openmatb_sysmon_scales"):
        items = parameters[key]
        if (
            not isinstance(items, list)
            or not items
            or any(not isinstance(item, str) or not item for item in items)
            or len(items) != len(set(items))
        ):
            raise ScenarioProvenanceError(f"scenario-builder parameter {key} is malformed")
    if parameters["communications_response_availability_sec"] != (
        math.ceil(float(parameters["communications_prompt_duration_sec"]))
        + parameters["openmatb_comm_max_response_delay_ms"] // 1000
    ):
        raise ScenarioProvenanceError(
            "scenario-builder communications response window is inconsistent"
        )
    if parameters["communications_minimum_onset_separation_sec"] != (
        parameters["communications_response_availability_sec"] + 1
    ):
        raise ScenarioProvenanceError(
            "scenario-builder communications separation is inconsistent"
        )

    questionnaires = _require_exact_keys(
        payload.get("questionnaires"),
        required=_BUILDER_QUESTIONNAIRE_KEYS,
        label="scenario-builder questionnaires",
    )
    isa_filename = _safe_questionnaire_filename(questionnaires["isa"], label="ISA")
    nasatlx_filename = _safe_questionnaire_filename(
        questionnaires["nasatlx"], label="NASA-TLX"
    )
    bedford_filename = _safe_questionnaire_filename(
        questionnaires["bedford"], label="Bedford"
    )
    for key in ("include_nasatlx", "include_bedford"):
        if type(questionnaires[key]) is not bool:
            raise ScenarioProvenanceError(
                f"scenario-builder questionnaire flag {key} is malformed"
            )

    expected = _require_exact_keys(
        payload.get("expected"),
        required=_BUILDER_EXPECTED_KEYS,
        label="scenario-builder expected observations",
    )
    count_keys = (
        "sysmon_light_events",
        "sysmon_scale_events",
        "sysmon_target_opportunities",
        "sysmon_nontarget_opportunities",
        "comm_events",
        "task_events_total",
        "sagat_freezes",
        "concurrent_event_overlap_pairs",
        "task_events_within_5s_of_probe",
    )
    if any(not _is_exact_int(expected[key]) for key in count_keys):
        raise ScenarioProvenanceError(
            "scenario-builder expected event counts are malformed"
        )
    if expected["expected_active_primary_tasks"] != 4:
        raise ScenarioProvenanceError(
            "scenario-builder active-primary-task count is malformed"
        )
    if expected["workload_label_status"] != payload.get("workload_label_status"):
        raise ScenarioProvenanceError(
            "scenario-builder workload-label evidence is inconsistent"
        )
    if expected["counterbalancing_method"] != (
        "complete_permutation_counterbalancing_3_conditions"
    ):
        raise ScenarioProvenanceError(
            "scenario-builder counterbalancing method is malformed"
        )
    if expected["overlap_definition"] != (
        "pairwise overlap of task response-availability intervals"
    ):
        raise ScenarioProvenanceError("scenario-builder overlap definition is malformed")

    isa_times = expected["isa_probe_times_sec"]
    if (
        not isinstance(isa_times, list)
        or any(
            not _is_exact_int(value, minimum=1) or value >= duration
            for value in isa_times
        )
        or isa_times != sorted(set(isa_times))
    ):
        raise ScenarioProvenanceError("scenario-builder ISA schedule is malformed")
    interval = parameters["isa_probe_interval_sec"]
    planned_isa_times = list(range(interval, duration, interval))
    if isa_times != planned_isa_times:
        raise ScenarioProvenanceError(
            "scenario-builder ISA schedule disagrees with its declared interval"
        )

    if expected["sysmon_target_opportunities"] != (
        expected["sysmon_light_events"] + expected["sysmon_scale_events"]
    ):
        raise ScenarioProvenanceError(
            "scenario-builder SYSMON target counts are inconsistent"
        )
    expected_total = (
        expected["sysmon_target_opportunities"]
        + expected["sysmon_nontarget_opportunities"]
        + expected["comm_events"]
    )
    if expected["task_events_total"] != expected_total:
        raise ScenarioProvenanceError(
            "scenario-builder total event count is inconsistent"
        )
    expected_rate = round(expected_total / (duration / 60), 3)
    if expected["event_rate_per_min"] != expected_rate:
        raise ScenarioProvenanceError("scenario-builder event rate is inconsistent")
    per_subtask = _require_exact_keys(
        expected["per_subtask_event_rate_per_min"],
        required={"sysmon", "communications"},
        label="scenario-builder per-subtask rates",
    )
    if per_subtask != {
        "sysmon": round(
            (
                expected["sysmon_target_opportunities"]
                + expected["sysmon_nontarget_opportunities"]
            )
            / (duration / 60),
            3,
        ),
        "communications": round(expected["comm_events"] / (duration / 60), 3),
    }:
        raise ScenarioProvenanceError(
            "scenario-builder per-subtask event rates are inconsistent"
        )

    executable: list[list[str]] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split(";")
        if len(fields) < 3:
            raise ScenarioProvenanceError("scenario contains a malformed executable line")
        _scenario_seconds(fields[0])
        executable.append(fields)
    light_events = sum(
        fields[1] == "sysmon" and fields[2].startswith("lights-")
        and fields[2].endswith("-failure")
        for fields in executable
    )
    scale_events = sum(
        fields[1] == "sysmon" and fields[2].startswith("scales-")
        and fields[2].endswith("-failure")
        for fields in executable
    )
    nontarget_events = sum(
        fields[1:3] == ["sysmon", "open_nontarget_opportunity"]
        for fields in executable
    )
    comm_events = sum(
        fields[1:3] == ["communications", "radioprompt"]
        for fields in executable
    )
    observed_counts = (light_events, scale_events, nontarget_events, comm_events)
    declared_counts = (
        expected["sysmon_light_events"],
        expected["sysmon_scale_events"],
        expected["sysmon_nontarget_opportunities"],
        expected["comm_events"],
    )
    if observed_counts != declared_counts:
        raise ScenarioProvenanceError(
            "scenario-builder declared event counts do not match executable scenario"
        )

    isa_onsets = [
        _scenario_seconds(fields[0])
        for fields in executable
        if len(fields) == 4
        and fields[1:3] == ["genericscales", "filename"]
        and fields[3] == isa_filename
    ]
    if isa_onsets != isa_times:
        raise ScenarioProvenanceError(
            "scenario-builder ISA schedule does not match executable scenario"
        )
    sagat_starts = sum(fields[1:3] == ["sagat", "start"] for fields in executable)
    if sagat_starts != expected["sagat_freezes"]:
        raise ScenarioProvenanceError(
            "scenario-builder SAGAT count does not match executable scenario"
        )
    for filename, flag in (
        (nasatlx_filename, questionnaires["include_nasatlx"]),
        (bedford_filename, questionnaires["include_bedford"]),
    ):
        observed = sum(
            len(fields) == 4
            and fields[1:3] == ["genericscales", "filename"]
            and fields[3] == filename
            and _scenario_seconds(fields[0]) == duration
            for fields in executable
        )
        if observed != int(flag):
            raise ScenarioProvenanceError(
                "scenario-builder questionnaire plan does not match executable scenario"
            )

    sagat = payload.get("sagat")
    if sagat is not None:
        sagat = _require_exact_keys(
            sagat,
            required={"manifest_filename", "sha256"},
            label="scenario-builder SAGAT binding",
        )
        if (
            not isinstance(sagat["manifest_filename"], str)
            or Path(sagat["manifest_filename"]).name != sagat["manifest_filename"]
            or not isinstance(sagat["sha256"], str)
            or _SHA256.fullmatch(sagat["sha256"]) is None
        ):
            raise ScenarioProvenanceError("scenario-builder SAGAT binding is malformed")
    elif expected["sagat_freezes"]:
        raise ScenarioProvenanceError(
            "scenario-builder SAGAT freezes lack a bound probe manifest"
        )

    # For the canonical non-SAGAT family, independently rerun the pinned
    # generator and require byte-for-byte identity. This reconciles every
    # parameter value, indicator assignment, COMM target class, lifecycle
    # command, header, and randomized onset—not merely aggregate counts.
    if expected["sagat_freezes"] == 0:
        try:
            from aircraft_monitor.research.protocol import WorkloadLevel
            from matb_integration.scenario_builder import build_block_scenario
        except (ImportError, ModuleNotFoundError) as exc:
            raise ScenarioProvenanceError(
                "scenario-builder artifact cannot be verified without its canonical generator"
            ) from exc
        try:
            regenerated = build_block_scenario(
                level=WorkloadLevel[workload_level],
                block_duration_sec=duration,
                seed=seed,
                isa_questionnaire=isa_filename,
                nasatlx_questionnaire=nasatlx_filename,
                bedford_questionnaire=bedford_filename,
                include_nasatlx=questionnaires["include_nasatlx"],
                include_bedford=questionnaires["include_bedford"],
                include_sagat=False,
                workload_settings={
                    "difficulty": parameters["difficulty"],
                    "track_target_proportion": parameters["track_target_proportion"],
                    "resman_loss_per_min": parameters["resman_loss_per_min"],
                    "isa_probe_interval_sec": parameters["isa_probe_interval_sec"],
                },
            )
        except Exception as exc:
            raise ScenarioProvenanceError(
                f"scenario-builder artifact cannot be regenerated: {exc}"
            ) from exc
        if regenerated.encode("utf-8") != scenario_content:
            raise ScenarioProvenanceError(
                "executable scenario does not match deterministic builder regeneration"
            )


def _source_status(source_commit: Any, source_dirty: Any) -> tuple[str, bool | None, str]:
    if not isinstance(source_commit, str) or not source_commit:
        raise ScenarioProvenanceError("manifest source_commit is missing")
    if source_dirty is not None and not isinstance(source_dirty, bool):
        raise ScenarioProvenanceError("manifest source_dirty must be boolean or null")
    if source_commit in {"unknown", "unavailable"}:
        if source_dirty is not None:
            raise ScenarioProvenanceError("missing manifest source cannot be clean or dirty")
        return source_commit, None, "provisional_missing_source_commit"
    if _GIT_OID.fullmatch(source_commit) is None:
        raise ScenarioProvenanceError("manifest source_commit is not a full lowercase Git object id")
    if source_dirty is None:
        status = "provisional_unverified_source_tree"
    elif source_dirty:
        status = "provisional_dirty_source_tree"
    else:
        status = "complete"
    return source_commit, source_dirty, status


def _builder_identity(
    payload: dict[str, Any],
    *,
    scenario_content: bytes,
    scenario_path: Path,
) -> tuple[dict[str, Any], str]:
    if payload.get("manifest_version") != 3:
        raise ScenarioProvenanceError("unsupported scenario-builder manifest version")
    if payload.get("metrics_schema_version") != "2.0":
        raise ScenarioProvenanceError("unsupported scenario-builder metrics schema")
    generated_by = payload.get("generated_by")
    required = {
        "component", "version", "source_commit", "source_dirty", "provenance_status"
    }
    if not isinstance(generated_by, dict) or set(generated_by) != required:
        raise ScenarioProvenanceError("scenario-builder provenance fields are malformed")
    if generated_by.get("component") != _BUILDER_COMPONENT:
        raise ScenarioProvenanceError("unsupported scenario-builder component")
    if generated_by.get("version") != _BUILDER_VERSION:
        raise ScenarioProvenanceError("unsupported scenario-builder version")
    commit, dirty, source_status = _source_status(
        generated_by.get("source_commit"), generated_by.get("source_dirty")
    )
    if generated_by.get("provenance_status") != source_status:
        raise ScenarioProvenanceError("scenario-builder provenance status is inconsistent")
    if payload.get("workload_label_status") != "engineering_preset_pending_human_calibration":
        raise ScenarioProvenanceError("unsupported workload-label claim in scenario manifest")
    _validate_builder_payload(
        payload,
        scenario_content=scenario_content,
        scenario_path=scenario_path,
    )
    scope = payload.get("artifact_scope")
    if scope not in {"session_bound", "exploratory_template"}:
        raise ScenarioProvenanceError("scenario manifest artifact scope is malformed")
    if scope == "session_bound":
        visit = payload.get("visit_ordinal")
        if (
            not isinstance(payload.get("participant_id"), str)
            or not payload.get("participant_id")
            or isinstance(visit, bool)
            or not isinstance(visit, int)
            or visit < 1
        ):
            raise ScenarioProvenanceError("session-bound manifest lacks participant/visit identity")
    elif payload.get("participant_id") is not None or payload.get("visit_ordinal") is not None:
        raise ScenarioProvenanceError("exploratory manifest cannot claim session bindings")
    identity = _common_identity(
        payload,
        compiler_id=_BUILDER_COMPONENT,
        compiler_version=_BUILDER_VERSION,
        source_commit=commit,
        source_dirty=dirty,
        source_status=source_status,
    )
    if source_status != "complete":
        return identity, "verified_provisional_manifest_source"
    if scope != "session_bound":
        return identity, "verified_provisional_exploratory_template"
    if payload["expected"]["sagat_freezes"] > 0:
        # The adjacent scenario manifest binds only the SAGAT probe-manifest
        # filename and digest.  Until the referenced probe and freeze artifacts
        # are themselves resolved, hashed, and semantically reconciled by the
        # runtime, this session cannot truthfully claim full verification.
        return identity, "verified_provisional_sagat_artifacts_unverified"
    return identity, "verified"


def _compiled_identity(
    payload: dict[str, Any],
    *,
    scenario_content: bytes,
) -> tuple[dict[str, Any], str]:
    if payload.get("schema_version") != "1.0":
        raise ScenarioProvenanceError("unsupported compiled-experiment manifest schema")
    compiler = payload.get("compiler")
    if not isinstance(compiler, dict):
        raise ScenarioProvenanceError("compiled manifest lacks compiler identity")
    if compiler.get("component_id") != _COMPILED_COMPONENT:
        raise ScenarioProvenanceError("unsupported compiled-experiment component")
    if compiler.get("version") != _COMPILED_VERSION:
        raise ScenarioProvenanceError("unsupported compiled-experiment version")
    if compiler.get("lossy_rounding_permitted") is not False:
        raise ScenarioProvenanceError("compiled manifest permits lossy timing")
    commit, dirty, source_status = _source_status(
        payload.get("source_commit"), payload.get("source_dirty")
    )
    if payload.get("provenance_status") != source_status:
        raise ScenarioProvenanceError("compiled manifest provenance status is inconsistent")
    spec = payload.get("spec")
    if not isinstance(spec, dict) or not isinstance(spec.get("canonical_record"), dict):
        raise ScenarioProvenanceError("compiled manifest lacks the canonical experiment spec")
    canonical_record = spec["canonical_record"]
    try:
        from matb_integration.contracts import ExperimentSpecV1
        from matb_integration.experiment_compiler import (
            ExperimentCompileError,
            compile_experiment_spec,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        raise ScenarioProvenanceError(
            "compiled experiment cannot be verified without the canonical compiler"
        ) from exc
    try:
        canonical_spec = ExperimentSpecV1.from_record(canonical_record)
    except Exception as exc:
        raise ScenarioProvenanceError(
            f"canonical experiment spec is invalid: {exc}"
        ) from exc
    if canonical_spec.to_record() != canonical_record:
        raise ScenarioProvenanceError(
            "canonical experiment spec record is not in normalized canonical form"
        )
    try:
        canonical_bytes = canonical_spec.canonical_json().encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ScenarioProvenanceError(
            "canonical experiment spec contains a non-finite JSON value"
        ) from exc
    if sha256(canonical_bytes).hexdigest() != spec.get("sha256"):
        raise ScenarioProvenanceError("canonical experiment spec hash does not verify")
    for key in (
        "schema_version", "experiment_id", "revision", "profile_id", "seed", "duration_ns"
    ):
        if canonical_record.get(key) != spec.get(key):
            raise ScenarioProvenanceError(
                f"compiled manifest spec summary disagrees with canonical record: {key}"
            )
    try:
        rebuilt = compile_experiment_spec(
            canonical_spec,
            source_commit=commit,
            source_dirty=dirty,
        )
    except ExperimentCompileError as exc:
        raise ScenarioProvenanceError(
            f"canonical experiment spec cannot be losslessly recompiled: {exc}"
        ) from exc
    if rebuilt.scenario_text.encode("utf-8") != scenario_content:
        raise ScenarioProvenanceError(
            "compiled scenario bytes do not match deterministic recompilation"
        )
    if rebuilt.manifest != payload:
        raise ScenarioProvenanceError(
            "compiled manifest does not match deterministic recompilation"
        )
    identity = _common_identity(
        payload,
        compiler_id=_COMPILED_COMPONENT,
        compiler_version=_COMPILED_VERSION,
        source_commit=commit,
        source_dirty=dirty,
        source_status=source_status,
    )
    return (
        identity,
        "verified" if source_status == "complete" else "verified_provisional_manifest_source",
    )


def _common_identity(
    payload: dict[str, Any],
    *,
    compiler_id: str,
    compiler_version: str,
    source_commit: str,
    source_dirty: bool | None,
    source_status: str,
) -> dict[str, Any]:

    spec = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
    seed = spec.get("seed", payload.get("seed"))
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ScenarioProvenanceError(
            "scenario manifest seed must be an exact non-negative integer"
        )
    spec_sha256 = spec.get("sha256")
    if spec_sha256 is not None and (
        not isinstance(spec_sha256, str) or _SHA256.fullmatch(spec_sha256) is None
    ):
        raise ScenarioProvenanceError("scenario manifest spec SHA-256 is malformed")
    if not isinstance(compiler_id, str) or not compiler_id.strip():
        raise ScenarioProvenanceError("scenario manifest compiler component is missing")
    if not isinstance(compiler_version, str) or not compiler_version.strip():
        raise ScenarioProvenanceError("scenario manifest compiler version is missing")
    manifest_schema = payload.get("manifest_version", payload.get("schema_version"))
    return {
        "manifest_schema_version": str(manifest_schema),
        "metrics_schema_version": payload.get("metrics_schema_version"),
        "experiment_spec_sha256": spec_sha256,
        "experiment_seed": seed,
        "scenario_compiler_id": compiler_id,
        "scenario_compiler_version": compiler_version,
        "manifest_source_commit": source_commit,
        "manifest_source_dirty": source_dirty,
        "manifest_provenance_status": source_status,
    }


def _identity(
    payload: dict[str, Any],
    *,
    scenario_content: bytes,
    scenario_path: Path,
) -> tuple[dict[str, Any], str]:
    if "manifest_version" in payload:
        return _builder_identity(
            payload,
            scenario_content=scenario_content,
            scenario_path=scenario_path,
        )
    if "schema_version" in payload:
        return _compiled_identity(payload, scenario_content=scenario_content)
    raise ScenarioProvenanceError("unknown adjacent scenario manifest type")


def load_adjacent_scenario_manifest(
    scenario_path: Path | None,
    *,
    scenario_sha256: str,
) -> BoundScenarioManifest:
    """Load one manifest snapshot and verify it binds the executable bytes."""
    if _SHA256.fullmatch(scenario_sha256) is None:
        raise ScenarioProvenanceError("runtime scenario SHA-256 is malformed")
    if scenario_path is None:
        return BoundScenarioManifest(
            evidence={
                "schema_version": SCENARIO_PROVENANCE_SCHEMA_VERSION,
                "status": "provisional_programmatic_scenario_no_manifest",
                "scenario_sha256": scenario_sha256,
                "adjacent_manifest_filename": None,
                "scenario_manifest_sha256": None,
                "manifest_identity": None,
            },
            content=None,
        )

    manifest_path = scenario_path.with_suffix(scenario_path.suffix + ".manifest.json")
    if not manifest_path.is_file():
        return BoundScenarioManifest(
            evidence={
                "schema_version": SCENARIO_PROVENANCE_SCHEMA_VERSION,
                "status": "provisional_missing_scenario_manifest",
                "scenario_sha256": scenario_sha256,
                "adjacent_manifest_filename": manifest_path.name,
                "scenario_manifest_sha256": None,
                "manifest_identity": None,
            },
            content=None,
        )

    content = manifest_path.read_bytes()
    if len(content) > MAX_SCENARIO_MANIFEST_BYTES:
        raise ScenarioProvenanceError(
            f"scenario manifest exceeds {MAX_SCENARIO_MANIFEST_BYTES} bytes"
        )
    def reject_nonfinite_json(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value}")

    try:
        payload = json.loads(
            content.decode("utf-8"),
            parse_constant=reject_nonfinite_json,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ScenarioProvenanceError("scenario manifest is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ScenarioProvenanceError("scenario manifest root must be an object")
    scenario = payload.get("scenario")
    if not isinstance(scenario, dict):
        raise ScenarioProvenanceError("scenario manifest lacks a scenario object")
    bound_digest = scenario.get("sha256")
    if bound_digest != scenario_sha256:
        raise ScenarioProvenanceError(
            "scenario manifest SHA-256 does not match executable scenario bytes"
        )
    bound_filename = scenario.get("filename")
    if bound_filename is not None and bound_filename != scenario_path.name:
        raise ScenarioProvenanceError(
            "scenario manifest filename does not match executable scenario"
        )
    try:
        scenario_content = scenario_path.read_bytes()
    except OSError as exc:
        raise ScenarioProvenanceError("executable scenario cannot be read") from exc
    if sha256(scenario_content).hexdigest() != scenario_sha256:
        raise ScenarioProvenanceError(
            "runtime scenario SHA-256 does not match executable scenario bytes"
        )
    identity, verification_status = _identity(
        payload,
        scenario_content=scenario_content,
        scenario_path=scenario_path,
    )
    evidence = {
        "schema_version": SCENARIO_PROVENANCE_SCHEMA_VERSION,
        "status": verification_status,
        "scenario_sha256": scenario_sha256,
        "adjacent_manifest_filename": manifest_path.name,
        "scenario_manifest_sha256": sha256(content).hexdigest(),
        "manifest_identity": identity,
    }
    return BoundScenarioManifest(evidence=evidence, content=content)
