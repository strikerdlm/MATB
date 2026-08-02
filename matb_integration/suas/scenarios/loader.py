"""Safe loading, semantic validation, and deterministic normalization of sUAS YAML."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any

import yaml
from yaml.events import AliasEvent, MappingStartEvent, ScalarEvent, SequenceStartEvent

from matb_integration.suas.domain.enums import (
    ContactClassification, ContactPriority, LinkState, Locale, SensorState,
    WorkloadProfile,
)
from matb_integration.suas.domain.geometry import (
    PointMM, PolygonMM, distance_mm, polygon_within_polygon,
)
from matb_integration.suas.domain.models import (
    AircraftDefinition, BlockDefinition, ConflictEventDefinition, ContactDefinition,
    EnergyDefinition, InitialViewDefinition, LinkEventDefinition,
    MetricThresholdDefinition, SagatScheduleDefinition, ScenarioDefinition,
    SensorDefinition, TerminationDefinition,
)
from matb_integration.suas.domain.scenario_context import register_scenario

from .profiles import SUAS_PROBE_IDS
from .schema import PointSpec, PolygonSpec, ScenarioSpec

MAX_YAML_BYTES = 1 << 20
MAX_YAML_ALIASES = 50
MAX_YAML_DEPTH = 64
MAX_YAML_SCALAR_BYTES = 64 << 10
_URI_SCHEME = re.compile(r"(?i)\b(?:[a-z][a-z0-9+.-]{0,31}):")


class _CappedSafeLoader(yaml.SafeLoader):
    """SafeLoader with explicit alias, nesting, scalar, and URI caps."""

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self._alias_count = 0
        self._collection_depth = 0

    def compose_node(self, parent: Any, index: Any) -> Any:
        event = self.peek_event()
        if isinstance(event, AliasEvent):
            self._alias_count += 1
            if self._alias_count > MAX_YAML_ALIASES:
                raise ValueError(f"scenario contains more than {MAX_YAML_ALIASES} YAML aliases")
        if isinstance(event, ScalarEvent):
            scalar = event.value
            if len(scalar.encode("utf-8")) > MAX_YAML_SCALAR_BYTES:
                raise ValueError(f"scenario contains a scalar over {MAX_YAML_SCALAR_BYTES} bytes")
            if _URI_SCHEME.search(scalar):
                raise ValueError("scenario content may not contain a URI scheme")
        is_collection = isinstance(event, (MappingStartEvent, SequenceStartEvent))
        if is_collection:
            self._collection_depth += 1
            if self._collection_depth > MAX_YAML_DEPTH:
                raise ValueError(f"scenario nesting exceeds {MAX_YAML_DEPTH} collections")
        try:
            return super().compose_node(parent, index)
        finally:
            if is_collection:
                self._collection_depth -= 1


@dataclass(frozen=True, slots=True)
class LoadedScenario:
    definition: ScenarioDefinition
    normalized_document: dict[str, Any]
    normalized_yaml: str
    sha256: str


def sha256_text(text: str) -> str:
    """Return the SHA-256 digest of UTF-8 scenario text."""

    return sha256(text.encode("utf-8")).hexdigest()


def load_scenario(path: Path | str) -> LoadedScenario:
    """Read a UTF-8 local scenario file and return its frozen normalized form."""

    source_path = Path(path)
    raw = source_path.read_bytes()
    if len(raw) > MAX_YAML_BYTES:
        raise ValueError(f"{source_path}: scenario exceeds {MAX_YAML_BYTES} UTF-8 bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{source_path}: scenario must be UTF-8") from error
    return load_scenario_text(text, source_name=str(source_path))


def load_scenario_text(text: str, *, source_name: str = "<scenario>") -> LoadedScenario:
    """Parse and validate bounded YAML without ever enabling unsafe constructors."""

    try:
        byte_length = len(text.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise ValueError(f"{source_name}: scenario must be UTF-8") from error
    if byte_length > MAX_YAML_BYTES:
        raise ValueError(f"{source_name}: scenario exceeds {MAX_YAML_BYTES} UTF-8 bytes")
    if "\0" in text:
        raise ValueError(f"{source_name}: scenario contains a NUL byte")

    # _CappedSafeLoader subclasses SafeLoader; no Python-object tags are available.
    raw = yaml.load(text, Loader=_CappedSafeLoader)
    if not isinstance(raw, dict):
        raise ValueError(f"{source_name}: scenario root must be a mapping")
    spec = ScenarioSpec.model_validate(raw)
    _validate_semantics(spec, source_name=source_name)
    normalized_document = canonicalize_spec_document(spec)
    normalized_yaml = yaml.safe_dump(
        normalized_document, allow_unicode=True, sort_keys=True, default_flow_style=False,
    )
    scenario_sha256 = sha256_text(normalized_yaml)
    definition = normalize_scenario(spec, scenario_sha256=scenario_sha256)
    register_scenario(definition)
    return LoadedScenario(
        definition=definition,
        normalized_document=normalized_document,
        normalized_yaml=normalized_yaml,
        sha256=scenario_sha256,
    )


def canonicalize_spec_document(spec: ScenarioSpec) -> dict[str, Any]:
    """Return schema-reloadable, order-normalized document data for hashing."""

    document = spec.model_dump(by_alias=True)
    for key, id_key in (
        ("aircraft", "aircraft_id"), ("contacts", "contact_id"),
        ("sectors", "polygon_id"), ("restricted_zones", "polygon_id"),
        ("blocks", "block_id"), ("link_events", "event_id"),
        ("conflict_events", "event_id"),
    ):
        document[key] = sorted(document[key], key=lambda item: item[id_key])
    return _canonicalize_value(document)


def normalize_scenario(spec: ScenarioSpec, *, scenario_sha256: str) -> ScenarioDefinition:
    """Convert validated Decimal input into immutable integer-only domain values."""

    terrain = _polygon(spec.terrain)
    sectors = _readonly_by_id(spec.sectors, "polygon_id", _polygon)
    restricted = _readonly_by_id(spec.restricted_zones, "polygon_id", _polygon)
    aircraft = MappingProxyType({item.aircraft_id: AircraftDefinition(
        aircraft_id=item.aircraft_id,
        label=item.label,
        home=_point(item.home),
        speed_mm_per_s=_scaled(item.speed_mps, 1_000),
        return_speed_mm_per_s=_scaled(item.return_speed_mps, 1_000),
        altitude_mm=_scaled(item.altitude_m, 1_000),
        initial_link=LinkState(item.initial_link),
        initial_sensor=SensorState(item.initial_sensor),
        energy=EnergyDefinition(
            capacity_units=item.energy.capacity_units,
            initial_units=item.energy.initial_units,
            idle_units_per_s=item.energy.idle_units_per_s,
            transit_units_per_s=item.energy.transit_units_per_s,
            search_units_per_s=item.energy.search_units_per_s,
            sensor_units_per_scan=item.energy.sensor_units_per_scan,
            reserve_margin_ppm=_scaled(item.energy.reserve_margin, 1_000_000),
        ),
        sensor=SensorDefinition(
            radius_mm=_scaled(item.sensor.radius_m, 1_000),
            scan_interval_ms=_scaled(item.sensor.scan_interval_s, 1_000),
            detection_probability_ppm=_scaled(item.sensor.detection_probability, 1_000_000),
            scans_to_inspectable=item.sensor.scans_to_inspectable,
        ),
    ) for item in sorted(spec.aircraft, key=lambda value: value.aircraft_id)})
    contacts = MappingProxyType({item.contact_id: ContactDefinition(
        contact_id=item.contact_id,
        position=_point(item.position),
        truth=ContactClassification(item.truth),
        truth_priority=ContactPriority(item.truth_priority),
        required_report=item.required_report,
    ) for item in sorted(spec.contacts, key=lambda value: value.contact_id)})
    blocks = MappingProxyType({item.block_id: BlockDefinition(
        block_id=item.block_id,
        profile=WorkloadProfile(item.block_id),
        duration_ms=item.duration_s * 1_000,
        aircraft_ids=tuple(item.aircraft_ids),
        contact_ids=tuple(item.contact_ids),
        required_action_window_ms=item.required_action_window_s * 1_000,
        isa_interval_ms=item.isa_interval_s * 1_000,
        isa_times_ms=tuple(_scaled(value, 1_000) for value in _isa_times(item)),
        sagat=SagatScheduleDefinition(
            window_start_ms=_scaled(item.sagat.window_start_s, 1_000),
            window_end_ms=_scaled(item.sagat.window_end_s, 1_000),
            probe_bank=item.sagat.probe_bank,
            probe_ids=tuple(item.sagat.probe_ids),
        ),
        post_block_questionnaires=tuple(item.post_block_questionnaires),
    ) for item in sorted(spec.blocks, key=lambda value: value.block_id)})
    link_events = tuple(LinkEventDefinition(
        event_id=item.event_id, block_id=item.block_id, at_ms=_scaled(item.at_s, 1_000),
        aircraft_id=item.aircraft_id, state=LinkState(item.state),
    ) for item in sorted(spec.link_events, key=lambda value: value.event_id))
    conflict_events = tuple(ConflictEventDefinition(
        event_id=item.event_id, block_id=item.block_id, at_ms=_scaled(item.at_s, 1_000),
        aircraft_a=item.aircraft_a, aircraft_b=item.aircraft_b,
        convergence_point=_point(item.convergence_point),
        convergence_in_ms=_scaled(item.convergence_in_s, 1_000),
    ) for item in sorted(spec.conflict_events, key=lambda value: value.event_id))
    return ScenarioDefinition(
        schema_version=spec.schema_version,
        scenario_id=spec.scenario_id,
        scenario_sha256=scenario_sha256,
        title=_localized(spec.title.en, spec.title.es_co),
        author=spec.author,
        description=_localized(spec.description.en, spec.description.es_co),
        seed=spec.seed,
        terrain=terrain,
        home=_point(spec.home_base),
        initial_view=InitialViewDefinition(
            center=_point(spec.initial_view.center),
            width_mm=_scaled(spec.initial_view.width_m, 1_000),
            height_mm=_scaled(spec.initial_view.height_m, 1_000),
        ),
        grid_cell_mm=_scaled(spec.grid_cell_m, 1_000),
        advisory_separation_mm=_scaled(spec.advisory_separation_m, 1_000),
        critical_separation_mm=_scaled(spec.critical_separation_m, 1_000),
        sectors=sectors,
        restricted_zones=restricted,
        aircraft=aircraft,
        contacts=contacts,
        blocks=blocks,
        link_events=link_events,
        conflict_events=conflict_events,
        report_note_codes=MappingProxyType({key: _localized(value.en, value.es_co)
                                            for key, value in sorted(spec.report_note_codes.items())}),
        metric_thresholds=MetricThresholdDefinition(
            coverage_target_ppm=_scaled(spec.metric_thresholds.coverage_target_percent, 10_000),
            contact_effectiveness_target_ppm=_scaled(spec.metric_thresholds.contact_effectiveness_target, 1_000_000),
            asset_preservation_target_ppm=_scaled(spec.metric_thresholds.asset_preservation_target, 1_000_000),
            timeliness_target_ppm=_scaled(spec.metric_thresholds.timeliness_target, 1_000_000),
        ),
        termination=TerminationDefinition(
            finish_at_duration=spec.termination.finish_at_duration,
            abort_when_all_aircraft_failed=spec.termination.abort_when_all_aircraft_failed,
        ),
    )


def _validate_semantics(spec: ScenarioSpec, *, source_name: str) -> None:
    terrain = _polygon(spec.terrain)
    if spec.critical_separation_m >= spec.advisory_separation_m:
        raise ValueError(f"{source_name}: critical separation must be less than advisory separation")
    _require_unique((polygon.polygon_id for polygon in [spec.terrain, *spec.sectors, *spec.restricted_zones]), "polygon")
    _require_unique((item.aircraft_id for item in spec.aircraft), "aircraft")
    _require_unique((item.contact_id for item in spec.contacts), "contact")
    _require_unique((item.block_id for item in spec.blocks), "block")
    _require_unique((item.event_id for item in [*spec.link_events, *spec.conflict_events]), "event")
    if {block.block_id for block in spec.blocks} != {profile.value for profile in WorkloadProfile}:
        raise ValueError(f"{source_name}: blocks must include PRACTICE, LOW, MEDIUM, and HIGH exactly once")
    _require_points_within(terrain, [spec.home_base], "home base")
    _require_points_within(terrain, [aircraft.home for aircraft in spec.aircraft], "aircraft home")
    _require_points_within(terrain, [contact.position for contact in spec.contacts], "contact")
    polygons = [*spec.sectors, *spec.restricted_zones]
    for polygon in polygons:
        _require_polygon_within_terrain(terrain, polygon)
    _validate_initial_view(terrain, spec)
    restricted = [_polygon(value) for value in spec.restricted_zones]
    homes = [_point(spec.home_base), *(_point(item.home) for item in spec.aircraft)]
    if any(zone.contains(home) for zone in restricted for home in homes):
        raise ValueError(f"{source_name}: restricted geometry blocks departure from home base")
    aircraft_ids = {item.aircraft_id for item in spec.aircraft}
    contact_ids = {item.contact_id for item in spec.contacts}
    blocks = {item.block_id: item for item in spec.blocks}
    for aircraft in spec.aircraft:
        if aircraft.energy.initial_units > aircraft.energy.capacity_units:
            raise ValueError(f"{source_name}: aircraft {aircraft.aircraft_id} initial energy exceeds capacity")
    for block in spec.blocks:
        _require_unique(block.aircraft_ids, f"block {block.block_id} aircraft")
        _require_unique(block.contact_ids, f"block {block.block_id} contact")
        unknown_aircraft = set(block.aircraft_ids) - aircraft_ids
        unknown_contacts = set(block.contact_ids) - contact_ids
        if unknown_aircraft:
            raise ValueError(f"{source_name}: block {block.block_id} references unknown aircraft {sorted(unknown_aircraft)[0]}")
        if unknown_contacts:
            raise ValueError(f"{source_name}: block {block.block_id} references unknown contact {sorted(unknown_contacts)[0]}")
        isa_times = _isa_times(block)
        if not isa_times:
            raise ValueError(f"{source_name}: block {block.block_id} has an empty ISA schedule")
        if len(isa_times) != len(set(isa_times)):
            raise ValueError(f"{source_name}: block {block.block_id} has duplicate ISA times")
        if any(value <= 0 or value >= block.duration_s for value in isa_times):
            raise ValueError(f"{source_name}: block {block.block_id} ISA time is outside the block")
        if block.sagat.window_start_s >= block.sagat.window_end_s or block.sagat.window_end_s > block.duration_s:
            raise ValueError(f"{source_name}: block {block.block_id} SAGAT window is outside the block")
        _require_unique(block.sagat.probe_ids, f"block {block.block_id} SAGAT probe")
        unsupported = set(block.sagat.probe_ids) - SUAS_PROBE_IDS
        if unsupported:
            raise ValueError(f"{source_name}: unsupported SAGAT probe {sorted(unsupported)[0]}")
        if set(block.post_block_questionnaires) != {"NASA_TLX", "BEDFORD"}:
            raise ValueError(f"{source_name}: block {block.block_id} must include NASA_TLX and BEDFORD once")
    for event in spec.link_events:
        _validate_event_time(event.block_id, event.at_s, blocks, source_name, event.event_id)
        if event.aircraft_id not in aircraft_ids:
            raise ValueError(f"{source_name}: link event {event.event_id} references unknown aircraft {event.aircraft_id}")
        if event.aircraft_id not in blocks[event.block_id].aircraft_ids:
            raise ValueError(f"{source_name}: link event {event.event_id} aircraft is not assigned to its block")
    for event in spec.conflict_events:
        _validate_event_time(event.block_id, event.at_s, blocks, source_name, event.event_id)
        if event.aircraft_a == event.aircraft_b:
            raise ValueError(f"{source_name}: conflict event {event.event_id} must use two aircraft")
        for aircraft_id in (event.aircraft_a, event.aircraft_b):
            if aircraft_id not in aircraft_ids:
                raise ValueError(f"{source_name}: conflict event {event.event_id} references unknown aircraft {aircraft_id}")
            if aircraft_id not in blocks[event.block_id].aircraft_ids:
                raise ValueError(f"{source_name}: conflict event {event.event_id} aircraft is not assigned to its block")
        _require_points_within(terrain, [event.convergence_point], f"conflict event {event.event_id}")
    _validate_energy_feasibility(spec, source_name)


def _validate_energy_feasibility(spec: ScenarioSpec, source_name: str) -> None:
    sector_points = [point for sector in spec.sectors for point in sector.vertices]
    assigned = {aircraft_id for block in spec.blocks for aircraft_id in block.aircraft_ids}
    for aircraft in spec.aircraft:
        if aircraft.aircraft_id not in assigned:
            continue
        home = _point(aircraft.home)
        furthest_mm = max(distance_mm(home, _point(point)) for point in sector_points)
        outbound_s = Decimal(furthest_mm) / Decimal(1_000) / aircraft.speed_mps
        return_s = Decimal(furthest_mm) / Decimal(1_000) / aircraft.return_speed_mps
        use = (outbound_s + return_s) * Decimal(aircraft.energy.transit_units_per_s)
        reserve = Decimal(aircraft.energy.capacity_units) * aircraft.energy.reserve_margin
        if Decimal(aircraft.energy.initial_units) < use + reserve:
            raise ValueError(
                f"{source_name}: aircraft {aircraft.aircraft_id} cannot reach furthest assigned sector and return with reserve"
            )


def _validate_event_time(block_id: str, at_s: Decimal, blocks: Mapping[str, Any], source_name: str, event_id: str) -> None:
    if block_id not in blocks:
        raise ValueError(f"{source_name}: event {event_id} references unknown block {block_id}")
    if at_s >= blocks[block_id].duration_s:
        raise ValueError(f"{source_name}: event {event_id} time is outside block {block_id}")


def _validate_initial_view(terrain: PolygonMM, spec: ScenarioSpec) -> None:
    center = spec.initial_view.center
    half_width = spec.initial_view.width_m / 2
    half_height = spec.initial_view.height_m / 2
    rectangle = PolygonMM(tuple(_point(PointSpec(x_m=x, y_m=y)) for x, y in (
        (center.x_m - half_width, center.y_m - half_height),
        (center.x_m + half_width, center.y_m - half_height),
        (center.x_m + half_width, center.y_m + half_height),
        (center.x_m - half_width, center.y_m + half_height),
    )))
    if not terrain.contains(_point(center)) or not polygon_within_polygon(terrain, rectangle):
        raise ValueError("initial view is outside terrain")


def _require_points_within(terrain: PolygonMM, points: list[PointSpec], description: str) -> None:
    if any(not terrain.contains(_point(point)) for point in points):
        raise ValueError(f"{description} is outside terrain")


def _require_polygon_within_terrain(terrain: PolygonMM, polygon_spec: PolygonSpec) -> None:
    """Reject a polygon if any part lies outside the simple terrain polygon.

    Checking vertices alone fails for concave terrain: an edge may bridge an
    excluded notch while both endpoints are valid.  We split every candidate
    edge at all terrain-boundary intersections and check one exact rational
    midpoint from every resulting interval.  Thus each full edge, including
    portions between crossings, is contained.  For simple, hole-free polygons,
    a connected candidate whose complete boundary is contained is itself
    contained; otherwise a path from an exterior interior point to its boundary
    would cross the terrain boundary.
    """

    candidate = _polygon(polygon_spec)
    description = f"polygon {polygon_spec.polygon_id}"
    if any(not terrain.contains(vertex) for vertex in candidate.vertices):
        raise ValueError(f"{description} is outside terrain")
    terrain_edges = _polygon_edges(terrain.vertices)
    for start, end in _polygon_edges(candidate.vertices):
        parameters = {Fraction(0), Fraction(1)}
        for terrain_start, terrain_end in terrain_edges:
            parameters.update(_edge_intersection_parameters(start, end, terrain_start, terrain_end))
        ordered = sorted(parameters)
        for left, right in zip(ordered, ordered[1:]):
            if left == right:
                continue
            midpoint = _point_on_edge(start, end, (left + right) / 2)
            if not _contains_fractional_point(terrain, midpoint):
                raise ValueError(f"{description} is outside terrain")


def _polygon_edges(vertices: tuple[PointMM, ...]) -> tuple[tuple[PointMM, PointMM], ...]:
    return tuple((point, vertices[(index + 1) % len(vertices)]) for index, point in enumerate(vertices))


def _edge_intersection_parameters(
    start: PointMM,
    end: PointMM,
    boundary_start: PointMM,
    boundary_end: PointMM,
) -> tuple[Fraction, ...]:
    """Return exact positions on one edge where it meets a boundary edge."""

    dx, dy = end.x_mm - start.x_mm, end.y_mm - start.y_mm
    bx, by = boundary_end.x_mm - boundary_start.x_mm, boundary_end.y_mm - boundary_start.y_mm
    offset_x, offset_y = boundary_start.x_mm - start.x_mm, boundary_start.y_mm - start.y_mm
    denominator = _cross_components(dx, dy, bx, by)
    if denominator:
        edge_fraction = Fraction(_cross_components(offset_x, offset_y, bx, by), denominator)
        boundary_fraction = Fraction(_cross_components(offset_x, offset_y, dx, dy), denominator)
        if Fraction(0) <= edge_fraction <= Fraction(1) and Fraction(0) <= boundary_fraction <= Fraction(1):
            return (edge_fraction,)
        return ()
    if _cross_components(offset_x, offset_y, dx, dy):
        return ()
    edge_length_squared = dx * dx + dy * dy
    if edge_length_squared == 0:
        return ()
    first = Fraction(offset_x * dx + offset_y * dy, edge_length_squared)
    last = Fraction(
        (boundary_end.x_mm - start.x_mm) * dx + (boundary_end.y_mm - start.y_mm) * dy,
        edge_length_squared,
    )
    return tuple(
        value for value in (first, last)
        if Fraction(0) <= value <= Fraction(1)
    )


def _point_on_edge(start: PointMM, end: PointMM, fraction: Fraction) -> tuple[Fraction, Fraction]:
    return (
        Fraction(start.x_mm) + fraction * (end.x_mm - start.x_mm),
        Fraction(start.y_mm) + fraction * (end.y_mm - start.y_mm),
    )


def _contains_fractional_point(terrain: PolygonMM, point: tuple[Fraction, Fraction]) -> bool:
    """Inclusive point-in-polygon test retaining exact rational intersections."""

    x, y = point
    inside = False
    for start, end in _polygon_edges(terrain.vertices):
        if _fractional_point_on_segment(x, y, start, end):
            return True
        if (start.y_mm > y) != (end.y_mm > y):
            cross = (
                (end.x_mm - start.x_mm) * (y - start.y_mm)
                - (x - start.x_mm) * (end.y_mm - start.y_mm)
            )
            if (end.y_mm > start.y_mm and cross > 0) or (end.y_mm < start.y_mm and cross < 0):
                inside = not inside
    return inside


def _fractional_point_on_segment(
    x: Fraction, y: Fraction, start: PointMM, end: PointMM,
) -> bool:
    return (
        (end.x_mm - start.x_mm) * (y - start.y_mm)
        == (x - start.x_mm) * (end.y_mm - start.y_mm)
        and min(start.x_mm, end.x_mm) <= x <= max(start.x_mm, end.x_mm)
        and min(start.y_mm, end.y_mm) <= y <= max(start.y_mm, end.y_mm)
    )


def _cross_components(left_x: int, left_y: int, right_x: int, right_y: int) -> int:
    return left_x * right_y - left_y * right_x


def _require_unique(values: Any, description: str) -> None:
    collected = list(values)
    if len(collected) != len(set(collected)):
        raise ValueError(f"duplicate {description} ID")


def _isa_times(block: Any) -> list[Decimal]:
    if block.isa_times_s is not None:
        return sorted(block.isa_times_s)
    duration = Decimal(block.duration_s)
    interval = Decimal(block.isa_interval_s)
    time = interval
    values: list[Decimal] = []
    while time < duration:
        values.append(time)
        time += interval
    return values


def _point(point: PointSpec) -> PointMM:
    return PointMM(_scaled(point.x_m, 1_000), _scaled(point.y_m, 1_000))


def _polygon(polygon: PolygonSpec) -> PolygonMM:
    return PolygonMM(tuple(_point(point) for point in polygon.vertices))


def _scaled(value: Decimal, factor: int) -> int:
    return int((value * factor).to_integral_value(rounding=ROUND_HALF_EVEN))


def _localized(en: str, es_co: str) -> Mapping[Locale, str]:
    return MappingProxyType({Locale.EN: en, Locale.ES_CO: es_co})


def _readonly_by_id(items: list[Any], id_key: str, converter: Any) -> Mapping[str, Any]:
    return MappingProxyType({getattr(item, id_key): converter(item) for item in sorted(items, key=lambda value: getattr(value, id_key))})


def _canonical_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _canonicalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _canonical_decimal(value)
    if isinstance(value, dict):
        return {str(key): _canonicalize_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonicalize_value(item) for item in value]
    return value
