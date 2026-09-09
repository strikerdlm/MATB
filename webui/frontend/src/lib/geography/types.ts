import type { PointMM } from "@/types/simulation";
export type GeographyLayer =
  | "roads"
  | "rivers"
  | "settlements"
  | "boundaries"
  | "airports";
export const GEOGRAPHY_LAYERS: GeographyLayer[] = [
  "roads",
  "rivers",
  "settlements",
  "boundaries",
  "airports",
];
export interface TrafficConfig {
  mode: "off" | "live" | "recorded";
  provider: "adsb.lol" | "opensky";
  recording_id?: string | null;
  recording_sha256?: string | null;
}
export interface TrafficTrack {
  id: string;
  callsign: string;
  lat: number;
  lon: number;
  observed_at: number;
  received_at: number;
  geometric_altitude_m: number | null;
  barometric_altitude_m: number | null;
  orthometric_altitude_m?: number | null;
  speed_mps: number | null;
  track_deg: number | null;
  vertical_rate_mps: number | null;
  on_ground: boolean;
  age_s: number;
  stale: boolean;
  source: string;
  position?: PointMM;
}
export interface TrafficFrame {
  origin?: {
    lat: number;
    lon: number;
    mission_x_m: number;
    mission_y_m: number;
  };
  version?: number;
  frame_id?: string;
  provider: string;
  status: string;
  sampled_at: number;
  received_at?: number | null;
  tracks: TrafficTrack[];
  query?: { lat: number; lon: number; radius_nm: number };
  attribution?: string;
  block_id?: string;
  simulation_time_ms?: number;
  source_simulation_time_ms?: number;
  discontinuity?: boolean;
  mode?: string;
}
export interface Region {
  id: string;
  title: string;
  region: string;
  lat: number;
  lon: number;
}
export interface TrafficRecording {
  id: string;
  title: string;
  sha256: string;
  scene_id: string;
  scene_sha256: string;
  duration_ms: number;
  provider: string;
}
export interface PreparationJob {
  id: string;
  scene_id: string;
  status: "queued" | "running" | "ready" | "failed" | "cancelled";
  progress: string;
  error?: string;
}
