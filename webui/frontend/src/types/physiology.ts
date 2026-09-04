export interface PolarCapabilities {
  schema_version: "1.0";
  device_alias: string;
  firmware: string | null;
  battery_percent: number | null;
  streams: Array<"hr_rr" | "ecg" | "acc">;
  ecg_sample_rates_hz: number[];
  ecg_resolutions_bits: number[];
  acc_sample_rates_hz: number[];
  acc_resolutions_bits: number[];
  acc_ranges_g: number[];
  internal_recording_qualified: false;
}

export interface PolarDevice {
  device_token: string;
  alias: string;
  connectable: boolean | null;
  rssi: number | null;
  broadcast_hr_bpm: number | null;
  broadcast_contact: boolean | null;
  token_expires_in_seconds: number;
}

export interface PolarConnection {
  connected: boolean;
  device_alias: string | null;
  capabilities: PolarCapabilities | null;
}

export interface PolarCapture {
  execution_purpose?: "practice" | "study";
  schema_version: "1.0";
  capture_id: string;
  participant_pseudonym: string;
  matb_session_kind: "openmatb" | "liftoff" | "suas" | "generic";
  matb_session_id: string;
  device_alias: string;
  lifecycle: "created" | "starting" | "capturing" | "stopping" | "complete" | "failed";
  requested_settings: Record<string, number>;
  resolved_settings: Record<string, number> | null;
  stream_counters: Record<string, number>;
  gap_count: number;
  connection_epoch: number;
  artifact_state: "none" | "partial" | "finalized" | "incomplete";
  incomplete_reasons: string[];
  started_at_utc: string | null;
  ended_at_utc: string | null;
}

export interface PreparedPolarCapture {
  capture: PolarCapture;
  controller_lease: string;
}

export interface PolarEvent {
  schema_version: "1.0";
  capture_id: string;
  sequence: number;
  event_type: "status" | "hr" | "quality" | "preview" | "marker" | "gap" | "error";
  occurred_at_utc: string;
  payload: Record<string, unknown>;
}

export interface PolarAnalysis {
  capture_id: string;
  valid: boolean;
  reason: string | null;
  phase_window_seconds: 300;
  phases: Array<Record<string, unknown>>;
  workload_responses: Array<{
    phase: string;
    valid: boolean;
    reason: string | null;
    delta_ln_rmssd: number | null;
    delta_mean_hr_bpm: number | null;
    artifact_burden_percent: number | null;
    usable_coverage_percent: number;
    movement_context: Record<string, unknown>;
  }>;
  interpretation: "descriptive_only_no_workload_classification";
}
