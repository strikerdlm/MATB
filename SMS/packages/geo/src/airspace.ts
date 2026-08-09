import { parseCoordinate, distanceM } from "./coordinates.js";
import type { Wgs84Coordinate } from "./coordinates.js";
import type { GeoFinding, GeoSafetyResult, RoutePlan } from "./types.js";

export type PolygonPoint = { lat: number; lon: number } | readonly [number, number];
export type AuthorityClass = "official" | "open-context" | "local-observation";

export interface AirspacePolygon {
  id: string;
  code: string;
  polygon: readonly PolygonPoint[];
  lowerAltitudeM?: number;
  upperAltitudeM?: number;
  altitudeReference?: "MSL" | "AGL";
  sourcePackageId: string;
  authorityClass: AuthorityClass;
  effectiveFromUtc?: string;
  effectiveToUtc?: string;
}

export interface NotamArea extends AirspacePolygon {
  notamId: string;
  effectiveFromUtc: string;
  effectiveToUtc: string;
}

export interface Intersection {
  layerId: string;
  code: string;
  segmentId: string;
  startUtc?: string;
  endUtc?: string;
  sourcePackageId: string;
}

export interface NotamMatch extends Intersection {
  notamId: string;
  effectiveFromUtc: string;
  effectiveToUtc: string;
}

export interface RouteAirspaceInput {
  route: RoutePlan;
  airspaces: readonly AirspacePolygon[];
  notams: readonly NotamArea[];
  nowUtc: string;
  requireOfficialAirspace?: boolean;
  requireCurrentNotams?: boolean;
  calculationVersion?: string;
}

export interface TimeWindow { fromUtc: string; toUtc: string; }
export type TimeWindowInput = TimeWindow | readonly [string, string];

const EPSILON = 1e-10;
const DEFAULT_CALCULATION_VERSION = "route-airspace-v1";
const UTC = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/;

function finite(value: unknown): value is number { return typeof value === "number" && Number.isFinite(value); }

function unique(values: readonly string[]): string[] { return [...new Set(values.filter((value) => value.trim() !== ""))]; }

function isExactUtc(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = UTC.exec(value);
  if (!match) return false;
  const [, year, month, day, hour, minute, second, fraction = ""] = match;
  const date = new Date(value);
  return Number.isFinite(date.getTime())
    && date.getUTCFullYear() === Number(year)
    && date.getUTCMonth() + 1 === Number(month)
    && date.getUTCDate() === Number(day)
    && date.getUTCHours() === Number(hour)
    && date.getUTCMinutes() === Number(minute)
    && date.getUTCSeconds() === Number(second)
    && date.getUTCMilliseconds() === Number(fraction.padEnd(3, "0") || 0);
}

function point(value: PolygonPoint): Wgs84Coordinate {
  if (Array.isArray(value)) return parseCoordinate({ lat: value[0], lon: value[1] });
  const object = value as { lat: number; lon: number };
  return parseCoordinate({ lat: object.lat, lon: object.lon });
}

function polygon(layer: AirspacePolygon): Wgs84Coordinate[] {
  return layer.polygon.map(point);
}

function cross(a: Wgs84Coordinate, b: Wgs84Coordinate, c: Wgs84Coordinate): number {
  return (b.lon - a.lon) * (c.lat - a.lat) - (b.lat - a.lat) * (c.lon - a.lon);
}

function between(value: number, left: number, right: number): boolean { return value >= Math.min(left, right) - EPSILON && value <= Math.max(left, right) + EPSILON; }

function onSegment(a: Wgs84Coordinate, b: Wgs84Coordinate, c: Wgs84Coordinate): boolean {
  return Math.abs(cross(a, b, c)) <= EPSILON && between(c.lat, a.lat, b.lat) && between(c.lon, a.lon, b.lon);
}

function segmentsIntersect(a: Wgs84Coordinate, b: Wgs84Coordinate, c: Wgs84Coordinate, d: Wgs84Coordinate): boolean {
  const first = cross(a, b, c);
  const second = cross(a, b, d);
  const third = cross(c, d, a);
  const fourth = cross(c, d, b);
  if (Math.abs(first) <= EPSILON && onSegment(a, b, c)) return true;
  if (Math.abs(second) <= EPSILON && onSegment(a, b, d)) return true;
  if (Math.abs(third) <= EPSILON && onSegment(c, d, a)) return true;
  if (Math.abs(fourth) <= EPSILON && onSegment(c, d, b)) return true;
  return (first > 0) !== (second > 0) && (third > 0) !== (fourth > 0);
}

function pointInPolygon(value: Wgs84Coordinate, area: readonly Wgs84Coordinate[]): boolean {
  for (let index = 0; index < area.length; index += 1) {
    const current = area[index];
    const next = area[(index + 1) % area.length];
    if (onSegment(current, next, value)) return true;
  }
  let inside = false;
  for (let index = 0, previous = area.length - 1; index < area.length; previous = index++) {
    const current = area[index];
    const prior = area[previous];
    const crosses = (current.lat > value.lat) !== (prior.lat > value.lat)
      && value.lon < (prior.lon - current.lon) * (value.lat - current.lat) / (prior.lat - current.lat) + current.lon;
    if (crosses) inside = !inside;
  }
  return inside;
}

function geometryIntersects(start: Wgs84Coordinate, end: Wgs84Coordinate, area: readonly Wgs84Coordinate[]): boolean {
  if (pointInPolygon(start, area) || pointInPolygon(end, area)) return true;
  for (let index = 0; index < area.length; index += 1) {
    if (segmentsIntersect(start, end, area[index], area[(index + 1) % area.length])) return true;
  }
  return false;
}

function altitudeIntersects(route: RoutePlan, fromAltitude: number, toAltitude: number, layer: AirspacePolygon): boolean {
  if (layer.altitudeReference !== undefined && layer.altitudeReference !== route.altitudeReference) return false;
  const lower = layer.lowerAltitudeM ?? Number.NEGATIVE_INFINITY;
  const upper = layer.upperAltitudeM ?? Number.POSITIVE_INFINITY;
  if (!finite(lower) && lower !== Number.NEGATIVE_INFINITY) return false;
  if (!finite(upper) && upper !== Number.POSITIVE_INFINITY) return false;
  if (lower > upper) return false;
  const routeLower = Math.min(fromAltitude, toAltitude);
  const routeUpper = Math.max(fromAltitude, toAltitude);
  return routeUpper >= lower && routeLower <= upper;
}

function routeSegmentPoints(route: RoutePlan, segmentId: string): { from: Wgs84Coordinate; to: Wgs84Coordinate; fromAltitude: number; toAltitude: number } | undefined {
  const segment = route.segments.find((candidate) => candidate.id === segmentId);
  if (segment === undefined) return undefined;
  const from = route.waypoints.find((waypoint) => waypoint.id === segment.fromWaypointId);
  const to = route.waypoints.find((waypoint) => waypoint.id === segment.toWaypointId);
  if (from === undefined || to === undefined) return undefined;
  return {
    from: point({ lat: from.lat, lon: from.lon }),
    to: point({ lat: to.lat, lon: to.lon }),
    fromAltitude: from.altitude,
    toAltitude: to.altitude,
  };
}

/** Intersect every validated route segment with polygon layers, including boundary touch. */
export function intersectRoute(route: RoutePlan, polygonLayers: readonly AirspacePolygon[]): Intersection[] {
  const intersections: Intersection[] = [];
  for (const segment of route.segments) {
    const geometry = routeSegmentPoints(route, segment.id);
    if (geometry === undefined) continue;
    for (const layer of polygonLayers) {
      let area: Wgs84Coordinate[];
      try { area = polygon(layer); } catch { continue; }
      if (area.length < 3 || !geometryIntersects(geometry.from, geometry.to, area) || !altitudeIntersects(route, geometry.fromAltitude, geometry.toAltitude, layer)) continue;
      intersections.push({
        layerId: layer.id,
        code: layer.code,
        segmentId: segment.id,
        ...(layer.effectiveFromUtc === undefined ? {} : { startUtc: layer.effectiveFromUtc }),
        ...(layer.effectiveToUtc === undefined ? {} : { endUtc: layer.effectiveToUtc }),
        sourcePackageId: layer.sourcePackageId,
      });
    }
  }
  return intersections;
}

function window(value: TimeWindowInput): TimeWindow | undefined {
  const result: TimeWindow = Array.isArray(value)
    ? { fromUtc: value[0], toUtc: value[1] }
    : value as TimeWindow;
  if (!isExactUtc(result.fromUtc) || !isExactUtc(result.toUtc) || Date.parse(result.fromUtc) >= Date.parse(result.toUtc)) return undefined;
  return result;
}

/** Match only NOTAM geometry whose effective period overlaps the requested mission window. */
export function matchNotams(route: RoutePlan, notams: readonly NotamArea[], windowUtc: TimeWindowInput): NotamMatch[] {
  const requested = window(windowUtc);
  if (requested === undefined) return [];
  const intersections = intersectRoute(route, notams);
  return intersections.flatMap((intersection) => {
    const notam = notams.find((candidate) => candidate.id === intersection.layerId);
    if (notam === undefined || !isExactUtc(notam.effectiveFromUtc) || !isExactUtc(notam.effectiveToUtc)) return [];
    const from = Math.max(Date.parse(requested.fromUtc), Date.parse(notam.effectiveFromUtc));
    const to = Math.min(Date.parse(requested.toUtc), Date.parse(notam.effectiveToUtc));
    if (from >= to) return [];
    return [{ ...intersection, notamId: notam.notamId, effectiveFromUtc: notam.effectiveFromUtc, effectiveToUtc: notam.effectiveToUtc }];
  });
}

function finding(code: string, severity: GeoFinding["severity"], concept: string, sourcePackageIds: readonly string[]): GeoFinding {
  return { code, severity, messageConceptId: concept, sourcePackageIds };
}

function activeAt(layer: AirspacePolygon, nowUtc: string): "active" | "inactive" | "unknown" {
  if (layer.effectiveFromUtc !== undefined && !isExactUtc(layer.effectiveFromUtc)) return "unknown";
  if (layer.effectiveToUtc !== undefined && !isExactUtc(layer.effectiveToUtc)) return "unknown";
  const now = Date.parse(nowUtc);
  if (layer.effectiveFromUtc !== undefined && now < Date.parse(layer.effectiveFromUtc)) return "inactive";
  if (layer.effectiveToUtc !== undefined && now >= Date.parse(layer.effectiveToUtc)) return "inactive";
  return "active";
}

/** Evaluate time/space/altitude airspace and NOTAM conflicts with authority-aware results. */
export function evaluateRouteAirspace(input: RouteAirspaceInput): GeoSafetyResult {
  const calculationVersion = input.calculationVersion ?? DEFAULT_CALCULATION_VERSION;
  const sourcePackageIds = unique([
    ...input.route.sourcePackageIds,
    ...input.airspaces.map((layer) => layer.sourcePackageId),
    ...input.notams.map((notam) => notam.sourcePackageId),
  ]);
  if (!isExactUtc(input.nowUtc)) return { status: "unknown", findings: [finding("AIRSPACE_TIME_UNKNOWN", "hard", "geo.airspace.time.unknown", sourcePackageIds)], sourcePackageIds, calculationVersion };

  const activeAirspaces: AirspacePolygon[] = [];
  let dataUnknown = false;
  for (const layer of input.airspaces) {
    const state = activeAt(layer, input.nowUtc);
    if (state === "unknown") dataUnknown = true;
    else if (state === "active") activeAirspaces.push(layer);
  }
  if (input.requireOfficialAirspace && !activeAirspaces.some((layer) => layer.authorityClass === "official")) dataUnknown = true;
  if (input.requireCurrentNotams && input.notams.length === 0) dataUnknown = true;

  const findings: GeoFinding[] = [];
  const officialIntersections = intersectRoute(input.route, activeAirspaces.filter((layer) => layer.authorityClass === "official"));
  for (const intersection of officialIntersections) findings.push(finding("AIRSPACE_CONFLICT", "hard", "geo.airspace.conflict", [intersection.sourcePackageId]));
  const advisoryIntersections = intersectRoute(input.route, activeAirspaces.filter((layer) => layer.authorityClass !== "official"));
  for (const intersection of advisoryIntersections) findings.push(finding("ADVISORY_AIRSPACE_CONFLICT", "warning", "geo.airspace.advisory.conflict", [intersection.sourcePackageId]));

  const notamIntersections = intersectRoute(input.route, input.notams);
  const currentNotams = matchNotams(input.route, input.notams, { fromUtc: input.nowUtc, toUtc: new Date(Date.parse(input.nowUtc) + 1_000).toISOString().replace(".000Z", "Z") });
  for (const intersection of notamIntersections) {
    const notam = input.notams.find((candidate) => candidate.id === intersection.layerId);
    if (notam === undefined) continue;
    const state = activeAt(notam, input.nowUtc);
    if (state === "unknown" || (state === "inactive" && Date.parse(notam.effectiveToUtc) <= Date.parse(input.nowUtc))) dataUnknown = true;
  }
  for (const match of currentNotams) {
    if (input.notams.find((notam) => notam.id === match.layerId)?.authorityClass === "official") findings.push(finding("NOTAM_CONFLICT", "hard", "geo.notam.conflict", [match.sourcePackageId]));
    else findings.push(finding("ADVISORY_NOTAM_CONFLICT", "warning", "geo.notam.advisory.conflict", [match.sourcePackageId]));
  }

  const status = dataUnknown ? "unknown" : findings.some((item) => item.severity === "hard") ? "blocked" : "pass";
  return { status, findings, sourcePackageIds, calculationVersion };
}
