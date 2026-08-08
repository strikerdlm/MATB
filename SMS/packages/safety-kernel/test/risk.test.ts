import { describe, expect, it } from "vitest";
import { evaluateRisk, type PolicyPackage, type RiskEvaluationInput } from "../src/index.js";

const approvedPolicy: PolicyPackage = {
  packageId: "policy-risk-1", version: "1.0.0", status: "approved", signature: "signature-risk-1",
  riskMatrix: { probabilityLevels: 2, severityLevels: 2, cells: ["low", "medium", "medium", "high"] },
  nasoThresholds: [{ band: "low", maxDurationHours: 12 }, { band: "medium", maxDurationHours: 4 }, { band: "high" }],
  delegatedAuthorities: [{ role: "safety", userRole: "safety-officer", bands: ["low", "medium"] }],
  freshness: {
    aip: { maxAgeMinutes: 60, critical: true }, notam: { maxAgeMinutes: 60, critical: true }, weather: { maxAgeMinutes: 60, critical: true },
    terrain: { maxAgeMinutes: 60, critical: true }, airspace: { maxAgeMinutes: 60, critical: true }, policy: { maxAgeMinutes: 60, critical: true }, regulation: { maxAgeMinutes: 60, critical: true },
  },
};

const riskInput: RiskEvaluationInput = {
  hazardIds: ["hazard-weather"], probability: 0.5, severity: 2, residualRiskBand: "medium",
  acceptanceAuthorityId: "safety-officer", mitigationIds: ["mitigation-divert"], status: "complete", durationHours: 4,
  probabilityLevel: 1, nowUtc: "2026-08-08T17:00:00Z", policy: approvedPolicy,
};

describe("approved risk and NASO evaluation", () => {
  it("blocks when the active policy has no approved probability/severity matrix", () => {
    expect(evaluateRisk({ ...riskInput, policy: undefined })).toMatchObject({ status: "blocked", reason: "APPROVED_RISK_POLICY_REQUIRED" });
    expect(evaluateRisk({ ...riskInput, policy: { ...approvedPolicy, riskMatrix: undefined } })).toMatchObject({ status: "blocked", reason: "APPROVED_RISK_MATRIX_REQUIRED" });
  });

  it.each(["draft", "expired", "revoked"] as const)("fails closed for a %s or unsigned policy", (status) => {
    expect(evaluateRisk({ ...riskInput, policy: { ...approvedPolicy, status } })).toMatchObject({ status: "blocked", reason: "APPROVED_RISK_POLICY_REQUIRED" });
    expect(evaluateRisk({ ...riskInput, policy: { ...approvedPolicy, signature: "   " } })).toMatchObject({ status: "blocked", reason: "APPROVED_RISK_POLICY_REQUIRED" });
  });

  it("uses the policy matrix cell, NASO duration threshold, and delegated authority", () => {
    expect(evaluateRisk(riskInput)).toEqual({ status: "accepted", band: "medium", reason: "RISK_ACCEPTED" });
    expect(evaluateRisk({ ...riskInput, durationHours: 4.0001 })).toMatchObject({ status: "blocked", band: "medium", reason: "NASO_DURATION_EXCEEDED" });
    expect(evaluateRisk({ ...riskInput, acceptanceAuthorityId: "commander" })).toMatchObject({ status: "blocked", reason: "RISK_ACCEPTANCE_AUTHORITY_MISSING" });
  });

  it("requires an explicit in-range probability level without inferring it from probability", () => {
    expect(evaluateRisk({ ...riskInput, probability: 0.01 })).toEqual({ status: "accepted", band: "medium", reason: "RISK_ACCEPTED" });
    expect(evaluateRisk({ ...riskInput, probabilityLevel: 0 })).toMatchObject({ status: "blocked", reason: "RISK_MATRIX_ASSIGNMENT_REQUIRED" });
    expect(evaluateRisk({ ...riskInput, probabilityLevel: 3 })).toMatchObject({ status: "blocked", reason: "RISK_MATRIX_ASSIGNMENT_REQUIRED" });
  });

  it("blocks an approved signed policy at or after its manifest expiry", () => {
    const policy = {
      ...approvedPolicy,
      manifest: { expiresAtUtc: "2026-08-08T17:00:00Z" },
    } as PolicyPackage;
    expect(evaluateRisk({ ...riskInput, policy })).toMatchObject({ status: "blocked", reason: "APPROVED_RISK_POLICY_REQUIRED" });
    expect(evaluateRisk({ ...riskInput, policy: { ...policy, manifest: { expiresAtUtc: "invalid" } } as PolicyPackage })).toMatchObject({ status: "blocked", reason: "APPROVED_RISK_POLICY_REQUIRED" });
  });

  it("blocks a residual band that does not match the approved matrix cell", () => {
    expect(evaluateRisk({ ...riskInput, residualRiskBand: "low" })).toMatchObject({ status: "blocked", reason: "RESIDUAL_RISK_BAND_MISMATCH" });
  });

  it("returns a frozen decision", () => {
    expect(Object.isFrozen(evaluateRisk(riskInput))).toBe(true);
  });

  it("fails closed for malformed approved-policy matrix and authority data", () => {
    expect(evaluateRisk({ ...riskInput, policy: { ...approvedPolicy, riskMatrix: { probabilityLevels: 2, severityLevels: 2, cells: undefined as unknown as readonly string[] } } })).toMatchObject({ status: "blocked", reason: "APPROVED_RISK_MATRIX_REQUIRED" });
    expect(evaluateRisk({ ...riskInput, policy: { ...approvedPolicy, delegatedAuthorities: undefined as unknown as readonly PolicyPackage["delegatedAuthorities"][number][] } })).toMatchObject({ status: "blocked", reason: "RISK_ACCEPTANCE_AUTHORITY_MISSING" });
  });
});
