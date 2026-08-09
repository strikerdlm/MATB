import { describe, expect, it } from "vitest";
import { buildRoute } from "../src/route.js";
import { evaluateRouteAirspace, intersectRoute, matchNotams } from "../src/airspace.js";
import type { AirspacePolygon, NotamArea } from "../src/airspace.js";

const route = buildRoute({
  id: "route-airspace",
  waypoints: [
    { id: "wp-1", lat: 4.7000, lon: -74.1000, altitude: 2_600, altitudeReference: "MSL" as const, role: "route" as const },
    { id: "wp-2", lat: 4.8000, lon: -74.0000, altitude: 2_600, altitudeReference: "MSL" as const, role: "recovery" as const },
  ],
  flightRule: "VFR" as const,
  visualCondition: "VLOS" as const,
  altitudeReference: "MSL" as const,
  sourcePackageIds: ["route-package"],
});

const area = {
  id: "restricted-1",
  code: "R-1",
  polygon: [
    { lat: 4.735, lon: -74.065 },
    { lat: 4.735, lon: -74.035 },
    { lat: 4.765, lon: -74.035 },
    { lat: 4.765, lon: -74.065 },
  ],
  lowerAltitudeM: 2_500,
  upperAltitudeM: 3_000,
  altitudeReference: "MSL" as const,
  sourcePackageId: "official-airspace-package",
  authorityClass: "official" as const,
  effectiveFromUtc: "2026-08-01T00:00:00Z",
  effectiveToUtc: "2026-09-01T00:00:00Z",
} satisfies AirspacePolygon;

const expiredNotam: NotamArea = {
  id: "notam-1",
  notamId: "A1234/26",
  code: "NOTAM",
  polygon: area.polygon,
  lowerAltitudeM: 2_500,
  upperAltitudeM: 3_000,
  altitudeReference: "MSL",
  sourcePackageId: "official-notam-package",
  authorityClass: "official",
  effectiveFromUtc: "2026-08-01T00:00:00Z",
  effectiveToUtc: "2026-08-08T00:00:00Z",
};

const nowUtc = "2026-08-09T00:00:00Z";

describe("route airspace and NOTAM intersections", () => {
  it("detects a restricted-area intersection with altitude and segment evidence", () => {
    const intersections = intersectRoute(route, [area]);
    expect(intersections).toContainEqual(expect.objectContaining({ layerId: "restricted-1", segmentId: "segment-1", sourcePackageId: "official-airspace-package" }));
    const result = evaluateRouteAirspace({ route, airspaces: [area], notams: [], nowUtc });
    expect(result.status).toBe("blocked");
    expect(result.findings[0].code).toBe("AIRSPACE_CONFLICT");
  });

  it("treats open context overlays as advisory and does not use stale NOTAM evidence", () => {
    const advisory = { ...area, id: "open-context", authorityClass: "open-context" as const, sourcePackageId: "open-context-package" };
    expect(evaluateRouteAirspace({ route, airspaces: [advisory], notams: [], nowUtc }).status).toBe("pass");
    expect(matchNotams(route, [expiredNotam], { fromUtc: "2026-08-09T00:00:00Z", toUtc: "2026-08-09T01:00:00Z" })).toEqual([]);
    const staleResult = evaluateRouteAirspace({ route, airspaces: [], notams: [expiredNotam], nowUtc });
    expect(staleResult.status).toBe("unknown");
  });

  it("matches a current NOTAM only inside its effective mission window", () => {
    const activeNotam = { ...expiredNotam, effectiveToUtc: "2026-08-10T00:00:00Z" };
    expect(matchNotams(route, [activeNotam], { fromUtc: nowUtc, toUtc: "2026-08-09T01:00:00Z" })).toHaveLength(1);
    const result = evaluateRouteAirspace({ route, airspaces: [], notams: [activeNotam], nowUtc });
    expect(result.status).toBe("blocked");
    expect(result.findings).toContainEqual(expect.objectContaining({ code: "NOTAM_CONFLICT" }));
  });

  it("passes when current route geometry, altitude, and time have no conflict", () => {
    const result = evaluateRouteAirspace({ route, airspaces: [{ ...area, lowerAltitudeM: 3_000, upperAltitudeM: 4_000 }], notams: [], nowUtc });
    expect(result.status).toBe("pass");
  });
});
