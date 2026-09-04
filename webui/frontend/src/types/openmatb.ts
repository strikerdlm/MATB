export type OpenMatbProfile = "PRACTICE" | "LOW" | "MEDIUM" | "HIGH";
export type OpenMatbVisualTheme = "classic" | "cockpit" | "fac_modern";
export type OpenMatbLifecycle = "INSTRUCTIONS" | "READY" | "STARTING" | "RUNNING" | "PAUSED" | "AWAITING_SCALE" | "BETWEEN_BLOCKS" | "COMPLETE" | "ABORTED" | "FAILED" | "INTERRUPTED";

export interface OpenMatbProfileSettings {
  duration_seconds: number;
  difficulty: number;
  track_target_proportion: number;
  resman_loss_per_min: number;
  isa_probe_interval_sec: number;
}

export interface OpenMatbPresetSet {
  preset_id: string;
  version: string;
  label_es: string;
  status: "draft" | "published";
  sha256: string;
  profiles: Record<OpenMatbProfile, OpenMatbProfileSettings>;
}

export interface OpenMatbInstructionProtocol {
  protocol_id: string;
  version: string;
  locale: string;
  status: "draft" | "published";
  sha256: string;
  title: string;
  steps: string[];
  task_instructions: Record<string, string>;
  visit_instructions: Record<string, string>;
}

export interface OpenMatbReadiness {
  ready: boolean;
  platform: string;
  python_executable: string;
  openmatb_entrypoint: string;
  display_index_default: number;
  checks: Record<string, boolean>;
  warnings: string[];
}

export interface OpenMatbVisualProfilePalette {
  app_background: string;
  panel_background: string;
  instrument_background: string;
  panel_header: string;
  panel_header_text: string;
  control_background: string;
  control_foreground: string;
  text: string;
  muted_text: string;
  border: string;
  grid: string;
  accent: string;
  safe: string;
  warning: string;
  critical: string;
  disabled: string;
}

export interface OpenMatbTrackingAppearance {
  panel: string;
  axis: string;
  grid: string;
  target: string;
  target_fill: string;
  cursor: string;
  cursor_outside: string;
  show_panel: boolean;
  show_grid: boolean;
  closed_target_border: boolean;
}

export interface OpenMatbSystemMonitoringAppearance {
  panel: string;
  lamp_1: string;
  lamp_2: string;
  lamp_3: string;
  lamp_4: string;
  lamp_off: string;
  lamp_border: string;
  lamp_shape: "rectangle" | "circle";
  scale: string;
  pointer: string;
  feedback_positive: string;
  feedback_negative: string;
}

export interface OpenMatbCommunicationsAppearance {
  panel: string;
  display_background: string;
  display_border: string;
  active: string;
  inactive: string;
  positive: string;
  negative: string;
  show_display_bezel: boolean;
}

export interface OpenMatbResourceManagementAppearance {
  panel: string;
  tank_1: string;
  tank_2: string;
  tank_3: string;
  tank_4: string;
  tank_5: string;
  tank_6: string;
  fluid: string;
  pipe_on: string;
  pipe_off: string;
  pump_on: string;
  pump_off: string;
  pump_failure: string;
  tolerance: string;
  meter: string;
  show_pump_ring: boolean;
}

export interface OpenMatbWorkloadAppearance {
  panel: string;
  scale: string;
  marker: string;
}

export interface OpenMatbVisualProfileDocument {
  schema_version: "openmatb-visual-profile-v1";
  profile_id: string;
  version: string;
  label: string;
  geometry_policy: "preserve_openmatb_v1";
  palette: OpenMatbVisualProfilePalette;
  metrics: {
    line_width: number;
    panel_radius: number;
    corner_mark_ratio: number;
  };
  modules: {
    tracking: OpenMatbTrackingAppearance;
    system_monitoring: OpenMatbSystemMonitoringAppearance;
    communications: OpenMatbCommunicationsAppearance;
    resource_management: OpenMatbResourceManagementAppearance;
    workload: OpenMatbWorkloadAppearance;
  };
}

export interface OpenMatbVisualProfileIssue {
  code: string;
  message: string;
  paths: string[];
  ratio: number;
  minimum: number;
}

export interface OpenMatbVisualProfile {
  profile_id: string;
  version: string;
  label: string;
  status: "draft" | "published";
  schema_version: "openmatb-visual-profile-v1";
  sha256: string;
  payload: OpenMatbVisualProfileDocument;
  validation: {
    valid: boolean;
    publishable: boolean;
    errors: OpenMatbVisualProfileIssue[];
    warnings: OpenMatbVisualProfileIssue[];
    unacknowledged_warning_codes: string[];
  };
  warning_acknowledgements: string[];
  bundled: boolean;
  created_at: string;
  published_at: string | null;
}

export interface OpenMatbVisualPreview {
  lifecycle: "IDLE" | "STARTING" | "RUNNING" | "FAILED";
  profile_id: string | null;
  profile_version: string | null;
  profile_sha256: string | null;
  pid: number | null;
  artifact_root: string | null;
  last_error: string | null;
}

export interface OpenMatbSession {
  execution_purpose: "practice" | "study";
  locale: "es-419" | "en";
  id: string;
  participant_id: string;
  visit_ordinal: number;
  visit_code: string;
  scheduled_day: number;
  lifecycle: OpenMatbLifecycle;
  block_order: OpenMatbProfile[];
  current_block_index: number;
  active_block: OpenMatbProfile | null;
  preset_id: string;
  preset_version: string;
  preset_sha256: string;
  instruction_protocol: OpenMatbInstructionProtocol;
  visit_instruction: string;
  visual_theme: string;
  visual_profile_id: string | null;
  visual_profile_version: string | null;
  visual_profile_schema_version: string | null;
  visual_profile_sha256: string | null;
  display_index: number;
  scores: Record<string, Record<string, unknown>>;
  active_pid: number | null;
  last_error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface PreparedOpenMatbSession {
  session: OpenMatbSession;
  controller_lease: string;
  participant_token: string;
}

export interface WorkloadScaleSubmission {
  nasa_tlx: Record<"mental_demand" | "physical_demand" | "temporal_demand" | "performance" | "effort" | "frustration", number>;
  bedford: number;
}
