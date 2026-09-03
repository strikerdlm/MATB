export type OpenMatbProfile = "PRACTICE" | "LOW" | "MEDIUM" | "HIGH";
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

export interface OpenMatbSession {
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
