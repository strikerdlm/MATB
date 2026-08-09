import { describe, expect, it } from "vitest";
import {
  createFlightPlanDraft,
  parseGeoPackageManifest,
  parseLayer,
  parseRoutePlan,
} from "../src/index.js";

const hash = "a".repeat(64);
const validLayer = {
  id: "airspace-layer-1",
  title: "Controlled airspace",
  authority: "FAC",
  authorityClass: "official" as const,
  effectiveFromUtc: "2026-08-01T00:00:00Z",
  expiresAtUtc: "2027-08-01T00:00:00Z",
  extent: [-78, -5, -70, 13] as [number, number, number, number],
  horizontalDatum: "EPSG:4326",
  verticalDatum: "EGM96",
  contentSha256: hash,
};
const validRoute = {
  id: "route-1",
  waypoints: [
    { id: "wp-1", lat: 4.7, lon: -74.1, altitude: 2_600, altitudeReference: "MSL" as const, role: "route" as const },
    { id: "wp-2", lat: 4.8, lon: -74.0, altitude: 2_650, altitudeReference: "MSL" as const, role: "recovery" as const },
  ],
  segments: [{ id: "seg-1", fromWaypointId: "wp-1", toWaypointId: "wp-2", kind: "track" as const, geometryHash: hash }],
  corridorWidthM: 100,
  flightRule: "VFR" as const,
  visualCondition: "VLOS" as const,
  altitudeReference: "MSL" as const,
  sourcePackageIds: ["map-package-1"],
};

describe("offline geospatial contracts", () => {
  it("requires datum and source metadata for every layer", () => {
    expect(() => parseLayer({ ...validLayer, horizontalDatum: undefined })).toThrow(/datum/i);
    expect(() => parseLayer({ ...validLayer, contentSha256: "not-a-hash" })).toThrow(/sha|hash/i);
  });

  it("rejects unsupported package formats, invalid extents, and incomplete signatures", () => {
    const manifest = {
      schemaVersion: "1.0" as const,
      packageId: "map-package-1",
      kind: "map" as const,
      issuer: "FAC",
      version: "1.0.0",
      issuedAtUtc: "2026-08-01T00:00:00Z",
      effectiveFromUtc: "2026-08-01T00:00:00Z",
      expiresAtUtc: "2027-08-01T00:00:00Z",
      geographicScope: "Colombia",
      contentSha256: hash,
      signature: "c2lnbmF0dXJl",
      keyId: "geo-key-1",
      dependencies: [],
      files: [{ path: "layers.pmtiles", sha256: hash, sizeBytes: 12 }],
      qualification: "approved" as const,
      caveats: ["fixture"],
      format: "pmtiles" as const,
      horizontalDatum: "EPSG:4326",
      layers: [validLayer],
    };
    expect(parseGeoPackageManifest(manifest).format).toBe("pmtiles");
    expect(() => parseGeoPackageManifest({ ...manifest, format: "exe" })).toThrow(/format/i);
    expect(() => parseGeoPackageManifest({ ...manifest, layers: [{ ...validLayer, extent: [-200, -5, -70, 13] }] })).toThrow(/extent/i);
    expect(() => parseGeoPackageManifest({ ...manifest, signature: "" })).toThrow(/signature/i);
  });

  it("requires route geometry references and WGS-compatible coordinate values", () => {
    expect(parseRoutePlan(validRoute).waypoints).toHaveLength(2);
    expect(() => parseRoutePlan({ ...validRoute, waypoints: [{ ...validRoute.waypoints[0], lat: 95 }, validRoute.waypoints[1]] })).toThrow(/latitude|lat/i);
    expect(() => parseRoutePlan({ ...validRoute, segments: [{ ...validRoute.segments[0], fromWaypointId: "missing" }] })).toThrow(/waypoint/i);
  });

  it("marks every flight-plan draft as non-transmittable", () => {
    const draft = createFlightPlanDraft(validRoute);
    expect(draft.transmission).toBe("not-supported");
    expect(JSON.stringify(draft)).not.toMatch(/send|transmit|command/i);
  });
});
