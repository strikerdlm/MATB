import { expect, it } from "vitest";
import { framesFrom } from "./ReplayTimeline";
import type { DebriefView } from "@/types/simulation";

it("places equal-time exposures on the public snapshot timeline without future state", () => {
  const debrief = { frames: [
    { block_id: "LOW", simulation_time_ms: 0, state_version: 0, snapshot: { marker: "before" } },
    { block_id: "LOW", simulation_time_ms: 1000, state_version: 1, snapshot: { marker: "after" } },
  ], presentation_events: [
    { version: 2, block_id: "LOW", simulation_time_ms: 500, sequence: 10, client_time_ms: 1500 },
    { version: 2, block_id: "LOW", simulation_time_ms: 500, sequence: 11, client_time_ms: 1700 },
    { version: 2, block_id: "HIGH", simulation_time_ms: 500, sequence: 12 },
  ] } as unknown as DebriefView;
  const frames = framesFrom(debrief);
  expect(frames.map(f => f.simulation_time_ms)).toEqual([0, 500, 500, 1000]);
  expect(frames[1].snapshot).toEqual({ marker: "before" });
  expect(frames[2].presentation_sequence).toBe(11);
});
