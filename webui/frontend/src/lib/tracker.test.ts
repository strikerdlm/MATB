import { describe, it, expect } from "vitest";
import { summarize, byParticipant, LEVELS } from "@/lib/tracker";
import type { TrackerCell } from "@/types";

function grid(present: Array<[string, number, string]>, pids = ["P01"]): TrackerCell[] {
  const cells: TrackerCell[] = [];
  const visits = [
    { ordinal: 1, scheduledDay: 0 },
    { ordinal: 2, scheduledDay: 8 },
    { ordinal: 3, scheduledDay: 15 },
  ];
  for (const pid of pids)
    for (const visit of visits)
      for (const lvl of LEVELS)
        cells.push({
          participant_id: pid, visit_ordinal: visit.ordinal, scheduled_day: visit.scheduledDay,
          workload_level: lvl,
          present: present.some(([p, vv, l]) => p === pid && vv === visit.ordinal && l === lvl),
        });
  return cells;
}

describe("tracker aggregation", () => {
  it("summarize counts filled vs total", () => {
    const s = summarize(grid([["P01", 1, "LOW"], ["P01", 1, "MEDIUM"]]));
    expect(s.total).toBe(9);
    expect(s.filled).toBe(2);
  });

  it("byParticipant groups cells and computes per-participant completeness", () => {
    const rows = byParticipant(grid([["P01", 1, "LOW"]], ["P01", "P02"]));
    expect(rows.map((r) => r.participantId)).toEqual(["P01", "P02"]);
    expect(rows[0].filled).toBe(1);
    expect(rows[0].total).toBe(9);
    expect(rows[1].filled).toBe(0);
  });

  it("byParticipant orders visit×level cells deterministically (visit then LOW/MED/HIGH)", () => {
    const rows = byParticipant(grid([["P01", 2, "HIGH"]]));
    const cell = rows[0].cells.find((c) => c.visit_ordinal === 2 && c.workload_level === "HIGH");
    expect(cell?.present).toBe(true);
    expect(rows[0].cells.length).toBe(9);
    expect(rows[0].cells[0]).toMatchObject({ visit_ordinal: 1, workload_level: "LOW" });
    expect(rows[0].cells[5]).toMatchObject({ visit_ordinal: 2, workload_level: "HIGH" });
  });
});
