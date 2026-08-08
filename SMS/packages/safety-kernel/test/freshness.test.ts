import { describe, expect, it } from "vitest";
import { evaluateException, evaluateFreshness, type ControlledExceptionInput, type DataSnapshotRef, type PolicyPackage } from "../src/index.js";

const nowUtc = "2026-08-08T17:00:00Z";
const approvedPolicy: PolicyPackage = {
  packageId: "policy-freshness-1", version: "1.0.0", status: "approved", signature: "signature-freshness-1",
  riskMatrix: { probabilityLevels: 1, severityLevels: 1, cells: ["medium"] },
  nasoThresholds: [{ band: "medium", maxDurationHours: 4 }],
  delegatedAuthorities: [{ role: "safety", userRole: "safety-officer", bands: ["medium"] }],
  freshness: {
    aip: { maxAgeMinutes: 60, critical: true }, notam: { maxAgeMinutes: 60, critical: true }, weather: { maxAgeMinutes: 60, critical: true },
    terrain: { maxAgeMinutes: 60, critical: false }, airspace: { maxAgeMinutes: 60, critical: false }, policy: { maxAgeMinutes: 60, critical: true }, regulation: { maxAgeMinutes: 60, critical: true },
  },
};

const weather: DataSnapshotRef = { snapshotId: "weather-1", kind: "weather", packageId: "weather-package", status: "current", capturedAtUtc: "2026-08-08T16:00:00Z" };
const exception: ControlledExceptionInput = {
  missionRevisionId: "mr-1", sourceRevisionId: "mr-1", snapshot: { ...weather, status: "expired" },
  alternateVerifiedSource: { ...weather, snapshotId: "weather-alternate", packageId: "weather-alternate-package", capturedAtUtc: nowUtc },
  consequence: "consequence-weather", mitigation: "mitigation-divert", validityEndUtc: "2026-08-08T18:00:00Z",
  safetyReview: { reviewerId: "safety-reviewer", approved: true }, riskAuthorityId: "safety-officer",
  residualRiskBand: "medium", operatorAcknowledged: true,
};

describe("deterministic data freshness", () => {
  it("expires critical data only after its exact UTC maximum-age boundary", () => {
    expect(evaluateFreshness(weather, approvedPolicy, nowUtc)).toEqual({ status: "current", reason: "DATA_CURRENT" });
    expect(evaluateFreshness({ ...weather, capturedAtUtc: "2026-08-08T15:59:59.999Z" }, approvedPolicy, nowUtc)).toEqual({ status: "expired", reason: "CRITICAL_DATA_EXPIRED" });
  });

  it("fails closed for an invalid policy or non-UTC timestamp", () => {
    expect(evaluateFreshness(weather, { ...approvedPolicy, signature: "" }, nowUtc)).toMatchObject({ status: "blocked", reason: "APPROVED_FRESHNESS_POLICY_REQUIRED" });
    expect(() => evaluateFreshness(weather, approvedPolicy, "2026-08-08T17:00:00-05:00")).toThrow("UTC ISO-8601");
  });

  it("fails closed rather than throwing for a malformed approved freshness policy", () => {
    expect(evaluateFreshness(weather, { ...approvedPolicy, freshness: undefined as unknown as PolicyPackage["freshness"] }, nowUtc)).toEqual({ status: "blocked", reason: "FRESHNESS_THRESHOLD_REQUIRED" });
  });
});

describe("controlled degraded-data exceptions", () => {
  it("requires every degraded-data exception field", () => {
    expect(evaluateException({ ...exception, alternateVerifiedSource: undefined }, approvedPolicy, nowUtc)).toMatchObject({ status: "blocked", reason: "EXCEPTION_ALTERNATE_SOURCE_REQUIRED" });
  });

  it.each([
    ["consequence", { consequence: undefined }],
    ["mitigation", { mitigation: undefined }],
    ["validity", { validityEndUtc: undefined }],
    ["safety review", { safetyReview: undefined }],
    ["risk authority", { riskAuthorityId: undefined }],
    ["operator acknowledgement", { operatorAcknowledged: false }],
  ] as const)("blocks without %s", (_field, change) => {
    expect(evaluateException({ ...exception, ...change }, approvedPolicy, nowUtc).status).toBe("blocked");
  });

  it("requires an active exception for the current revision and a delegated authority", () => {
    expect(evaluateException(exception, approvedPolicy, nowUtc)).toEqual({ status: "accepted", reason: "EXCEPTION_ACCEPTED" });
    expect(evaluateException({ ...exception, validityEndUtc: nowUtc }, approvedPolicy, nowUtc)).toMatchObject({ status: "expired", reason: "EXCEPTION_EXPIRED" });
    expect(evaluateException({ ...exception, sourceRevisionId: "mr-0" }, approvedPolicy, nowUtc)).toMatchObject({ status: "blocked", reason: "EXCEPTION_REVISION_MISMATCH" });
    expect(evaluateException({ ...exception, missionRevisionId: "" }, approvedPolicy, nowUtc)).toMatchObject({ status: "blocked", reason: "EXCEPTION_REVISION_REQUIRED" });
    expect(evaluateException({ ...exception, sourceRevisionId: "" }, approvedPolicy, nowUtc)).toMatchObject({ status: "blocked", reason: "EXCEPTION_REVISION_REQUIRED" });
    expect(Object.isFrozen(evaluateException(exception, approvedPolicy, nowUtc))).toBe(true);
  });

  it("accepts an explicit noncritical DATA_STALE source but not conflicting or unverified data", () => {
    const staleTerrain: DataSnapshotRef = { snapshotId: "terrain-stale", kind: "terrain", packageId: "terrain-package", status: "current", capturedAtUtc: "2026-08-08T15:59:59.999Z" };
    expect(evaluateFreshness(staleTerrain, approvedPolicy, nowUtc)).toEqual({ status: "unknown", reason: "DATA_STALE" });
    expect(evaluateException({ ...exception, snapshot: staleTerrain }, approvedPolicy, nowUtc)).toEqual({ status: "accepted", reason: "EXCEPTION_ACCEPTED" });
    expect(evaluateException({ ...exception, snapshot: { ...staleTerrain, status: "conflicting" } }, approvedPolicy, nowUtc)).toMatchObject({ status: "blocked", reason: "EXCEPTION_DEGRADED_DATA_REQUIRED" });
  });

  it("requires an alternate source with distinct immutable snapshot and package provenance", () => {
    expect(evaluateException({ ...exception, alternateVerifiedSource: { ...exception.snapshot, status: "current" } }, approvedPolicy, nowUtc)).toMatchObject({ status: "blocked", reason: "EXCEPTION_ALTERNATE_SOURCE_NOT_DISTINCT" });
    expect(evaluateException({ ...exception, alternateVerifiedSource: { ...exception.alternateVerifiedSource!, packageId: exception.snapshot.packageId } }, approvedPolicy, nowUtc)).toMatchObject({ status: "blocked", reason: "EXCEPTION_ALTERNATE_SOURCE_NOT_DISTINCT" });
  });

  it("requires a valid matrix and a band actually present in its cells", () => {
    expect(evaluateException(exception, { ...approvedPolicy, riskMatrix: undefined }, nowUtc)).toMatchObject({ status: "blocked", reason: "APPROVED_RISK_MATRIX_REQUIRED" });
    expect(evaluateException(exception, { ...approvedPolicy, riskMatrix: { probabilityLevels: 1, severityLevels: 1, cells: ["low"] } }, nowUtc)).toMatchObject({ status: "blocked", reason: "EXCEPTION_RISK_BAND_REQUIRED" });
  });
});
