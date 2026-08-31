import { describe, expect, it } from "vitest";

import {
  buildExperimentSpec,
  compareUnicodeCodePoints,
  formatTimelineTime,
  INITIAL_EXPERIMENT_EVENTS,
  summarizeExperiment,
  validateTimeline,
} from "@/lib/experiment-designer";
import type { ExperimentTimelineEvent } from "@/types";

const EVENTS: ExperimentTimelineEvent[] = [
  { eventKey: "target", atSeconds: 10, durationSeconds: 10, task: "sysmon", command: "lights-1-failure", value: true },
  { eventKey: "nontarget", atSeconds: 25, durationSeconds: 2, task: "sysmon", command: "open_nontarget_opportunity" },
];

describe("experiment designer helpers", () => {
  it("derives scientific summaries without storing duplicate UI state", () => {
    const summary = summarizeExperiment([
      { eventKey: "start", atSeconds: 0, durationSeconds: null, task: "sysmon", command: "start" },
      ...EVENTS,
      { eventKey: "stop", atSeconds: 59, durationSeconds: null, task: "sysmon", command: "stop" },
    ], 60);
    expect(summary.sourceCommandCount).toBe(4);
    expect(summary.sourceCommandRatePerMinute).toBe(4);
    expect(summary.stimulusOpportunityCount).toBe(2);
    expect(summary.stimulusOpportunityRatePerMinute).toBe(2);
    expect(summary.perTaskStimulusOpportunityRatePerMinute.sysmon).toBe(2);
    expect(summary.minimumStimulusRefractoryMsByTask.sysmon).toBe(15_000);
    expect(summary.overlapCount).toBe(0);
    expect(summary.sysmonTargetOpportunities).toBe(1);
    expect(summary.sysmonNontargetOpportunities).toBe(1);
  });

  it("builds the strict wire contract in integer nanoseconds", () => {
    const spec = buildExperimentSpec(EVENTS, 60, 42);
    expect(spec.duration_ns).toBe(60_000_000_000);
    expect(spec.timeline[0].at_ns).toBe(10_000_000_000);
    expect(spec.metadata.workload_label_status).toBe("engineering_preset_pending_human_calibration");
  });

  it("fails local constraints for events beyond the experiment boundary", () => {
    const constraints = validateTimeline([
      { ...EVENTS[0], atSeconds: 55, durationSeconds: 10 },
    ], 60);
    expect(constraints.find((item) => item.id === "timeline-boundary")?.status).toBe("fail");
  });

  it("keeps the shipped design compiler-valid, including the COMM evidence boundary", () => {
    expect(validateTimeline(INITIAL_EXPERIMENT_EVENTS, 60, 42).some((item) => (
      item.status === "fail"
    ))).toBe(false);
  });

  it("counts the implicit COMM response-availability interval in overlap summaries", () => {
    const summary = summarizeExperiment(INITIAL_EXPERIMENT_EVENTS, 60);

    expect(summary.overlapCount).toBe(1);
    expect(summary.overlapPercent).toBeCloseTo(100 / 3);
  });

  it("mirrors strict runtime lifecycle and supported-command semantics locally", () => {
    const constraints = validateTimeline([
      { eventKey: "prompt", atSeconds: 10, durationSeconds: null, task: "communications", command: "radioprompt", value: "own" },
      { eventKey: "stop", atSeconds: 59, durationSeconds: null, task: "communications", command: "stop" },
    ], 60, 42);
    expect(constraints.find((item) => item.id === "runtime-semantics")?.status).toBe("fail");

    const unsupported = validateTimeline([
      { eventKey: "probe", atSeconds: 1, durationSeconds: null, task: "genericscales", command: "start" },
    ], 60, 42);
    expect(unsupported.find((item) => item.id === "runtime-semantics")?.status).toBe("fail");
  });

  it("uses backend-equivalent Unicode code-point ordering for same-tick keys", () => {
    expect(compareUnicodeCodePoints("Z-start", "a-stop")).toBeLessThan(0);
    const constraints = validateTimeline([
      { eventKey: "Z-start", atSeconds: 0, durationSeconds: null, task: "track", command: "start" },
      { eventKey: "a-stop", atSeconds: 0, durationSeconds: null, task: "track", command: "stop" },
    ], 60, 42);
    expect(constraints.find((item) => item.id === "runtime-semantics")?.status).toBe("pass");
  });

  it("rejects values that cannot be represented exactly by browser integers", () => {
    const unsafe = validateTimeline([
      { ...EVENTS[0], atSeconds: Number.MAX_SAFE_INTEGER + 1 },
    ], 60, Number.MAX_SAFE_INTEGER + 1);
    expect(unsafe.find((item) => item.id === "integer-precision")?.status).toBe("fail");
    expect(() => buildExperimentSpec(EVENTS, 60, Number.MAX_SAFE_INTEGER + 1)).toThrow(/safe integer/i);
  });

  it("rejects negative experiment seeds locally and before wire serialization", () => {
    const constraints = validateTimeline(EVENTS, 60, -1);
    expect(constraints.find((item) => item.id === "seed-range")?.status).toBe("fail");
    expect(() => buildExperimentSpec(EVENTS, 60, -1)).toThrow(/seed.*non-negative/i);
  });

  it("formats short and long experiment times", () => {
    expect(formatTimelineTime(65)).toBe("01:05");
    expect(formatTimelineTime(3665)).toBe("01:01:05");
  });
});
