import { describe, expect, it } from "vitest";
import { calculateViewshed, evaluateVisualCondition } from "../src/visibility.js";
import type { ObserverPosition, VisualConditionFacts } from "../src/visibility.js";
import type { Obstacle, TerrainProvider } from "../src/terrain.js";
import type { RoutePlan } from "../src/index.js";

const route: RoutePlan = {
  id: "route-visibility",
  waypoints: [
    { id: "wp-1", lat: 4.7000, lon: -74.1000, altitude: 2_600, altitudeReference: "MSL", role: "route" },
    { id: "wp-2", lat: 4.8000, lon: -74.0000, altitude: 2_600, altitudeReference: "MSL", role: "recovery" },
  ],
  segments: [{ id: "seg-1", fromWaypointId: "wp-1", toWaypointId: "wp-2", kind: "track", geometryHash: "b".repeat(64) }],
  flightRule: "VFR",
  visualCondition: "VLOS",
  altitudeReference: "MSL",
  sourcePackageIds: ["route-package"],
};

const observer: ObserverPosition = { lat: 4.7000, lon: -74.1000, altitude: 2_600, altitudeReference: "MSL" };

function terrain(coverage: TerrainProvider["coverage"] = () => "covered"): TerrainProvider {
  return {
    coverage,
    sample: () => ({
      elevationMslM: 2_400,
      horizontalAccuracyM: 10,
      verticalAccuracyM: 15,
      sourcePackageId: "terrain-package",
      sampledAtUtc: "2026-08-08T23:30:00Z",
      horizontalDatum: "EPSG:4326",
      verticalDatum: "EGM96",
      resolutionM: 30,
    }),
  };
}

const tower: Obstacle = {
  id: "visibility-tower",
  lat: 4.7500,
  lon: -74.0500,
  elevationMslM: 2_400,
  heightM: 500,
  sourcePackageId: "obstacle-package",
  horizontalDatum: "EPSG:4326",
  verticalDatum: "EGM96",
};

describe("terrain-aware visual condition checks", () => {
  it("reports a limiting obstacle in a viewshed", () => {
    const result = calculateViewshed(observer, route, terrain(), [tower]);
    expect(result.status).toBe("blocked");
    expect(result.visibleFraction).toBeLessThan(1);
    expect(result.limitingPoint).toBeDefined();
    expect(result.sourcePackageIds).toEqual(expect.arrayContaining(["terrain-package", "obstacle-package"]));
  });

  it("returns unknown instead of assuming visibility when terrain is missing", () => {
    const result = calculateViewshed(observer, route, terrain(() => "missing"), []);
    expect(result.status).toBe("unknown");
  });

  it("requires the appropriate evidence for VLOS, EVLOS, and BVLOS", () => {
    const viewshed = { status: "pass" as const, visibleFraction: 1, sourcePackageIds: ["terrain-package"] };
    const vlos: VisualConditionFacts = { viewshed, observerQualified: true };
    expect(evaluateVisualCondition(route, "VLOS", vlos).status).toBe("pass");
    expect(evaluateVisualCondition(route, "EVLOS", vlos).status).toBe("unknown");
    expect(evaluateVisualCondition(route, "BVLOS", vlos).status).toBe("unknown");
    expect(evaluateVisualCondition(route, "EVLOS", { ...vlos, relayAvailable: true }).status).toBe("pass");
    expect(evaluateVisualCondition(route, "BVLOS", { ...vlos, authorization: true, detectAndAvoid: true, c2Continuity: true }).status).toBe("pass");
  });
});
