from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError as JsonSchemaValidationError

from matb_integration.contracts import (
    MAX_EXPERIMENT_DURATION_NS,
    MAX_EXPERIMENT_TIMELINE_EVENTS,
    ExperimentSpecV1,
    TimelineEventV1,
)


def timeline_events() -> tuple[TimelineEventV1, ...]:
    return (
        TimelineEventV1.create(
            event_key="tlx-after-block",
            at_ns=50_000_000_000,
            duration_ns=None,
            component_id="matb-research",
            task=None,
            event_type="workload.rtlx.prompt",
            parameters={"required": True},
        ),
        TimelineEventV1.create(
            event_key="sysmon-target-001",
            at_ns=10_000_000_000,
            duration_ns=2_000_000_000,
            component_id="matb-runtime",
            task="SYSMON",
            event_type="sysmon.opportunity.target",
            parameters={"signal": "F1", "response_window_ns": 2_000_000_000},
        ),
    )


def make_spec(*, events: tuple[TimelineEventV1, ...] | None = None) -> ExperimentSpecV1:
    return ExperimentSpecV1.create(
        experiment_id="matb-calibration-v1",
        revision=1,
        title="MATB workload calibration",
        seed=20260830,
        profile_id="matb-extended-2.0",
        duration_ns=60_000_000_000,
        components=("matb-runtime", "matb-research"),
        timeline=timeline_events() if events is None else events,
        metadata={"workload_label_status": "engineering_preset_pending_human_calibration"},
    )


def test_experiment_spec_canonicalizes_components_and_timeline_order() -> None:
    """Catch hashes that depend on UI insertion order rather than experiment meaning."""
    record = make_spec().to_record()

    assert record["components"] == ["matb-research", "matb-runtime"]
    assert [event["event_key"] for event in record["timeline"]] == [
        "sysmon-target-001",
        "tlx-after-block",
    ]
    reordered = ExperimentSpecV1.create(
        experiment_id="matb-calibration-v1",
        revision=1,
        title="MATB workload calibration",
        seed=20260830,
        profile_id="matb-extended-2.0",
        duration_ns=60_000_000_000,
        components=("matb-research", "matb-runtime"),
        timeline=tuple(reversed(timeline_events())),
        metadata={"workload_label_status": "engineering_preset_pending_human_calibration"},
    )
    assert reordered.sha256() == make_spec().sha256()


def test_experiment_spec_round_trip_preserves_canonical_hash() -> None:
    """Catch lossy wire parsing that changes the scenario provenance hash."""
    original = make_spec()
    restored = ExperimentSpecV1.from_record(original.to_record())

    assert restored.to_record() == original.to_record()
    assert restored.sha256() == original.sha256()
    assert len(original.sha256()) == 64


def test_experiment_spec_nested_json_is_deeply_immutable() -> None:
    source = ExperimentSpecV1.create(
        experiment_id="immutable",
        revision=1,
        title="Immutable specification",
        seed=1,
        profile_id="profile",
        duration_ns=10,
        components=("matb-runtime",),
        timeline=(
            TimelineEventV1.create(
                event_key="event",
                at_ns=1,
                duration_ns=None,
                component_id="matb-runtime",
                task="sysmon",
                event_type="runtime.command",
                parameters={"nested": {"values": [1, 2]}},
            ),
        ),
        metadata={"nested": {"labels": ["candidate"]}},
    )

    with pytest.raises(TypeError):
        source.metadata["new"] = True
    with pytest.raises(TypeError):
        source.timeline[0].parameters["nested"]["new"] = True  # type: ignore[index]
    with pytest.raises(AttributeError):
        source.timeline[0].parameters["nested"]["values"].append(3)  # type: ignore[index,union-attr]

    with pytest.raises(TypeError):
        dict.__setitem__(source.metadata, "base-class-bypass", True)
    assert "base-class-bypass" not in source.metadata


def test_experiment_spec_rejects_duplicate_or_out_of_bounds_events() -> None:
    """Catch ambiguous event identity and timeline events outside the session."""
    duplicate = timeline_events()[1]
    with pytest.raises(ValueError, match="duplicate timeline event_key"):
        make_spec(events=(duplicate, duplicate))

    out_of_bounds = TimelineEventV1.create(
        event_key="late-event",
        at_ns=59_000_000_000,
        duration_ns=2_000_000_000,
        component_id="matb-runtime",
        task="COMM",
        event_type="communications.target",
        parameters={},
    )
    with pytest.raises(ValueError, match="outside experiment duration"):
        make_spec(events=(out_of_bounds,))


def test_experiment_spec_rejects_unavailable_component_and_non_json_parameters() -> None:
    """Catch timeline dependencies absent from the declared component graph."""
    unavailable = TimelineEventV1.create(
        event_key="automation-handoff",
        at_ns=20_000_000_000,
        duration_ns=None,
        component_id="matb-automation",
        task="TRACK",
        event_type="automation.engage",
        parameters={},
    )
    with pytest.raises(ValueError, match="undeclared component"):
        make_spec(events=(unavailable,))

    with pytest.raises(ValueError, match="JSON"):
        TimelineEventV1.create(
            event_key="bad-parameters",
            at_ns=1,
            duration_ns=None,
            component_id="matb-runtime",
            task=None,
            event_type="runtime.invalid",
            parameters={"value": float("nan")},
        )


def test_experiment_spec_enforces_duration_and_timeline_resource_bounds() -> None:
    with pytest.raises(ValueError):
        ExperimentSpecV1.create(
            experiment_id="too-long",
            revision=1,
            title="Too long",
            seed=1,
            profile_id="profile",
            duration_ns=MAX_EXPERIMENT_DURATION_NS + 1,
            components=("matb-runtime",),
            timeline=(timeline_events()[1],),
        )

    repeated = tuple(timeline_events()[1] for _ in range(MAX_EXPERIMENT_TIMELINE_EVENTS + 1))
    with pytest.raises(ValueError):
        make_spec(events=repeated)


def test_experiment_spec_schema_validates_canonical_wire_record() -> None:
    """Catch wire-schema drift and incomplete experiment specifications."""
    path = Path(__file__).parents[1] / "docs" / "contracts" / "experiment-spec-v1.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    record = make_spec().to_record()
    validator.validate(record)

    record.pop("seed")
    with pytest.raises(JsonSchemaValidationError):
        validator.validate(record)

    padded = make_spec().to_record()
    padded["title"] = " MATB workload calibration"
    with pytest.raises(JsonSchemaValidationError):
        validator.validate(padded)
    with pytest.raises(ValueError):
        ExperimentSpecV1.from_record(padded)
