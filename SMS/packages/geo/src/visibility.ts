import { distanceM, parseCoordinate } from "./coordinates.js";
import type { Wgs84Coordinate } from "./coordinates.js";
import type { Obstacle, TerrainProvider, TerrainSample } from "./terrain.js";
import type { GeoFinding, GeoSafetyResult, RoutePlan } from "./types.js";

export interface ViewshedResult {
  status: "pass" | "blocked" | "unknown";
  visibleFraction: number;
  sourcePackageIds: readonly string[];
  limitingPoint?: { lat: number; lon: number };
}

export interface ObserverPosition {
  lat: number;
  lon: number;
  altitude: number;
  altitudeReference: "MSL" | "AGL";
  sourcePackageId?: string;
}

export interface VisualConditionFacts {
  viewshed?: ViewshedResult;
  observerQualified?: boolean;
  relayAvailable?: boolean;
  authorization?: boolean;
  detectAndAvoid?: boolean;
  c2Continuity?: boolean;
  calculationVersion?: string;
  sourcePackageIds?: readonly string[];
}

const DEFAULT_CALCULATION_VERSION = "visual-condition-v1";
const DEFAULT_OBSTACLE_INFLUENCE_M = 100;
const MIN_VISIBLE_FRACTION = 0.95;

function finite(value: unknown): value is number { return typeof value === "number" && Number.isFinite(value); }

function unique(values: readonly string[]): string[] { return [...new Set(values.filter((value) => value.trim() !== ""))]; }

function finding(
  code: string,
  severity: GeoFinding["severity"],
  messageConceptId: string,
  sourcePackageIds: readonly string[],
): GeoFinding {
  return { code, severity, messageConceptId, sourcePackageIds };
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
    && (sample.horizontalDatum === undefined || sample.horizontalDatum === "EPSG:4326")
    && (sample.verticalDatum === undefined || sample.verticalDatum.trim() !== "")
    && (sample.resolutionM === undefined || (finite(sample.resolutionM) && sample.resolutionM > 0));
}

function sampleSynchronously(provider: TerrainProvider, point: Wgs84Coordinate): TerrainSample | null {
  try {
    if (provider.coverage(point) !== "covered") return null;
    const value = provider.sample(point);
    if (value !== null && typeof value === "object" && "then" in value) return null;
    return validSample(value) ? value : null;
  } catch {
    return null;
  }
}

function localMeters(origin: Wgs84Coordinate, point: Wgs84Coordinate): { x: number; y: number } {
  const metersPerDegree = 111_320;
  const latitudeScale = Math.cos(((origin.lat + point.lat) / 2) * Math.PI / 180);
  return {
    x: (point.lon - origin.lon) * metersPerDegree * latitudeScale,
    y: (point.lat - origin.lat) * metersPerDegree,
  };
}

function projectionOnSegment(start: Wgs84Coordinate, end: Wgs84Coordinate, point: Wgs84Coordinate): { distanceM: number; fraction: number } {
  const endLocal = localMeters(start, end);
  const pointLocal = localMeters(start, point);
  const lengthSquared = endLocal.x ** 2 + endLocal.y ** 2;
  const rawFraction = lengthSquared === 0 ? 0 : (pointLocal.x * endLocal.x + pointLocal.y * endLocal.y) / lengthSquared;
  const fraction = Math.max(0, Math.min(1, rawFraction));
  const closest = { x: endLocal.x * fraction, y: endLocal.y * fraction };
  return { distanceM: Math.hypot(pointLocal.x - closest.x, pointLocal.y - closest.y), fraction };
}

function routeWaypoints(route: RoutePlan): Wgs84Coordinate[] {
  return route.waypoints.map((waypoint) => parseCoordinate({ lat: waypoint.lat, lon: waypoint.lon }));
}

function routeAltitudeMsl(altitude: number, reference: "MSL" | "AGL", terrain: TerrainSample): number {
  return reference === "MSL" ? altitude : altitude + terrain.elevationMslM;
}

/** Calculate a conservative terrain/obstacle line-of-sight result offline. */
export function calculateViewshed(
  observer: ObserverPosition,
  route: RoutePlan,
  terrain: TerrainProvider,
  obstacles: readonly Obstacle[],
): ViewshedResult {
  const sourceIds = new Set(unique([...route.sourcePackageIds, ...(observer.sourcePackageId === undefined ? [] : [observer.sourcePackageId]), ...obstacles.map((obstacle) => obstacle.sourcePackageId)]));
  let observerPoint: Wgs84Coordinate;
  try { observerPoint = parseCoordinate({ lat: observer.lat, lon: observer.lon }); } catch { return { status: "unknown", visibleFraction: 0, sourcePackageIds: [...sourceIds] }; }
  const observerTerrain = sampleSynchronously(terrain, observerPoint);
  if (observerTerrain === null) return { status: "unknown", visibleFraction: 0, sourcePackageIds: [...sourceIds] };
  sourceIds.add(observerTerrain.sourcePackageId);
  if (!finite(observer.altitude)) return { status: "unknown", visibleFraction: 0, sourcePackageIds: [...sourceIds] };
  const observerAltitudeMsl = routeAltitudeMsl(observer.altitude, observer.altitudeReference, observerTerrain);
  let targets: Wgs84Coordinate[];
  try { targets = routeWaypoints(route).filter((point) => distanceM(point, observerPoint) > 0.01); } catch { return { status: "unknown", visibleFraction: 0, sourcePackageIds: [...sourceIds] }; }
  if (targets.length === 0) return { status: "unknown", visibleFraction: 0, sourcePackageIds: [...sourceIds] };

  let visible = 0;
  let unknown = false;
  let limitingPoint: { lat: number; lon: number } | undefined;
  for (let index = 0; index < targets.length; index += 1) {
    const target = targets[index];
    const targetTerrain = sampleSynchronously(terrain, target);
    if (targetTerrain === null) { unknown = true; continue; }
    sourceIds.add(targetTerrain.sourcePackageId);
    const routeWaypoint = route.waypoints.find((waypoint) => Math.abs(waypoint.lat - target.lat) < 1e-9 && Math.abs(waypoint.lon - target.lon) < 1e-9);
    if (routeWaypoint === undefined || !finite(routeWaypoint.altitude)) { unknown = true; continue; }
    const targetAltitudeMsl = routeAltitudeMsl(routeWaypoint.altitude, routeWaypoint.altitudeReference, targetTerrain);
    let blocked = false;
    for (const fraction of [0.25, 0.5, 0.75]) {
      const linePoint = parseCoordinate({
        lat: observerPoint.lat + (target.lat - observerPoint.lat) * fraction,
        lon: observerPoint.lon + (target.lon - observerPoint.lon) * fraction,
      });
      const lineTerrain = sampleSynchronously(terrain, linePoint);
      if (lineTerrain === null) { unknown = true; break; }
      sourceIds.add(lineTerrain.sourcePackageId);
      const lineAltitude = observerAltitudeMsl + (targetAltitudeMsl - observerAltitudeMsl) * fraction;
      if (lineTerrain.elevationMslM >= lineAltitude) blocked = true;
    }
    if (unknown) continue;
    for (const obstacle of obstacles) {
      let obstaclePoint: Wgs84Coordinate;
      try { obstaclePoint = parseCoordinate({ lat: obstacle.lat, lon: obstacle.lon }); } catch { unknown = true; continue; }
      const projection = projectionOnSegment(observerPoint, target, obstaclePoint);
      const influenceRadiusM = obstacle.influenceRadiusM ?? DEFAULT_OBSTACLE_INFLUENCE_M;
      if (!finite(obstacle.elevationMslM) || !finite(obstacle.heightM) || obstacle.heightM < 0 || !finite(influenceRadiusM) || influenceRadiusM < 0 || (obstacle.horizontalDatum !== undefined && obstacle.horizontalDatum !== "EPSG:4326") || (obstacle.verticalDatum !== undefined && obstacle.verticalDatum.trim() === "")) {
        unknown = true;
        continue;
      }
      if (projection.distanceM <= influenceRadiusM) {
        const lineAltitude = observerAltitudeMsl + (targetAltitudeMsl - observerAltitudeMsl) * projection.fraction;
        if (obstacle.elevationMslM + obstacle.heightM >= lineAltitude) {
          blocked = true;
          limitingPoint = { lat: obstaclePoint.lat, lon: obstaclePoint.lon };
        }
      }
    }
    if (blocked) limitingPoint ??= { lat: target.lat, lon: target.lon };
    else visible += 1;
  }

  const visibleFraction = visible / targets.length;
  if (unknown) return { status: "unknown", visibleFraction, sourcePackageIds: [...sourceIds], ...(limitingPoint === undefined ? {} : { limitingPoint }) };
  if (visibleFraction < 1) return { status: "blocked", visibleFraction, sourcePackageIds: [...sourceIds], ...(limitingPoint === undefined ? {} : { limitingPoint }) };
  return { status: "pass", visibleFraction, sourcePackageIds: [...sourceIds] };
}

function result(
  status: GeoSafetyResult["status"],
  code: string,
  messageConceptId: string,
  route: RoutePlan,
  facts: VisualConditionFacts,
): GeoSafetyResult {
  const sourcePackageIds = unique([...route.sourcePackageIds, ...(facts.sourcePackageIds ?? []), ...(facts.viewshed?.sourcePackageIds ?? [])]);
  return {
    status,
    findings: status === "pass" ? [] : [finding(code, "hard", messageConceptId, sourcePackageIds)],
    sourcePackageIds,
    calculationVersion: facts.calculationVersion ?? DEFAULT_CALCULATION_VERSION,
  };
}

/** Apply conservative evidence gates for VLOS, EVLOS, and authorized BVLOS. */
export function evaluateVisualCondition(
  route: RoutePlan,
  requestedCondition: "VLOS" | "EVLOS" | "BVLOS",
  facts: VisualConditionFacts,
): GeoSafetyResult {
  if (facts.observerQualified === false) return result("blocked", "VISUAL_OBSERVER_UNQUALIFIED", "geo.visual.observer.unqualified", route, facts);
  if (requestedCondition !== "BVLOS" && facts.observerQualified !== true) return result("unknown", "VISUAL_OBSERVER_UNKNOWN", "geo.visual.observer.unknown", route, facts);

  if (requestedCondition === "VLOS" || requestedCondition === "EVLOS") {
    if (facts.viewshed === undefined) return result("unknown", "VIEWSHED_UNKNOWN", "geo.visual.viewshed.unknown", route, facts);
    if (facts.viewshed.status === "unknown") return result("unknown", "VIEWSHED_UNKNOWN", "geo.visual.viewshed.unknown", route, facts);
    if (facts.viewshed.status === "blocked" || facts.viewshed.visibleFraction < MIN_VISIBLE_FRACTION) return result("blocked", "VISUAL_COVERAGE_INSUFFICIENT", "geo.visual.coverage.insufficient", route, facts);
  }
  if (requestedCondition === "EVLOS") {
    if (facts.relayAvailable === false) return result("blocked", "RELAY_UNAVAILABLE", "geo.visual.relay.unavailable", route, facts);
    if (facts.relayAvailable !== true) return result("unknown", "RELAY_UNKNOWN", "geo.visual.relay.unknown", route, facts);
  }
  if (requestedCondition === "BVLOS") {
    const requirements: Array<[keyof Pick<VisualConditionFacts, "authorization" | "detectAndAvoid" | "c2Continuity">, string, string]> = [
      ["authorization", "BVLOS_AUTHORIZATION_UNKNOWN", "geo.visual.bvlos.authorization.unknown"],
      ["detectAndAvoid", "DAA_UNKNOWN", "geo.visual.bvlos.daa.unknown"],
      ["c2Continuity", "C2_CONTINUITY_UNKNOWN", "geo.visual.bvlos.c2.unknown"],
    ];
    for (const [field, unknownCode, concept] of requirements) {
      if (facts[field] === false) return result("blocked", unknownCode.replace("_UNKNOWN", "_MISSING"), concept.replace("unknown", "missing"), route, facts);
      if (facts[field] !== true) return result("unknown", unknownCode, concept, route, facts);
    }
  }
  return result("pass", "", "", route, facts);
}
