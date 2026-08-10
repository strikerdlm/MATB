import { describe, expect, it } from "vitest";
import { createCrmBrief, evaluateAlertLoad, evaluateOperationalStatus, recordWorkloadPulse } from "../src/operational.js";

const validStatusInput = {
  userId: "operator-1",
  role: "operator",
  dutyPeriodId: "DUTY-1",
  qualificationStatus: "current" as const,
  fatigueSelfDeclaration: "able" as const,
  screenExposureMinutes: 45,
  workloadLevel: "moderate" as const,
  alertLoad: 2,
  status: "available" as const,
  evidenceRefs: ["EV-HF-001"],
};

describe("operational human-performance controls", () => {
  it("restricts duty when screen exposure exceeds the approved policy limit", () => {
    const result = evaluateOperationalStatus({ ...validStatusInput, screenExposureMinutes: 999 }, { maxScreenExposureMinutes: 120, maxAlertLoad: 4, policyVersion: "HF-POL-1" });
    expect(result.status).toBe("restricted");
    expect(result.evidenceRefs).toContain("policy:HF-POL-1");
  });

  it("stores workload pulses as operational minimum data", () => {
    const pulse = recordWorkloadPulse({ userId: "operator-1", missionRevisionId: "mission-1:r0", observedAtUtc: "2026-08-10T15:00:00.000Z", level: "high", source: "self-report", evidenceRefs: ["EV-HF-002"] });
    expect(pulse.level).toBe("high");
    expect(JSON.stringify(pulse)).not.toMatch(/diagnosis|clinical|medical reasoning/i);
  });

  it("raises escalation when unresolved alert load exceeds policy", () => {
    const result = evaluateAlertLoad([{ severity: "warning", acknowledged: false }, { severity: "blocker", acknowledged: false }, { severity: "info", acknowledged: true }], { escalateAtUnresolved: 2, policyVersion: "HF-POL-1" });
    expect(result.level).toBe("high");
    expect(result.escalationRequired).toBe(true);
    expect(result.unresolved).toBe(2);
  });

  it("requires CRM transfer and incapacitation plans", () => {
    expect(() => createCrmBrief({ missionRevisionId: "mission-1:r0", participants: [{ userId: "operator-1", role: "operator" }], communicationPlan: "", transferOfControl: "", incapacitationPlan: "", acknowledgedBy: [] })).toThrow(/communication/i);
  });
});
