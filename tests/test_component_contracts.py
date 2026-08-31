from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError as JsonSchemaValidationError

from matb_integration.contracts import ComponentManifestV1, ComponentRegistry


def manifest(
    component_id: str,
    *,
    capabilities: tuple[str, ...],
    requires: tuple[str, ...] = (),
    distribution: str = "core",
) -> ComponentManifestV1:
    return ComponentManifestV1.create(
        component_id=component_id,
        component_version="3.0.0-alpha.1",
        component_kind="runtime" if component_id == "matb-runtime" else "research",
        stability="experimental",
        distribution=distribution,
        capabilities=capabilities,
        requires=requires,
        python_entrypoint=f"{component_id.replace('-', '_')}.component:provider",
        license_expression="MIT",
    )


def test_manifest_serialization_is_canonical_and_explicit() -> None:
    """Catch nondeterministic capability ordering and missing release metadata."""
    item = ComponentManifestV1.create(
        component_id="matb-runtime",
        component_version="3.0.0-alpha.1",
        component_kind="runtime",
        stability="experimental",
        distribution="core",
        capabilities=("runtime.timing", "runtime.classical_tasks"),
        requires=("matb-contracts",),
        python_entrypoint="matb_runtime.component:provider",
        license_expression="MIT AND CECILL-2.1",
    )

    assert item.to_record() == {
        "schema_version": "1.0",
        "component_id": "matb-runtime",
        "component_version": "3.0.0-alpha.1",
        "component_kind": "runtime",
        "stability": "experimental",
        "distribution": "core",
        "capabilities": ["runtime.classical_tasks", "runtime.timing"],
        "requires": ["matb-contracts"],
        "python_entrypoint": "matb_runtime.component:provider",
        "license_expression": "MIT AND CECILL-2.1",
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"component_id": "MATB Runtime"},
        {"component_version": "development"},
        {"capabilities": ["runtime.timing", "runtime.timing"]},
        {"requires": ["matb-runtime"]},
        {"python_entrypoint": "not an entry point"},
        {"license_expression": ""},
    ],
)
def test_manifest_rejects_ambiguous_component_metadata(changes: dict[str, object]) -> None:
    """Catch manifests that cannot be resolved or audited deterministically."""
    record = manifest("matb-runtime", capabilities=("runtime.timing",)).to_record()
    record.update(changes)
    with pytest.raises(ValueError):
        ComponentManifestV1.from_record(record)


def test_registry_resolves_capabilities_in_dependency_order() -> None:
    """Catch activation before required contracts or runtimes are available."""
    registry = ComponentRegistry()
    registry.register(manifest("matb-research", capabilities=("research.metrics",), requires=("matb-runtime",)))
    registry.register(manifest("matb-runtime", capabilities=("runtime.tasks",), requires=("matb-contracts",)))
    registry.register(manifest("matb-contracts", capabilities=("contracts.events",)))

    assert registry.provider_for("runtime.tasks").component_id == "matb-runtime"
    assert tuple(item.component_id for item in registry.activation_order()) == (
        "matb-contracts",
        "matb-runtime",
        "matb-research",
    )


def test_registry_fails_closed_for_missing_duplicate_or_cyclic_components() -> None:
    """Catch partial installations and ambiguous/cyclic capability graphs."""
    missing = ComponentRegistry()
    missing.register(manifest("matb-runtime", capabilities=("runtime.tasks",), requires=("matb-contracts",)))
    with pytest.raises(ValueError, match="missing required component"):
        missing.activation_order()

    duplicate = ComponentRegistry()
    duplicate.register(manifest("matb-runtime", capabilities=("runtime.tasks",)))
    with pytest.raises(ValueError, match="capability already provided"):
        duplicate.register(manifest("matb-research", capabilities=("runtime.tasks",)))

    cyclic = ComponentRegistry()
    cyclic.register(manifest("matb-runtime", capabilities=("runtime.tasks",), requires=("matb-research",)))
    cyclic.register(manifest("matb-research", capabilities=("research.metrics",), requires=("matb-runtime",)))
    with pytest.raises(ValueError, match="dependency cycle"):
        cyclic.activation_order()


def test_component_schema_validates_wire_manifest_and_required_fields() -> None:
    """Catch schema drift that would admit incomplete component distributions."""
    path = Path(__file__).parents[1] / "docs" / "contracts" / "component-manifest-v1.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    record = manifest("matb-runtime", capabilities=("runtime.tasks",)).to_record()
    validator.validate(record)

    record.pop("license_expression")
    with pytest.raises(JsonSchemaValidationError):
        validator.validate(record)

    padded = manifest("matb-runtime", capabilities=("runtime.tasks",)).to_record()
    padded["license_expression"] = " MIT"
    with pytest.raises(JsonSchemaValidationError):
        validator.validate(padded)
    with pytest.raises(ValueError):
        ComponentManifestV1.from_record(padded)
