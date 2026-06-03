import { describe, it, expect } from "vitest";
import { METRICS, trajectorySeries, groupOverview } from "@/lib/viz";
import type { MetricRow } from "@/types";

const row = (p: string, v: number, l: MetricRow["workload_level"], value: number): MetricRow => ({
  participant_id: p, visit_ordinal: v, workload_level: l, metric: "nasatlx_raw_tlx", value,
});

describe("viz reshapers", () => {
  it("METRICS registry covers the seven backend metrics", () => {
    expect(Object.keys(METRICS)).toEqual([
      "sysmon_d_prime", "sysmon_hit_rate", "sysmon_mean_rt_ms",
      "comm_d_prime", "nasatlx_raw_tlx", "bedford", "isa_mean",
    ]);
    expect(METRICS.nasatlx_raw_tlx.label).toBeTruthy();
  });

  it("trajectorySeries fills 6 visits per level with null gaps", () => {
    const rows = [row("P01", 1, "LOW", 40), row("P01", 3, "LOW", 44), row("P01", 1, "HIGH", 80)];
    const t = trajectorySeries(rows, "P01", "nasatlx_raw_tlx");
    expect(t.visits).toEqual([1, 2, 3, 4, 5, 6]);
    expect(t.series.LOW).toEqual([40, null, 44, null, null, null]);
    expect(t.series.HIGH).toEqual([80, null, null, null, null, null]);
    expect(t.series.MEDIUM).toEqual([null, null, null, null, null, null]);
  });

  it("trajectorySeries ignores other participants and metrics", () => {
    const rows = [row("P02", 1, "LOW", 99), { ...row("P01", 1, "LOW", 40), metric: "bedford" }];
    const t = trajectorySeries(rows, "P01", "nasatlx_raw_tlx");
    expect(t.series.LOW).toEqual([null, null, null, null, null, null]);
  });

  it("groupOverview computes mean/sd/n across participants", () => {
    const rows = [row("P01", 1, "LOW", 40), row("P02", 1, "LOW", 60), row("P03", 1, "LOW", 50)];
    const g = groupOverview(rows, "nasatlx_raw_tlx");
    expect(g.stats.LOW.n[0]).toBe(3);
    expect(g.stats.LOW.mean[0]).toBeCloseTo(50, 6);
    expect(g.stats.LOW.sd[0]).toBeCloseTo(10, 6);        // sample SD of 40/50/60
    expect(g.stats.LOW.mean[1]).toBeNull();              // visit 2: no data
    expect(g.stats.MEDIUM.n.every((n) => n === 0)).toBe(true);
  });

  it("groupOverview sd is null when n < 2", () => {
    const g = groupOverview([row("P01", 2, "HIGH", 80)], "nasatlx_raw_tlx");
    expect(g.stats.HIGH.mean[1]).toBe(80);
    expect(g.stats.HIGH.sd[1]).toBeNull();
  });
});
