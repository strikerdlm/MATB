import { describe, expect, it } from "vitest";
import { parseCapability, parseUASSystem } from "../src/types.js";

const validUas = { id: "uas-1", manufacturer: "Example", model: "X", aircraftClass: "IC", mtowKg: 15, configuration: "unarmed-isr", approvedConfigurationId: "cfg-1" };
const validClaim = { id: "claim-1", subjectId: "uas-1", capability: "vlos", value: true, operatingConditions: {}, evidenceRefs: ["evidence-1"], confidence: "qualified", validFromUtc: "2026-08-08T00:00:00Z" };

describe("fleet contracts", () => {
  it("parses a valid UAS and rejects invalid class, mass, and local timestamps", () => {
    expect(parseUASSystem(validUas).aircraftClass).toBe("IC");
    expect(() => parseUASSystem({ ...validUas, aircraftClass: "unknown" })).toThrow();
    expect(() => parseUASSystem({ ...validUas, mtowKg: Number.NaN })).toThrow();
    expect(() => parseCapability({ ...validClaim, validFromUtc: "2026-02-30T00:00:00Z" })).toThrow();
  });
  it("requires evidence for a non-research capability claim", () => {
    expect(() => parseCapability({ ...validClaim, evidenceRefs: [] })).toThrow("evidence");
    expect(() => parseCapability({ ...validClaim, validFromUtc: "2026-08-08T00:00:00-05:00" })).toThrow();
    expect(parseCapability(validClaim).confidence).toBe("qualified");
  });
});
