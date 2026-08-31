from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError as JsonSchemaValidationError

from matb_integration.contracts import ScientificEventV3, TimingObservationV1


SESSION_ID = UUID("2d2c8064-cff4-4c12-b453-1de5ca36ef01")
SCENARIO_SHA256 = "a" * 64
SOURCE_COMMIT = "48e9dbaa946349021d2ce2186d599c1f82182ab4"


def make_event() -> ScientificEventV3:
    return ScientificEventV3.create(
        session_id=SESSION_ID,
        sequence=42,
        component_id="matb-runtime",
        task="SYSMON",
        event_type="sysmon.opportunity.opened",
        scenario_time_ns=12_500_000_000,
        scenario_sha256=SCENARIO_SHA256,
        profile_id="matb-extended-2.0",
        source_commit=SOURCE_COMMIT,
        source_dirty=False,
        component_version="3.0.0-dev",
        payload={"opportunity_kind": "target", "signal": "F1"},
    )


def test_event_identity_is_stable_and_changes_when_the_order_changes() -> None:
    """Catch non-deterministic IDs and collisions between ordered events."""
    first = make_event()
    repeated = make_event()
    next_event = ScientificEventV3.create(
        session_id=SESSION_ID,
        sequence=43,
        component_id="matb-runtime",
        task="SYSMON",
        event_type="sysmon.opportunity.opened",
        scenario_time_ns=12_600_000_000,
        scenario_sha256=SCENARIO_SHA256,
        profile_id="matb-extended-2.0",
        source_commit=SOURCE_COMMIT,
        source_dirty=False,
        component_version="3.0.0-dev",
        payload={"opportunity_kind": "non_target", "signal": "F2"},
    )

    assert str(first.event_id) == "1b8e7f77-e9e7-5ec5-9860-2ebc0071d188"
    assert repeated.event_id == first.event_id
    assert next_event.event_id != first.event_id


def test_event_identity_is_structured_and_cannot_collide_on_delimiters() -> None:
    """Identity fields are encoded as data, never concatenated ambiguously."""
    first = ScientificEventV3.expected_event_id(
        session_id=SESSION_ID,
        component_id="runtime-7",
        sequence=8,
        event_type="event",
    )
    second = ScientificEventV3.expected_event_id(
        session_id=SESSION_ID,
        component_id="runtime",
        sequence=7,
        event_type="8|event",
    )
    assert first != second


def test_frozen_event_and_timing_contracts_are_deeply_immutable() -> None:
    event = ScientificEventV3.create(
        session_id=SESSION_ID,
        sequence=1,
        component_id="matb-runtime",
        component_version="1.0.0",
        task="sysmon",
        event_type="sysmon.sample",
        scenario_time_ns=1,
        scenario_sha256=SCENARIO_SHA256,
        profile_id="profile",
        source_commit=SOURCE_COMMIT,
        source_dirty=False,
        payload={"nested": {"samples": [1, 2]}},
    )
    observation = TimingObservationV1.create(
        session_id=SESSION_ID,
        event_id=event.event_id,
        observation_index=0,
        kind="dispatch_start",
        clock_id="host-monotonic",
        value=1,
        unit="ns",
        evidence_source="software",
        method="software_clock",
        details={"nested": {"labels": ["dispatch"]}},
    )

    with pytest.raises(TypeError):
        event.payload["new"] = True
    with pytest.raises(TypeError):
        event.payload["nested"]["new"] = True  # type: ignore[index]
    with pytest.raises(AttributeError):
        event.payload["nested"]["samples"].append(3)  # type: ignore[index,union-attr]
    with pytest.raises(AttributeError):
        observation.details["nested"]["labels"].append("onset")  # type: ignore[index,union-attr]

    # A dict subclass can be mutated by bypassing its overridden methods via
    # the concrete base-class descriptor. Scientific payloads must resist that
    # low-level escape hatch too.
    with pytest.raises(TypeError):
        dict.__setitem__(event.payload, "base-class-bypass", True)
    assert "base-class-bypass" not in event.payload


def test_event_record_preserves_provenance_and_explicit_missing_links() -> None:
    """Catch provenance loss or silent omission of unavailable relationships."""
    assert make_event().to_record() == {
        "schema_version": "3.0",
        "session_id": "2d2c8064-cff4-4c12-b453-1de5ca36ef01",
        "event_id": "1b8e7f77-e9e7-5ec5-9860-2ebc0071d188",
        "sequence": 42,
        "component_id": "matb-runtime",
        "component_version": "3.0.0-dev",
        "task": "SYSMON",
        "event_type": "sysmon.opportunity.opened",
        "scenario_time_ns": 12_500_000_000,
        "scenario_sha256": "a" * 64,
        "profile_id": "matb-extended-2.0",
        "source_commit": SOURCE_COMMIT,
        "source_dirty": False,
        "provenance_status": "complete",
        "causation_id": None,
        "correlation_id": None,
        "opportunity_id": None,
        "payload": {"opportunity_kind": "target", "signal": "F1"},
    }


def test_event_rejects_forged_identity_and_non_json_evidence() -> None:
    """Catch records whose identity or payload cannot be audited reproducibly."""
    forged = make_event().to_record()
    forged["event_id"] = "00000000-0000-0000-0000-000000000000"

    with pytest.raises(ValueError, match="event_id does not match"):
        ScientificEventV3.from_record(forged)

    with pytest.raises(ValueError, match="JSON"):
        ScientificEventV3.create(
            session_id=SESSION_ID,
            sequence=44,
            component_id="matb-runtime",
            task="TRACK",
            event_type="track.sample",
            scenario_time_ns=13_000_000_000,
            scenario_sha256=SCENARIO_SHA256,
            profile_id="matb-extended-2.0",
            source_commit=SOURCE_COMMIT,
            source_dirty=False,
            component_version="3.0.0-dev",
            payload={"error": float("nan")},
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sequence", -1),
        ("sequence", True),
        ("scenario_time_ns", -1),
        ("component_id", ""),
        ("component_id", "matb-runtime/sysmon"),
        ("event_type", " "),
        ("scenario_sha256", "not-a-digest"),
        ("source_commit", "48e9dba"),
    ],
)
def test_event_rejects_ambiguous_or_invalid_required_fields(field: str, value: object) -> None:
    """Catch values that would make ordering or provenance ambiguous."""
    record = make_event().to_record()
    record[field] = value
    if field in {"sequence", "component_id", "event_type"}:
        record["event_id"] = str(
            ScientificEventV3.expected_event_id(
                session_id=record["session_id"],
                component_id=str(record["component_id"]),
                sequence=record["sequence"],
                event_type=str(record["event_type"]),
            )
        )

    with pytest.raises(ValueError):
        ScientificEventV3.from_record(record)


@pytest.mark.parametrize(
    ("source_commit", "source_dirty", "expected_status"),
    [
        (SOURCE_COMMIT, True, "provisional_dirty_source_tree"),
        (SOURCE_COMMIT, None, "provisional_unverified_source_tree"),
        ("unavailable", None, "provisional_missing_source_commit"),
    ],
)
def test_event_provenance_status_is_derived_fail_closed(
    source_commit: str,
    source_dirty: bool | None,
    expected_status: str,
) -> None:
    event = ScientificEventV3.create(
        session_id=SESSION_ID,
        sequence=1,
        component_id="matb-runtime",
        component_version="1.0.0",
        task="sysmon",
        event_type="sysmon.sample",
        scenario_time_ns=1,
        scenario_sha256=SCENARIO_SHA256,
        profile_id="profile",
        source_commit=source_commit,
        source_dirty=source_dirty,
        payload={},
    )

    assert event.provenance_status == expected_status


def test_event_rejects_forged_provenance_status_in_python_and_json_schema() -> None:
    record = make_event().to_record()
    record["provenance_status"] = "provisional_dirty_source_tree"
    with pytest.raises(ValueError, match="inconsistent"):
        ScientificEventV3.from_record(record)

    schema = json.loads(
        (Path(__file__).parents[1] / "docs/contracts/scientific-event-v3.schema.json")
        .read_text(encoding="utf-8")
    )
    with pytest.raises(JsonSchemaValidationError):
        Draft202012Validator(schema).validate(record)
    invalid_source = make_event().to_record()
    invalid_source["source_commit"] = "48e9dba"
    with pytest.raises(JsonSchemaValidationError):
        Draft202012Validator(schema).validate(invalid_source)


def test_physical_timing_observation_requires_physical_evidence() -> None:
    """Catch software timestamps mislabeled as measured stimulus onset."""
    event = make_event()
    observation = TimingObservationV1.create(
        session_id=SESSION_ID,
        event_id=event.event_id,
        observation_index=0,
        kind="physical_onset",
        clock_id="host-monotonic",
        value=12_501_234_567,
        unit="ns",
        evidence_source="physical",
        method="photodiode",
        rig_id="matb-lab-a-2026-01",
        uncertainty_ns=250_000,
    )

    assert str(observation.observation_id) == "ad6e4446-7541-5813-afa4-f08109c8d378"
    assert observation.to_record()["kind"] == "physical_onset"
    assert observation.to_record()["evidence_source"] == "physical"

    with pytest.raises(ValueError, match="physical timing"):
        TimingObservationV1.create(
            session_id=SESSION_ID,
            event_id=event.event_id,
            observation_index=0,
            kind="physical_onset",
            clock_id="host-monotonic",
            value=12_501_234_567,
            unit="ns",
            evidence_source="software",
            method="software_clock",
        )


def test_nanosecond_timing_accepts_arbitrarily_large_json_integer_without_overflow() -> None:
    event = make_event()
    observation = TimingObservationV1.create(
        session_id=SESSION_ID,
        event_id=event.event_id,
        observation_index=0,
        kind="dispatch_start",
        clock_id="host-monotonic",
        value=10**400,
        unit="ns",
        evidence_source="software",
        method="software_clock",
    )

    assert observation.value == 10**400


def test_dispatch_and_physical_onset_are_distinct_linked_observations() -> None:
    """Catch schemas that overwrite dispatch time with physical onset time."""
    event = make_event()
    dispatch = TimingObservationV1.create(
        session_id=SESSION_ID,
        event_id=event.event_id,
        observation_index=0,
        kind="dispatch_start",
        clock_id="host-monotonic",
        value=12_500_400_000,
        unit="ns",
        evidence_source="software",
        method="software_clock",
    )
    onset = TimingObservationV1.create(
        session_id=SESSION_ID,
        event_id=event.event_id,
        observation_index=1,
        kind="physical_onset",
        clock_id="host-monotonic",
        value=12_501_234_567,
        unit="ns",
        evidence_source="physical",
        method="photodiode",
        rig_id="matb-lab-a-2026-01",
    )

    assert dispatch.observation_id != onset.observation_id
    assert dispatch.value == 12_500_400_000
    assert onset.value == 12_501_234_567


def test_dispatch_observation_rejects_physical_evidence_even_with_a_photodiode() -> None:
    """Physical apparatus cannot relabel a software dispatch timestamp as onset evidence."""
    event = make_event()
    with pytest.raises(ValueError, match="dispatch_start.*software_clock"):
        TimingObservationV1.create(
            session_id=SESSION_ID,
            event_id=event.event_id,
            observation_index=0,
            kind="dispatch_start",
            clock_id="host-monotonic",
            value=12_500_400_000,
            unit="ns",
            evidence_source="physical",
            method="photodiode",
            rig_id="matb-lab-a-2026-01",
        )


@pytest.mark.parametrize(
    ("kind", "method"),
    [
        ("physical_onset", "actuated_input"),
        ("physical_input", "photodiode"),
    ],
)
def test_physical_observation_kind_rejects_the_wrong_instrument_family(
    kind: str,
    method: str,
) -> None:
    with pytest.raises(ValueError, match="measurement method"):
        TimingObservationV1.create(
            session_id=SESSION_ID,
            event_id=make_event().event_id,
            observation_index=0,
            kind=kind,
            clock_id="rig-clock",
            value=12_501_234_567,
            unit="ns",
            evidence_source="physical",
            method=method,
            rig_id="matb-lab-a-2026-01",
        )


def test_timing_record_rejects_forged_identity_and_non_finite_clock_values() -> None:
    """Catch timing observations that cannot be traced or compared."""
    event = make_event()
    valid = TimingObservationV1.create(
        session_id=SESSION_ID,
        event_id=event.event_id,
        observation_index=0,
        kind="lsl_timestamp",
        clock_id="lsl-local-clock",
        value=8123.25,
        unit="s",
        evidence_source="software",
        method="lsl_clock",
    ).to_record()
    valid["observation_id"] = "00000000-0000-0000-0000-000000000000"

    with pytest.raises(ValueError, match="observation_id does not match"):
        TimingObservationV1.from_record(valid)

    with pytest.raises(ValueError, match="finite"):
        TimingObservationV1.create(
            session_id=SESSION_ID,
            event_id=event.event_id,
            observation_index=0,
            kind="lsl_timestamp",
            clock_id="lsl-local-clock",
            value=float("inf"),
            unit="s",
            evidence_source="software",
            method="lsl_clock",
        )


@pytest.mark.parametrize(
    ("filename", "record", "missing_field"),
    [
        ("scientific-event-v3.schema.json", make_event().to_record(), "event_type"),
        (
            "timing-observation-v1.schema.json",
            TimingObservationV1.create(
                session_id=SESSION_ID,
                event_id=make_event().event_id,
                observation_index=0,
                kind="dispatch_start",
                clock_id="host-monotonic",
                value=12_500_400_000,
                unit="ns",
                evidence_source="software",
                method="software_clock",
            ).to_record(),
            "kind",
        ),
    ],
)
def test_committed_json_schemas_validate_wire_records_and_required_fields(
    filename: str,
    record: dict[str, object],
    missing_field: str,
) -> None:
    """Catch wire schemas that drift from valid records or allow incomplete evidence."""
    schema_path = Path(__file__).parents[1] / "docs" / "contracts" / filename
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    validator.validate(record)

    incomplete = dict(record)
    incomplete.pop(missing_field)
    with pytest.raises(JsonSchemaValidationError):
        validator.validate(incomplete)

    invalid_format = dict(record)
    invalid_format["session_id"] = "not-a-uuid"
    with pytest.raises(JsonSchemaValidationError):
        validator.validate(invalid_format)

    padded_field = "clock_id" if filename.startswith("timing") else "profile_id"
    padded = dict(record)
    padded[padded_field] = f" {padded[padded_field]}"
    with pytest.raises(JsonSchemaValidationError):
        validator.validate(padded)
    contract = TimingObservationV1 if filename.startswith("timing") else ScientificEventV3
    with pytest.raises(ValueError):
        contract.from_record(padded)


def test_every_schema_valid_integral_timing_number_normalizes_at_model_boundary() -> None:
    observation = TimingObservationV1.create(
        session_id=SESSION_ID,
        event_id=make_event().event_id,
        observation_index=0,
        kind="dispatch_start",
        clock_id="host-monotonic",
        value=1,
        unit="ns",
        evidence_source="software",
        method="software_clock",
        uncertainty_ns=1,
    )
    record = observation.to_record()
    record["observation_index"] = 0.0
    record["value"] = 1.0
    record["uncertainty_ns"] = 1.0
    schema = json.loads(
        (Path(__file__).parents[1] / "docs/contracts/timing-observation-v1.schema.json")
        .read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(record)

    restored = TimingObservationV1.from_record(record)

    assert type(restored.observation_index) is int
    assert type(restored.value) is int
    assert type(restored.uncertainty_ns) is int
