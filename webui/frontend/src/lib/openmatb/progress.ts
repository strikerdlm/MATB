import type { ExperimentFlowStage } from "@/lib/experiment-flow";
import type { OpenMatbLifecycle } from "@/types/openmatb";

export function openMatbStage(lifecycle?: OpenMatbLifecycle): ExperimentFlowStage | null {
  if (!lifecycle || ["ABORTED", "FAILED", "INTERRUPTED"].includes(lifecycle)) return null;
  if (lifecycle === "INSTRUCTIONS" || lifecycle === "READY") return "instructions";
  return lifecycle === "COMPLETE" ? "complete" : "perform";
}

export const OPENMATB_TERMINAL = new Set<OpenMatbLifecycle>(["COMPLETE", "ABORTED", "FAILED", "INTERRUPTED"]);
