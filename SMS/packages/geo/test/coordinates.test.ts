import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  convertAltitude,
  distanceM,
  formatDms,
  fromMgrs,
  fromUtm,
  parseCoordinate,
  parseDms,
  toMgrs,
  toUtm,
  transformApprovedDatum,
} from "../src/coordinates.js";
import type { Wgs84Coordinate } from "../src/coordinates.js";

const fixtures = JSON.parse(readFileSync(new URL("./fixtures/coordinates.json", import.meta.url), "utf8")) as Record<string, Wgs84Coordinate>;
const bogota = fixtures.bogota;

describe("audited coordinate and altitude conversions", () => {
  it("parses decimal degrees and rejects invalid or unsupported coordinate units", () => {
    expect(parseCoordinate(bogota)).toMatchObject({ lat: bogota.lat, lon: bogota.lon, datum: "EPSG:4326" });
    expect(() => parseCoordinate({ lat: 91, lon: bogota.lon, datum: "EPSG:4326" })).toThrow(/latitude/i);
    expect(() => parseCoordinate({ lat: bogota.lat, lon: bogota.lon, datum: "EPSG:4326", units: "feet" })).toThrow(/units|coordinate/i);
  });

  it("preserves DMS hemisphere signs and parses the formatted value", () => {
    const dms = formatDms(bogota);
    expect(dms.latitude.hemisphere).toBe("N");
    expect(dms.longitude.hemisphere).toBe("W");
    const roundTrip = parseDms(dms);
    expect(distanceM(roundTrip, bogota)).toBeLessThan(0.01);
  });

  it("round-trips UTM and MGRS within aviation fixture tolerance", () => {
    const utm = toUtm(bogota, 18);
    expect(utm.zone).toBe(18);
    expect(distanceM(fromUtm(utm), bogota)).toBeLessThan(0.01);
    const southern = fixtures.southernHemisphere;
    const southernUtm = toUtm(southern, 19);
    expect(southernUtm.hemisphere).toBe("S");
    expect(distanceM(fromUtm(southernUtm), southern)).toBeLessThan(0.01);
    const mgrs = toMgrs(bogota, 5);
    expect(mgrs).toMatch(/^18[A-Z]{3}\d{10}$/);
    expect(distanceM(fromMgrs(mgrs), bogota)).toBeLessThan(2);
    expect(() => toUtm(bogota, 0)).toThrow(/zone/i);
  });

  it("requires an approved datum transformation and preserves WGS 84 output", () => {
    expect(transformApprovedDatum({ ...bogota, datum: "EPSG:4326" }, "EPSG:4326-identity").datum).toBe("EPSG:4326");
    expect(() => transformApprovedDatum({ easting: 1_000_000, northing: 1_000_000, datum: "EPSG:3116" }, "unregistered-transform")).toThrow(/approved|transformation/i);
  });

  it("does not convert MSL to AGL without terrain elevation", () => {
    expect(convertAltitude(2_600, "MSL", "AGL", { elevationMslM: 2_500 })).toBe(100);
    expect(convertAltitude(100, "AGL", "MSL", { elevationMslM: 2_500 })).toBe(2_600);
    expect(() => convertAltitude(9_000, "MSL", "AGL", undefined)).toThrow("terrain");
  });
});
