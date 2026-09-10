import { describe, expect, it } from "vitest";
import { openMatbStage } from "./progress";

describe("authoritative OpenMATB progress", () => {
  it("uses lifecycle for instructions, task, ratings and completion", () => {
    expect(openMatbStage("INSTRUCTIONS")).toBe("instructions");
    expect(openMatbStage("READY")).toBe("instructions");
    expect(openMatbStage("STARTING")).toBe("perform");
    expect(openMatbStage("AWAITING_SCALE")).toBe("perform");
    expect(openMatbStage("BETWEEN_BLOCKS")).toBe("perform");
    expect(openMatbStage("COMPLETE")).toBe("complete");
    for (const state of ["FAILED", "ABORTED", "INTERRUPTED"] as const) expect(openMatbStage(state)).toBeNull();
  });
});
