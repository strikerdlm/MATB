import { distanceM, parseCoordinate } from "./coordinates.js";
import type { Wgs84Coordinate } from "./coordinates.js";
import type { GeoFinding, GeoSafetyResult, RoutePlan, Waypoint } from "./types.js";

export type TerrainCoverage = "covered" | "missing" | "expired";

export interface TerrainSample {
  elevationMslM: number;
  horizontalAccuracyM: number;
  verticalAccuracyM: number;
  sourcePackageId: string;
  sampledAtUtc: string;
  /** Optional explicit source metadata retained for audit and datum checks. */
  horizontalDatum?: string;
  verticalDatum?: string;
  resolutionM?: number;
}

export interface TerrainProvider {
  coverage(point: Wgs84Coordinate): TerrainCoverage;
  sample(point: Wgs84Coordinate): TerrainSample | null | Promise<TerrainSample | null>;
}

export interface Obstacle {
  id: string;
  lat: number;
  lon: number;
  elevationMslM: number;
  heightM: number;
  sourcePackageId: string;
  influenceRadiusM?: number;
  horizontalDatum?: string;
  verticalDatum?: string;
}

export interface ClearancePolicy {
  minimumTerrainClearanceM: number;
  minimumObstacleClearanceM: number;
  asOfUtc?: string;
  maxSampleAgeMinutes?: number;
  calculationVersion?: string;
}

interface RoutePoint {
  coordinate: Wgs84Coordinate;
  altitude: number;
  altitudeReference: "MSL" | "AGL";
}

interface SampleResult {
  sample?: TerrainSample;
  reason?: string;
}

const EPSG_4326 = "EPSG:4326";
const DEFAULT_CALCULATION_VERSION = "terrain-clearance-v1";
const UTC = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/;

function finite(value: unknown): value is number { return typeof value === "number" && Number.isFinite(value); }

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

function isThenable(value: unknown): value is PromiseLike<unknown> {
  return value !== null && typeof value === "object" && "then" in value && typeof value.then === "function";
}

function validSample(value: unknown): value is TerrainSample {
  if (value === null || typeof value !== "object") return false;
  const sample = value as TerrainSample;
  return finite(sample.elevationMslM)
    && finite(sample.horizontalAccuracyM)
    && sample.horizontalAccuracyM >= 0
    && finite(sample.verticalAccuracyM)
    && sample.verticalAccuracyM >= 0
    && typeof sample.sourcePackageId === "string"
    && sample.sourcePackageId.trim() !== ""
    && isExactUtc(sample.sampledAtUtc)
    && (sample.horizontalDatum === undefined || sample.horizontalDatum === EPSG_4326)
    && (sample.verticalDatum === undefined || sample.verticalDatum.trim() !== "")
    && (sample.resolutionM === undefined || (finite(sample.resolutionM) && sample.resolutionM > 0));
}

function pointForWaypoint(waypoint: Waypoint): RoutePoint {
  return {
    coordinate: parseCoordinate({ lat: waypoint.lat, lon: waypoint.lon }),
    altitude: waypoint.altitude,
    altitudeReference: waypoint.altitudeReference,
  };
}

function routePoints(route: RoutePlan): RoutePoint[] {
  const byId = new Map(route.waypoints.map((waypoint) => [waypoint.id, waypoint]));
  const points: RoutePoint[] = [];
  for (const waypoint of route.waypoints) points.push(pointForWaypoint(waypoint));
  for (const segment of route.segments) {
    const from = byId.get(segment.fromWaypointId);
    const to = byId.get(segment.toWaypointId);
    if (from === undefined || to === undefined) throw new Error(`segment ${segment.id} references an unknown waypoint`);
    points.push({
      coordinate: parseCoordinate({ lat: (from.lat + to.lat) / 2, lon: (from.lon + to.lon) / 2 }),
      altitude: (from.altitude + to.altitude) / 2,
      altitudeReference: route.altitudeReference,
    });
  }
  return points;
}

function sampleSynchronously(provider: TerrainProvider, point: Wgs84Coordinate, policy: ClearancePolicy): SampleResult {
  try {
    const coverage = provider.coverage(point);
    if (coverage !== "covered") return { reason: `terrain coverage is ${coverage}` };
    const result = provider.sample(point);
    if (isThenable(result)) return { reason: "terrain provider returned an asynchronous sample" };
    if (!validSample(result)) return { reason: "terrain sample metadata is invalid or incomplete" };
    if (policy.maxSampleAgeMinutes !== undefined) {
      if (!isExactUtc(policy.asOfUtc)) return { reason: "terrain freshness requires an exact UTC as-of time" };
      const ageMinutes = (Date.parse(policy.asOfUtc) - Date.parse(result.sampledAtUtc)) / 60_000;
      if (ageMinutes < 0 || ageMinutes > policy.maxSampleAgeMinutes) return { reason: "terrain sample is stale" };
    }
    return { sample: result };
  } catch (error) {
    return { reason: error instanceof Error ? error.message : String(error) };
  }
}

function finding(
  code: string,
  severity: GeoFinding["severity"],
  messageConceptId: string,
  sourcePackageIds: readonly string[],
  location?: Wgs84Coordinate,
): GeoFinding {
  return {
    code,
    severity,
    messageConceptId,
    sourcePackageIds,
    ...(location === undefined ? {} : { location: { lat: location.lat, lon: location.lon } }),
  };
}

function unique(values: readonly string[]): string[] { return [...new Set(values.filter((value) => value.trim() !== ""))]; }

/** Sample a terrain provider conservatively; missing or expired coverage is null, never zero elevation. */
export async function sampleTerrain(provider: TerrainProvider, coordinate: Wgs84Coordinate): Promise<TerrainSample | null> {
  const point = parseCoordinate(coordinate);
  try {
    if (provider.coverage(point) !== "covered") return null;
    const sample = await provider.sample(point);
    return validSample(sample) ? Object.freeze({ ...sample }) : null;
  } catch {
    return null;
  }
}

/** Evaluate all route waypoints and segment midpoints using an explicit MSL/AGL reference. */
export function evaluateClearance(
  route: RoutePlan,
  terrain: TerrainProvider,
  obstacles: readonly Obstacle[],
  policy: ClearancePolicy,
): GeoSafetyResult {
  const calculationVersion = policy.calculationVersion ?? DEFAULT_CALCULATION_VERSION;
  const sourcePackageIds = unique([...route.sourcePackageIds, ...obstacles.map((obstacle) => obstacle.sourcePackageId)]);
  if (!finite(policy.minimumTerrainClearanceM) || policy.minimumTerrainClearanceM < 0 || !finite(policy.minimumObstacleClearanceM) || policy.minimumObstacleClearanceM < 0) {
    return { status: "unknown", findings: [finding("CLEARANCE_POLICY_UNKNOWN", "hard", "geo.clearance.policy.unknown", sourcePackageIds)], sourcePackageIds, calculationVersion };
  }

  let points: RoutePoint[];
  try { points = routePoints(route); } catch (error) {
    return { status: "unknown", findings: [finding("ROUTE_GEOMETRY_UNKNOWN", "hard", "geo.route.geometry.unknown", sourcePackageIds)], sourcePackageIds, calculationVersion };
  }
  if (points.length === 0) return { status: "unknown", findings: [finding("ROUTE_GEOMETRY_UNKNOWN", "hard", "geo.route.geometry.unknown", sourcePackageIds)], sourcePackageIds, calculationVersion };

  const findings: GeoFinding[] = [];
  const evidenceIds = new Set(sourcePackageIds);
  let dataUnknown = false;
  for (const point of points) {
    const sampled = sampleSynchronously(terrain, point.coordinate, policy);
    if (sampled.sample === undefined) {
      dataUnknown = true;
      findings.push(finding("TERRAIN_COVERAGE_UNKNOWN", "hard", "geo.terrain.coverage.unknown", sourcePackageIds, point.coordinate));
      continue;
    }
    evidenceIds.add(sampled.sample.sourcePackageId);
    const routeAltitudeMsl = point.altitudeReference === "MSL" ? point.altitude : point.altitude + sampled.sample.elevationMslM;
    const terrainClearance = routeAltitudeMsl - sampled.sample.elevationMslM;
    if (terrainClearance < policy.minimumTerrainClearanceM) {
      findings.push(finding("TERRAIN_CLEARANCE", "hard", "geo.terrain.clearance.insufficient", [sampled.sample.sourcePackageId], point.coordinate));
    }
    for (const obstacle of obstacles) {
      if (!finite(obstacle.elevationMslM) || !finite(obstacle.heightM) || obstacle.heightM < 0) {
        dataUnknown = true;
        findings.push(finding("OBSTACLE_DATA_UNKNOWN", "hard", "geo.obstacle.data.unknown", [obstacle.sourcePackageId], point.coordinate));
        continue;
      }
      if ((obstacle.horizontalDatum !== undefined && obstacle.horizontalDatum !== EPSG_4326) || (obstacle.verticalDatum !== undefined && obstacle.verticalDatum.trim() === "")) {
        dataUnknown = true;
        findings.push(finding("OBSTACLE_DATA_UNKNOWN", "hard", "geo.obstacle.datum.unknown", [obstacle.sourcePackageId], point.coordinate));
        continue;
      }
      const influenceRadiusM = obstacle.influenceRadiusM ?? 100;
      if (!finite(influenceRadiusM) || influenceRadiusM < 0) { dataUnknown = true; continue; }
      let obstaclePoint: Wgs84Coordinate;
      try { obstaclePoint = parseCoordinate({ lat: obstacle.lat, lon: obstacle.lon }); } catch {
        dataUnknown = true;
        findings.push(finding("OBSTACLE_DATA_UNKNOWN", "hard", "geo.obstacle.location.unknown", [obstacle.sourcePackageId], point.coordinate));
        continue;
      }
      if (distanceM(point.coordinate, obstaclePoint) > influenceRadiusM) continue;
      evidenceIds.add(obstacle.sourcePackageId);
      const obstacleClearance = routeAltitudeMsl - obstacle.elevationMslM - obstacle.heightM;
      if (obstacleClearance < policy.minimumObstacleClearanceM) {
        findings.push(finding("OBSTACLE_CLEARANCE", "hard", "geo.obstacle.clearance.insufficient", [obstacle.sourcePackageId, sampled.sample.sourcePackageId], obstaclePoint));
      }
    }
  }

  const status = dataUnknown ? "unknown" : findings.length > 0 ? "blocked" : "pass";
  return { status, findings, sourcePackageIds: unique([...evidenceIds]), calculationVersion };
}
