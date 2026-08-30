import { describe, expect, it } from "vitest";
import {
  buildGroupTrajectoryOption,
  buildIntervalForestOption,
  buildLmmForestOption,
  ci95,
  lmmIntervalRows,
  preflightScientificOption,
} from "@/lib/figures";
import type { GroupStats } from "@/lib/viz";
import type { LmmResult } from "@/types";

const okLmm = (name: string, coef: number, low: number, high: number): LmmResult => ({
  status: "ok",
  coefs: [{
    name,
    coef,
    ci95: [low, high],
    p: 0.02,
    std_effect: 0.4,
    standardizer: "sqrt(re_var + resid_var)",
  }],
});

describe("scientific figure builders", () => {
  it("computes 95% confidence intervals from mean, sd, and n", () => {
    expect(ci95(50, 10, 4)).toEqual([40.2, 59.8]);
    expect(ci95(50, null, 4)).toBeNull();
    expect(ci95(50, 10, 1)).toBeNull();
  });

  it("builds cohort trajectories with 95% CI ribbons", () => {
    const group: GroupStats = {
      visits: [1, 2, 3, 4, 5, 6],
      stats: {
        LOW: { mean: [50, null, null, null, null, null], sd: [10, null, null, null, null, null], n: [4, 0, 0, 0, 0, 0] },
        MEDIUM: { mean: [60, null, null, null, null, null], sd: [10, null, null, null, null, null], n: [4, 0, 0, 0, 0, 0] },
        HIGH: { mean: [70, null, null, null, null, null], sd: [10, null, null, null, null, null], n: [4, 0, 0, 0, 0, 0] },
      },
    };
    const option = buildGroupTrajectoryOption(group, "nasatlx_rtlx_mean_0_100");
    const series = option.series as Array<Record<string, unknown>>;
    expect(series).toHaveLength(9);
    expect(series[0].data).toEqual([40.2, null, null, null, null, null]);
    expect(series[1].data).toEqual([19.6, null, null, null, null, null]);
    expect(preflightScientificOption(option)).toEqual([]);
  });

  it("extracts LMM interval rows with readable terms", () => {
    const rows = lmmIntervalRows({
      nasatlx_rtlx_mean_0_100: okLmm("visit_c", -1.2, -2.1, -0.3),
    }, "q2");
    expect(rows).toEqual([{
      label: "RTLX mean (0–100): Visit slope",
      estimate: -1.2,
      low: -2.1,
      high: -0.3,
      group: "Q2",
    }]);
  });

  it("builds serializable interval forest options that pass preflight", () => {
    const option = buildLmmForestOption({
      nasatlx_rtlx_mean_0_100: okLmm("visit_c", -1.2, -2.1, -0.3),
    }, "q2");
    expect(JSON.stringify(option)).toContain("Visit slope");
    expect(preflightScientificOption(option)).toEqual([]);
  });

  it("preflight catches non-publication options", () => {
    const issues = preflightScientificOption(buildIntervalForestOption([], "Estimate", { reference: 0 }));
    expect(issues).toEqual([]);
    const bad = preflightScientificOption({ title: { text: "Bad" }, animation: true });
    expect(bad.some((issue) => issue.message.includes("animation"))).toBe(true);
    expect(bad.some((issue) => issue.message.includes("title"))).toBe(true);
  });
});
