"use client";
import { useSearchParams } from "next/navigation";
import type { ExecutionPurpose } from "@/lib/experiments";
export function useExecutionPurpose(): ExecutionPurpose {
  const query = useSearchParams();
  return query.get("purpose") === "practice" || query.get("fast") === "1" ? "practice" : "study";
}
export function announceExperimentStage(stage: number) {
  window.dispatchEvent(new CustomEvent("matb-experiment-stage", { detail: stage }));
}
