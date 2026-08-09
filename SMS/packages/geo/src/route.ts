import { createHash } from "node:crypto";
import { canonicalJson } from "@fac-isr/evidence";
import { parseRoutePlan } from "./types.js";
import type { RoutePlan, RouteSegment, Waypoint } from "./types.js";

export interface RouteBuildInput {
  id: string;
  waypoints: readonly Waypoint[];
  segments?: readonly RouteSegment[];
  corridorWidthM?: number;
  flightRule: RoutePlan["flightRule"];
  visualCondition: RoutePlan["visualCondition"];
  altitudeReference: RoutePlan["altitudeReference"];
  sourcePackageIds: readonly string[];
}

function segmentHash(from: Waypoint, to: Waypoint): string {
  return createHash("sha256").update(canonicalJson({
    from: { lat: from.lat, lon: from.lon, altitude: from.altitude, altitudeReference: from.altitudeReference },
    to: { lat: to.lat, lon: to.lon, altitude: to.altitude, altitudeReference: to.altitudeReference },
  })).digest("hex");
}

/** Build a validated route, generating stable track segments when the drawing has none. */
export function buildRoute(input: RouteBuildInput | RoutePlan): RoutePlan {
  const segments = input.segments === undefined
    ? input.waypoints.slice(1).map((waypoint, index) => {
      const from = input.waypoints[index];
      return {
        id: `segment-${index + 1}`,
        fromWaypointId: from.id,
        toWaypointId: waypoint.id,
        kind: "track" as const,
        geometryHash: segmentHash(from, waypoint),
      };
    })
    : [...input.segments];
  return parseRoutePlan({ ...input, segments });
}
