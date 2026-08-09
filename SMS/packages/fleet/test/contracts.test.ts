import { describe, expect, it } from "vitest";
import { parseCapability, parseDiscrepancy, parseMaintenanceRelease, parseUASSystem } from "../src/types.js";

const validUas = { id: "uas-1", manufacturer: "Example", model: "X", aircraftClass: "IC", mtowKg: 15, configuration: "unarmed-isr", approvedConfigurationId: "cfg-1" };
const validClaim = { id: "claim-1", subjectId: "uas-1", capability: "vlos", value: true, operatingConditions: {}, evidenceRefs: ["evidence-1"], confidence: "qualified", validFromUtc: "2026-08-08T00:00:00Z" };

describe("fleet contracts", () => {
  it("parses a valid UAS and rejects invalid class, mass, and local timestamps", () => {
    expect(parseUASSystem({ ...validUas, rawManufacturerValues: { mtow: "15 kg" } }).rawManufacturerValues).toEqual({ mtow: "15 kg" });
    expect(() => parseUASSystem({ ...validUas, aircraftClass: "unknown" })).toThrow();
    expect(() => parseUASSystem({ ...validUas, mtowKg: Number.NaN })).toThrow();
    expect(() => parseCapability({ ...validClaim, validFromUtc: "2026-02-30T00:00:00Z" })).toThrow();
  });
  it("requires evidence for a non-research capability claim", () => {
    expect(() => parseCapability({ ...validClaim, evidenceRefs: [] })).toThrow("evidence");
    expect(() => parseCapability({ ...validClaim, validFromUtc: "2026-08-08T00:00:00-05:00" })).toThrow();
    expect(parseCapability(validClaim).confidence).toBe("qualified");
  });
  it("strictly parses discrepancies and maintenance releases", () => {
    expect(parseDiscrepancy({ id: "d-1", description: "minor", severity: "minor", disposition: "resolved", evidenceRefs: ["ev-1"] }).severity).toBe("minor");
    expect(() => parseDiscrepancy({ id: "d-1", description: "minor", severity: "minor", disposition: "resolved", evidenceRefs: [] })).toThrow("evidence");
    const release = { aircraftId: "uas-1", configurationHash: "hash", inspectionDueAtUtc: "2027-01-01T00:00:00Z", openDiscrepancies: [], minimumEquipmentSatisfied: true, batteryRelease: "released", payloadRelease: "released", softwareBaseline: "sw-1", authorizedBy: "maintainer-1", decision: "released", signedAtUtc: "2026-08-08T00:00:00Z" };
    expect(parseMaintenanceRelease(release).decision).toBe("released");
    expect(() => parseMaintenanceRelease({ ...release, signedAtUtc: "2026-02-30T00:00:00Z" })).toThrow();
  });
});
