import type { PresentationConfig } from "@/lib/simulation/presentation/contracts";
/** Public, redacted transport contracts for the native sUAS simulator. */

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export type Locale = "en" | "es-CO";
export type Lifecycle = "PREPARED" | "RUNNING" | "PAUSED" | "FINISHED" | "ABORTED" | "INTERRUPTED";
export type Profile = "PRACTICE" | "LOW" | "MEDIUM" | "HIGH";
export type SessionMode = "research" | "interactive_technical";
export type RecordClass = "research" | "technical_only";

export type AircraftMode =
  | "READY"
  | "TRANSIT"
  | "SEARCH"
  | "HOLD"
  | "RETURN_TO_BASE"
  | "LOST_LINK_PROCEDURE"
  | "RECOVERED"
  | "MISSION_FAILED";
export type LinkMode = "NOMINAL" | "DEGRADED" | "LOST";
export type SensorMode = "NOMINAL" | "OFFLINE";
export type ContactEvidence = "NONE" | "DETECTED" | "INSPECTABLE";
export type ContactMode = "UNDETECTED" | "DETECTED" | "INSPECTED" | "CLASSIFIED" | "PRIORITIZED" | "REPORTED";
export type ContactWorkflow = ContactMode;
export type ContactClassification = "routine" | "priority" | "uncertain";
export type ContactPriority = "LOW" | "MEDIUM" | "HIGH";
export type AlertSeverity = "ADVISORY" | "CRITICAL" | "FATAL";
export type AlertKind =
  | "ENERGY_RESERVE"
  | "ENERGY_CRITICAL"
  | "LINK_LOST"
  | "SEPARATION_ADVISORY"
  | "SEPARATION_CRITICAL"
  | "RUNTIME_FAILURE";
export type CommandKind =
  | "ASSIGN_SECTOR"
  | "SET_WAYPOINT"
  | "HOLD"
  | "RESUME_MISSION"
  | "RETURN_TO_BASE"
  | "ACKNOWLEDGE_ALERT"
  | "INSPECT_CONTACT"
  | "CLASSIFY_CONTACT"
  | "SET_CONTACT_PRIORITY"
  | "REPORT_CONTACT";
export type ProtocolCommandKind = "SUBMIT_ISA" | "SUBMIT_SAGAT" | "SUBMIT_POST_BLOCK_SCALE";
export type StreamKind = "traffic"
  | "snapshot"
  | "domain_event"
  | "alert"
  | "command_result"
  | "probe"
  | "lifecycle"
  | "checkpoint"
  | "error";
export type ConnectionMode = "live" | "reconnecting" | "paused" | "observer" | "disconnected";

export interface PointMM {
  x_mm: number;
  y_mm: number;
}
export type RouteSnapshot = PointMM[];

export interface TerrainBounds {
  min_x_mm: number;
  min_y_mm: number;
  max_x_mm: number;
  max_y_mm: number;
}

export interface AircraftSnapshot {
  aircraft_id: string;
  label: string;
  position: PointMM;
  heading_mdeg: number;
  altitude_mm?: number;
  energy_units: number;
  predicted_home_reserve_units: number;
  mode: AircraftMode;
  link: LinkMode;
  sensor: SensorMode;
  assigned_sector_id: string | null;
  route: RouteSnapshot;
  mission_progress_ppm: number;
}

export interface ContactSnapshot {
  contact_id: string;
  evidence: ContactEvidence;
  workflow: ContactMode;
  classification: ContactClassification | null;
  priority: ContactPriority | null;
  report_ids: string[];
  /** Present only after backend evidence exists; never contains hidden truth. */
  position?: PointMM;
}

export interface AlertSnapshot {
  alert_id: string;
  kind: AlertKind;
  severity: AlertSeverity;
  entity_ids: string[];
  opened_sequence: number;
  opened_at_ms: number;
  closed_sequence: number | null;
  closed_at_ms: number | null;
  acknowledged: boolean;
  acknowledged_sequence: number | null;
  acknowledged_at_ms: number | null;
  payload: Record<string, JsonValue>;
}

export interface CoverageSectorSnapshot {
  covered_cells: number[][];
  covered_count: number;
  eligible_count: number;
  covered_cell_count: number;
  eligible_cell_count: number;
  coverage_ppm: number;
}

export interface CoverageSnapshot {
  grid_cell_mm: number;
  origin: PointMM;
  sectors: Record<string, CoverageSectorSnapshot>;
}

export interface InitialViewSnapshot {
  center: PointMM;
  width_mm: number;
  height_mm: number;
}

export interface WorldSnapshot {
  scenario_id: string;
  scenario_sha256: string;
  block_id: string;
  tick: number;
  simulation_time_ms: number;
  state_version: number;
  state_sha256: string;
  title: Record<Locale, string>;
  description: Record<Locale, string>;
  terrain: {
    bounds: TerrainBounds;
    polygon: PointMM[];
  };
  home: PointMM;
  initial_view: InitialViewSnapshot;
  sectors: Record<string, PointMM[]>;
  restricted_zones: Record<string, PointMM[]>;
  report_note_codes: Record<string, Record<Locale, string>>;
  aircraft: Record<string, AircraftSnapshot>;
  contacts: Record<string, ContactSnapshot>;
  alerts: Record<string, AlertSnapshot>;
  coverage: CoverageSnapshot;
}

export interface SessionView {
  presentation?: PresentationConfig | null;
  id: string;
  participant_id: string | null;
  visit_id: number | null;
  visit_ordinal: number | null;
  scenario_id: string;
  scenario_sha256: string | null;
  locale: Locale;
  lifecycle: Lifecycle;
  active_block_id: string | null;
  validity: string;
  session_mode: SessionMode;
  record_class: RecordClass;
  selected_block_id: Profile | null;
  block_order: Profile[];
  state_version: number;
  simulation_time_ms: number;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  interrupted_at: string | null;
  protocol_phase?: string;
  current_block_index?: number;
  active_probe?: ActiveProbePayload | null;
  next_block_id?: string | null;
}

export interface CreateSimulationSession {
  presentation?: PresentationConfig;
  participant_id: string;
  visit_ordinal: number;
  scenario_id: string;
  locale: Locale;
}

export interface CreateTechnicalSimulationSession {
  presentation?: PresentationConfig;
  scenario_id: string;
  block_id: Profile;
  locale: Locale;
}

export interface PreparedSession extends SessionView {
  controller_lease: string;
}

export interface RecoveryView extends SessionView {
  controller_lease: string | null;
}

export interface ScenarioSummary {
  scenario_id: string;
  scenario_sha256: string | null;
  title: string | null;
  description: string | null;
  titles?: Partial<Record<Locale, string>>;
  descriptions?: Partial<Record<Locale, string>>;
  aircraft_count: number | null;
  block_order: Profile[];
  locales: Locale[];
  profile_details?: Partial<Record<Profile, {
    duration_seconds: number;
    aircraft_count: number;
    contact_count: number;
    calibration_status: "engineering_preset_pending_human_calibration";
  }>>;
}

export interface ScenarioValidationView {
  valid: boolean;
  scenario_id: string | null;
  scenario_sha256: string | null;
  summary: ScenarioSummary | null;
  errors: ErrorDetail[];
}

export interface ErrorDetail {
  code: string;
  message: string;
  context?: Record<string, JsonValue>;
}

export interface CommandRequest {
  command_id: string;
  expected_state_version: number;
  kind: CommandKind | ProtocolCommandKind;
  payload: Record<string, JsonValue>;
}

export interface CommandResultView {
  command_id: string;
  status: "accepted" | "rejected" | "duplicate";
  code: string | null;
  message: string | null;
  expected_state_version: number | null;
  state_version: number;
  simulation_time_ms: number;
  payload: Record<string, JsonValue>;
}

export interface StreamEnvelope<T = JsonValue> {
  session_id: string;
  sequence: number;
  simulation_time_ms: number;
  wall_time_utc: string;
  state_version: number;
  kind: StreamKind;
  payload: T;
  /** Set on a post-reconnect full snapshot so the store can resynchronize. */
  resynchronizes_after_sequence?: number;
}

export interface IsaProbePayload {
  kind: "ISA";
  probe_id: string;
  question?: string;
  timeout_ms: number;
  options?: number[];
  min?: 1;
  max?: 10;
}

export interface SagatProbePayload {
  kind: "SAGAT";
  probe_id: string;
  sa_level: 1 | 2 | 3;
  domain: string;
  question: string;
  options: string[];
  timeout_ms: number;
}

export interface PostBlockScalePayload {
  kind: "POST_BLOCK";
  block_id?: string;
  scales?: ("NASA_TLX" | "BEDFORD")[];
  required?: ("NASA_TLX" | "BEDFORD")[];
}

export type ActiveProbePayload = IsaProbePayload | SagatProbePayload | PostBlockScalePayload;

export interface ArtifactView {
  kind: string;
  relative_path: string;
  sha256: string;
  size_bytes: number;
  created_at: string | null;
}

export interface DebriefView {
  status?: string;
  session_id?: string;
  scenario_id?: string;
  block_id?: string;
  timeline?: JsonValue[];
  metrics?: Record<string, JsonValue>;
  questionnaires?: Record<string, JsonValue>;
  [key: string]: JsonValue | undefined;
}

export interface LifecycleRequest {
  block_id?: string;
  reason?: string;
}

export interface FinishRequest {
  disposition?: "complete" | "abort";
  reason?: string;
}

export interface RecoverRequest {
  checkpoint_version: number;
  confirm_process_restart?: boolean;
}
