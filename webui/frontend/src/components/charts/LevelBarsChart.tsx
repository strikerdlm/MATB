"use client";

import { TrajectoryChart } from "@/components/charts/TrajectoryChart";
import type { Trajectory } from "@/lib/viz";

export function LevelBarsChart({ data, metric }: { data: Trajectory; metric: string }) {
  return <TrajectoryChart data={data} metric={metric} kind="bar" />;
}
