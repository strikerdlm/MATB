from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import shutil

import pytest

from matb_integration.contracts import ExperimentSpecV1, TimelineEventV1
from matb_integration.experiment_compiler import (
    ExperimentCompileError,
    _summary,
    compile_experiment_spec,
)


SOURCE_COMMIT = "48e9dbaa946349021d2ce2186d599c1f82182ab4"


def event(
    key: str,
    at_s: int,
    task: str,
    command: str,
    *,
    value: object | None = None,
    duration_s: int | None = None,
) -> TimelineEventV1:
    parameters = {"command": command}
    if value is not None:
        parameters["value"] = value
    return TimelineEventV1.create(
        event_key=key,
        at_ns=at_s * 1_000_000_000,
        duration_ns=None if duration_s is None else duration_s * 1_000_000_000,
        component_id="matb-runtime",
        task=task,
        event_type="openmatb.command",
        parameters=parameters,
    )


def spec(*timeline: TimelineEventV1) -> ExperimentSpecV1:
    return ExperimentSpecV1.create(
        experiment_id="calibration-low",
        revision=1,
        title="Calibration low workload",
        seed=42,
        profile_id="MATB-EXTENDED-2.0",
        duration_ns=60_000_000_000,
        components=("matb-runtime",),
        timeline=timeline,
        metadata={"workload_label_status": "engineering_preset_pending_human_calibration"},
    )


def test_compiler_emits_deterministic_openmatb_scenario_and_bound_manifest():
    source = spec(
        event("sysmon-start", 0, "sysmon", "start"),
        event("sysmon-nontarget", 10, "sysmon", "open_nontarget_opportunity", duration_s=2),
        event("sysmon-failure", 20, "sysmon", "lights-1-failure", value=True, duration_s=10),
        event("sysmon-stop", 59, "sysmon", "stop"),
    )

    first = compile_experiment_spec(
        source, source_commit=SOURCE_COMMIT, source_dirty=False
    )
    second = compile_experiment_spec(
        source, source_commit=SOURCE_COMMIT, source_dirty=False
    )

    assert first == second
    assert "0:00:10;sysmon;open_nontarget_opportunity" in first.scenario_text
    assert "0:00:20;sysmon;lights-1-failure;True" in first.scenario_text
    lines = first.scenario_text.splitlines()
    assert lines[lines.index("0:00:10;sysmon;open_nontarget_opportunity") - 1] == (
        "0:00:10;sysmon;nontargetduration;2000"
    )
    assert lines[lines.index("0:00:20;sysmon;lights-1-failure;True") - 1] == (
        "0:00:20;sysmon;alerttimeout;10000"
    )
    assert first.manifest["spec"]["sha256"] == source.sha256()
    assert first.manifest["scenario"]["sha256"] == sha256(first.scenario_text.encode()).hexdigest()
    assert first.manifest["source_commit"] == SOURCE_COMMIT
    assert first.manifest["source_dirty"] is False
    assert first.manifest["provenance_status"] == "complete"
    assert first.scenario_text.rstrip().endswith("0:01:00;system;boundary")
    assert first.manifest["spec"]["canonical_record"] == source.to_record()


@pytest.mark.parametrize(
    "task",
    ["sysmon", "track", "resman"],
)
def test_compiler_does_not_activate_communications_for_non_comm_task_subsets(task: str):
    compiled = compile_experiment_spec(
        spec(
            event(f"{task}-start", 0, task, "start"),
            event(f"{task}-stop", 59, task, "stop"),
        ),
        source_commit=SOURCE_COMMIT,
        source_dirty=False,
    )

    executable = [
        line for line in compiled.scenario_text.splitlines()
        if line and not line.startswith("#")
    ]
    parsed_plugins = {line.split(";", 2)[1] for line in executable}
    assert parsed_plugins == {task, "system"}
    assert "communications" not in parsed_plugins
    assert compiled.manifest["scenario"]["compiler_injected_line_count"] == 1
    assert compiled.manifest["communications_timing_profile"] is None


def test_compiler_rechecks_audio_inventory_after_first_compile(tmp_path, monkeypatch):
    """A long-lived Designer process must detect WAV replacement between requests."""
    import matb_integration.communications_profile as profile_module

    source_audio = (
        Path(__file__).parents[1]
        / "openmatb"
        / "includes"
        / "sounds"
        / "english"
        / "male"
    )
    copied_audio = tmp_path / "audio"
    shutil.copytree(source_audio, copied_audio)
    monkeypatch.setattr(profile_module, "_sound_directory", lambda: copied_audio)
    maybe_cache_clear = getattr(
        profile_module.verify_communications_audio_profile,
        "cache_clear",
        None,
    )
    if maybe_cache_clear is not None:
        maybe_cache_clear()
    communications_spec = spec(
        event("communications-start", 0, "communications", "start"),
        event("communications-stop", 59, "communications", "stop"),
    )

    compile_experiment_spec(
        communications_spec,
        source_commit=SOURCE_COMMIT,
        source_dirty=False,
    )
    changed_wav = next(iter(sorted(copied_audio.glob("*.wav"))))
    changed_wav.write_bytes(changed_wav.read_bytes() + b"changed-after-first-compile")

    with pytest.raises(ExperimentCompileError, match="audio inventory changed"):
        compile_experiment_spec(
            communications_spec,
            source_commit=SOURCE_COMMIT,
            source_dirty=False,
        )


def test_compiler_reports_event_rates_overlap_refractory_and_opportunity_counts():
    compiled = compile_experiment_spec(
        spec(
            event("sysmon-start", 0, "sysmon", "start"),
            event("target-1", 10, "sysmon", "lights-1-failure", value=True, duration_s=10),
            event("nontarget-1", 25, "sysmon", "open_nontarget_opportunity", duration_s=2),
            event("sysmon-stop", 59, "sysmon", "stop"),
        ),
        source_commit=SOURCE_COMMIT,
    )

    summary = compiled.manifest["summary"]
    assert summary["source_command_count"] == 4
    assert summary["source_command_rate_per_min"] == 4.0
    assert summary["per_task_source_command_rate_per_min"]["sysmon"] == 4.0
    assert summary["stimulus_opportunity_count"] == 2
    assert summary["stimulus_opportunity_rate_per_min"] == 2.0
    assert summary["per_task_stimulus_opportunity_rate_per_min"]["sysmon"] == 2.0
    assert summary["pairwise_overlap_count"] == 0
    assert summary["minimum_stimulus_refractory_ms_by_task"]["sysmon"] == 15_000.0
    assert summary["sysmon_target_opportunities"] == 1
    assert summary["sysmon_nontarget_opportunities"] == 1


def test_compiler_rejects_subsecond_onset_instead_of_silently_rounding():
    subsecond = TimelineEventV1.create(
        event_key="unsafe-rounding",
        at_ns=1_500_000_000,
        duration_ns=None,
        component_id="matb-runtime",
        task="sysmon",
        event_type="openmatb.command",
        parameters={"command": "start"},
    )

    with pytest.raises(ExperimentCompileError, match="whole-second"):
        compile_experiment_spec(spec(subsecond), source_commit=SOURCE_COMMIT)


def test_compiler_rejects_duration_that_openmatb_cannot_execute_losslessly():
    unsupported = (
        event("track-window", 1, "track", "start", duration_s=2),
        event("comm-window", 1, "communications", "radioprompt", value="own", duration_s=2),
    )

    for item in unsupported:
        with pytest.raises(ExperimentCompileError, match="cannot represent duration"):
            compile_experiment_spec(spec(item), source_commit=SOURCE_COMMIT)


def test_compiler_rejects_overlapping_timed_events_with_shared_timeout_state():
    source = spec(
        event("first", 10, "sysmon", "lights-1-failure", value=True, duration_s=10),
        event("second", 15, "sysmon", "scales-1-failure", value=True, duration_s=5),
    )

    with pytest.raises(ExperimentCompileError, match="overlapping timed events"):
        compile_experiment_spec(source, source_commit=SOURCE_COMMIT)


def test_compiler_rejects_simultaneous_communications_prompts() -> None:
    source = spec(
        event("communications-start", 0, "communications", "start"),
        event("prompt-own", 10, "communications", "radioprompt", value="own"),
        event("prompt-other", 10, "communications", "radioprompt", value="other"),
        event("communications-stop", 59, "communications", "stop"),
    )

    with pytest.raises(ExperimentCompileError, match="simultaneous communications"):
        compile_experiment_spec(source, source_commit=SOURCE_COMMIT)


@pytest.mark.parametrize("second_prompt_s", [43, 54])
def test_compiler_rejects_communications_prompts_without_full_serial_boundary(
    second_prompt_s: int,
) -> None:
    source = spec(
        event("communications-start", 0, "communications", "start"),
        event("prompt-own", 10, "communications", "radioprompt", value="own"),
        event("prompt-other", second_prompt_s, "communications", "radioprompt", value="other"),
        event("communications-stop", 59, "communications", "stop"),
    )

    with pytest.raises(ExperimentCompileError, match="communications prompts require"):
        compile_experiment_spec(source, source_commit=SOURCE_COMMIT)


@pytest.mark.parametrize("stop_s", [53, 54])
def test_compiler_rejects_communications_stop_before_response_window_closes(
    stop_s: int,
) -> None:
    source = spec(
        event("communications-start", 0, "communications", "start"),
        event("prompt-own", 10, "communications", "radioprompt", value="own"),
        event("communications-stop", stop_s, "communications", "stop"),
    )

    with pytest.raises(ExperimentCompileError, match="before prior command evidence can close"):
        compile_experiment_spec(source, source_commit=SOURCE_COMMIT)


def test_compiler_accepts_communications_prompt_after_full_refractory_boundary() -> None:
    source = ExperimentSpecV1.create(
        experiment_id="calibration-low",
        revision=1,
        title="Calibration low workload",
        seed=42,
        profile_id="MATB-EXTENDED-2.0",
        duration_ns=92_000_000_000,
        components=("matb-runtime",),
        timeline=(
            event("communications-start", 0, "communications", "start"),
            event("prompt-own", 1, "communications", "radioprompt", value="own"),
            event("prompt-other", 46, "communications", "radioprompt", value="other"),
            event("communications-stop", 91, "communications", "stop"),
        ),
        metadata={"workload_label_status": "engineering_preset_pending_human_calibration"},
    )

    compiled = compile_experiment_spec(source, source_commit=SOURCE_COMMIT)
    assert compiled.scenario_text.count(";communications;radioprompt;") == 2
    assert "0:00:00;communications;voiceidiom;english" in compiled.scenario_text
    assert compiled.manifest["communications_timing_profile"]["qualified_ceiling_sec"] == 24


def test_event_map_uses_zero_based_scenario_lines() -> None:
    source = spec(
        event("sysmon-start", 0, "sysmon", "start"),
        event("sysmon-nontarget", 10, "sysmon", "open_nontarget_opportunity", duration_s=2),
        event("sysmon-stop", 59, "sysmon", "stop"),
    )
    compiled = compile_experiment_spec(source, source_commit=SOURCE_COMMIT)
    lines = compiled.scenario_text.splitlines()

    assert compiled.manifest["scenario"]["line_number_base"] == 0
    for mapping in compiled.manifest["event_map"]:
        assert lines[mapping["scenario_line"]].split(";")[1] == "sysmon"
        assert all(lines[index].split(";")[1] == "sysmon" for index in mapping["supporting_scenario_lines"])


@pytest.mark.parametrize("stop_s", [11, 20])
def test_compiler_rejects_sysmon_stop_before_timed_opportunity_is_observable(
    stop_s: int,
) -> None:
    source = spec(
        event("sysmon-start", 0, "sysmon", "start"),
        event(
            "target",
            10,
            "sysmon",
            "lights-1-failure",
            value=True,
            duration_s=10,
        ),
        event("sysmon-stop", stop_s, "sysmon", "stop"),
    )

    with pytest.raises(ExperimentCompileError, match="before prior command evidence can close"):
        compile_experiment_spec(source, source_commit=SOURCE_COMMIT)


def test_compiler_rejects_same_tick_stop_after_transient_communications_prompt() -> None:
    source = spec(
        event("communications-start", 0, "communications", "start"),
        event("prompt", 10, "communications", "radioprompt", value="own"),
        event("zz-communications-stop", 10, "communications", "stop"),
    )

    with pytest.raises(ExperimentCompileError, match="before prior command evidence can close"):
        compile_experiment_spec(source, source_commit=SOURCE_COMMIT)


def test_summary_sweep_counts_endpoint_exclusive_overlaps() -> None:
    source = spec(
        event("sysmon-start", 0, "sysmon", "start"),
        event("a", 1, "sysmon", "lights-1-failure", value=True, duration_s=10),
        event("b", 5, "communications", "radioprompt", value="own"),
        event("c", 11, "resman", "start"),
        event("sysmon-stop", 59, "sysmon", "stop"),
    )
    # Give the cross-task events explicit intervals only for summary analysis;
    # compile-time representability is tested independently.
    b = source.timeline[2].model_copy(update={"duration_ns": 10_000_000_000})
    c = source.timeline[3].model_copy(update={"duration_ns": 10_000_000_000})
    bounded = source.model_copy(update={"timeline": (source.timeline[0], source.timeline[1], b, c, source.timeline[4])})

    assert _summary(bounded)["pairwise_overlap_count"] == 2


def test_compiler_marks_missing_source_commit_without_upgrading_provenance():
    compiled = compile_experiment_spec(
        spec(
            event("sysmon-start", 0, "sysmon", "start"),
            event("sysmon-stop", 59, "sysmon", "stop"),
        ),
        source_commit="unavailable",
    )

    assert compiled.manifest["provenance_status"] == "provisional_missing_source_commit"
    assert compiled.manifest["source_dirty"] is None


def test_compiler_discards_impossible_clean_attestation_for_missing_commit():
    compiled = compile_experiment_spec(
        spec(
            event("sysmon-start", 0, "sysmon", "start"),
            event("sysmon-stop", 59, "sysmon", "stop"),
        ),
        source_commit="unknown",
        source_dirty=False,
    )

    assert compiled.manifest["source_commit"] == "unknown"
    assert compiled.manifest["source_dirty"] is None
    assert compiled.manifest["provenance_status"] == "provisional_missing_source_commit"


@pytest.mark.parametrize(
    "source_commit",
    ["foo", "n/a", "48e9dbaa", "A" * 40, f" {SOURCE_COMMIT}", f"{SOURCE_COMMIT} "],
)
def test_compiler_rejects_noncanonical_source_commit(source_commit: str):
    with pytest.raises(ExperimentCompileError, match="full lowercase Git object ID"):
        compile_experiment_spec(
            spec(
                event("sysmon-start", 0, "sysmon", "start"),
                event("sysmon-stop", 59, "sysmon", "stop"),
            ),
            source_commit=source_commit,
        )


@pytest.mark.parametrize("source_dirty", [0, 1, "false"])
def test_compiler_rejects_non_boolean_source_dirty(source_dirty: object):
    with pytest.raises(ExperimentCompileError, match="boolean or null"):
        compile_experiment_spec(
            spec(
                event("sysmon-start", 0, "sysmon", "start"),
                event("sysmon-stop", 59, "sysmon", "stop"),
            ),
            source_commit=SOURCE_COMMIT,
            source_dirty=source_dirty,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("source_commit", ["UNKNOWN", " unavailable "])
def test_compiler_normalizes_case_and_padding_for_missing_commit_sentinels(
    source_commit: str,
):
    compiled = compile_experiment_spec(
        spec(
            event("sysmon-start", 0, "sysmon", "start"),
            event("sysmon-stop", 59, "sysmon", "stop"),
        ),
        source_commit=source_commit,
    )

    assert compiled.manifest["source_commit"] in {"unknown", "unavailable"}
    assert compiled.manifest["provenance_status"] == "provisional_missing_source_commit"


@pytest.mark.parametrize(
    ("source_dirty", "expected_status"),
    [
        (True, "provisional_dirty_source_tree"),
        (None, "provisional_unverified_source_tree"),
    ],
)
def test_compiler_full_commit_requires_clean_tree_attestation(
    source_dirty: bool | None,
    expected_status: str,
):
    compiled = compile_experiment_spec(
        spec(
            event("sysmon-start", 0, "sysmon", "start"),
            event("sysmon-stop", 59, "sysmon", "stop"),
        ),
        source_commit=SOURCE_COMMIT,
        source_dirty=source_dirty,
    )

    assert compiled.manifest["provenance_status"] == expected_status
    assert compiled.manifest["source_dirty"] is source_dirty


@pytest.mark.parametrize(
    "bad_event",
    [
        TimelineEventV1.create(
            event_key="wrong-component",
            at_ns=0,
            duration_ns=None,
            component_id="matb-automation",
            task="sysmon",
            event_type="openmatb.command",
            parameters={"command": "start"},
        ),
        TimelineEventV1.create(
            event_key="missing-task",
            at_ns=0,
            duration_ns=None,
            component_id="matb-runtime",
            task=None,
            event_type="openmatb.command",
            parameters={"command": "start"},
        ),
        TimelineEventV1.create(
            event_key="delimiter-injection",
            at_ns=0,
            duration_ns=None,
            component_id="matb-runtime",
            task="sysmon",
            event_type="openmatb.command",
            parameters={"command": "start;communications;stop"},
        ),
    ],
)
def test_compiler_fails_closed_for_unsupported_or_ambiguous_events(bad_event: TimelineEventV1):
    components = ("matb-runtime", "matb-automation")
    source = ExperimentSpecV1.create(
        experiment_id="invalid",
        revision=1,
        title="Invalid compile case",
        seed=1,
        profile_id="MATB-EXTENDED-2.0",
        duration_ns=10_000_000_000,
        components=components,
        timeline=(bad_event,),
    )
    with pytest.raises(ExperimentCompileError):
        compile_experiment_spec(source, source_commit=SOURCE_COMMIT)


def test_compiler_rejects_unused_or_unsupported_declared_components():
    source = ExperimentSpecV1.create(
        experiment_id="invalid-components",
        revision=1,
        title="Invalid component set",
        seed=1,
        profile_id="MATB-EXTENDED-2.0",
        duration_ns=60_000_000_000,
        components=("matb-runtime", "matb-automation"),
        timeline=(
            event("track-start", 0, "track", "start"),
            event("track-stop", 59, "track", "stop"),
        ),
    )

    with pytest.raises(ExperimentCompileError, match="exactly the matb-runtime"):
        compile_experiment_spec(source, source_commit=SOURCE_COMMIT)


@pytest.mark.parametrize("value", [None, False])
def test_compiler_rejects_sysmon_failure_without_literal_true(value: object | None):
    source = spec(
        event("sysmon-start", 0, "sysmon", "start"),
        event(
            "invalid-failure",
            10,
            "sysmon",
            "lights-1-failure",
            value=value,
            duration_s=10,
        ),
        event("sysmon-stop", 59, "sysmon", "stop"),
    )

    with pytest.raises(ExperimentCompileError, match="literal True"):
        compile_experiment_spec(source, source_commit=SOURCE_COMMIT)


@pytest.mark.parametrize("value", [None, "invalid", True])
def test_compiler_rejects_invalid_communications_prompt(value: object | None):
    source = spec(
        event("communications-start", 0, "communications", "start"),
        event("invalid-prompt", 10, "communications", "radioprompt", value=value),
        event("communications-stop", 59, "communications", "stop"),
    )

    with pytest.raises(ExperimentCompileError, match="own.*other"):
        compile_experiment_spec(source, source_commit=SOURCE_COMMIT)


def test_summary_counts_implicit_communications_response_window_overlap():
    source = spec(
        event("sysmon-start", 0, "sysmon", "start"),
        event("communications-start", 0, "communications", "start"),
        event(
            "sysmon-target",
            24,
            "sysmon",
            "lights-1-failure",
            value=True,
            duration_s=10,
        ),
        event("comm-prompt", 10, "communications", "radioprompt", value="own"),
        event("sysmon-stop", 59, "sysmon", "stop"),
        event("communications-stop", 59, "communications", "stop"),
    )

    compiled = compile_experiment_spec(source, source_commit=SOURCE_COMMIT)

    assert compiled.manifest["summary"]["pairwise_overlap_count"] == 1
    assert compiled.manifest["summary"]["pairwise_overlap_percent"] == 100.0


def test_compiler_rejects_unsupported_task_command_pair():
    source = spec(
        event("track-start", 0, "track", "start"),
        event("unsupported", 10, "track", "radioprompt", value="own"),
        event("track-stop", 59, "track", "stop"),
    )

    with pytest.raises(ExperimentCompileError, match="unsupported command"):
        compile_experiment_spec(source, source_commit=SOURCE_COMMIT)


def test_compiler_rejects_command_before_task_start():
    source = spec(
        event("nontarget-before-start", 10, "sysmon", "open_nontarget_opportunity", duration_s=2),
        event("sysmon-start", 20, "sysmon", "start"),
        event("sysmon-stop", 59, "sysmon", "stop"),
    )

    with pytest.raises(ExperimentCompileError, match="before an active start"):
        compile_experiment_spec(source, source_commit=SOURCE_COMMIT)


def test_compiler_rejects_task_lifecycle_without_stop():
    source = spec(event("sysmon-start", 0, "sysmon", "start"))

    with pytest.raises(ExperimentCompileError, match="without a matching stop"):
        compile_experiment_spec(source, source_commit=SOURCE_COMMIT)
