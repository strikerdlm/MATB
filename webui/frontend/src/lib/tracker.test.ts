import { describe, it, expect } from "vitest";
import { summarize, byParticipant, LEVELS } from "@/lib/tracker";
import type { TrackerCell } from "@/types";

function grid(present: Array<[string, number, string]>, pids = ["P01"]): TrackerCell[] {
  const cells: TrackerCell[] = [];
  for (const pid of pids)
    for (let v = 1; v <= 6; v++)
      for (const lvl of LEVELS)
        cells.push({
          participant_id: pid, visit_ordinal: v, scheduled_day: (v - 1) * 3,
          workload_level: lvl,
          present: present.some(([p, vv, l]) => p === pid && vv === v && l === lvl),
        });
  return cells;
}

describe("tracker aggregation", () => {
  it("summarize counts filled vs total", () => {
    const s = summarize(grid([["P01", 1, "LOW"], ["P01", 1, "MEDIUM"]]));
    expect(s.total).toBe(18);
    expect(s.filled).toBe(2);
  });

  it("byParticipant groups cells and computes per-participant completeness", () => {
    const rows = byParticipant(grid([["P01", 1, "LOW"]], ["P01", "P02"]));
    expect(rows.map((r) => r.participantId)).toEqual(["P01", "P02"]);
    expect(rows[0].filled).toBe(1);
    expect(rows[0].total).toBe(18);
    expect(rows[1].filled).toBe(0);
  });

  it("byParticipant orders visit×level cells deterministically (visit then LOW/MED/HIGH)", () => {
    const rows = byParticipant(grid([["P01", 2, "HIGH"]]));
    const cell = rows[0].cells.find((c) => c.visit_ordinal === 2 && c.workload_level === "HIGH");
    expect(cell?.present).toBe(true);
    expect(rows[0].cells.length).toBe(18);
    expect(rows[0].cells[0]).toMatchObject({ visit_ordinal: 1, workload_level: "LOW" });
    expect(rows[0].cells[5]).toMatchObject({ visit_ordinal: 2, workload_level: "HIGH" });
  });
});
