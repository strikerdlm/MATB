"use client";

import { EChart, LEVEL_COLORS, AXIS_STYLE } from "@/components/charts/EChart";
import { METRICS, type GroupStats } from "@/lib/viz";
import { LEVELS } from "@/lib/tracker";

export function GroupChart({ data, metric }: { data: GroupStats; metric: string }) {
  const meta = METRICS[metric];
  const series: Record<string, unknown>[] = [];
  for (const level of LEVELS) {
    const { mean, sd } = data.stats[level];
    const lower = mean.map((m, i) => (m !== null && sd[i] !== null ? m - (sd[i] as number) : null));
    const band = mean.map((m, i) => (m !== null && sd[i] !== null ? 2 * (sd[i] as number) : null));
    // invisible base + band (stacked) render the ±SD envelope
    series.push({
      name: `${level} −SD`, type: "line", stack: `band-${level}`, data: lower,
      lineStyle: { opacity: 0 }, symbol: "none", tooltip: { show: false }, legendHoverLink: false,
    });
    series.push({
      name: `${level} ±SD`, type: "line", stack: `band-${level}`, data: band,
      lineStyle: { opacity: 0 }, symbol: "none",
      areaStyle: { color: LEVEL_COLORS[level], opacity: 0.12 },
      tooltip: { show: false }, legendHoverLink: false,
    });
    series.push({
      name: level, type: "line", data: mean, color: LEVEL_COLORS[level],
      connectNulls: false, symbolSize: 7,
    });
  }
  const option = {
    xAxis: { type: "category", data: data.visits.map((v) => `Visit ${v}`), ...AXIS_STYLE },
    yAxis: { type: "value", name: meta?.unit ?? "", scale: true, ...AXIS_STYLE },
    legend: { data: [...LEVELS], textStyle: { color: "#94a3b8" } },
    series,
  };
  return <EChart option={option} height={400} />;
}
