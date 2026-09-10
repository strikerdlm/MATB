export type LiftoffAction =
  | "baseline/start"
  | "baseline/finish"
  | "task/start"
  | "task/finish"
  | "recovery/start"
  | "recovery/finish";

export interface LiftoffConfiguration {
  liftoff_build: string;
  track_id: string;
  drone_id: string;
  flight_mode: string;
  camera_angle_deg: number;
  fov_deg: number;
  rates_profile: string;
  controller_model: string;
  controller_firmware: string;
  resolution: string;
  refresh_rate_hz: number;
  graphics_preset: string;
  damage_enabled: boolean;
  battery_enabled: boolean;
  telemetry_profile: "liftoff-telemetry-all-v1";
}

export interface CreateLiftoffSession {
  attempt_id?: string;
  locale?: "es-419" | "en";
  execution_purpose: "practice" | "study";
  participant_id: string;
  visit_ordinal: number;
  configuration: LiftoffConfiguration;
  polar_recording_confirmed: boolean;
  performance_only_reason: string | null;
}

export interface LiftoffSessionView {
  purpose_provenance_id?: string | null;
  execution_purpose: "practice" | "study";
  id: string;
  participant_id: string;
  visit_id: number;
  visit_ordinal: number;
  visit_code: string;
  attempt_number: number;
  protocol_id: string;
  protocol_version: string;
  liftoff_build: string;
  track_id: string;
  telemetry_profile: string;
  status: string;
  validity: string;
  sync_quality: string;
  polar_recording_confirmed: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  interrupted_at: string | null;
}

export interface PreparedLiftoffSession extends LiftoffSessionView {
  controller_lease: string;
}

export interface LiftoffReadiness {
  ready: boolean;
  valid_packets: number;
  invalid_packet_count: number;
  overflow_count: number;
  duplicate_time_count: number;
  out_of_order_count: number;
  clock_step_detected: boolean;
}

export interface LiftoffVisibleResults {
  valid_lap_times_s: number[];
  invalid_laps: number;
  observer_restart_count: number;
}

export interface LiftoffQuestionnaires {
  kss: number;
  mental_demand: number;
  physical_demand: number;
  temporal_demand: number;
  performance: number;
  effort: number;
  frustration: number;
}

export interface TelemetryQuality {
  packet_count: number;
  expected_packet_count: number;
  loss_pct: number;
  observed_rate_hz: number;
  maximum_gap_s: number;
  invalid_packet_count: number;
  overflow_count: number;
  nonmonotonic_count: number;
  clock_step_detected: boolean;
  validity: string;
  reason_codes: string[];
}

export interface LiftoffDebriefView {
  id: string;
  status: string;
  validity: string;
  sync_quality: string;
  quality: TelemetryQuality;
  primary: Record<string, unknown>;
}

export interface LiftoffArtifactView {
  kind: string;
  relative_path: string;
  sha256: string;
  size_bytes: number;
  created_at?: string | null;
}
