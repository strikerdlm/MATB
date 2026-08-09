import { describe, expect, it } from "vitest";
import { compareCapabilityBaselines, evaluateCapability } from "../src/capabilities.js";
const claim = { id: "c-1", subjectId: "uas-1", capability: "vlos" as const, value: true, operatingConditions: {}, evidenceRefs: ["ev-1"], confidence: "qualified" as const, validFromUtc: "2026-01-01T00:00:00Z" };
const snapshot = { current: true, acceptedEvidenceRefs: ["ev-1"], approved: true, asOfUtc: "2026-08-08T00:00:00Z", subjectId: "uas-1" };
describe("capability evidence", () => {
  it("does not treat vendor-claimed IFR capability as approved", () => {
    expect(evaluateCapability({ ...claim, capability: "ifr", confidence: "vendor-claimed" }, { flightRule: "IFR" }, snapshot).status).toBe("unknown");
    expect(evaluateCapability({ ...claim, confidence: "research-only" }, {}, snapshot).status).toBe("unknown");
  });
  it("requires current accepted evidence and matches conditions", () => {
    expect(evaluateCapability(claim, {}, snapshot).status).toBe("pass");
    expect(evaluateCapability({ ...claim, operatingConditions: { windApproved: false } }, { windApproved: true }, snapshot).status).toBe("blocked");
    expect(evaluateCapability({ ...claim, confidence: "vendor-claimed" }, {}, snapshot, "airworthiness").status).toBe("unknown");
    expect(evaluateCapability({ ...claim, capability: "c2" }, { useCase: "release", conditions: {}, hard: true }, { ...snapshot, approved: false }).status).toBe("unknown");
    expect(evaluateCapability(claim, {}, { ...snapshot, current: false }).status).toBe("unknown");
    expect(evaluateCapability({ ...claim, evidenceRefs: ["missing"] }, {}, snapshot).status).toBe("unknown");
  });
  it("compares capability baselines without operational approval", () => {
    expect(compareCapabilityBaselines([{ id: "a", vendor: "A", model: "X", capabilities: ["vlos"] }, { id: "b", vendor: "B", model: "Y", capabilities: ["vlos", "bvlos"] }]).differences).toContain("bvlos");
  });
});
