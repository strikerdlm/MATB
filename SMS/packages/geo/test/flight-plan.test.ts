import { describe, expect, it } from "vitest";
import { createFlightPlanDraft, evaluateFlightRules, exportDraft } from "../src/flight-plan.js";
import type { FlightRuleFacts } from "../src/flight-plan.js";
import type { RoutePlan } from "../src/index.js";

const route: RoutePlan = {
  id: "route-draft",
  waypoints: [
    { id: "wp-1", lat: 4.7000, lon: -74.1000, altitude: 2_600, altitudeReference: "MSL", role: "route" },
    { id: "wp-2", lat: 4.8000, lon: -74.0000, altitude: 2_650, altitudeReference: "MSL", role: "recovery" },
  ],
  segments: [{ id: "segment-1", fromWaypointId: "wp-1", toWaypointId: "wp-2", kind: "track", geometryHash: "a".repeat(64) }],
  flightRule: "VFR",
  visualCondition: "VLOS",
  altitudeReference: "MSL",
  sourcePackageIds: ["map-package-1", "airspace-package-1"],
};

const validFacts: FlightRuleFacts = {
  aircraftClass: "IC",
  flightRule: "IFR",
  ifrApproved: true,
  approvedCapabilityEvidence: true,
  aircraftEquipmentCapable: true,
  segregatedAirspace: true,
  ifrAuthorization: true,
  sourcePackageIds: ["policy-package-1", "airspace-package-1"],
};

describe("flight-rule gates and draft-only exports", () => {
  it("blocks IFR for a class IA aircraft", () => {
    expect(evaluateFlightRules({ ...validFacts, aircraftClass: "IA" }).status).toBe("blocked");
  });

  it("requires approved authorization and segregated airspace for IC IFR", () => {
    expect(evaluateFlightRules({ ...validFacts, ifrAuthorization: undefined }).status).toBe("unknown");
    expect(evaluateFlightRules({ ...validFacts, segregatedAirspace: false }).status).toBe("blocked");
    expect(evaluateFlightRules(validFacts).status).toBe("pass");
  });

  it("creates a draft that cannot represent transmission", () => {
    const draft = createFlightPlanDraft({ missionId: "mission-1", route, checks: [] });
    expect(draft.transmission).toBe("not-supported");
    expect(JSON.stringify(draft)).not.toMatch(/send|transmit|command/i);
  });

  it("exports JSON, GeoJSON, KML, GPX, and KMZ without changing route geometry", () => {
    const draft = createFlightPlanDraft({ missionId: "mission-1", route, checks: [] });
    expect(JSON.parse(exportDraft(draft, "json"))).toMatchObject({ missionId: "mission-1", transmission: "not-supported" });
    const geoJson = JSON.parse(exportDraft(draft, "geojson"));
    expect(geoJson.features[0].geometry.coordinates).toEqual([[route.waypoints[0].lon, route.waypoints[0].lat, route.waypoints[0].altitude], [route.waypoints[1].lon, route.waypoints[1].lat, route.waypoints[1].altitude]]);
    expect(exportDraft(draft, "kml")).toContain("<kml");
    expect(exportDraft(draft, "gpx")).toContain("<gpx");
    expect(exportDraft(draft, "kmz")).toBeInstanceOf(Uint8Array);
  });
});
