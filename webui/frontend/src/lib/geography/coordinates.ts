import proj4 from "proj4";
import type { SceneManifest } from "@/lib/simulation/presentation/contracts";
import type { TrafficFrame, TrafficTrack } from "./types";
export function toLocal(
  lon: number,
  lat: number,
  origin: SceneManifest["origin"],
) {
  const [x, y] = proj4(
    "EPSG:4326",
    `+proj=aeqd +lat_0=${origin.lat} +lon_0=${origin.lon} +datum=WGS84 +units=m`,
    [lon, lat],
  );
  return {
    x_mm: Math.round((x + origin.mission_x_m) * 1000),
    y_mm: Math.round((y + origin.mission_y_m) * 1000),
  };
}
export function footprint(
  lon: number,
  lat: number,
): GeoJSON.Feature<GeoJSON.Polygon> {
  const crs = `+proj=aeqd +lat_0=${lat} +lon_0=${lon} +datum=WGS84 +units=m`;
  return {
    type: "Feature",
    properties: {},
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [-6000, -4000],
          [6000, -4000],
          [6000, 4000],
          [-6000, 4000],
          [-6000, -4000],
        ].map((p) => proj4(crs, "EPSG:4326", p)),
      ],
    },
  };
}
/** Estimate only the first 15 seconds after a position observation. */
export function displayedTraffic(
  frame: TrafficFrame | null | undefined,
  elapsedMs = 0,
): TrafficTrack[] {
  if (!frame) return [];
  return frame.tracks.flatMap((track) => {
    const age = track.age_s + Math.max(0, elapsedMs) / 1000;
    if (!Number.isFinite(age) || age > 60) return [];
    const seconds = track.on_ground ? 0 : Math.min(age, 15),
      bearing = ((track.track_deg ?? 0) * Math.PI) / 180;
    const distance =
      track.track_deg === null ? 0 : (track.speed_mps ?? 0) * seconds;
    const lat = track.lat + (distance * Math.cos(bearing)) / 111195;
    const lon =
      track.lon +
      (distance * Math.sin(bearing)) /
        (111195 * Math.max(0.2, Math.cos((track.lat * Math.PI) / 180)));
    return [{ ...track, lat, lon, age_s: age, stale: age > 15 }];
  });
}
