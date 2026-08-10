import { describe, expect, it } from "vitest";
import { parseOperationalHumanPerformanceStatus } from "../src/index.js";

describe("operational human-performance contracts", () => {
  it("keeps the operational status minimum and privacy-minimized", () => {
    const status = parseOperationalHumanPerformanceStatus({
      userId: "operator-1",
      role: "operator",
      dutyPeriodId: "DUTY-1",
      qualificationStatus: "current",
      fatigueSelfDeclaration: "able",
      screenExposureMinutes: 45,
      workloadLevel: "moderate",
      alertLoad: 2,
      status: "available",
      evidenceRefs: ["EV-HF-001"],
    });

    expect(Object.isFrozen(status)).toBe(true);
    expect(status.status).toBe("available");
    expect(Object.keys(status)).not.toContain("diagnosis");
    expect(JSON.stringify(status)).not.toMatch(/clinical|medical reasoning|fit-to-fly/i);
  });
});
