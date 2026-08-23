export type WorkloadLevel = "LOW" | "MEDIUM" | "HIGH";

export interface PolarCapabilities {
  supported_os: boolean;
  platform: string;
  backend_name: string;
  bleak_version: string | null;
  heart_rate_service_uuid: string;
  heart_rate_measurement_uuid: string;
  requirements: string[];
}

export interface PolarDevice {
  device_token: string;
  display_name: string;
  rssi: number | null;
  is_polar_h10: boolean;
  heart_rate_service_advertised: boolean;
  token_expires_at_utc_ns: string;
}

export interface PolarStatus {
  state: string;
  backend_name: string;
  connected_device_name: string | null;
  device_identifier_sha256?: string | null;
  battery_level: number | null;
  recording: boolean;
  reconnect_attempts: number;
  last_error_code: string | null;
  preflight_ready: boolean;
  last_rr_at_utc_ns: string | null;
  sensor_contact_detected?: boolean | null;
}

export interface PolarPreflight {
  ready: boolean;
  heart_rate_bpm: number | null;
  rr_count: number;
  sensor_contact_detected: boolean | null;
  battery_level: number | null;
  measured_at_utc_ns: string;
  reason_code: string | null;
}

export interface ClassicScenario {
  name: string;
  workload_level: WorkloadLevel;
}

export interface CreateClassicSession {
  participant_id: string;
  visit_ordinal: number;
  workload_level: WorkloadLevel;
  scenario_name: string;
  performance_only_override: boolean;
  override_reason_code: string | null;
}

export interface ClassicSessionView {
  id: string;
  participant_id: string;
  visit_id: number;
  visit_ordinal: number;
  workload_level: WorkloadLevel;
  attempt_number: number;
  scenario_name: string;
  scenario_sha256: string | null;
  openmatb_source_sha256: string | null;
  test_mode: boolean;
  wall_time_scale: number;
  post_task_timeout_seconds: number;
  status: string;
  task_validity: string;
  physiology_quality: string;
  performance_only_override: boolean;
  failure_reason_code: string | null;
  battery_level_at_start: number | null;
  created_at: string;
  baseline_started_at: string | null;
  task_started_at: string | null;
  task_finished_at: string | null;
  recovery_started_at: string | null;
  recovery_finished_at: string | null;
  finished_at: string | null;
}

export interface PreparedClassicSession extends ClassicSessionView {
  controller_lease: string;
}

export interface ClassicArtifact {
  kind: string;
  relative_path: string;
  sha256: string;
  size_bytes: number;
  created_at?: string | null;
}

export interface HrvMetricSection {
  status: string;
  reason_code?: string;
  reason_codes?: string[];
  metrics: Record<string, number | null> | null;
}

export interface HrvPhaseResult {
  quality?: {
    label?: string;
    score?: number;
    corrected_pct?: number;
  };
  raw_rr_count?: number;
  coverage_fraction?: number;
  time_domain?: HrvMetricSection;
  frequency_domain?: HrvMetricSection;
}

export interface ClassicHrvDocument {
  phases?: Record<string, HrvPhaseResult>;
  summary?: Record<string, unknown>;
}

export interface ClassicDebriefView {
  session: ClassicSessionView;
  matb_metrics: Record<string, unknown>;
  hrv: ClassicHrvDocument;
  selected_for_visit: boolean;
}

export type ClassicResourceRequest =
  | { sessionId: string; relativePath?: never; participantId?: never; visitOrdinal?: never; format?: never }
  | { sessionId: string; relativePath: string; participantId?: never; visitOrdinal?: never; format?: never }
  | { participantId: string; visitOrdinal: number; format: "json" | "csv" | "md"; sessionId?: never; relativePath?: never };
