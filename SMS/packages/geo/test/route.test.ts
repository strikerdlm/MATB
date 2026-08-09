import { describe, expect, it } from "vitest";
import { buildRoute } from "../src/route.js";

const waypoints = [
  { id: "wp-1", lat: 4.7000, lon: -74.1000, altitude: 2_600, altitudeReference: "MSL" as const, role: "route" as const },
  { id: "wp-2", lat: 4.8000, lon: -74.0000, altitude: 2_650, altitudeReference: "MSL" as const, role: "recovery" as const },
];

describe("route construction", () => {
  it("builds stable segment IDs and geometry hashes from drawn waypoints", () => {
    const input = {
      id: "route-drawn",
      waypoints,
      flightRule: "VFR" as const,
      visualCondition: "VLOS" as const,
      altitudeReference: "MSL" as const,
      sourcePackageIds: ["map-package"],
    };
    const first = buildRoute(input);
    const second = buildRoute(input);
    expect(first.segments).toHaveLength(1);
    expect(first.segments[0]).toMatchObject({ id: "segment-1", fromWaypointId: "wp-1", toWaypointId: "wp-2", kind: "track" });
    expect(first.segments[0].geometryHash).toMatch(/^[a-f0-9]{64}$/);
    expect(first.segments[0].geometryHash).toBe(second.segments[0].geometryHash);
  });

  it("preserves explicit hold/orbit segment geometry and rejects invalid routes", () => {
    const route = buildRoute({
      id: "route-pattern",
      waypoints,
      segments: [{ id: "orbit-1", fromWaypointId: "wp-1", toWaypointId: "wp-2", kind: "orbit", geometryHash: "b".repeat(64) }],
      flightRule: "IFR",
      visualCondition: "BVLOS",
      altitudeReference: "MSL",
      sourcePackageIds: ["map-package"],
    });
    expect(route.segments[0].kind).toBe("orbit");
    expect(() => buildRoute({ ...route, segments: [{ ...route.segments[0], fromWaypointId: "missing" }] })).toThrow(/waypoint/i);
  });
});
