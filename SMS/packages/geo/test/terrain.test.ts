import { describe, expect, it } from "vitest";
import { evaluateClearance, sampleTerrain } from "../src/terrain.js";
import type { ClearancePolicy, Obstacle, TerrainProvider } from "../src/terrain.js";
import type { RoutePlan } from "../src/index.js";

const route: RoutePlan = {
  id: "route-1",
  waypoints: [
    { id: "wp-1", lat: 4.7000, lon: -74.1000, altitude: 2_600, altitudeReference: "MSL", role: "route" },
    { id: "wp-2", lat: 4.8000, lon: -74.0000, altitude: 2_600, altitudeReference: "MSL", role: "recovery" },
  ],
  segments: [{ id: "seg-1", fromWaypointId: "wp-1", toWaypointId: "wp-2", kind: "track", geometryHash: "a".repeat(64) }],
  flightRule: "VFR",
  visualCondition: "VLOS",
  altitudeReference: "MSL",
  sourcePackageIds: ["route-package"],
};

const outsideRoute: RoutePlan = {
  ...route,
  id: "route-outside",
  waypoints: route.waypoints.map((waypoint) => ({ ...waypoint, lat: 6.0000 })),
};

const policy: ClearancePolicy = {
  minimumTerrainClearanceM: 100,
  minimumObstacleClearanceM: 50,
  asOfUtc: "2026-08-09T00:00:00Z",
  maxSampleAgeMinutes: 60,
  calculationVersion: "terrain-test-v1",
};

function terrain(coverage: TerrainProvider["coverage"] = () => "covered", sampledAtUtc = "2026-08-08T23:30:00Z"): TerrainProvider {
  return {
    coverage,
    sample: () => ({
      elevationMslM: 2_400,
      horizontalAccuracyM: 10,
      verticalAccuracyM: 15,
      sourcePackageId: "terrain-package",
      sampledAtUtc,
      horizontalDatum: "EPSG:4326",
      verticalDatum: "EGM96",
      resolutionM: 30,
    }),
  };
}

const tower: Obstacle = {
  id: "tower-1",
  lat: 4.7500,
  lon: -74.0500,
  elevationMslM: 2_400,
  heightM: 300,
  sourcePackageId: "obstacle-package",
  horizontalDatum: "EPSG:4326",
  verticalDatum: "EGM96",
};

describe("terrain sampling and clearance", () => {
  it("returns a terrain sample only when coverage is current and explicit", async () => {
    const sample = await sampleTerrain(terrain(), { lat: 4.7, lon: -74.1, datum: "EPSG:4326" });
    expect(sample).toMatchObject({ sourcePackageId: "terrain-package", verticalDatum: "EGM96", resolutionM: 30 });
    expect(await sampleTerrain(terrain(() => "missing"), { lat: 4.7, lon: -74.1, datum: "EPSG:4326" })).toBeNull();
    expect(await sampleTerrain(terrain(() => "expired"), { lat: 4.7, lon: -74.1, datum: "EPSG:4326" })).toBeNull();
  });

  it("returns unknown when terrain coverage does not include the route", () => {
    const result = evaluateClearance(outsideRoute, terrain((point) => point.lat > 5 ? "missing" : "covered"), [], policy);
    expect(result.status).toBe("unknown");
    expect(result.findings).toContainEqual(expect.objectContaining({ code: "TERRAIN_COVERAGE_UNKNOWN" }));
  });

  it("returns unknown when terrain samples are stale under the clearance policy", () => {
    const result = evaluateClearance(route, terrain(() => "covered", "2026-08-08T00:00:00Z"), [], policy);
    expect(result.status).toBe("unknown");
    expect(result.findings).toContainEqual(expect.objectContaining({ code: "TERRAIN_COVERAGE_UNKNOWN" }));
  });

  it("reports the limiting obstacle and vertical reference", () => {
    const result = evaluateClearance(route, terrain(), [tower], policy);
    expect(result.status).toBe("blocked");
    expect(result.findings).toContainEqual(expect.objectContaining({ code: "OBSTACLE_CLEARANCE" }));
    expect(result.sourcePackageIds).toEqual(expect.arrayContaining(["terrain-package", "obstacle-package"]));
  });

  it("never improves clearance when an obstacle is raised", () => {
    const lower = evaluateClearance(route, terrain(), [{ ...tower, heightM: 10 }], policy);
    const higher = evaluateClearance(route, terrain(), [{ ...tower, heightM: 500 }], policy);
    expect(lower.status).toBe("pass");
    expect(higher.status).toBe("blocked");
  });
});
