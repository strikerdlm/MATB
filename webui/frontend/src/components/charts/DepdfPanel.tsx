"use client";

import { EChart, AXIS_STYLE } from "@/components/charts/EChart";
import type { FitRow } from "@/types";

const VISIT_COLORS = ["#38bdf8", "#34d399", "#f59e0b", "#f472b6", "#a78bfa", "#ef4444"];

function ParamChart({ fits, param, label }: { fits: FitRow[]; param: "g0" | "p0" | "tau0"; label: string }) {
  // P0 is a probability (fixed [0,1] axis); G0/tau0 use a 0-anchored axis so a
  // single early fit doesn't produce a degenerate auto-scaled range.
  const yAxis = param === "p0"
    ? { type: "value", min: 0, max: 1, ...AXIS_STYLE }
    : { type: "value", ...AXIS_STYLE };
  const option = {
    title: { text: label, textStyle: { color: "#94a3b8", fontSize: 12 } },
    xAxis: { type: "category", data: fits.map((f) => `V${f.visit_ordinal}`), ...AXIS_STYLE },
    yAxis,
    series: [{ type: "line", data: fits.map((f) => f[param]), color: "#38bdf8", symbolSize: 7 }],
    legend: { show: false },
  };
  return <EChart option={option} height={200} />;
}

export function DepdfPanel({ fits }: { fits: FitRow[] }) {
  if (fits.length === 0)
    return <p className="text-sm text-muted-foreground">No fits yet — a fit needs all 3 levels of a visit ingested.</p>;
  const sorted = [...fits].sort((a, b) => a.visit_ordinal - b.visit_ordinal);
  const curveOption = {
    xAxis: { type: "value", name: "G / G₀", min: 1, max: 3, ...AXIS_STYLE },
    yAxis: { type: "value", name: "P^h", min: 0, max: 1, ...AXIS_STYLE },
    tooltip: { trigger: "axis" },
    series: sorted.map((f) => ({
      name: `Visit ${f.visit_ordinal}`,
      type: "line",
      showSymbol: false,
      data: f.curve.map((pt) => [pt.r, pt.p]),
      color: VISIT_COLORS[(f.visit_ordinal - 1) % VISIT_COLORS.length],
    })),
  };
  return (
    <div className="space-y-6">
      <div>
        <h3 className="mb-2 text-sm font-medium">Human-nonfailure curve P^h(G/G₀) per fitted visit</h3>
        <EChart option={curveOption} height={380} />
      </div>
      <div>
        <h3 className="mb-2 text-sm font-medium">Fitted parameters across visits</h3>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <ParamChart fits={sorted} param="g0" label="G₀ (baseline MWL)" />
          <ParamChart fits={sorted} param="p0" label="P₀ (baseline nonfailure)" />
          <ParamChart fits={sorted} param="tau0" label="τ₀ (baseline MTTF)" />
        </div>
      </div>
    </div>
  );
}
