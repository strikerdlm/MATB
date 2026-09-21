"""Authoritative definitions and mutable runtime state for sUAS scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .enums import (
    AircraftMode,
    ContactClassification,
    ContactEvidence,
    ContactPriority,
    ContactWorkflow,
    LinkState,
    Locale,
    SensorState,
    WorkloadProfile,
)
from .events import AlertState
from .geometry import PointMM, PolygonMM


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
    route_leg_start: PointMM | None = None
    route_leg_target: PointMM | None = None
    route_leg_distance_mm: int = 0
    route_leg_progress_mm: int = 0


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
class SagatScheduleDefinition:
    window_start_ms: int
    window_end_ms: int
    probe_bank: str
    probe_ids: tuple[str, ...]


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
    swarm: Mapping[str, object] | None = field(default=None, metadata={"omit_none": True})


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
    # Checkpoint-safe scenario identity; defaults for legacy/manual world builders.
    scenario_sha256: str = ""
    swarms: dict[str, dict] | None = field(default=None, metadata={"omit_none": True})
