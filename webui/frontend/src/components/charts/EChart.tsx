"use client";

import dynamic from "next/dynamic";

// echarts-for-react touches `window`; load client-side only.
const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

// Canvas charts cannot consume CSS variables; these literals track the theme's
// info / warning / danger hues for LOW / MEDIUM / HIGH.
export const LEVEL_COLORS: Record<string, string> = {
  LOW: "#38bdf8",
  MEDIUM: "#f59e0b",
  HIGH: "#ef4444",
};

export const AXIS_STYLE = {
  axisLine: { lineStyle: { color: "#475569" } },
  axisLabel: { color: "#94a3b8" },
  splitLine: { lineStyle: { color: "#1e293b" } },
} as const;

const BASE_OPTION = {
  backgroundColor: "transparent",
  textStyle: { fontFamily: "Inter, system-ui, sans-serif" },
  toolbox: {
    feature: { saveAsImage: { pixelRatio: 2, name: "matb-chart", title: "PNG" } },
    iconStyle: { borderColor: "#94a3b8" },
    right: 8,
  },
  tooltip: { trigger: "axis" },
  legend: { textStyle: { color: "#94a3b8" } },
  grid: { left: 48, right: 24, top: 40, bottom: 32, containLabel: true },
};

export function EChart({ option, height = 360 }: { option: Record<string, unknown>; height?: number }) {
  return (
    <ReactECharts
      option={{ ...BASE_OPTION, ...option }}
      style={{ height, width: "100%" }}
      notMerge
      lazyUpdate
    />
  );
}
