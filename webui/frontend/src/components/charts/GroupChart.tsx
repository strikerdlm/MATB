"use client";

import { ScientificChart } from "@/components/charts/EChart";
import { buildGroupTrajectoryOption } from "@/lib/figures";
import { METRICS, type GroupStats } from "@/lib/viz";

export function GroupChart({ data, metric }: { data: GroupStats; metric: string }) {
  const meta = METRICS[metric];
  return (
    <ScientificChart
      figureId="Cohort Mean Trajectory"
      exportName={`${metric}-cohort-mean-ci`}
      option={buildGroupTrajectoryOption(data, metric)}
      height={420}
      caption={`${meta?.label ?? metric} cohort mean trajectory with 95% confidence intervals computed from available participants at each visit and workload level.`}
    />
  );
}
