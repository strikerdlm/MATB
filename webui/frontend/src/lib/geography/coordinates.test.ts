import { describe, expect, it } from "vitest";
import { displayedTraffic, footprint, toLocal } from "./coordinates";
import type { TrafficFrame } from "./types";
const frame: TrafficFrame = {
  provider: "adsb.lol",
  status: "live",
  sampled_at: 1000,
  tracks: [
    {
      id: "a12345",
      callsign: "TEST",
      lat: 4.15,
      lon: -73.65,
      observed_at: 1000,
      received_at: 1000,
      geometric_altitude_m: null,
      barometric_altitude_m: 3000,
      speed_mps: 100,
      track_deg: 90,
      vertical_rate_mps: null,
      on_ground: false,
      age_s: 0,
      stale: false,
      source: "adsb.lol",
    },
  ],
};
describe("Colombia coordinates and observed traffic", () => {
  it("centers all region origins and creates a closed local footprint", () => {
    for (const [lat, lon] of [
      [4.15, -73.65],
      [2.4448, -76.6147],
      [7.8939, -72.5078],
      [6.1533, -75.3742],
      [11.143, -74.116],
      [6.422, -72.428],
    ]) {
      const origin = { lat, lon, mission_x_m: 6000, mission_y_m: 4000 };
      expect(toLocal(lon, lat, origin)).toEqual({
        x_mm: 6000000,
        y_mm: 4000000,
      });
      const polygon = footprint(lon, lat).geometry.coordinates[0];
      expect(polygon[0]).toEqual(polygon[4]);
      expect(toLocal(polygon[2][0], polygon[2][1], origin)).toEqual({
        x_mm: 12000000,
        y_mm: 8000000,
      });
    }
  });
  it("caps extrapolation at 15 seconds, expires positions and preserves observations", () => {
    const a = displayedTraffic(frame, 15000)[0],
      b = displayedTraffic(frame, 45000)[0];
    expect(a.lon).toBeGreaterThan(frame.tracks[0].lon);
    expect(b.lon).toBe(a.lon);
    expect(b.stale).toBe(true);
    expect(displayedTraffic(frame, 61000)).toEqual([]);
    expect(frame.tracks[0].lon).toBe(-73.65);
    expect(a.geometric_altitude_m).toBeNull();
  });
  it("holds ground and missing-velocity observations", () => {
    const ground = {
      ...frame,
      tracks: [{ ...frame.tracks[0], on_ground: true }],
    };
    expect(displayedTraffic(ground, 10000)[0].lon).toBe(-73.65);
    expect(
      displayedTraffic(
        { ...frame, tracks: [{ ...frame.tracks[0], speed_mps: null }] },
        10000,
      )[0].lon,
    ).toBe(-73.65);
  });
});
