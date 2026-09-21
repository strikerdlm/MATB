"""Closed Pydantic input schema for declarative sUAS scenarios."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    post_block_questionnaires: tuple[
        Literal["NASA_TLX", "BEDFORD"], Literal["NASA_TLX", "BEDFORD"]
    ]


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


class SwarmGroupSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    aircraft_ids: list[str] = Field(min_length=1, max_length=8)


class SwarmSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    algorithm: Literal["fixed-slot-v1"] = "fixed-slot-v1"
    spacing_m: Decimal = Field(gt=0)
    groups: list[SwarmGroupSpec] = Field(min_length=1, max_length=8)


class ScenarioSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1, 2]
    swarm: SwarmSpec | None = None
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
