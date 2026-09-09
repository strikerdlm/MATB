import { getApiBase } from "@/lib/runtime-config";
import type { GeographyLayer, TrafficConfig } from "@/lib/geography/types";
import type { PointMM, TerrainBounds } from "@/types/simulation";

export interface CameraPose {
  camera_position: [number, number, number];
  camera_quaternion: [number, number, number, number];
}
export type CameraMode = "overview" | "follow" | "drone";
export interface PresentationConfig {
  version: 1;
  layers?: GeographyLayer[];
  traffic?: TrafficConfig;
  blocks: Partial<Record<"PRACTICE" | "LOW" | "MEDIUM" | "HIGH", "2d" | "3d">>;
  scene_id: string | null;
  scene_sha256: string | null;
  camera: CameraMode;
}
export interface SceneManifest {
  version: 1 | 2;
  region?: string;
  acquired_at?: string;
  footprint_cloud_percent?: number;
  imagery_valid_percent?: number;
  geographic_bounds?: [number, number, number, number];
  available_layers?: string[];
  id: string;
  sha256?: string;
  title: string;
  origin: {
    lat: number;
    lon: number;
    mission_x_m: number;
    mission_y_m: number;
  };
  altitude_reference: "terrain_relative_illustrative";
  files: {
    "elevation.json": string;
    "imagery.png": string;
    "overlays.json"?: string;
  };
  attribution: string;
}
export interface ElevationGrid {
  width: number;
  height: number;
  bounds_m: [number, number, number, number];
  values: number[];
}
export interface SceneAssets {
  manifest: SceneManifest;
  elevation: ElevationGrid;
  imagery: Blob;
  overlays?: GeoJSON.FeatureCollection;
}
export function missionToWorld(
  point: PointMM,
  altitudeM: number,
): [number, number, number] {
  if (![point.x_mm, point.y_mm, altitudeM].every(Number.isFinite))
    throw new Error("Non-finite scene coordinate");
  return [point.x_mm / 1000 - 6000, altitudeM, -(point.y_mm / 1000 - 4000)];
}
export function worldToMission(
  x: number,
  z: number,
  bounds: TerrainBounds,
): PointMM | null {
  const x_mm = Math.round((x + 6000) * 1000),
    y_mm = Math.round((-z + 4000) * 1000);
  if (
    ![x_mm, y_mm].every(Number.isFinite) ||
    x_mm < bounds.min_x_mm ||
    x_mm > bounds.max_x_mm ||
    y_mm < bounds.min_y_mm ||
    y_mm > bounds.max_y_mm
  )
    return null;
  return { x_mm, y_mm };
}
export function headingRadians(millidegrees: number): number {
  return (-millidegrees * Math.PI) / 180000;
}
export function validateElevation(value: ElevationGrid): ElevationGrid {
  if (
    !Number.isInteger(value.width) ||
    !Number.isInteger(value.height) ||
    value.width < 2 ||
    value.height < 2 ||
    value.width > 2048 ||
    value.height > 2048 ||
    value.values.length !== value.width * value.height ||
    !value.values.every(Number.isFinite) ||
    JSON.stringify(value.bounds_m) !== "[-2000,-2000,14000,10000]"
  )
    throw new Error("Invalid elevation grid");
  return value;
}
export function elevationAt(grid: ElevationGrid, point: PointMM): number {
  const [west, south, east, north] = grid.bounds_m;
  const col = ((point.x_mm / 1000 - west) / (east - west)) * (grid.width - 1);
  const row =
    ((point.y_mm / 1000 - south) / (north - south)) * (grid.height - 1);
  if (
    !Number.isFinite(col + row) ||
    col < 0 ||
    row < 0 ||
    col > grid.width - 1 ||
    row > grid.height - 1
  )
    throw new Error("Position outside terrain");
  const x = Math.min(Math.floor(col), grid.width - 2),
    y = Math.min(Math.floor(row), grid.height - 2);
  const u = col - x,
    v = row - y,
    i = y * grid.width + x;
  return (
    (1 - v) * ((1 - u) * grid.values[i] + u * grid.values[i + 1]) +
    v *
      ((1 - u) * grid.values[i + grid.width] +
        u * grid.values[i + grid.width + 1])
  );
}
async function checked(
  url: string,
  hash: string,
  signal: AbortSignal,
): Promise<ArrayBuffer> {
  const response = await fetch(url, { signal });
  if (!response.ok)
    throw new Error(`Offline asset unavailable (${response.status})`);
  const bytes = await response.arrayBuffer();
  const digest = Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (b) => b.toString(16).padStart(2, "0"),
  ).join("");
  if (digest !== hash) throw new Error("Offline asset checksum mismatch");
  return bytes;
}
export async function loadScene(
  config: PresentationConfig,
  signal: AbortSignal,
): Promise<SceneAssets> {
  if (
    !config.scene_id ||
    !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(config.scene_id) ||
    !config.scene_sha256
  )
    throw new Error("No offline scene selected");
  const base = `${await getApiBase()}/geography/scenes/${config.scene_id}/`;
  const manifest: SceneManifest = JSON.parse(
    new TextDecoder().decode(
      await checked(`${base}manifest.json`, config.scene_sha256, signal),
    ),
  );
  if (
    manifest.id !== config.scene_id ||
    ![1, 2].includes(manifest.version) ||
    manifest.altitude_reference !== "terrain_relative_illustrative" ||
    manifest.origin.mission_x_m !== 6000 ||
    manifest.origin.mission_y_m !== 4000
  )
    throw new Error("Unsupported scene package");
  const [elevation, imagery] = await Promise.all([
    checked(`${base}elevation.json`, manifest.files["elevation.json"], signal),
    checked(`${base}imagery.png`, manifest.files["imagery.png"], signal),
  ]);
  const overlays = manifest.files["overlays.json"]
    ? (JSON.parse(
        new TextDecoder().decode(
          await checked(
            `${base}overlays.json`,
            manifest.files["overlays.json"],
            signal,
          ),
        ),
      ) as GeoJSON.FeatureCollection)
    : undefined;
  return {
    overlays,
    manifest,
    elevation: validateElevation(
      JSON.parse(new TextDecoder().decode(elevation)),
    ),
    imagery: new Blob([imagery], { type: "image/png" }),
  };
}
