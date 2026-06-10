"use client";

import { ScientificChart } from "@/components/charts/EChart";
import { buildTrajectoryOption } from "@/lib/figures";
import { type Trajectory } from "@/lib/viz";

export function TrajectoryChart({ data, metric, kind = "line" }: {
  data: Trajectory; metric: string; kind?: "line" | "bar";
}) {
  return (
    <ScientificChart
      figureId={kind === "bar" ? "Participant Workload Profile" : "Participant Trajectory"}
      exportName={`${metric}-${kind === "bar" ? "workload-profile" : "participant-trajectory"}`}
      option={buildTrajectoryOption(data, metric, kind)}
      caption="Per-participant observed metric values across the six planned visits, stratified by MATB workload level."
    />
  );
}
