# sUAS C2 Phase 1 — Deterministic Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a strict YAML scenario system and a deterministic, headless, fixed-step synthetic engine for 2–8 supervisory-controlled sUAS.

**Architecture:** Domain types and geometry are isolated from Pydantic scenario parsing. A normalized immutable `ScenarioDefinition` feeds a fixed-step `SimulationEngine`, which delegates vehicle advancement to `SyntheticVehicleBackend` and produces canonical snapshots/events without importing FastAPI or frontend code.

**Tech Stack:** Python 3.12, stdlib dataclasses/enums/hashlib/json/math, Pydantic 2.5+, PyYAML 6+, pytest 7.4+.

## Global Constraints

- Read first: `docs/superpowers/specs/2026-08-01-suas-c2-research-simulator-design.md` and `docs/superpowers/plans/2026-08-01-suas-c2-v1-master.md`.
- Preserve the master plan's time, numerical, randomness, offline, non-kinetic, fleet, compatibility, test, and Git constraints.
- `matb_integration/suas` must remain importable without FastAPI, SQLModel, NumPy, browser, OpenMATB, or `aircraft_monitor` imports.
- Use fixed-point authoritative fields and independent PCG32 streams; never call module-level `random`.
- Run `git status --short` before each task and stage only that task's listed files.
- After every task commit, run `git push origin HEAD` before starting the next task.

---

### Task 1: Domain enums, geometry, state types, and canonical serialization

**Files:**
- Create: `matb_integration/suas/__init__.py`
- Create: `matb_integration/suas/domain/__init__.py`
- Create: `matb_integration/suas/domain/enums.py`
- Create: `matb_integration/suas/domain/geometry.py`
- Create: `matb_integration/suas/domain/models.py`
- Create: `matb_integration/suas/domain/events.py`
- Create: `matb_integration/suas/domain/serialization.py`
- Create: `tests/suas/__init__.py`
- Create: `tests/suas/helpers.py`
- Create: `tests/suas/test_domain.py`

**Interfaces:**
- Consumes: no new feature interfaces.
- Produces: `PointMM`, `PolygonMM`, `Route`, `AircraftDefinition`, `AircraftState`, `ContactDefinition`, `ContactState`, `BlockDefinition`, `ScenarioDefinition`, `WorldState`, `DomainEvent`, `canonical_data()`, `canonical_json()`, and `canonical_sha256()`.

- [ ] **Step 1: Write failing enum, geometry, and canonical-state tests**

```python
# tests/suas/test_domain.py
from matb_integration.suas.domain.enums import AircraftMode, WorkloadProfile
from matb_integration.suas.domain.geometry import PointMM, PolygonMM, distance_mm, heading_mdeg
from matb_integration.suas.domain.serialization import canonical_json, canonical_sha256


def test_geometry_uses_integer_millimetres_and_inclusive_boundary() -> None:
    square = PolygonMM((PointMM(0, 0), PointMM(10_000, 0),
                        PointMM(10_000, 10_000), PointMM(0, 10_000)))
    assert square.contains(PointMM(5_000, 5_000))
    assert square.contains(PointMM(0, 5_000))
    assert not square.contains(PointMM(10_001, 5_000))
    assert distance_mm(PointMM(0, 0), PointMM(3_000, 4_000)) == 5_000
    assert [heading_mdeg(dx, dy) for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0))] == [
        0, 90_000, 180_000, 270_000,
    ]


def test_polygon_rejects_self_intersection() -> None:
    bow_tie = (PointMM(0, 0), PointMM(10_000, 10_000),
               PointMM(0, 10_000), PointMM(10_000, 0))
    with pytest.raises(ValueError, match="self-intersects"):
        PolygonMM(bow_tie)


def test_canonical_hash_is_independent_of_mapping_insertion_order() -> None:
    left = {"mode": AircraftMode.SEARCH, "profile": WorkloadProfile.LOW, "xy": [1, 2]}
    right = {"xy": [1, 2], "profile": WorkloadProfile.LOW, "mode": AircraftMode.SEARCH}
    assert canonical_json(left) == canonical_json(right)
    assert canonical_sha256(left) == canonical_sha256(right)
```

- [ ] **Step 2: Run the tests and confirm collection fails for the missing package**

Run: `python3 -m pytest tests/suas/test_domain.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'matb_integration.suas'`.

- [ ] **Step 3: Implement the locked enums and geometry primitives**

```python
# matb_integration/suas/domain/enums.py
from enum import StrEnum

class Locale(StrEnum):
    EN = "en"
    ES_CO = "es-CO"

class WorkloadProfile(StrEnum):
    PRACTICE = "PRACTICE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class AircraftMode(StrEnum):
    READY = "READY"
    TRANSIT = "TRANSIT"
    SEARCH = "SEARCH"
    HOLD = "HOLD"
    RETURN_TO_BASE = "RETURN_TO_BASE"
    LOST_LINK_PROCEDURE = "LOST_LINK_PROCEDURE"
    RECOVERED = "RECOVERED"
    MISSION_FAILED = "MISSION_FAILED"

class LinkState(StrEnum):
    NOMINAL = "NOMINAL"
    DEGRADED = "DEGRADED"
    LOST = "LOST"

class SensorState(StrEnum):
    NOMINAL = "NOMINAL"
    OFFLINE = "OFFLINE"

class ContactEvidence(StrEnum):
    NONE = "NONE"
    DETECTED = "DETECTED"
    INSPECTABLE = "INSPECTABLE"

class ContactWorkflow(StrEnum):
    UNDETECTED = "UNDETECTED"
    DETECTED = "DETECTED"
    INSPECTED = "INSPECTED"
    CLASSIFIED = "CLASSIFIED"
    PRIORITIZED = "PRIORITIZED"
    REPORTED = "REPORTED"

class ContactClassification(StrEnum):
    ROUTINE = "routine"
    PRIORITY = "priority"
    UNCERTAIN = "uncertain"

class ContactPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class AlertSeverity(StrEnum):
    ADVISORY = "ADVISORY"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"

class AlertKind(StrEnum):
    ENERGY_RESERVE = "ENERGY_RESERVE"
    ENERGY_CRITICAL = "ENERGY_CRITICAL"
    LINK_LOST = "LINK_LOST"
    SEPARATION_ADVISORY = "SEPARATION_ADVISORY"
    SEPARATION_CRITICAL = "SEPARATION_CRITICAL"
    RUNTIME_FAILURE = "RUNTIME_FAILURE"

class EventKind(StrEnum):
    AIRCRAFT_MODE_CHANGED = "AIRCRAFT_MODE_CHANGED"
    ENERGY_THRESHOLD_CROSSED = "ENERGY_THRESHOLD_CROSSED"
    LINK_STATE_CHANGED = "LINK_STATE_CHANGED"
    LOST_LINK_PROCEDURE_STARTED = "LOST_LINK_PROCEDURE_STARTED"
    CONTACT_EVIDENCE_CHANGED = "CONTACT_EVIDENCE_CHANGED"
    CONTACT_WORKFLOW_CHANGED = "CONTACT_WORKFLOW_CHANGED"
    CONTACT_CORRECTED = "CONTACT_CORRECTED"
    COVERAGE_UPDATED = "COVERAGE_UPDATED"
    SEPARATION_ADVISORY_OPENED = "SEPARATION_ADVISORY_OPENED"
    SEPARATION_VIOLATION = "SEPARATION_VIOLATION"
    SEPARATION_ALERT_CLOSED = "SEPARATION_ALERT_CLOSED"
    CONFLICT_INJECTION_STARTED = "CONFLICT_INJECTION_STARTED"
    CONFLICT_INJECTION_SKIPPED = "CONFLICT_INJECTION_SKIPPED"
```

Implement `PointMM` and `PolygonMM` as frozen, slotted dataclasses. Use integer cross products for point-on-segment, ray casting, segment intersection, signed polygon area, and self-intersection checks. `distance_mm()` must use `math.isqrt(dx * dx + dy * dy)` and never return a float. `heading_mdeg(dx, dy)` uses integer CORDIC vectoring with a checked-in microdegree arctangent table, converts north-clockwise to `[0, 360_000)`, rounds half-even to millidegrees, and rejects `(0, 0)`; runtime `atan2`, platform trigonometry, and floats are forbidden.

`tests/suas/helpers.py` owns only deterministic test builders such as `rectangle()`, `envelope()`, `place_pair()`, and `event_kinds()`; add each helper in the same task that first consumes it. Product code must never import this module.

- [ ] **Step 4: Implement authoritative definitions/state and canonical conversion**

```python
# matb_integration/suas/domain/models.py (required public shapes)
@dataclass(frozen=True, slots=True)
class Route:
    waypoints: tuple[PointMM, ...]

@dataclass(frozen=True, slots=True)
class EnergyDefinition:
    capacity_units: int
    initial_units: int
    idle_units_per_s: int
    transit_units_per_s: int
    search_units_per_s: int
    sensor_units_per_scan: int
    reserve_margin_ppm: int

@dataclass(frozen=True, slots=True)
class SensorDefinition:
    radius_mm: int
    scan_interval_ms: int
    detection_probability_ppm: int
    scans_to_inspectable: int

@dataclass(frozen=True, slots=True)
class AircraftDefinition:
    aircraft_id: str
    label: str
    home: PointMM
    speed_mm_per_s: int
    return_speed_mm_per_s: int
    altitude_mm: int
    initial_link: LinkState
    initial_sensor: SensorState
    energy: EnergyDefinition
    sensor: SensorDefinition

@dataclass(slots=True)
class AircraftState:
    aircraft_id: str
    position: PointMM
    heading_mdeg: int
    energy_units: int
    predicted_home_reserve_units: int
    mode: AircraftMode
    previous_mode: AircraftMode | None
    link: LinkState
    sensor: SensorState
    assigned_sector_id: str | None
    route: Route
    route_leg: int
    movement_remainder: int
    energy_remainder: int
    lost_link_since_ms: int | None
    last_communication_ms: int
    next_sensor_scan_ms: int
    mission_progress_ppm: int
    last_accepted_command_id: str | None

@dataclass(frozen=True, slots=True)
class ContactDefinition:
    contact_id: str
    position: PointMM
    truth: ContactClassification
    truth_priority: ContactPriority
    required_report: bool

@dataclass(slots=True)
class ContactState:
    contact_id: str
    evidence: ContactEvidence
    successful_scans: int
    workflow: ContactWorkflow
    classification: ContactClassification | None
    priority: ContactPriority | None
    revision: int
    last_reported_revision: int | None
    report_ids: list[str]

@dataclass(frozen=True, slots=True)
class BlockDefinition:
    block_id: str
    profile: WorkloadProfile
    duration_ms: int
    aircraft_ids: tuple[str, ...]
    contact_ids: tuple[str, ...]
    required_action_window_ms: int
    isa_interval_ms: int
    isa_times_ms: tuple[int, ...]
    sagat: SagatScheduleDefinition
    post_block_questionnaires: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class InitialViewDefinition:
    center: PointMM
    width_mm: int
    height_mm: int

@dataclass(frozen=True, slots=True)
class LinkEventDefinition:
    event_id: str
    block_id: str
    at_ms: int
    aircraft_id: str
    state: LinkState

@dataclass(frozen=True, slots=True)
class ConflictEventDefinition:
    event_id: str
    block_id: str
    at_ms: int
    aircraft_a: str
    aircraft_b: str
    convergence_point: PointMM
    convergence_in_ms: int

@dataclass(frozen=True, slots=True)
class SagatScheduleDefinition:
    window_start_ms: int
    window_end_ms: int
    probe_bank: str
    probe_ids: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class TerminationDefinition:
    finish_at_duration: bool
    abort_when_all_aircraft_failed: bool

@dataclass(frozen=True, slots=True)
class MetricThresholdDefinition:
    coverage_target_ppm: int
    contact_effectiveness_target_ppm: int
    asset_preservation_target_ppm: int
    timeliness_target_ppm: int

@dataclass(frozen=True, slots=True)
class ScenarioDefinition:
    schema_version: int
    scenario_id: str
    scenario_sha256: str
    title: Mapping[Locale, str]
    author: str
    description: Mapping[Locale, str]
    seed: int
    terrain: PolygonMM
    home: PointMM
    initial_view: InitialViewDefinition
    grid_cell_mm: int
    advisory_separation_mm: int
    critical_separation_mm: int
    sectors: Mapping[str, PolygonMM]
    restricted_zones: Mapping[str, PolygonMM]
    aircraft: Mapping[str, AircraftDefinition]
    contacts: Mapping[str, ContactDefinition]
    blocks: Mapping[str, BlockDefinition]
    link_events: tuple[LinkEventDefinition, ...]
    conflict_events: tuple[ConflictEventDefinition, ...]
    report_note_codes: Mapping[str, Mapping[Locale, str]]
    metric_thresholds: MetricThresholdDefinition
    termination: TerminationDefinition

@dataclass(slots=True)
class WorldState:
    block_id: str
    tick: int
    simulation_time_ms: int
    version: int
    aircraft: dict[str, AircraftState]
    contacts: dict[str, ContactState]
    alerts: dict[str, AlertState]
    coverage_cells: set[tuple[int, int]]
    event_sequence: int
```

Define `AlertState` and `DomainEvent` with stable string IDs, opening/closing sequence, simulation time, `AlertKind`/`EventKind`, entity IDs, acknowledgement, and JSON-safe payloads. Implement `canonical_data()` recursively for dataclasses, `StrEnum`, mappings, tuples/lists, sets sorted by canonical JSON, and `PointMM`; reject unsupported objects with `TypeError`. `canonical_json()` must use UTF-8-safe compact JSON with sorted keys and no NaN; `canonical_sha256()` hashes its encoded bytes.

- [ ] **Step 5: Run focused tests and the pre-existing manifest tests**

Run: `python3 -m pytest tests/suas/test_domain.py tests/test_scenario_manifest.py -q`

Expected: PASS.

- [ ] **Step 6: Commit and push Task 1**

```bash
git add matb_integration/suas tests/suas
git diff --cached --check
git commit -m "feat(suas): add deterministic domain primitives"
git push origin HEAD
```

### Task 2: Strict scenario schema, normalization, manifest, and bundled reference scenario

**Files:**
- Modify: `requirements.txt`
- Create: `matb_integration/suas/scenarios/__init__.py`
- Create: `matb_integration/suas/scenarios/schema.py`
- Create: `matb_integration/suas/scenarios/loader.py`
- Create: `matb_integration/suas/scenarios/manifest.py`
- Create: `matb_integration/suas/scenarios/profiles.py`
- Create: `matb_integration/questionnaires/sagat_suas_en.yaml`
- Create: `matb_integration/questionnaires/sagat_suas_es.yaml`
- Create: `matb_integration/questionnaires/isa_suas_en.txt`
- Create: `matb_integration/questionnaires/isa_suas_es.txt`
- Create: `matb_integration/questionnaires/nasatlx_en.txt`
- Create: `scenarios/suas/reference_area_search.yaml`
- Create: `tests/suas/conftest.py`
- Create: `tests/suas/test_scenario_schema.py`

**Interfaces:**
- Consumes: Phase 1 Task 1 domain definitions and canonical serialization.
- Produces: `LoadedScenario`, `load_scenario()`, `load_scenario_text()`, `block_order_for_participant()`, `build_session_manifest()`, and a valid bundled `reference_area_search` scenario containing PRACTICE/LOW/MEDIUM/HIGH blocks.

- [ ] **Step 1: Add failing schema and normalization tests**

```python
# tests/suas/test_scenario_schema.py
from pathlib import Path
import pytest
from pydantic import ValidationError

from matb_integration.suas.domain.enums import Locale, WorkloadProfile
from matb_integration.suas.scenarios.loader import load_scenario, load_scenario_text
from matb_integration.suas.scenarios.manifest import build_session_manifest

REFERENCE = Path("scenarios/suas/reference_area_search.yaml")

def test_reference_scenario_normalizes_all_profiles() -> None:
    loaded = load_scenario(REFERENCE)
    assert loaded.definition.scenario_id == "reference_area_search"
    assert set(loaded.definition.blocks) == {p.value for p in WorkloadProfile}
    assert len(loaded.definition.aircraft) == 8
    assert len(loaded.definition.contacts) == 12
    assert loaded.normalized_yaml.endswith("\n")
    assert len(loaded.sha256) == 64

def test_unknown_key_fails_closed() -> None:
    raw = REFERENCE.read_text(encoding="utf-8") + "unexpected_root_key: true\n"
    with pytest.raises(ValidationError, match="unexpected_root_key"):
        load_scenario_text(raw)

def test_cross_reference_and_energy_feasibility_are_validated() -> None:
    raw = REFERENCE.read_text(encoding="utf-8").replace("UAS-08", "UAS-99", 1)
    with pytest.raises(ValueError, match="unknown aircraft"):
        load_scenario_text(raw)

def test_session_manifest_is_stable_and_session_specific() -> None:
    loaded = load_scenario(REFERENCE)
    order = (WorkloadProfile.LOW, WorkloadProfile.MEDIUM, WorkloadProfile.HIGH)
    manifest = build_session_manifest(
        loaded, participant_id="P01", visit_ordinal=1, locale=Locale.ES_CO,
        block_order=order, ui_version="0.1.0",
    )
    assert manifest["scenario_sha256"] == loaded.sha256
    assert manifest["participant_id"] == "P01"
    assert manifest["locale"] == "es-CO"
    assert manifest["block_order"] == ["LOW", "MEDIUM", "HIGH"]

def test_native_latin_order_matches_existing_repository_contract() -> None:
    for number in range(100):
        participant_id = f"P{number:02d}"
        native = tuple(item.value for item in block_order_for_participant(participant_id))
        legacy = tuple(item.value for item in legacy_block_order(participant_id))
        assert native == legacy
```

- [ ] **Step 2: Run the schema tests and confirm missing-module failure**

Run: `python3 -m pytest tests/suas/test_scenario_schema.py -q`

Expected: FAIL importing `matb_integration.suas.scenarios.loader`.

- [ ] **Step 3: Add PyYAML and implement strict Pydantic input models**

Add `PyYAML>=6.0` to root `requirements.txt`. In `schema.py`, define all models with `model_config = ConfigDict(extra="forbid")` and constrained numeric fields:

```python
class LocalizedText(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    en: str = Field(min_length=1)
    es_co: str = Field(alias="es-CO", min_length=1)

class PointSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x_m: Decimal
    y_m: Decimal

class InitialViewSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    center: PointSpec
    width_m: Decimal = Field(gt=0)
    height_m: Decimal = Field(gt=0)

class PolygonSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    polygon_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    label: LocalizedText
    vertices: list[PointSpec] = Field(min_length=3)

class EnergySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capacity_units: int = Field(gt=0)
    initial_units: int = Field(gt=0)
    idle_units_per_s: int = Field(ge=0)
    transit_units_per_s: int = Field(gt=0)
    search_units_per_s: int = Field(gt=0)
    sensor_units_per_scan: int = Field(ge=0)
    reserve_margin: Decimal = Field(ge=0, le=1)

class SensorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    radius_m: Decimal = Field(gt=0)
    scan_interval_s: Decimal = Field(gt=0)
    detection_probability: Decimal = Field(ge=0, le=1)
    scans_to_inspectable: int = Field(ge=1)

class AircraftSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aircraft_id: str
    label: str
    home: PointSpec
    speed_mps: Decimal = Field(gt=0)
    return_speed_mps: Decimal = Field(gt=0)
    altitude_m: Decimal = Field(gt=0)
    initial_link: Literal["NOMINAL", "DEGRADED", "LOST"]
    initial_sensor: Literal["NOMINAL", "OFFLINE"]
    energy: EnergySpec
    sensor: SensorSpec

class ContactSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_id: str
    position: PointSpec
    truth: Literal["routine", "priority", "uncertain"]
    truth_priority: Literal["LOW", "MEDIUM", "HIGH"]
    required_report: bool

class LinkEventSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    block_id: str
    at_s: Decimal = Field(ge=0)
    aircraft_id: str
    state: Literal["DEGRADED", "LOST", "NOMINAL"]

class ConflictEventSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    block_id: str
    at_s: Decimal = Field(ge=0)
    aircraft_a: str
    aircraft_b: str
    convergence_point: PointSpec
    convergence_in_s: Decimal = Field(gt=0)

class SagatScheduleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    window_start_s: Decimal = Field(ge=0)
    window_end_s: Decimal = Field(gt=0)
    probe_bank: Literal["suas"]
    probe_ids: list[str] = Field(min_length=1)

class BlockSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_id: Literal["PRACTICE", "LOW", "MEDIUM", "HIGH"]
    duration_s: int = Field(gt=0)
    aircraft_ids: list[str] = Field(min_length=2, max_length=8)
    contact_ids: list[str] = Field(min_length=1)
    required_action_window_s: int = Field(gt=0)
    isa_interval_s: int = Field(gt=0)
    isa_times_s: list[Decimal] | None = None
    sagat: SagatScheduleSpec
    post_block_questionnaires: tuple[Literal["NASA_TLX", "BEDFORD"], Literal["NASA_TLX", "BEDFORD"]]

class TerminationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finish_at_duration: bool
    abort_when_all_aircraft_failed: bool

class MetricThresholdSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coverage_target_percent: Decimal = Field(gt=0, le=100)
    contact_effectiveness_target: Decimal = Field(gt=0, le=1)
    asset_preservation_target: Decimal = Field(gt=0, le=1)
    timeliness_target: Decimal = Field(gt=0, le=1)

class ScenarioSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    scenario_id: str
    title: LocalizedText
    author: str
    description: LocalizedText
    seed: int = Field(ge=0, le=2**63 - 1)
    terrain: PolygonSpec
    home_base: PointSpec
    initial_view: InitialViewSpec
    grid_cell_m: Decimal = Field(gt=0)
    advisory_separation_m: Decimal = Field(gt=0)
    critical_separation_m: Decimal = Field(gt=0)
    sectors: list[PolygonSpec] = Field(min_length=1)
    restricted_zones: list[PolygonSpec]
    aircraft: list[AircraftSpec] = Field(min_length=2, max_length=8)
    contacts: list[ContactSpec]
    blocks: list[BlockSpec] = Field(min_length=4, max_length=4)
    link_events: list[LinkEventSpec]
    conflict_events: list[ConflictEventSpec]
    report_note_codes: dict[str, LocalizedText]
    metric_thresholds: MetricThresholdSpec
    termination: TerminationSpec
```

- [ ] **Step 4: Implement safe loading, normalization, and all cross-field checks**

`load_scenario_text()` first rejects UTF-8 content over 1 MiB, NUL bytes, more than 50 YAML aliases, nesting deeper than 64 collections, scalar values over 64 KiB, and any string containing a URI scheme such as `http:`, `https:`, `ftp:`, or `file:`. Use a capped subclass of `yaml.SafeLoader`; never call `yaml.load` with the default/unsafe loader. It then performs this exact semantic pipeline:

```python
raw = yaml.safe_load(text)
if not isinstance(raw, dict):
    raise ValueError(f"{source_name}: scenario root must be a mapping")
spec = ScenarioSpec.model_validate(raw)
normalized_document = canonicalize_spec_document(spec)
normalized_yaml = yaml.safe_dump(
    normalized_document, allow_unicode=True, sort_keys=True,
    default_flow_style=False,
)
scenario_sha256 = sha256_text(normalized_yaml)
definition = normalize_scenario(spec, scenario_sha256=scenario_sha256)
return LoadedScenario(
    definition=definition,
    normalized_document=normalized_document,
    normalized_yaml=normalized_yaml,
    sha256=scenario_sha256,
)
```

`canonicalize_spec_document()` returns schema-reloadable data: every `Decimal` becomes its non-exponent canonical decimal string; aircraft, contacts, sectors, restricted zones, blocks, link events, conflict events, and mapping keys are sorted by stable ID; polygon vertex order, questionnaire order, and probe order are preserved because they are semantic. Therefore equivalent harmless YAML ordering/number spelling produces the same normalized YAML/hash.

Domain normalization converts `Decimal` metres to integer millimetres with round-half-even, seconds to integer milliseconds, probabilities/margins/metric thresholds to integer parts per million, and lists to ID-keyed read-only mappings. If `isa_times_s` is absent, derive all positive interval multiples strictly before block duration; if present, preserve its sorted unique values in `isa_times_ms` while retaining `isa_interval_ms` as manipulation metadata. Reject every cross-field case enumerated in Design §6, including duplicate IDs, unknown block references, event/ISA time outside block, empty or duplicate ISA schedules, SAGAT window outside block, unsupported probe IDs, duplicate/missing post-block questionnaires, home/contacts/aircraft outside terrain, initial view outside terrain, restricted geometry that blocks departure, self-intersecting polygons, invalid threshold order, and nominal inability to reach the furthest assigned sector and return with reserve. `profiles.py` defines the closed nine-ID sUAS probe registry used for structural validation; Phase 5 validates the corresponding bilingual evaluator banks.

- [ ] **Step 5: Add the exact bundled instrument assets, reference scenario, and manifest builder**

In `profiles.py`, define the same six explicit LOW/MEDIUM/HIGH permutations as the existing repository Latin square and map the numeric participant suffix by `n % 6`; the sUAS product module must not import the OpenMATB builder, while the parity test may import it as `legacy_block_order`.

Create the two schema-valid sUAS SAGAT YAML banks with three probes per SA level, functionally equivalent English/es-CO questions, option-source IDs rather than hidden answers, and 15 s timeouts. The exact ID/evaluator set is `suas_l1_lost_links`, `suas_l1_lowest_battery`, `suas_l1_unreported`, `suas_l2_largest_gap`, `suas_l2_attention`, `suas_l2_mission_state`, `suas_l3_reserve_first`, `suas_l3_next_sector`, and `suas_l3_conflict_risk`; evaluator IDs equal probe IDs. Create sUAS ISA text assets with range `1/10/5`. Create the missing English NASA-TLX text asset with the same six-row order/range as `nasatlx_es.txt`: mental, physical, temporal, performance, effort, frustration, each `0/10/5`. Do not change legacy `isa_en.txt`, `isa_es.txt`, or generic SAGAT assets because existing OpenMATB scenarios depend on them.

Create `scenarios/suas/reference_area_search.yaml` with:

- fictional rectangular terrain `0..12000 m × 0..8000 m` and home `(600, 4000)`;
- four non-overlapping rectangular search sectors and two restricted polygons;
- aircraft `UAS-01` through `UAS-08` with common synthetic performance;
- contacts `C-01` through `C-12` using only `routine`, `priority`, and `uncertain` truth;
- PRACTICE/LOW/MEDIUM/HIGH rows exactly matching Design §9.2;
- one three-probe SAGAT set per block containing exactly one L1, one L2, and one L3 ID from the bundled sUAS banks;
- 0/0/1/2 lost-link events and 0/1/2/3 conflict injections for PRACTICE/LOW/MEDIUM/HIGH, with all recovery events explicit;
- bilingual report note codes `observed`, `needs_review`, and `completed`;
- thresholds for coverage, contact effectiveness, asset preservation, and timeliness.

`build_session_manifest()` must include `manifest_version=1`, scenario/schema/engine/UI versions, normalized scenario hash, participant/visit/locale/block order, exact block parameters, and SHA-256 values for both sUAS SAGAT banks, both sUAS ISA assets, English/Spanish NASA-TLX, and English/Spanish Bedford assets. Retain legacy OpenMATB questionnaire hashes under a separate `legacy_questionnaire_assets` key; native and legacy inventories never overwrite one another.

Create `tests/suas/conftest.py` with session-scoped `loaded_scenario` and `reference_scenario` fixtures. It must import only loader/domain code available after Task 2; Task 3 extends it with a function-scoped `reference_world` fixture once the synthetic backend exists.

- [ ] **Step 6: Run focused and root scenario tests**

Run: `python3 -m pytest tests/suas/test_scenario_schema.py tests/test_scenario_builder.py tests/test_scenario_manifest.py -q`

Expected: PASS.

- [ ] **Step 7: Commit and push Task 2**

```bash
git add requirements.txt matb_integration/suas/scenarios matb_integration/questionnaires/sagat_suas_en.yaml matb_integration/questionnaires/sagat_suas_es.yaml matb_integration/questionnaires/isa_suas_en.txt matb_integration/questionnaires/isa_suas_es.txt matb_integration/questionnaires/nasatlx_en.txt scenarios/suas tests/suas/conftest.py tests/suas/test_scenario_schema.py
git diff --cached --check
git commit -m "feat(suas): add strict reference scenario schema"
git push origin HEAD
```

### Task 3: PCG32 streams, fixed clock, search routes, movement, and energy

**Files:**
- Create: `matb_integration/suas/engine/__init__.py`
- Create: `matb_integration/suas/engine/clock.py`
- Create: `matb_integration/suas/engine/prng.py`
- Create: `matb_integration/suas/engine/routes.py`
- Create: `matb_integration/suas/adapters/__init__.py`
- Create: `matb_integration/suas/adapters/base.py`
- Create: `matb_integration/suas/adapters/synthetic.py`
- Create: `tests/suas/test_prng_clock.py`
- Create: `tests/suas/test_routes_vehicle.py`
- Modify: `tests/suas/conftest.py`
- Modify: `tests/suas/helpers.py`

**Interfaces:**
- Consumes: `ScenarioDefinition`, `BlockDefinition`, `WorldState`, geometry primitives.
- Produces: `PCG32`, `PCG32.get_state()/set_state()`, `derive_stream_seed()`, `SimulationClock`, `lawnmower_route()`, `VehicleBackend`, and `SyntheticVehicleBackend`.

- [ ] **Step 1: Write failing deterministic-vector, route, movement, and energy tests**

```python
# tests/suas/test_prng_clock.py
def test_pcg32_reference_vector_and_stream_independence() -> None:
    rng = PCG32(seed=42, stream=54)
    assert [rng.next_uint32() for _ in range(6)] == [
        0xA15C02B7, 0x7B47F409, 0xBA1D3330,
        0x83D2F293, 0xBFA4784B, 0xCBED606E,
    ]
    assert derive_stream_seed(7, "sensor", "UAS-01:C-01") != derive_stream_seed(
        7, "sensor", "UAS-02:C-01"
    )

def test_clock_advances_only_in_exact_100_ms_ticks() -> None:
    clock = SimulationClock()
    assert [clock.advance() for _ in range(3)] == [100, 200, 300]
    clock.pause()
    assert clock.advance() == 300

def test_pcg_state_round_trip_continues_exact_stream() -> None:
    rng = PCG32(seed=42, stream=54)
    rng.next_uint32()
    saved = rng.get_state()
    expected = [rng.next_uint32() for _ in range(4)]
    restored = PCG32.from_state(saved)
    assert [restored.next_uint32() for _ in range(4)] == expected

# tests/suas/test_routes_vehicle.py
def test_lawnmower_route_is_inside_sector_and_alternates() -> None:
    sector = rectangle(0, 0, 4_000_000, 2_000_000)
    route = lawnmower_route(sector, spacing_mm=500_000)
    assert len(route.waypoints) == 8
    assert all(sector.contains(point) for point in route.waypoints)
    assert route.waypoints[0].x_mm < route.waypoints[1].x_mm
    assert route.waypoints[2].x_mm > route.waypoints[3].x_mm

def test_vehicle_step_is_fixed_point_and_energy_exact(reference_scenario) -> None:
    backend = SyntheticVehicleBackend()
    state = backend.initialize(reference_scenario, reference_scenario.blocks["LOW"])
    state.aircraft["UAS-01"].route = Route((PointMM(1_600_000, 4_000_000),))
    state.aircraft["UAS-01"].mode = AircraftMode.TRANSIT
    before = state.aircraft["UAS-01"].energy_units
    for _ in range(10):
        state, _ = backend.advance(state, tick_ms=100)
    assert state.aircraft["UAS-01"].position.x_mm == 620_000
    assert state.aircraft["UAS-01"].energy_units == before - 40
```

The reference aircraft speed/energy values in YAML must make the asserted one-second movement and consumption exact; keep the expected values synchronized with the fixture.

Extend `tests/suas/conftest.py` with a fresh `reference_world` per test, initialized from `reference_scenario.blocks["LOW"]`. Add the route geometry helper to `tests/suas/helpers.py`; every test snippet imports helpers explicitly.

- [ ] **Step 2: Run focused tests and confirm missing engine modules**

Run: `python3 -m pytest tests/suas/test_prng_clock.py tests/suas/test_routes_vehicle.py -q`

Expected: FAIL importing `matb_integration.suas.engine.prng`.

- [ ] **Step 3: Implement PCG32 and named stream derivation**

```python
MASK_64 = (1 << 64) - 1
PCG_MULTIPLIER = 6364136223846793005

class PCG32:
    def __init__(self, *, seed: int, stream: int) -> None:
        self._state = 0
        self._increment = ((stream << 1) | 1) & MASK_64
        self.next_uint32()
        self._state = (self._state + seed) & MASK_64
        self.next_uint32()

    def next_uint32(self) -> int:
        old = self._state
        self._state = (old * PCG_MULTIPLIER + self._increment) & MASK_64
        xorshifted = (((old >> 18) ^ old) >> 27) & 0xFFFFFFFF
        rotation = (old >> 59) & 31
        return ((xorshifted >> rotation) |
                (xorshifted << ((-rotation) & 31))) & 0xFFFFFFFF

    def bernoulli_ppm(self, probability_ppm: int) -> bool:
        if not 0 <= probability_ppm <= 1_000_000:
            raise ValueError("probability_ppm must be in [0, 1000000]")
        threshold = (probability_ppm * (1 << 32)) // 1_000_000
        return self.next_uint32() < threshold

def derive_stream_seed(scenario_seed: int, subsystem: str, entity_id: str) -> tuple[int, int]:
    raw = f"{scenario_seed}\0{subsystem}\0{entity_id}".encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], "big"), int.from_bytes(digest[8:16], "big")
```

Keep the published PCG reference vector test; if this constructor differs from the vector, fix the constructor rather than changing expected output.

`get_state()` returns a frozen `PCG32State(state, increment)` with unsigned 64-bit integers. `from_state()`/`set_state()` validate the range and odd increment without advancing the stream. This state is private checkpoint data and never appears in public snapshots.

- [ ] **Step 4: Implement polygon scanline routes and the adapter protocol**

`lawnmower_route(sector, spacing_mm)` must scan from minimum Y to maximum Y, calculate integer segment intersections for each row, pair sorted intersections, emit alternating left-to-right/right-to-left endpoints, remove adjacent duplicates, and reject a spacing that yields fewer than two route points. The route must not enter restricted geometry; the caller validates candidate segments with `route_intersects_polygon()`.

```python
@runtime_checkable
class VehicleBackend(Protocol):
    def initialize(self, scenario: ScenarioDefinition, block: BlockDefinition) -> WorldState:
        raise NotImplementedError
    def advance(
        self, state: WorldState, *, tick_ms: int,
    ) -> tuple[WorldState, tuple[DomainEvent, ...]]:
        raise NotImplementedError
```

Both signatures must be implemented exactly by `SyntheticVehicleBackend`.

- [ ] **Step 5: Implement fixed-point vehicle movement and energy**

For each active aircraft in lexical ID order:

1. choose consumption rate from mode and add sensor scan charge when requested;
2. calculate `numerator = rate_per_s * tick_ms + energy_remainder`;
3. subtract `numerator // 1000`, retain `numerator % 1000`;
4. calculate movement budget the same way from speed;
5. advance along route legs with integer ratios and carried remainder;
6. change TRANSIT to SEARCH at the first completed sector route, RETURN_TO_BASE to RECOVERED at home, and energy exhaustion away from home to MISSION_FAILED;
7. emit state-change and energy-threshold events only on threshold crossings.

After movement, calculate direct nominal return cost with integer ceiling division:

```python
return_cost = ceil_div(distance_mm(position, home) * transit_units_per_s,
                       return_speed_mm_per_s)
margin_units = ceil_div(capacity_units * reserve_margin_ppm, 1_000_000)
predicted_home_reserve_units = energy_units - return_cost
```

Open the reserve advisory when predicted reserve first falls to or below `margin_units`; open critical when it first falls below zero. Close/downgrade only on the inverse boundary transition. Store the predicted reserve in authoritative state and expose it without floats. Initialize only `block.aircraft_ids`; raise `ValueError` for missing definitions. The synthetic adapter may mutate its owned `WorldState` internally but must return it and serialize only canonical copies.

- [ ] **Step 6: Run focused tests twice to detect hidden state leakage**

Run: `python3 -m pytest tests/suas/test_prng_clock.py tests/suas/test_routes_vehicle.py -q && python3 -m pytest tests/suas/test_prng_clock.py tests/suas/test_routes_vehicle.py -q`

Expected: both runs PASS with identical golden values.

- [ ] **Step 7: Commit and push Task 3**

```bash
git add matb_integration/suas/engine/clock.py matb_integration/suas/engine/prng.py matb_integration/suas/engine/routes.py matb_integration/suas/engine/__init__.py matb_integration/suas/adapters tests/suas/conftest.py tests/suas/helpers.py tests/suas/test_prng_clock.py tests/suas/test_routes_vehicle.py
git diff --cached --check
git commit -m "feat(suas): add fixed-step synthetic vehicle backend"
git push origin HEAD
```

### Task 4: Link behavior, sensor evidence, coverage, and contact workflow

**Files:**
- Create: `matb_integration/suas/engine/links.py`
- Create: `matb_integration/suas/engine/sensors.py`
- Create: `matb_integration/suas/engine/coverage.py`
- Create: `tests/suas/test_links.py`
- Create: `tests/suas/test_sensors_coverage.py`

**Interfaces:**
- Consumes: normalized scheduled link events, `PCG32`, `WorldState`, `SyntheticVehicleBackend` state.
- Produces: `LinkSystem`, `SensorSystem`, `CoverageGrid`, `apply_contact_action()`, and deterministic sensor/link domain events.

- [ ] **Step 1: Write failing lost-link and sensor isolation tests**

```python
def test_lost_link_holds_ten_seconds_then_returns_home(reference_world) -> None:
    links = LinkSystem(reference_scenario)
    links.force_state(reference_world, "UAS-01", LinkState.LOST, at_ms=1_000)
    assert reference_world.aircraft["UAS-01"].mode is AircraftMode.LOST_LINK_PROCEDURE
    links.step(reference_world, now_ms=10_900)
    assert reference_world.aircraft["UAS-01"].mode is AircraftMode.LOST_LINK_PROCEDURE
    links.step(reference_world, now_ms=11_000)
    assert reference_world.aircraft["UAS-01"].mode is AircraftMode.RETURN_TO_BASE

def test_sensor_stream_for_one_pair_does_not_perturb_another(
    reference_scenario, reference_world,
) -> None:
    baseline_world = deepcopy(reference_world)
    observed_world = deepcopy(reference_world)
    first = SensorSystem(reference_scenario)
    baseline = run_scans(first, baseline_world, pairs=[("UAS-01", "C-01")], count=5)
    second = SensorSystem(reference_scenario)
    run_scans(second, observed_world, pairs=[("UAS-08", "C-12")], count=99)
    observed = run_scans(second, observed_world, pairs=[("UAS-01", "C-01")], count=5)
    assert observed == baseline

def test_hidden_truth_never_appears_in_public_snapshot(reference_world) -> None:
    snapshot = public_snapshot(reference_world)
    assert "truth" not in snapshot["contacts"]["C-01"]
```

- [ ] **Step 2: Run the tests and confirm missing systems**

Run: `python3 -m pytest tests/suas/test_links.py tests/suas/test_sensors_coverage.py -q`

Expected: FAIL importing `LinkSystem` and `SensorSystem`.

- [ ] **Step 3: Implement scheduled links and safe recovery semantics**

`LinkSystem.step(state, now_ms)` applies each event exactly once by event ID. LOST stores `previous_mode`, changes to LOST_LINK_PROCEDURE, records `lost_link_since_ms`, rejects aircraft commands, holds for 10,000 ms, then installs a direct home route and changes to RETURN_TO_BASE. NOMINAL recovery clears the timestamp but does not resume SEARCH; recovery before RTB leaves HOLD, recovery after RTB begins leaves RETURN_TO_BASE until an explicit reassignment. Emit `LINK_STATE_CHANGED` and `LOST_LINK_PROCEDURE_STARTED` events.

- [ ] **Step 4: Implement deterministic observations and public contact state**

`SensorSystem` owns one PCG32 per `<aircraft-id>:<contact-id>`. On a due scan, it checks nominal sensor state, sensor radius, and link-independent sensor operation; a successful Bernoulli trial changes NONE→DETECTED on the first success and DETECTED→INSPECTABLE when `successful_scans == scans_to_inspectable`. Emit transition events only once. `public_snapshot()` returns contact ID, position only after DETECTED, evidence, workflow, operator classification/priority, and report IDs; it never serializes truth or required-report flags.

Implement `apply_contact_action()` with these gates:

```python
INSPECT_CONTACT: evidence == INSPECTABLE and workflow in {DETECTED, INSPECTED}
CLASSIFY_CONTACT: workflow in {INSPECTED, CLASSIFIED, PRIORITIZED, REPORTED}
SET_CONTACT_PRIORITY: workflow in {CLASSIFIED, PRIORITIZED, REPORTED}
REPORT_CONTACT: workflow in {PRIORITIZED, REPORTED}, both fields set, revision != last_reported_revision
```

Classification/priority changes increment `revision`. Each accepted action emits a workflow event; changing either field after REPORTED emits `CONTACT_CORRECTED` and makes the revised state reportable again. Every report receives a new stable report ID, stores `last_reported_revision`, and includes `replaces_report_id` for the previous immutable report while retaining full history.

- [ ] **Step 5: Implement deterministic coverage cells**

`CoverageGrid` derives integer cell coordinates from terrain bounds and `grid_cell_mm`. On each nominal sensor scan it marks cells whose centers lie within sensor radius and inside the assigned sector. It returns newly covered cells and cumulative per-sector counts. Store cells as `(x_index, y_index)` tuples; public snapshots expose sorted lists, covered/eligible counts, and integer `coverage_ppm = covered * 1_000_000 // eligible`, not Python sets or authoritative floats.

- [ ] **Step 6: Run focused tests and the whole sUAS suite**

Run: `python3 -m pytest tests/suas/test_links.py tests/suas/test_sensors_coverage.py tests/suas -q`

Expected: PASS.

- [ ] **Step 7: Commit and push Task 4**

```bash
git add matb_integration/suas/engine/links.py matb_integration/suas/engine/sensors.py matb_integration/suas/engine/coverage.py tests/suas/test_links.py tests/suas/test_sensors_coverage.py
git diff --cached --check
git commit -m "feat(suas): model links sensors and search coverage"
git push origin HEAD
```

### Task 5: Typed commands, reducer, separation, scheduled conflicts, runtime, and headless CLI

**Files:**
- Create: `matb_integration/suas/domain/commands.py`
- Create: `matb_integration/suas/engine/reducer.py`
- Create: `matb_integration/suas/engine/separation.py`
- Create: `matb_integration/suas/engine/runtime.py`
- Create: `matb_integration/suas/cli.py`
- Modify: `matb_integration/suas/__init__.py`
- Create: `tests/suas/test_commands.py`
- Create: `tests/suas/test_separation.py`
- Create: `tests/suas/test_runtime.py`
- Create: `tests/suas/test_cli.py`
- Modify: `tests/suas/helpers.py`

**Interfaces:**
- Consumes: every Phase 1 subsystem.
- Produces: the master-plan `SimulationEngine` and `StepResult` interfaces, typed commands/results, separation alerts, scheduled conflict injection, and `python -m matb_integration.suas.cli validate|run`.

- [ ] **Step 1: Write failing command, ordering, separation, and CLI tests**

```python
def test_command_applies_at_next_tick_and_rejects_stale_version(loaded_scenario) -> None:
    engine = SimulationEngine(loaded_scenario.definition, "LOW")
    accepted = envelope("cmd-1", expected=0, command=AssignSector("UAS-01", "SECTOR-A"))
    first = engine.step([accepted])
    assert first.command_results[0].status is CommandStatus.ACCEPTED
    assert first.command_results[0].applied_tick == 1
    stale = envelope("cmd-2", expected=0, command=Hold("UAS-01"))
    second = engine.step([stale])
    assert second.command_results[0].code == "stale_state_version"

def test_same_tick_events_have_stable_sequence(loaded_scenario) -> None:
    left = SimulationEngine(loaded_scenario.definition, "HIGH")
    right = SimulationEngine(loaded_scenario.definition, "HIGH")
    assert left.step().events == right.step().events
    assert left.state_hash == right.state_hash

def test_separation_alert_opens_and_closes_once(reference_world) -> None:
    monitor = SeparationMonitor(advisory_mm=300_000, critical_mm=150_000)
    place_pair(reference_world, 290_000)
    assert event_kinds(monitor.step(reference_world)) == ["SEPARATION_ADVISORY_OPENED"]
    assert monitor.step(reference_world) == ()
    place_pair(reference_world, 140_000)
    assert event_kinds(monitor.step(reference_world)) == ["SEPARATION_VIOLATION"]
    place_pair(reference_world, 400_000)
    assert event_kinds(monitor.step(reference_world)) == ["SEPARATION_ALERT_CLOSED"]

def test_cli_run_is_repeatable(tmp_path: Path) -> None:
    args = [sys.executable, "-m", "matb_integration.suas.cli", "run",
            "scenarios/suas/reference_area_search.yaml", "--block", "LOW",
            "--ticks", "100"]
    first = subprocess.run(args, check=True, capture_output=True, text=True)
    second = subprocess.run(args, check=True, capture_output=True, text=True)
    assert json.loads(first.stdout)["state_sha256"] == json.loads(second.stdout)["state_sha256"]
```

- [ ] **Step 2: Run the tests and confirm the command/runtime imports fail**

Run: `python3 -m pytest tests/suas/test_commands.py tests/suas/test_separation.py tests/suas/test_runtime.py tests/suas/test_cli.py -q`

Expected: FAIL importing `domain.commands` or `engine.runtime`.

- [ ] **Step 3: Implement the exact typed command union and results**

Use frozen slotted dataclasses for `AssignSector`, `SetWaypoint`, `Hold`, `ResumeMission`, `ReturnToBase`, `AcknowledgeAlert`, `InspectContact`, `ClassifyContact`, `SetContactPriority`, and `ReportContact`. Keep questionnaire submission types out of Phase 1; Phase 5 adds them without changing the envelope.

```python
@dataclass(frozen=True, slots=True)
class AssignSector:
    aircraft_id: str
    sector_id: str

@dataclass(frozen=True, slots=True)
class SetWaypoint:
    aircraft_id: str
    waypoint: PointMM

@dataclass(frozen=True, slots=True)
class Hold:
    aircraft_id: str

@dataclass(frozen=True, slots=True)
class ResumeMission:
    aircraft_id: str

@dataclass(frozen=True, slots=True)
class ReturnToBase:
    aircraft_id: str

@dataclass(frozen=True, slots=True)
class AcknowledgeAlert:
    alert_id: str

@dataclass(frozen=True, slots=True)
class InspectContact:
    contact_id: str

@dataclass(frozen=True, slots=True)
class ClassifyContact:
    contact_id: str
    classification: ContactClassification

@dataclass(frozen=True, slots=True)
class SetContactPriority:
    contact_id: str
    priority: ContactPriority

@dataclass(frozen=True, slots=True)
class ReportContact:
    contact_id: str
    note_code: str

OperatorCommand = (
    AssignSector | SetWaypoint | Hold | ResumeMission | ReturnToBase |
    AcknowledgeAlert | InspectContact | ClassifyContact |
    SetContactPriority | ReportContact
)

@dataclass(frozen=True, slots=True)
class CommandEnvelope:
    command_id: str
    expected_state_version: int
    command: OperatorCommand

class CommandStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"

@dataclass(frozen=True, slots=True)
class CommandResult:
    command_id: str
    status: CommandStatus
    code: str
    applied_tick: int | None
    state_version: int
```

The reducer validates link, mode, entity existence, geometry, restricted zones, and critical reserve. Assignment/waypoint/resume commands whose planned route would make predicted reserve negative are rejected; `RETURN_TO_BASE` remains allowed whenever the link/mode permits because it is the safe recovery command. It stores the first result by command ID and returns the original result with `status=DUPLICATE` on retry. Accepted commands update `last_accepted_command_id` and increment the state version exactly once; rejected/duplicate commands do not.

`WorldState.version` is a concurrency epoch, not the 10 Hz tick counter. Continuous position, heading, energy integration, and coverage accumulation change state/hash but do not advance this epoch. Each accepted command advances it once. After commands, each subsystem advances it once only when that subsystem's tick batch changes a command-relevant discrete field (mode, link, sensor/evidence/workflow, route ownership, or alert lifecycle). The reducer compares `expected_state_version` before autonomous systems run, and every command is fully revalidated against current truth at application. `WorldState.tick` and `simulation_time_ms` always advance independently, so the 4 Hz client can issue useful commands without treating ordinary movement as a concurrent edit.

Define `envelope()`, `place_pair()`, and `event_kinds()` in `tests/suas/helpers.py` and import them explicitly in the test modules; they construct only public Phase 1 types.

- [ ] **Step 4: Implement separation and scheduled conflict injection**

`SeparationMonitor` uses lexical aircraft-pair keys, opens advisory and critical events only on threshold transitions, records duration while below each threshold, and closes only after distance is at or above advisory. Scheduled conflict injection is applied once at its configured tick: it computes two routes through the normalized convergence point with the requested arrival interval and emits `CONFLICT_INJECTION_STARTED`. If an aircraft is recovered, failed, or lost-link at injection time, emit `CONFLICT_INJECTION_SKIPPED` with a stable reason instead of changing it.

- [ ] **Step 5: Implement `SimulationEngine` with the approved subsystem order**

```python
class SimulationEngine:
    def step(self, commands: Sequence[CommandEnvelope] = ()) -> StepResult:
        self._clock.advance()
        command_results, command_events = self._reducer.apply(
            self._state, commands, tick=self._clock.tick,
        )
        link_events = self._links.step(self._state, self._clock.time_ms)
        conflict_events = self._conflicts.step(self._state, self._clock.time_ms)
        self._state, vehicle_events = self._backend.advance(self._state, tick_ms=TICK_MS)
        sensor_events = self._sensors.step(self._state, self._clock.time_ms)
        coverage_events = self._coverage.step(self._state, self._clock.time_ms)
        separation_events = self._separation.step(self._state)
        events = self._sequence(
            command_events + link_events + conflict_events + vehicle_events +
            sensor_events + coverage_events + separation_events
        )
        return StepResult(self.snapshot(), events, command_results)
```

Initialize all subsystems once. `snapshot()` is the complete public-safe, sorted view used by `StepResult`, REST, and WebSocket. Its root includes scenario/block IDs, tick/time/version/hash, terrain bounds/polygon, home, initial view, sectors, restricted zones, localized labels/report-note codes, active aircraft, revealed contacts, alerts, and coverage. It never contains contact truth, truth priority, required-report flags, correct probe answers, future event schedules, PRNG state, or command lease data. Emit it on demand; Phase 3 controls 4 Hz transport.

`checkpoint_snapshot()` is private and contains engine/scenario/block versions, clock/tick/concurrency epoch, full world/contact state, every PCG32 state, applied link/conflict IDs, sensor due times, coverage, open/closed alert monitor state, and the command UUID/result cache. It includes `authoritative_state_sha256` computed over all fields except that hash. `restore()` accepts only this private shape, verifies scenario ID/hash, block ID, engine version, internal hash, entity sets, counter ranges, and PRNG increments before atomically replacing every subsystem; failure leaves the current engine unchanged. `state_hash` equals the checkpoint snapshot's authoritative hash, not the redacted public snapshot hash.

- [ ] **Step 6: Add the headless validation/run CLI**

`validate PATH` prints normalized scenario ID/hash/profile counts as JSON and exits 2 with the validation message on failure. `run PATH --block PROFILE --ticks N` validates positive `N`, advances without sleeping, and prints engine version, ticks, simulation time, event count, state SHA-256, and canonical final snapshot. It writes no files in Phase 1.

- [ ] **Step 7: Run Phase 1 focused, full root, and CLI smoke tests**

Run:

```bash
python3 -m pytest tests/suas -q
python3 -m pytest tests -q
python3 -m matb_integration.suas.cli validate scenarios/suas/reference_area_search.yaml
python3 -m matb_integration.suas.cli run scenarios/suas/reference_area_search.yaml --block HIGH --ticks 1000
```

Expected: all tests PASS; both CLI commands exit 0 and output valid JSON.

- [ ] **Step 8: Commit and push the Phase 1 gate**

```bash
git add matb_integration/suas/domain/commands.py matb_integration/suas/engine/reducer.py matb_integration/suas/engine/separation.py matb_integration/suas/engine/runtime.py matb_integration/suas/cli.py matb_integration/suas/__init__.py tests/suas/helpers.py tests/suas/test_commands.py tests/suas/test_separation.py tests/suas/test_runtime.py tests/suas/test_cli.py
git diff --cached --check
git commit -m "feat(suas): deliver deterministic headless mission core"
git push origin HEAD
```
