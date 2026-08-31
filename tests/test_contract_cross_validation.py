"""Cross-validator corpus for every public MATB contract schema."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from matb_integration.contracts import (
    ComponentManifestV1,
    ExperimentSpecV1,
    ScientificEventV3,
    TimelineEventV1,
    TimingObservationV1,
)


SESSION_ID = UUID("2d2c8064-cff4-4c12-b453-1de5ca36ef01")
SOURCE_COMMIT = "48e9dbaa946349021d2ce2186d599c1f82182ab4"


def _contract_corpus() -> tuple[tuple[str, type, dict], ...]:
    event = ScientificEventV3.create(
        session_id=SESSION_ID,
        sequence=1,
        component_id="matb-runtime",
        component_version="3.0.0-dev",
        task="SYSMON",
        event_type="sysmon.opportunity.opened",
        scenario_time_ns=1_000,
        scenario_sha256="a" * 64,
        profile_id="matb-extended-2.0",
        source_commit=SOURCE_COMMIT,
        source_dirty=False,
        payload={},
    )
    event_record = event.to_record()
    event_record["sequence"] = 1.0
    event_record["scenario_time_ns"] = 1_000.0

    observation = TimingObservationV1.create(
        session_id=SESSION_ID,
        event_id=event.event_id,
        observation_index=0,
        kind="dispatch_start",
        clock_id="host-monotonic",
        value=1_000,
        unit="ns",
        evidence_source="software",
        method="software_clock",
        uncertainty_ns=1,
    )
    observation_record = observation.to_record()
    observation_record.update({
        "observation_index": 0.0,
        "value": 1_000.0,
        "uncertainty_ns": 1.0,
    })

    spec = ExperimentSpecV1.create(
        experiment_id="cross-validator",
        revision=1,
        title="Cross-validator corpus",
        seed=7,
        profile_id="matb-extended-2.0",
        duration_ns=10_000,
        components=("matb-runtime",),
        timeline=(
            TimelineEventV1.create(
                event_key="sysmon-target",
                at_ns=1_000,
                duration_ns=2_000,
                component_id="matb-runtime",
                task="SYSMON",
                event_type="sysmon.opportunity.target",
                parameters={},
            ),
        ),
    )
    spec_record = spec.to_record()
    spec_record.update({"revision": 1.0, "seed": 7.0, "duration_ns": 10_000.0})
    spec_record["timeline"][0].update({"at_ns": 1_000.0, "duration_ns": 2_000.0})

    component = ComponentManifestV1.create(
        component_id="matb-runtime",
        component_version="3.0.0-dev",
        component_kind="runtime",
        stability="experimental",
        distribution="core",
        capabilities=("runtime.timing",),
        requires=(),
        python_entrypoint="openmatb.component:provider",
        license_expression="CECILL-2.1",
    )
    return (
        ("scientific-event-v3.schema.json", ScientificEventV3, event_record),
        ("timing-observation-v1.schema.json", TimingObservationV1, observation_record),
        ("experiment-spec-v1.schema.json", ExperimentSpecV1, spec_record),
        ("component-manifest-v1.schema.json", ComponentManifestV1, component.to_record()),
    )


@pytest.mark.parametrize("schema_name,contract,record", _contract_corpus())
def test_json_schema_valid_records_are_accepted_by_strict_models(
    schema_name: str,
    contract: type,
    record: dict,
) -> None:
    """Prevent JSON Schema and strict Pydantic from accepting different wires."""

    schema = json.loads(
        (Path(__file__).parents[1] / "docs" / "contracts" / schema_name).read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(record)

    restored = contract.from_record(record)

    assert restored.to_record()
    if schema_name == "scientific-event-v3.schema.json":
        assert type(restored.sequence) is int
        assert type(restored.scenario_time_ns) is int
    elif schema_name == "timing-observation-v1.schema.json":
        assert type(restored.observation_index) is int
        assert type(restored.value) is int
        assert type(restored.uncertainty_ns) is int
    elif schema_name == "experiment-spec-v1.schema.json":
        assert type(restored.revision) is int
        assert type(restored.seed) is int
        assert type(restored.duration_ns) is int
        assert type(restored.timeline[0].at_ns) is int
        assert type(restored.timeline[0].duration_ns) is int
