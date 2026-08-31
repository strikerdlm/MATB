"""Fail-closed compiler from canonical experiments to OpenMATB scenarios."""

from __future__ import annotations

import hashlib
import heapq
import json
import re
from dataclasses import dataclass
from typing import Any

from matb_integration.contracts import ExperimentSpecV1, TimelineEventV1
from matb_integration.communications_profile import (
    COMM_AUDIO_INVENTORY_SHA256,
    COMM_AUDIO_PROFILE_ID,
    COMM_MAX_RESPONSE_DELAY_MS,
    COMM_MIN_ONSET_SEPARATION_SEC,
    COMM_PROMPT_UPPER_BOUND_SEC,
    COMM_RESPONSE_AVAILABILITY_SEC,
    COMM_VOICE_GENDER,
    COMM_VOICE_IDIOM,
    CommunicationsProfileError,
    verify_communications_audio_profile,
)


COMPILER_VERSION = "1.0.0"
_SECOND_NS = 1_000_000_000
_MILLISECOND_NS = 1_000_000
_COMM_RESPONSE_AVAILABILITY_NS = COMM_RESPONSE_AVAILABILITY_SEC * _SECOND_NS
_COMM_MIN_ONSET_SEPARATION_NS = COMM_MIN_ONSET_SEPARATION_SEC * _SECOND_NS
_MISSING_SOURCE_COMMITS = {"unavailable", "unknown"}
_FULL_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_RUNTIME_TASKS = frozenset({"sysmon", "communications", "track", "resman"})
_LIFECYCLE_COMMANDS = frozenset({"start", "stop"})
_SYSMON_FAILURE_COMMANDS = frozenset(
    {
        "lights-1-failure",
        "lights-2-failure",
        "scales-1-failure",
        "scales-2-failure",
        "scales-3-failure",
        "scales-4-failure",
    }
)
_SUPPORTED_COMMANDS = {
    "sysmon": _LIFECYCLE_COMMANDS
    | _SYSMON_FAILURE_COMMANDS
    | {"open_nontarget_opportunity"},
    "communications": _LIFECYCLE_COMMANDS | {"radioprompt"},
    "track": _LIFECYCLE_COMMANDS,
    "resman": _LIFECYCLE_COMMANDS,
}


class ExperimentCompileError(ValueError):
    """The experiment cannot be represented without ambiguity or precision loss."""


def _classify_source_commit(source_commit: str) -> tuple[str, str]:
    if not isinstance(source_commit, str):
        raise ExperimentCompileError("source_commit must be a string")
    normalized = source_commit.strip()
    if not normalized:
        raise ExperimentCompileError("source_commit must not be empty")
    lowered = normalized.lower()
    if lowered in _MISSING_SOURCE_COMMITS:
        return lowered, "provisional_missing_source_commit"
    if normalized == source_commit and _FULL_GIT_OID.fullmatch(source_commit) is not None:
        return source_commit, "complete"
    raise ExperimentCompileError(
        "source_commit must be a full lowercase Git object ID or "
        "the unknown/unavailable sentinel"
    )


@dataclass(frozen=True, slots=True)
class CompiledExperiment:
    scenario_text: str
    manifest: dict[str, Any]


def _scenario_time(at_ns: int) -> str:
    if at_ns % _SECOND_NS:
        raise ExperimentCompileError(
            "OpenMATB compilation requires whole-second event onsets; refusing silent rounding"
        )
    total = at_ns // _SECOND_NS
    return f"{total // 3600}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def _safe_token(value: object, *, field_name: str) -> str:
    if isinstance(value, bool):
        rendered = "True" if value else "False"
    elif value is None:
        raise ExperimentCompileError(f"{field_name} cannot be null")
    elif isinstance(value, (dict, list)):
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    else:
        rendered = str(value)
    if not rendered or any(character in rendered for character in (";", "\n", "\r")):
        raise ExperimentCompileError(f"{field_name} contains an OpenMATB delimiter or newline")
    return rendered


def _duration_parameter_line(
    event: TimelineEventV1,
    *,
    task: str,
    command: str,
) -> str | None:
    """Encode a canonical duration only where OpenMATB has exact semantics."""
    duration_ns = event.duration_ns
    duration_sensitive = (
        (task == "sysmon" and command == "open_nontarget_opportunity")
        or (task == "sysmon" and command in _SYSMON_FAILURE_COMMANDS)
    )
    if duration_ns is None:
        if duration_sensitive:
            raise ExperimentCompileError(
                f"event {event.event_key} requires an explicit duration for lossless compilation"
            )
        return None
    if duration_ns % _MILLISECOND_NS:
        raise ExperimentCompileError(
            f"event {event.event_key} duration requires whole milliseconds; refusing silent rounding"
        )
    duration_parameter: str | None = None
    if task == "sysmon" and command == "open_nontarget_opportunity":
        duration_parameter = "nontargetduration"
    elif task == "sysmon" and command in _SYSMON_FAILURE_COMMANDS:
        duration_parameter = "alerttimeout"
    if duration_parameter is None:
        raise ExperimentCompileError(
            f"event {event.event_key} cannot represent duration in OpenMATB"
        )
    duration_ms = duration_ns // _MILLISECOND_NS
    return ";".join(
        (_scenario_time(event.at_ns), task, duration_parameter, str(duration_ms))
    )


def _validate_event_semantics(event: TimelineEventV1) -> tuple[str, str]:
    # Onset precision is checked first so no malformed event can obscure a
    # silent time-rounding hazard.
    _scenario_time(event.at_ns)
    if event.component_id != "matb-runtime" or event.event_type != "openmatb.command":
        raise ExperimentCompileError(
            f"event {event.event_key} is not a supported matb-runtime openmatb.command"
        )
    if event.task is None:
        raise ExperimentCompileError(f"event {event.event_key} requires a runtime task")
    task = _safe_token(event.task, field_name=f"event {event.event_key} task")
    command = _safe_token(
        event.parameters.get("command"),
        field_name=f"event {event.event_key} command",
    )
    unexpected = set(event.parameters) - {"command", "value"}
    if unexpected:
        raise ExperimentCompileError(
            f"event {event.event_key} has unsupported parameters: {', '.join(sorted(unexpected))}"
        )
    if task not in _RUNTIME_TASKS:
        raise ExperimentCompileError(f"event {event.event_key} uses unsupported task {task}")
    if command not in _SUPPORTED_COMMANDS[task]:
        raise ExperimentCompileError(
            f"event {event.event_key} uses unsupported command {command} for task {task}"
        )

    has_value = "value" in event.parameters
    value = event.parameters.get("value")
    if command in _LIFECYCLE_COMMANDS or command == "open_nontarget_opportunity":
        if has_value:
            raise ExperimentCompileError(
                f"event {event.event_key} command {command} must not include a value"
            )
    elif command in _SYSMON_FAILURE_COMMANDS:
        if not has_value or value is not True:
            raise ExperimentCompileError(
                f"event {event.event_key} failure value must be literal True"
            )
    elif command == "radioprompt":
        if not has_value or not isinstance(value, str) or value not in {"own", "other"}:
            raise ExperimentCompileError(
                f"event {event.event_key} radioprompt value must be 'own' or 'other'"
            )

    # This also proves required/forbidden duration semantics without emitting.
    _duration_parameter_line(event, task=task, command=command)
    return task, command


def _compile_lines(event: TimelineEventV1) -> tuple[str, ...]:
    task, command = _validate_event_semantics(event)
    fields = [_scenario_time(event.at_ns), task, command]
    if "value" in event.parameters:
        fields.append(
            _safe_token(
                event.parameters["value"],
                field_name=f"event {event.event_key} value",
            )
        )
    command_line = ";".join(fields)
    duration_line = _duration_parameter_line(
        event,
        task=task,
        command=command,
    )
    return (command_line,) if duration_line is None else (duration_line, command_line)


def _validate_task_lifecycles(spec: ExperimentSpecV1) -> None:
    active: dict[str, bool] = {task: False for task in _RUNTIME_TASKS}
    # OpenMATB updates plugins before dispatching the frame's due events. A stop
    # at the same timestamp as a transient command prevents that command from
    # ever being rendered/processed; a stop at a timed event's deadline can
    # likewise deactivate the plugin before it closes the evidence window.
    required_command_end_ns: dict[str, int | None] = {
        task: None for task in _RUNTIME_TASKS
    }
    for event in spec.timeline:
        assert event.task is not None
        task = event.task
        command = str(event.parameters["command"])
        if command == "start":
            if active[task]:
                raise ExperimentCompileError(
                    f"event {event.event_key} starts already-active task {task}"
                )
            active[task] = True
            required_command_end_ns[task] = None
        elif command == "stop":
            if not active[task]:
                raise ExperimentCompileError(
                    f"event {event.event_key} stops task {task} before an active start"
                )
            required_end_ns = required_command_end_ns[task]
            if required_end_ns is not None and event.at_ns <= required_end_ns:
                raise ExperimentCompileError(
                    f"event {event.event_key} stops task {task} before prior command "
                    f"evidence can close after {required_end_ns} ns"
                )
            active[task] = False
            required_command_end_ns[task] = None
        elif not active[task]:
            raise ExperimentCompileError(
                f"event {event.event_key} executes task {task} before an active start"
            )
        else:
            command_end_ns = event.at_ns + (event.duration_ns or 0)
            if task == "communications" and command == "radioprompt":
                command_end_ns = event.at_ns + _COMM_RESPONSE_AVAILABILITY_NS
            previous_end_ns = required_command_end_ns[task]
            required_command_end_ns[task] = (
                command_end_ns
                if previous_end_ns is None
                else max(previous_end_ns, command_end_ns)
            )

    unterminated = sorted(task for task, is_active in active.items() if is_active)
    if unterminated:
        raise ExperimentCompileError(
            "task lifecycle ended without a matching stop: " + ", ".join(unterminated)
        )


def _validate_timed_event_intervals(spec: ExperimentSpecV1) -> None:
    """Reject same-task overlaps whose task-global timeout state is ambiguous."""
    by_task: dict[str, list[TimelineEventV1]] = {}
    for event in spec.timeline:
        if event.duration_ns is not None and event.task is not None:
            by_task.setdefault(event.task, []).append(event)
    for task, events in sorted(by_task.items()):
        ordered = sorted(events, key=lambda item: (item.at_ns, item.event_key))
        for first, second in zip(ordered, ordered[1:]):
            assert first.duration_ns is not None
            if second.at_ns < first.at_ns + first.duration_ns:
                raise ExperimentCompileError(
                    "overlapping timed events are not losslessly representable for "
                    f"task {task}: {first.event_key}, {second.event_key}"
                )


def _validate_transient_collisions(spec: ExperimentSpecV1) -> None:
    """Reject simultaneous stimuli whose physical presentation must be serial."""
    communications_prompts: dict[int, list[str]] = {}
    for event in spec.timeline:
        if (
            event.task == "communications"
            and event.parameters.get("command") == "radioprompt"
        ):
            communications_prompts.setdefault(event.at_ns, []).append(event.event_key)
    for at_ns, keys in sorted(communications_prompts.items()):
        if len(keys) > 1:
            raise ExperimentCompileError(
                "simultaneous communications radioprompt events are not losslessly "
                f"presentable at {at_ns} ns: {', '.join(sorted(keys))}"
            )
    ordered_prompts = sorted(
        (
            event.at_ns,
            event.event_key,
        )
        for event in spec.timeline
        if event.task == "communications"
        and event.parameters.get("command") == "radioprompt"
    )
    for first, second in zip(ordered_prompts, ordered_prompts[1:]):
        if second[0] - first[0] < _COMM_MIN_ONSET_SEPARATION_NS:
            raise ExperimentCompileError(
                f"communications prompts require at least {COMM_MIN_ONSET_SEPARATION_SEC} "
                "seconds between onsets "
                f"({COMM_PROMPT_UPPER_BOUND_SEC}-second verified presentation ceiling + "
                f"{COMM_MAX_RESPONSE_DELAY_MS // 1000}-second response window + 1-second "
                f"refractory guard): {first[1]}, {second[1]}"
            )


def _summary(spec: ExperimentSpecV1) -> dict[str, Any]:
    duration_min = spec.duration_ns / 60_000_000_000
    source_counts: dict[str, int] = {}
    stimulus_counts: dict[str, int] = {}
    stimulus_task_onsets: dict[str, list[int]] = {}
    intervals: list[tuple[int, int]] = []
    targets = 0
    nontargets = 0
    for event in spec.timeline:
        task = event.task or "unassigned"
        source_counts[task] = source_counts.get(task, 0) + 1
        command = event.parameters.get("command")
        is_stimulus_or_opportunity = command not in _LIFECYCLE_COMMANDS
        if is_stimulus_or_opportunity:
            stimulus_counts[task] = stimulus_counts.get(task, 0) + 1
            stimulus_task_onsets.setdefault(task, []).append(event.at_ns)
        interval_end_ns: int | None = None
        if event.duration_ns is not None:
            interval_end_ns = event.at_ns + event.duration_ns
        elif event.task == "communications" and command == "radioprompt":
            # A COMM prompt has an evidence-bearing response-availability
            # interval even though the source event has no explicit duration.
            # Summary overlap must reflect the same 44-second contract enforced
            # by lifecycle validation and the runtime.
            interval_end_ns = event.at_ns + _COMM_RESPONSE_AVAILABILITY_NS
        if interval_end_ns is not None and interval_end_ns > event.at_ns:
            intervals.append((event.at_ns, interval_end_ns))
        if event.task == "sysmon" and isinstance(command, str):
            if command in _SYSMON_FAILURE_COMMANDS:
                targets += 1
            elif command == "open_nontarget_opportunity":
                nontargets += 1

    # Sweep by onset while a min-heap tracks intervals whose end remains in the
    # future. Every active interval overlaps the newly encountered interval.
    # This is O(n log n), rather than materializing all O(n²) pairs.
    overlap_count = 0
    active_ends: list[int] = []
    for start, end in sorted(intervals):
        while active_ends and active_ends[0] <= start:
            heapq.heappop(active_ends)
        overlap_count += len(active_ends)
        heapq.heappush(active_ends, end)
    possible_pairs = len(intervals) * (len(intervals) - 1) // 2

    refractory: dict[str, float | None] = {}
    for task, onsets in sorted(stimulus_task_onsets.items()):
        ordered = sorted(onsets)
        refractory[task] = (
            min(second - first for first, second in zip(ordered, ordered[1:])) / 1_000_000
            if len(ordered) > 1
            else None
        )
    return {
        "source_command_count": len(spec.timeline),
        "source_command_rate_per_min": round(len(spec.timeline) / duration_min, 6),
        "per_task_source_command_rate_per_min": {
            task: round(count / duration_min, 6)
            for task, count in sorted(source_counts.items())
        },
        "stimulus_opportunity_count": sum(stimulus_counts.values()),
        "stimulus_opportunity_rate_per_min": round(
            sum(stimulus_counts.values()) / duration_min,
            6,
        ),
        "per_task_stimulus_opportunity_rate_per_min": {
            task: round(count / duration_min, 6)
            for task, count in sorted(stimulus_counts.items())
        },
        "pairwise_overlap_count": overlap_count,
        "pairwise_overlap_percent": (
            round(overlap_count / possible_pairs * 100.0, 6) if possible_pairs else 0.0
        ),
        "minimum_stimulus_refractory_ms_by_task": refractory,
        "sysmon_target_opportunities": targets,
        "sysmon_nontarget_opportunities": nontargets,
    }


def compile_experiment_spec(
    spec: ExperimentSpecV1,
    *,
    source_commit: str,
    source_dirty: bool | None = None,
) -> CompiledExperiment:
    """Compile one immutable specification without lossy time conversion."""
    if source_dirty is not None and type(source_dirty) is not bool:
        raise ExperimentCompileError("source_dirty must be boolean or null")
    normalized_source_commit, provenance_status = _classify_source_commit(source_commit)
    if provenance_status == "provisional_missing_source_commit":
        # An unknown source object cannot truthfully carry a clean-tree
        # attestation. Preserve that uncertainty instead of emitting
        # contradictory provenance.
        source_dirty = None
    uses_communications = any(event.task == "communications" for event in spec.timeline)
    communications_profile: dict[str, Any] | None = None
    if uses_communications:
        try:
            communications_profile = verify_communications_audio_profile()
        except CommunicationsProfileError as exc:
            raise ExperimentCompileError(str(exc)) from exc
    if provenance_status == "complete":
        if source_dirty is True:
            provenance_status = "provisional_dirty_source_tree"
        elif source_dirty is not False:
            provenance_status = "provisional_unverified_source_tree"
    if spec.components != ("matb-runtime",):
        raise ExperimentCompileError(
            "OpenMATB compiler supports exactly the matb-runtime component; "
            f"declared components were {list(spec.components)!r}"
        )
    for event in spec.timeline:
        _validate_event_semantics(event)
    _validate_timed_event_intervals(spec)
    _validate_transient_collisions(spec)
    _validate_task_lifecycles(spec)
    lines = [
        f"# MATB ExperimentSpecV1 {spec.experiment_id} revision {spec.revision}",
        f"# Spec SHA-256: {spec.sha256()}",
        f"# Compiler: matb_integration.experiment_compiler {COMPILER_VERSION}",
        f"# Seed: {spec.seed} | Profile: {spec.profile_id}",
        "",
    ]
    compiler_injected_line_count = 1  # exact-duration system boundary
    if uses_communications:
        lines.extend(
            [
                f"0:00:00;communications;voiceidiom;{COMM_VOICE_IDIOM}",
                f"0:00:00;communications;voicegender;{COMM_VOICE_GENDER}",
                f"0:00:00;communications;maxresponsedelay;{COMM_MAX_RESPONSE_DELAY_MS}",
            ]
        )
        compiler_injected_line_count += 3
    event_map: list[dict[str, Any]] = []
    for event in spec.timeline:
        rendered_lines = _compile_lines(event)
        first_line_number = len(lines)
        lines.extend(rendered_lines)
        command_line_number = len(lines) - 1
        event_map.append(
            {
                "event_key": event.event_key,
                "scenario_line": command_line_number,
                "supporting_scenario_lines": list(
                    range(first_line_number, command_line_number)
                ),
                "at_ns": event.at_ns,
                "duration_ns": event.duration_ns,
            }
        )
    lines.append(f"{_scenario_time(spec.duration_ns)};system;boundary")
    scenario_text = "\n".join(lines) + "\n"
    scenario_sha256 = hashlib.sha256(scenario_text.encode("utf-8")).hexdigest()
    manifest = {
        "schema_version": "1.0",
        "compiler": {
            "component_id": "matb-research",
            "version": COMPILER_VERSION,
            "time_resolution_ns": _SECOND_NS,
            "duration_resolution_ns": _MILLISECOND_NS,
            "lossy_rounding_permitted": False,
        },
        "source_commit": normalized_source_commit,
        "source_dirty": source_dirty,
        "source_commit_format": "full-lowercase-git-object-id-sha1-or-sha256",
        "provenance_status": provenance_status,
        "communications_timing_profile": (
            {
                **communications_profile,
                "asset_inventory_sha256": COMM_AUDIO_INVENTORY_SHA256,
                "profile_id": COMM_AUDIO_PROFILE_ID,
                "minimum_onset_separation_sec": COMM_MIN_ONSET_SEPARATION_SEC,
                "response_availability_sec": COMM_RESPONSE_AVAILABILITY_SEC,
            }
            if communications_profile is not None
            else None
        ),
        "spec": {
            "schema_version": spec.schema_version,
            "experiment_id": spec.experiment_id,
            "revision": spec.revision,
            "sha256": spec.sha256(),
            "profile_id": spec.profile_id,
            "seed": spec.seed,
            "duration_ns": spec.duration_ns,
            "canonical_record": spec.to_record(),
        },
        "scenario": {
            "format": "openmatb-text",
            "line_number_base": 0,
            "sha256": scenario_sha256,
            "event_line_count": sum(
                1 for line in lines if line and not line.startswith("#")
            ),
            "source_event_count": len(spec.timeline),
            "compiler_injected_line_count": compiler_injected_line_count,
        },
        "event_map": event_map,
        "summary": _summary(spec),
        "claim_boundary": (
            "Compiler validation establishes deterministic software representation only; "
            "it does not establish workload calibration, human validity, or physical timing."
        ),
    }
    return CompiledExperiment(scenario_text=scenario_text, manifest=manifest)
