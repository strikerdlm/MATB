"""Capability-driven composition for the Research Console.

Core modules are always present. Product components are loaded only through
their provider entry points, so an allowlisted research-core distribution can
start without importing Liftoff or sUAS implementation modules.
"""

from __future__ import annotations

from importlib import import_module
import os
from typing import Any, Protocol

from fastapi import FastAPI

from matb_integration.contracts import ComponentManifestV1, ComponentRegistry


class ConsoleComponentProvider(Protocol):
    manifest: ComponentManifestV1
    model_modules: tuple[str, ...]
    router_modules: tuple[str, ...]

    async def startup(self, app: FastAPI) -> None: ...

    async def shutdown(self, app: FastAPI) -> None: ...


_OPTIONAL_ENTRYPOINTS = {
    "matb-liftoff": "app.liftoff_component:provider",
    "matb-openmatb": "app.openmatb_component:provider",
    "matb-physiology": "app.physiology_component:provider",
    "matb-suas": "app.simulation_component:provider",
}

_ACTIVE_REGISTRY: ComponentRegistry | None = None


def _core_manifests() -> tuple[ComponentManifestV1, ...]:
    version = "0.1.0-alpha.1"
    return (
        ComponentManifestV1.create(
            component_id="matb-contracts",
            component_version=version,
            component_kind="contracts",
            stability="candidate",
            distribution="core",
            capabilities=(
                "contracts.components",
                "contracts.events",
                "contracts.experiments",
                "contracts.timing",
            ),
            license_expression="MIT",
        ),
        ComponentManifestV1.create(
            component_id="matb-runtime",
            component_version=version,
            component_kind="runtime",
            stability="candidate",
            distribution="core",
            capabilities=(
                "runtime.classical-tasks",
                "runtime.event-recording",
                "runtime.lsl-observations",
                "runtime.timing-qc",
            ),
            requires=("matb-contracts",),
            license_expression="CECILL-2.1",
        ),
        ComponentManifestV1.create(
            component_id="matb-automation",
            component_version=version,
            component_kind="automation",
            stability="experimental",
            distribution="core",
            capabilities=(
                "automation.allocation-policies",
                "automation.audit-chain",
                "automation.failure-models",
            ),
            requires=("matb-contracts",),
            license_expression="MIT",
        ),
        ComponentManifestV1.create(
            component_id="matb-research",
            component_version=version,
            component_kind="research",
            stability="candidate",
            distribution="core",
            capabilities=("research.analysis", "research.metrics", "research.provenance"),
            requires=("matb-contracts", "matb-runtime"),
            license_expression="MIT",
        ),
        ComponentManifestV1.create(
            component_id="matb-console",
            component_version=version,
            component_kind="console",
            stability="candidate",
            distribution="core",
            capabilities=("console.http", "console.offline"),
            requires=("matb-research",),
            license_expression="MIT",
        ),
    )


def _load_entrypoint(value: str) -> ConsoleComponentProvider:
    module_name, attribute = value.split(":", 1)
    module = import_module(module_name)
    loaded: Any = module
    for part in attribute.split("."):
        loaded = getattr(loaded, part)
    return loaded


def _selected_optional_components(raw: str | None) -> tuple[tuple[str, str], ...]:
    selection = "auto" if raw is None else raw.strip()
    if not selection:
        raise ValueError("MATB_COMPONENTS must be 'auto', 'core', or component IDs")
    if selection == "core":
        return ()
    if selection == "auto":
        return tuple(sorted(_OPTIONAL_ENTRYPOINTS.items()))
    requested = tuple(part.strip() for part in selection.split(","))
    if any(not part for part in requested):
        raise ValueError("MATB_COMPONENTS must not contain empty component IDs")
    unknown = sorted(set(requested) - set(_OPTIONAL_ENTRYPOINTS))
    if unknown:
        raise ValueError(f"unknown MATB components: {', '.join(unknown)}")
    return tuple((component_id, _OPTIONAL_ENTRYPOINTS[component_id]) for component_id in sorted(set(requested)))


def configure_components(raw: str | None = None) -> tuple[ComponentRegistry, tuple[ConsoleComponentProvider, ...]]:
    """Build the active registry; auto mode ignores components not installed."""

    global _ACTIVE_REGISTRY
    selection = os.getenv("MATB_COMPONENTS") if raw is None else raw
    auto = selection is None or selection.strip() == "auto"
    registry = ComponentRegistry()
    for manifest in _core_manifests():
        registry.register(manifest)
    providers: list[ConsoleComponentProvider] = []
    for component_id, entrypoint in _selected_optional_components(selection):
        try:
            provider = _load_entrypoint(entrypoint)
        except ModuleNotFoundError as exc:
            entry_module = entrypoint.split(":", 1)[0]
            missing_module = exc.name or ""
            entrypoint_is_absent = (
                missing_module == entry_module
                or entry_module.startswith(f"{missing_module}.")
            )
            if auto and entrypoint_is_absent:
                continue
            if entrypoint_is_absent:
                raise ValueError(
                    f"requested MATB component is not installed: {component_id}"
                ) from None
            # A provider exists but one of its own dependencies is broken. Silent
            # disablement would create an environment-dependent partial product.
            raise
        if provider.manifest.component_id != component_id:
            raise ValueError(
                f"component entry point mismatch: expected {component_id}, observed {provider.manifest.component_id}"
            )
        registry.register(provider.manifest)
        providers.append(provider)
    registry.activation_order()
    _ACTIVE_REGISTRY = registry
    return registry, tuple(providers)


def is_component_active(component_id: str) -> bool:
    registry = _ACTIVE_REGISTRY
    return registry is not None and any(
        manifest.component_id == component_id for manifest in registry.manifests()
    )
