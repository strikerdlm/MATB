"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { usePathname } from "next/navigation";

import type { ExecutionPurpose, ExperimentId } from "@/lib/experiments";

export type ExperimentFlowStage = "prepare" | "instructions" | "perform" | "complete";

export interface ExperimentFlowProgress {
  experimentId: ExperimentId;
  stage: ExperimentFlowStage | null;
  purpose?: ExecutionPurpose;
}

export type PvtPageStage = "select" | "kss" | "instructions" | "pvt" | "saving" | "save_error" | "complete";
export type ScreenPageStage = "select" | "run" | "saving" | "review";

export function flowStageForPvt(stage: PvtPageStage, activityStarted: boolean): ExperimentFlowStage {
  if (stage === "select") return "prepare";
  if (stage === "kss" || stage === "instructions" || (stage === "pvt" && !activityStarted)) return "instructions";
  if (stage === "complete") return "complete";
  return "perform";
}

export function flowStageForScreen(
  stage: ScreenPageStage,
  activityStarted: boolean,
  saved: boolean,
): ExperimentFlowStage {
  if (stage === "select") return "prepare";
  if (stage === "run" && !activityStarted) return "instructions";
  if (stage === "review" && saved) return "complete";
  return "perform";
}

interface RoutedProgress extends ExperimentFlowProgress {
  pathname: string;
}

interface ExperimentFlowContextValue {
  progress: ExperimentFlowProgress | null;
  report: (progress: ExperimentFlowProgress) => void;
}

const ExperimentFlowContext = createContext<ExperimentFlowContextValue>({
  progress: null,
  report: () => undefined,
});

export function ExperimentFlowProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const [reported, setReported] = useState<RoutedProgress | null>(null);
  const report = useCallback((progress: ExperimentFlowProgress) => {
    setReported({ ...progress, pathname });
  }, [pathname]);
  const progress = useMemo<ExperimentFlowProgress | null>(() => reported?.pathname === pathname
    ? { experimentId: reported.experimentId, stage: reported.stage, purpose: reported.purpose }
    : null, [pathname, reported]);
  const value = useMemo(() => ({ progress, report }), [progress, report]);

  return <ExperimentFlowContext.Provider value={value}>{children}</ExperimentFlowContext.Provider>;
}

export function useExperimentFlowProgress(): ExperimentFlowProgress | null {
  return useContext(ExperimentFlowContext).progress;
}

export function useReportExperimentFlow(
  experimentId: ExperimentId,
  stage: ExperimentFlowStage | null,
  purpose?: ExecutionPurpose,
): void {
  const { report } = useContext(ExperimentFlowContext);
  useEffect(() => report({ experimentId, stage, purpose }), [experimentId, report, stage, purpose]);
}
