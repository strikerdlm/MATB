import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { NormalizedRequirement } from "@fac-isr/evidence";
import { evaluateMission, explainEvaluation, type MissionRevision, type PolicyPackage } from "../src/index.js";
import type { ApplicabilityPolicy } from "../src/applicability.js";

const nowUtc = "2026-08-08T17:00:00Z";

const mission = (overrides: Partial<MissionRevision> = {}): MissionRevision => ({
  id: "mr-evaluate-1", missionId: "m-evaluate-1", revision: 1, profileId: "fac-state-aviation", state: "Planned",
  aircraft: [{ aircraftId: "ac-1", aircraftClass: "IC", configuration: "unarmed-isr", operatorUserId: "op-1" }],
  flightRule: "VFR", visualCondition: "VLOS", configuration: "unarmed-isr",
  route: { areaId: "area-1", routeHash: "route-1", terrainStatus: "pass", obstacleStatus: "pass", airspaceStatus: "pass", notamStatus: "pass", visualConditionStatus: "pass" },
  crew: [{ userId: "op-1", role: "operator", aircraftId: "ac-1", qualified: true, recencyCurrent: true, dutyStatus: "available" }],
  evidenceSnapshotId: "mission-evidence-1", dataSnapshots: [], riskAssessment: { hazardIds: [], mitigationIds: [], status: "complete" },
  ...overrides,
});

const approvedPolicy: PolicyPackage = {
  packageId: "policy-1", version: "1.0.0", status: "approved", signature: "signature-1",
  freshness: {
    aip: { maxAgeMinutes: 60, critical: true }, notam: { maxAgeMinutes: 60, critical: true }, weather: { maxAgeMinutes: 60, critical: true },
    terrain: { maxAgeMinutes: 60, critical: true }, airspace: { maxAgeMinutes: 60, critical: true }, policy: { maxAgeMinutes: 60, critical: true }, regulation: { maxAgeMinutes: 60, critical: true },
  },
  delegatedAuthorities: [],
};

const expiredPolicyManifest: NonNullable<PolicyPackage["manifest"]> = {
  schemaVersion: "1.0", packageId: "policy-manifest-1", kind: "policy", issuer: "FAC", version: "1.0.0",
  issuedAtUtc: "2026-01-01T00:00:00Z", effectiveFromUtc: "2026-01-01T00:00:00Z", expiresAtUtc: "2026-08-08T16:00:00Z",
  geographicScope: "CO", contentSha256: "manifest-content", signature: "manifest-signature", keyId: "key-1",
  dependencies: [], files: [], qualification: "approved", caveats: [],
};

const acceptedEvidence = {
  evidenceId: "evidence-accepted", sourceId: "source-accepted", edition: "edition-1", locator: { section: "1" }, quoteLanguage: "es", extractionSha256: "sha-accepted", reviewState: "accepted",
} as NormalizedRequirement["sourceRefs"][number];

const requirement = (requirementId: string, overrides: Partial<NormalizedRequirement> = {}): NormalizedRequirement => ({
  requirementId, sourceRefs: [acceptedEvidence], Spanish: "Requisito controlado", EnglishControlled: "Controlled requirement",
  applicabilityExpression: "state_aviation", severity: "hard", evidenceRequired: true,
  effectiveFromUtc: "2026-01-01T00:00:00Z", interpretationStatus: "approved", reviewerIds: ["reviewer-1"],
  ...overrides,
});

const goldenCases = JSON.parse(readFileSync(fileURLToPath(new URL("./fixtures/golden-missions.json", import.meta.url)), "utf8")) as readonly {
  name: string;
  requirementIds: readonly string[];
  sourceEvidence: "accepted" | "missing";
  status: string;
  blockerCode?: string;
  dataSnapshot?: MissionRevision["dataSnapshots"][number];
}[];

describe("deterministic safety evaluation", () => {
  it("evaluates requirements by ID and preserves the exact evidence IDs", () => {
    const evidenceA = { ...acceptedEvidence, evidenceId: "evidence-a" } as NormalizedRequirement["sourceRefs"][number];
    const result = evaluateMission({ mission: mission(), requirements: [requirement("req-z"), requirement("req-a", { sourceRefs: [evidenceA] })], policy: approvedPolicy, nowUtc });
    expect(result.status).toBe("ready");
    expect(result.evaluations.map((evaluation) => evaluation.requirementId)).toEqual(["req-a", "req-z"]);
    expect(result.evaluations[0]?.evidenceRefs).toEqual(["evidence-a"]);
    expect(Object.isFrozen(result)).toBe(true);
    expect(JSON.stringify(evaluateMission({ mission: mission(), requirements: [requirement("req-z"), requirement("req-a", { sourceRefs: [evidenceA] })], policy: approvedPolicy, nowUtc }))).toBe(JSON.stringify(result));
  });

  it("blocks when a hard requirement is unknown", () => {
    const result = evaluateMission({ mission: mission(), requirements: [requirement("req-unknown", { sourceRefs: [] })], policy: approvedPolicy, nowUtc });
    expect(result.status).toBe("blocked");
    expect(result.evaluations[0]).toMatchObject({ result: "unknown", reason: "ACCEPTED_EVIDENCE_REQUIRED" });
    expect(result.blockers[0]).toMatchObject({ code: "REQUIREMENT_UNKNOWN", evidenceRefs: [] });
  });

  it("blocks a hard requirement that fails applicability", () => {
    const autonomousPolicy = { ...approvedPolicy, automationMode: "autonomous" };
    const result = evaluateMission({ mission: mission(), requirements: [requirement("req-autonomous", { applicabilityExpression: "autonomous_flight" })], policy: autonomousPolicy, nowUtc });
    expect(result.status).toBe("blocked");
    expect(result.evaluations[0]).toMatchObject({ result: "fail", reason: "AUTONOMOUS_FLIGHT_PROHIBITED" });
    expect(result.blockers[0]?.code).toBe("REQUIREMENT_FAILED");
  });

  it("marks applicable evidence expired from the mission-level freshness gate", () => {
    const result = evaluateMission({
      mission: mission({ dataSnapshots: [{ snapshotId: "weather-1", kind: "weather", packageId: "package-weather", status: "current", capturedAtUtc: "2026-08-08T14:00:00Z" }] }),
      requirements: [requirement("req-current")], policy: approvedPolicy, nowUtc,
    });
    expect(result.status).toBe("blocked");
    expect(result.evaluations[0]).toMatchObject({ result: "expired", reason: "MISSION_DATA_EXPIRED" });
    expect(result.blockers[0]).toMatchObject({ code: "REQUIREMENT_EXPIRED", evidenceRefs: ["evidence-accepted", "weather-1"] });
  });

  it("uses explicit mission data status as a non-ready freshness gate", () => {
    const result = evaluateMission({
      mission: mission({ dataSnapshots: [{ snapshotId: "notam-missing", kind: "notam", packageId: "package-notam", status: "missing", capturedAtUtc: nowUtc }] }),
      requirements: [requirement("req-current")], policy: approvedPolicy, nowUtc,
    });
    expect(result.status).toBe("blocked");
    expect(result.evaluations[0]).toMatchObject({ result: "unknown", reason: "MISSION_DATA_MISSING" });
    expect(result.blockers[0]).toMatchObject({ code: "REQUIREMENT_UNKNOWN", evidenceRefs: ["evidence-accepted", "notam-missing"] });
  });

  it.each(["draft", "revoked"] as const)("fails closed for a %s policy required by a hard rule", (status) => {
    const result = evaluateMission({ mission: mission(), requirements: [requirement("req-policy")], policy: { ...approvedPolicy, status }, nowUtc });
    expect(result).toMatchObject({ status: "blocked", evaluations: [expect.objectContaining({ result: "unknown", reason: "APPROVED_POLICY_REQUIRED" })] });
  });

  it("preserves an applicability unknown when its policy is expired", () => {
    const result = evaluateMission({ mission: mission(), requirements: [requirement("req-policy-expired")], policy: { ...approvedPolicy, status: "expired" }, nowUtc });
    expect(result).toMatchObject({ status: "blocked", evaluations: [expect.objectContaining({ result: "unknown", reason: "APPROVED_POLICY_REQUIRED" })] });
  });

  it("does not overwrite an autonomous applicability failure with expired policy freshness", () => {
    const expiredAutonomousPolicy: PolicyPackage & ApplicabilityPolicy = { ...approvedPolicy, status: "expired", automationMode: "autonomous" };
    const result = evaluateMission({
      mission: mission(), requirements: [requirement("req-autonomous-expired", { applicabilityExpression: "autonomous_flight" })],
      policy: expiredAutonomousPolicy, nowUtc,
    });
    expect(result.evaluations[0]).toMatchObject({ result: "fail", reason: "AUTONOMOUS_FLIGHT_PROHIBITED" });
    expect(result.blockers[0]).toMatchObject({ code: "REQUIREMENT_FAILED", conceptId: "racae94.94-155.autonomous-flight.prohibited" });
  });

  it("does not overwrite an IFR applicability unknown with expired manifest or snapshot freshness", () => {
    const expiredIncompleteIfrPolicy: PolicyPackage & ApplicabilityPolicy = { ...approvedPolicy, ifrApproved: true, manifest: expiredPolicyManifest };
    const result = evaluateMission({
      mission: mission({
        flightRule: "IFR",
        dataSnapshots: [{ snapshotId: "expired-ifr-weather", kind: "weather", packageId: "weather-1", status: "expired", capturedAtUtc: "2026-08-08T14:00:00Z" }],
      }),
      requirements: [requirement("req-ifr-expired", { applicabilityExpression: "ifr" })],
      policy: expiredIncompleteIfrPolicy,
      nowUtc,
    });
    expect(result.evaluations[0]).toMatchObject({ result: "unknown", reason: "IFR_EVIDENCE_INCOMPLETE" });
    expect(result.blockers[0]).toMatchObject({ code: "REQUIREMENT_UNKNOWN", conceptId: "flight-rules.ifr.evidence-incomplete" });
  });

  it("invalidates release gates for mission-level hard blockers", () => {
    const result = evaluateMission({
      mission: mission({ configuration: "armed", aircraft: [{ aircraftId: "ac-1", aircraftClass: "IC", configuration: "armed", operatorUserId: "op-1" }] }),
      requirements: [requirement("req-current")], policy: approvedPolicy, nowUtc,
    });
    expect(result).toMatchObject({ status: "blocked", invalidatedGates: ["operator", "safety", "commander"] });
  });

  it("rejects non-UTC or invalid freshness timestamps instead of treating them as current", () => {
    expect(() => evaluateMission({ mission: mission(), requirements: [requirement("req-current")], policy: approvedPolicy, nowUtc: "2026-08-08" })).toThrow("UTC ISO-8601");
    expect(() => evaluateMission({
      mission: mission({ dataSnapshots: [{ snapshotId: "bad-weather", kind: "weather", packageId: "package-weather", status: "current", capturedAtUtc: "2026-02-30T00:00:00Z" }] }),
      requirements: [requirement("req-current")], policy: approvedPolicy, nowUtc,
    })).toThrow("UTC ISO-8601");
  });

  it.each(goldenCases)("matches the $name golden decision", (goldenCase) => {
    const result = evaluateMission({
      mission: mission({ dataSnapshots: goldenCase.dataSnapshot ? [goldenCase.dataSnapshot] : [] }),
      requirements: goldenCase.requirementIds.map((id) => requirement(id, { sourceRefs: goldenCase.sourceEvidence === "accepted" ? [acceptedEvidence] : [] })),
      policy: approvedPolicy,
      nowUtc,
    });
    expect(result.status).toBe(goldenCase.status);
    expect(result.blockers[0]?.code).toBe(goldenCase.blockerCode);
  });
});

describe("controlled explanations", () => {
  it("does not change decision concepts when the explanation locale changes", () => {
    const result = evaluateMission({ mission: mission(), requirements: [requirement("req-unknown", { sourceRefs: [] })], policy: approvedPolicy, nowUtc });
    expect(explainEvaluation(result, "es").conceptIds).toEqual(explainEvaluation(result, "en").conceptIds);
  });

  it("uses the authoritative Spanish label when a controlled English label is unavailable", () => {
    const result = evaluateMission({ mission: mission(), requirements: [requirement("req-unknown", { sourceRefs: [] })], policy: approvedPolicy, nowUtc });
    expect(explainEvaluation(result, "en")).toMatchObject({
      locale: "en",
      labels: ["Requisito pendiente de evidencia aceptada"],
      translationMissing: true,
    });
  });
});
