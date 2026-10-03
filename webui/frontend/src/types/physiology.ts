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
  purpose_provenance_id?: string | null;
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

export interface PolarRRExport {
  capture_id: string;
  execution_purpose: "practice" | "study";
  units: "ms";
  row_count: number;
  rr_count: number;
  excluded_nonpositive_or_nonfinite: number;
  contact_not_detected_count: number;
  segment_count: number;
  segments: Array<{ segment_id: number; rr_count: number; first_beat_index: number; last_beat_index: number; txt_filename: string; csv_filename: string }>;
  preview: Array<{ beat_index: number; rr_ms: number; segment_id: number }>;
  files: Array<{ filename: string; kind: "kubios_txt" | "rr_csv" | "trace_csv"; row_count: number; segment_id: number | null; sha256: string; size_bytes: number }>;
  incomplete_reasons: string[];
}

export interface PolarReview {
  schema_version: "1.0";
  capture_id: string;
  execution_purpose: "practice" | "study";
  metrics: {
    valid: boolean; reason: string | null; window_kind: "five_minute" | "short_exploratory";
    duration_s: number; sqi: number | null; n_intervals: number;
    mean_instantaneous_hr_bpm: number | null; rmssd_ms: number | null;
    sdnn_ms: number | null; ln_rmssd: number | null; pnn50_percent: number | null;
    spectrum?: Array<[number, number]>;
  } | null;
  rr_tachogram: Array<[number, number | null]>;
  poincare: Array<[number, number]>;
  respiration: {
    status: "unavailable" | "estimated"; respiratory_rate_bpm: number | null;
    accuracy_bpm: null; validated_against_reference: false;
    accepted_windows: number; evaluated_windows: number; accepted_window_percent: number;
    windows: Array<{ time_s: number; rate_bpm: number | null; accepted: boolean }>;
    waveform: Array<[number, number]>;
  };
  incomplete_reasons: string[];
}
