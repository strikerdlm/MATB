import { describe, expect, it } from "vitest";
import { evaluateOperationalStatus } from "../src/operational.js";

describe("operational human-performance privacy boundary", () => {
  it("does not expose diagnosis or automated fitness decisions", () => {
    const result = evaluateOperationalStatus({ userId: "operator-1", role: "operator", dutyPeriodId: "DUTY-1", qualificationStatus: "current", fatigueSelfDeclaration: "not-recorded", screenExposureMinutes: 10, workloadLevel: "low", alertLoad: 0, status: "available", evidenceRefs: ["EV-HF-003"] }, { maxScreenExposureMinutes: 120, maxAlertLoad: 4, policyVersion: "HF-POL-1" });
    expect(Object.keys(result)).not.toContain("diagnosis");
    expect(Object.keys(result)).not.toContain("fitnessToFly");
    expect(JSON.stringify(result)).not.toMatch(/clinical|medical reasoning|fit-to-fly/i);
  });
});
