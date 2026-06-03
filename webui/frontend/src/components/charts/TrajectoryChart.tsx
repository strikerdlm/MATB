"use client";

import { EChart, LEVEL_COLORS, AXIS_STYLE } from "@/components/charts/EChart";
import { METRICS, type Trajectory } from "@/lib/viz";
import { LEVELS } from "@/lib/tracker";

export function TrajectoryChart({ data, metric, kind = "line" }: {
  data: Trajectory; metric: string; kind?: "line" | "bar";
}) {
  const meta = METRICS[metric];
  const option = {
    xAxis: { type: "category", data: data.visits.map((v) => `Visit ${v}`), ...AXIS_STYLE },
    yAxis: { type: "value", name: meta?.unit ?? "", ...AXIS_STYLE },
    series: LEVELS.map((level) => ({
      name: level,
      type: kind,
      data: data.series[level],
      connectNulls: false,
      color: LEVEL_COLORS[level],
      symbolSize: 7,
    })),
  };
  return <EChart option={option} />;
}
