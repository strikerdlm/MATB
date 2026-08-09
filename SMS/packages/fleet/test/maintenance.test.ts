import { describe, expect, it } from "vitest";
import { classifyDiscrepancy, evaluateMaintenanceRelease, isMinimumEquipmentSatisfied } from "../src/maintenance.js";
const release = { aircraftId: "uas-1", configurationHash: "cfg-hash", inspectionDueAtUtc: "2027-01-01T00:00:00Z", openDiscrepancies: [], minimumEquipmentSatisfied: true, batteryRelease: "released" as const, payloadRelease: "released" as const, softwareBaseline: "sw-1", authorizedBy: "maintainer-1", decision: "released" as const, signedAtUtc: "2026-08-08T00:00:00Z" };
const input = { release, aircraftId: "uas-1", configurationHash: "cfg-hash", softwareBaseline: "sw-1", asOfUtc: "2026-08-09T00:00:00Z", evidenceRefs: ["maintenance-ev"], acceptedEvidenceRefs: ["maintenance-ev"] };
describe("maintenance release", () => {
  it("accepts a complete signed release and rejects identity/hash/date failures", () => {
    expect(evaluateMaintenanceRelease(input).status).toBe("pass");
    expect(evaluateMaintenanceRelease({ ...input, aircraftId: "other" }).status).toBe("blocked");
    expect(evaluateMaintenanceRelease({ ...input, asOfUtc: "2027-02-01T00:00:00Z" }).status).toBe("blocked");
    expect(evaluateMaintenanceRelease({ ...input, asOfUtc: "2026-02-30T00:00:00Z" }).status).toBe("unknown");
    expect(evaluateMaintenanceRelease({ ...input, release: { ...release, inspectionDueAtUtc: "2026-02-30T00:00:00Z" } }).status).toBe("unknown");
  });
  it("fails closed for restricted release facts and missing evidence", () => {
    expect(evaluateMaintenanceRelease({ ...input, release: { ...release, batteryRelease: "restricted" } }).status).toBe("blocked");
    expect(evaluateMaintenanceRelease({ ...input, evidenceRefs: [], acceptedEvidenceRefs: [] }).status).toBe("unknown");
    expect(isMinimumEquipmentSatisfied({ ...release, minimumEquipmentSatisfied: false })).toBe(false);
  });
  it("classifies discrepancies with explicit approved deferrals", () => {
    const discrepancy = { id: "d-1", description: "minor", severity: "minor" as const, disposition: "open" as const, evidenceRefs: ["ev"] };
    expect(classifyDiscrepancy(discrepancy, [])).toBe("blocking");
    expect(classifyDiscrepancy(discrepancy, [{ id: "d-1", authorizedBy: "safety", evidenceRefs: ["ev"], validUntilUtc: "2027-01-01T00:00:00Z" }], "2026-08-09T00:00:00Z", ["ev"])).toBe("deferred");
    expect(classifyDiscrepancy(discrepancy, [{ id: "d-1", authorizedBy: " ", evidenceRefs: [], validUntilUtc: "2027-01-01T00:00:00Z" }], "2026-08-09T00:00:00Z", [])).toBe("blocking");
    expect(evaluateMaintenanceRelease({ ...input, release: { ...release, openDiscrepancies: [discrepancy] }, evidenceRefs: [], acceptedEvidenceRefs: [] }).status).toBe("blocked");
    expect(evaluateMaintenanceRelease({ ...input, release: { ...release, authorizedBy: " " } }).status).toBe("blocked");
  });
});
