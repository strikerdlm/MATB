export const PVT_PROTOCOL_DURATION_MS = 10 * 60 * 1_000;
export const PVT_RESPONSE_TIMEOUT_MS = 30_000;
export const PVT_MIN_WAIT_MS = 2_000;
export const PVT_MAX_WAIT_MS = 10_000;

export type PvtOutcome = "response" | "lapse" | "false_start" | "timeout";

export interface PvtTrial {
  index: number;
  wait_ms: number;
  stimulus_at_ms: number | null;
  response_at_ms: number | null;
  rt_ms: number | null;
  outcome: PvtOutcome;
}
export interface PvtPayload {
  locale?: "es-419" | "en";
  execution_purpose?: "practice" | "study";
  timing_version?: 1 | 2;
  interruption_count?: number;
  max_frame_gap_ms?: number;
  terminal_phase?: "waiting" | "stimulus" | "feedback" | "complete";
  terminal_stimulus_at_ms?: number | null;
  participant_id: string;
  visit_ordinal: number;
  kss_score: number;
  administered_at: string;
  duration_ms: number;
  fast_mode: boolean;
  trials: PvtTrial[];
  overwrite?: boolean;
}

export interface PvtRunResult {
  durationMs: number; trials: PvtTrial[]; administeredAt: string;
  interruptionCount: number; maxFrameGapMs: number;
  terminalPhase: "waiting" | "stimulus" | "feedback" | "complete";
  terminalStimulusAtMs: number | null;
}

export function randomPvtWait(random: () => number = Math.random): number {
  return PVT_MIN_WAIT_MS + Math.floor(random() * (PVT_MAX_WAIT_MS - PVT_MIN_WAIT_MS + 1));
}

export function classifyPvtResponse(rtMs: number): Extract<PvtOutcome, "response" | "lapse" | "false_start"> {
  if (rtMs < 100) return "false_start";
  if (rtMs >= 500) return "lapse";
  return "response";
}
