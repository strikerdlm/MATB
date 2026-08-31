"""Component manifests and deterministic capability resolution."""

from __future__ import annotations

from typing import Any, ClassVar, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ComponentKind = Literal[
    "contracts",
    "runtime",
    "research",
    "console",
    "physiology",
    "automation",
    "simulation",
    "governance",
]
ComponentStability = Literal["stable", "candidate", "experimental"]
ComponentDistribution = Literal["core", "optional"]

COMPONENT_ID_PATTERN = r"^[a-z][a-z0-9]*(?:[-.][a-z0-9]+)*$"
_SEMVER_PATTERN = (
    r"^(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_CAPABILITY_PATTERN = r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$"
_ENTRYPOINT_PATTERN = (
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:"
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
)


class ComponentManifestV1(BaseModel):
    """Auditable metadata for one independently distributable component."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    SCHEMA_VERSION: ClassVar[str] = "1.0"

    schema_version: Literal["1.0"] = "1.0"
    component_id: str = Field(pattern=COMPONENT_ID_PATTERN)
    component_version: str = Field(pattern=_SEMVER_PATTERN)
    component_kind: ComponentKind
    stability: ComponentStability
    distribution: ComponentDistribution
    capabilities: tuple[str, ...]
    requires: tuple[str, ...]
    python_entrypoint: str | None = Field(default=None, pattern=_ENTRYPOINT_PATTERN)
    license_expression: str

    @field_validator("capabilities", "requires", mode="before")
    @classmethod
    def parse_wire_sequences(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("capabilities", "requires")
    @classmethod
    def normalize_identifiers(cls, value: tuple[str, ...], info: Any) -> tuple[str, ...]:
        if any(not isinstance(item, str) for item in value):
            raise ValueError(f"{info.field_name} must contain strings")
        if len(value) != len(set(value)):
            raise ValueError(f"{info.field_name} must not contain duplicates")
        pattern = _CAPABILITY_PATTERN if info.field_name == "capabilities" else COMPONENT_ID_PATTERN
        import re

        if any(re.fullmatch(pattern, item) is None for item in value):
            raise ValueError(f"{info.field_name} contains an invalid identifier")
        return tuple(sorted(value))

    @field_validator("license_expression")
    @classmethod
    def validate_license_expression(cls, value: str) -> str:
        if not value or not value.strip() or value != value.strip():
            raise ValueError("license_expression must not be empty or padded")
        return value

    @model_validator(mode="after")
    def validate_dependency_boundary(self) -> "ComponentManifestV1":
        if self.component_id in self.requires:
            raise ValueError("component cannot require itself")
        return self

    @classmethod
    def create(
        cls,
        *,
        component_id: str,
        component_version: str,
        component_kind: ComponentKind,
        stability: ComponentStability,
        distribution: ComponentDistribution,
        capabilities: tuple[str, ...] | list[str],
        requires: tuple[str, ...] | list[str] = (),
        python_entrypoint: str | None = None,
        license_expression: str,
    ) -> "ComponentManifestV1":
        return cls(
            component_id=component_id,
            component_version=component_version,
            component_kind=component_kind,
            stability=stability,
            distribution=distribution,
            capabilities=tuple(capabilities),
            requires=tuple(requires),
            python_entrypoint=python_entrypoint,
            license_expression=license_expression,
        )

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "ComponentManifestV1":
        return cls.model_validate(dict(record))

    def to_record(self) -> dict[str, Any]:
        record = self.model_dump(mode="json")
        record["capabilities"] = list(self.capabilities)
        record["requires"] = list(self.requires)
        return record


class ComponentRegistry:
    """In-memory registry with deterministic, fail-closed dependency ordering."""

    def __init__(self) -> None:
        self._components: dict[str, ComponentManifestV1] = {}
        self._capabilities: dict[str, str] = {}

    def register(self, manifest: ComponentManifestV1) -> None:
        if manifest.component_id in self._components:
            raise ValueError(f"component already registered: {manifest.component_id}")
        conflicts = sorted(
            capability
            for capability in manifest.capabilities
            if capability in self._capabilities
        )
        if conflicts:
            providers = ", ".join(
                f"{capability} by {self._capabilities[capability]}"
                for capability in conflicts
            )
            raise ValueError(f"capability already provided: {providers}")
        self._components[manifest.component_id] = manifest
        for capability in manifest.capabilities:
            self._capabilities[capability] = manifest.component_id

    def provider_for(self, capability: str) -> ComponentManifestV1:
        try:
            component_id = self._capabilities[capability]
        except KeyError as exc:
            raise KeyError(f"capability is unavailable: {capability}") from exc
        return self._components[component_id]

    def manifests(self) -> tuple[ComponentManifestV1, ...]:
        return tuple(self._components[key] for key in sorted(self._components))

    def activation_order(self) -> tuple[ComponentManifestV1, ...]:
        state: dict[str, Literal["visiting", "visited"]] = {}
        ordered: list[ComponentManifestV1] = []
        trail: list[str] = []

        def visit(component_id: str) -> None:
            status = state.get(component_id)
            if status == "visited":
                return
            if status == "visiting":
                start = trail.index(component_id)
                cycle = " -> ".join((*trail[start:], component_id))
                raise ValueError(f"component dependency cycle: {cycle}")
            manifest = self._components[component_id]
            state[component_id] = "visiting"
            trail.append(component_id)
            for required_id in manifest.requires:
                if required_id not in self._components:
                    raise ValueError(
                        f"missing required component: {required_id} required by {component_id}"
                    )
                visit(required_id)
            trail.pop()
            state[component_id] = "visited"
            ordered.append(manifest)

        for component_id in sorted(self._components):
            visit(component_id)
        return tuple(ordered)
