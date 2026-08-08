import { describe, expect, it } from "vitest";
import * as kernel from "@fac-isr/safety-kernel";

describe("compiled safety-kernel entrypoint", () => {
  it("loads the package export after its build step", () => {
    expect(typeof kernel.parseMissionRevision).toBe("function");
    expect(typeof kernel.parseSafetyEvaluationResult).toBe("function");
  });
});
