import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { NormalizedRequirement } from "../../packages/evidence/src/index.js";
import {
  evaluateMission,
  getClassBand,
  type ApplicabilityPolicy,
  type MissionRevision,
  type PolicyPackage,
} from "../../packages/safety-kernel/src/index.js";

const nowUtc = "2026-08-10T12:00:00.000Z";
const evidenceRef = {
  evidenceId: "state-aviation-evidence",
  sourceId: "racae-94-enm2",
  edition: "Enmienda 2",
  locator: { section: "verification fixture" },
  quoteLanguage: "es",
  extractionSha256: "fixture-extraction-sha256",
  reviewState: "accepted",
} as NormalizedRequirement["sourceRefs"][number];

const basePolicy: PolicyPackage & ApplicabilityPolicy = {
  packageId: "state-aviation-policy-fixture",
  version: "1.0.0",
  status: "approved",
  signature: "signed-fixture",
  delegatedAuthorities: [],
  freshness: {
    aip: { maxAgeMinutes: 60, critical: true },
    notam: { maxAgeMinutes: 60, critical: true },
    weather: { maxAgeMinutes: 60, critical: true },
    terrain: { maxAgeMinutes: 60, critical: true },
    airspace: { maxAgeMinutes: 60, critical: true },
    policy: { maxAgeMinutes: 60, critical: true },
    regulation: { maxAgeMinutes: 60, critical: true },
  },
};

function requirement(id: string, expression = "state_aviation", interpretationStatus: NormalizedRequirement["interpretationStatus"] = "approved"): NormalizedRequirement {
  return {
    requirementId: id,
    sourceRefs: [evidenceRef],
    Spanish: "Requisito de aviación de Estado revisado",
    EnglishControlled: "Reviewed State Aviation requirement",
    applicabilityExpression: expression,
    severity: "hard",
    evidenceRequired: true,
    effectiveFromUtc: "2026-01-01T00:00:00.000Z",
    interpretationStatus,
    reviewerIds: ["automated-verification-fixture"],
  };
}

function mission(overrides: Partial<MissionRevision> = {}): MissionRevision {
  const aircraft = overrides.aircraft ?? [{
    aircraftId: "aircraft-1",
    aircraftClass: "IC" as const,
    configuration: overrides.configuration ?? "unarmed-isr",
    operatorUserId: "operator-1",
  }];
  return {
    id: "state-mission:r0",
    missionId: "state-mission",
    revision: 0,
    profileId: "fac-state-aviation",
    state: "Planned",
    aircraft,
    flightRule: "VFR",
    visualCondition: "VLOS",
    configuration: "unarmed-isr",
    route: {
      areaId: "area-1",
      routeHash: "route-1",
      terrainStatus: "pass",
      obstacleStatus: "pass",
      airspaceStatus: "pass",
      notamStatus: "pass",
      visualConditionStatus: "pass",
    },
    crew: [{ userId: "operator-1", role: "operator", aircraftId: "aircraft-1", qualified: true, recencyCurrent: true, dutyStatus: "available" }],
    evidenceSnapshotId: "state-evidence-snapshot",
    policyPackageId: basePolicy.packageId,
    dataSnapshots: [],
    riskAssessment: { hazardIds: ["hazard-1"], mitigationIds: ["mitigation-1"], status: "complete" },
    ...overrides,
  };
}

interface BlockedCase {
  readonly id: string;
  readonly kind: "automation" | "configuration" | "data" | "operator" | "qualified-review";
  readonly configuration?: MissionRevision["configuration"];
  readonly operatorAssigned?: boolean;
  readonly automationMode?: "autonomous";
  readonly routeStatus?: "blocked";
  readonly snapshot?: MissionRevision["dataSnapshots"][number];
  readonly expectedCode?: string;
  readonly expectedReason?: string;
  readonly limitation?: string;
}

function blockedCases(): readonly BlockedCase[] {
  const root = resolve(process.cwd(), "test/fixtures/blocked-cases");
  return readdirSync(root).filter((name) => name.endsWith(".json")).sort()
    .map((name) => JSON.parse(readFileSync(resolve(root, name), "utf8")) as BlockedCase);
}

describe("State Aviation class and operating-envelope matrix", () => {
  it.each([
    [0.015, "IA"],
    [7, "IB"],
    [15, "IC"],
    [150.001, "II"],
    [600.001, "III"],
  ] as const)("reaches ready for unarmed VFR class %s kg / %s with accepted evidence", (mtowKg, aircraftClass) => {
    expect(getClassBand(mtowKg)).toBe(aircraftClass);
    const candidate = mission({ aircraft: [{ aircraftId: "aircraft-1", aircraftClass, configuration: "unarmed-isr", operatorUserId: "operator-1" }] });

    const result = evaluateMission({ mission: candidate, requirements: [requirement(`class-${aircraftClass}`)], policy: basePolicy, nowUtc });

    expect(result).toMatchObject({ status: "ready", blockers: [] });
    expect(result.evaluations[0]).toMatchObject({ result: "pass", evidenceRefs: ["state-aviation-evidence"] });
  });

  it.each(["VLOS", "EVLOS", "BVLOS"] as const)("preserves the explicit %s visual condition in a ready unarmed fixture", (visualCondition) => {
    const result = evaluateMission({ mission: mission({ visualCondition }), requirements: [requirement(`visual-${visualCondition}`)], policy: basePolicy, nowUtc });
    expect(result.status).toBe("ready");
  });

  it("permits IFR only with explicit policy, equipment, segregated-airspace, and authorization evidence", () => {
    const ifrMission = mission({ flightRule: "IFR", visualCondition: "BVLOS" });
    const approvedIfr = { ...basePolicy, ifrApproved: true, aircraftEquipmentCapable: true, segregatedAirspace: true, authorizationEvidence: true };
    expect(evaluateMission({ mission: ifrMission, requirements: [requirement("ifr-approved", "ifr")], policy: approvedIfr, nowUtc })).toMatchObject({ status: "ready" });

    for (const missing of ["ifrApproved", "aircraftEquipmentCapable", "segregatedAirspace", "authorizationEvidence"] as const) {
      const incomplete = { ...approvedIfr, [missing]: false };
      expect(evaluateMission({ mission: ifrMission, requirements: [requirement(`ifr-missing-${missing}`, "ifr")], policy: incomplete, nowUtc })).toMatchObject({
        status: "blocked",
        evaluations: [expect.objectContaining({ reason: "IFR_EVIDENCE_INCOMPLETE" })],
      });
    }
  });
});

describe("named State Aviation hard-block fixtures", () => {
  it.each(blockedCases())("keeps $id non-ready with an explicit reason or blocker", (fixture) => {
    const configuration = fixture.configuration ?? "unarmed-isr";
    const operatorUserId = fixture.operatorAssigned === false ? undefined : "operator-1";
    const candidate = mission({
      configuration,
      aircraft: [{ aircraftId: "aircraft-1", aircraftClass: "IC", configuration, ...(operatorUserId === undefined ? {} : { operatorUserId }) }],
      crew: fixture.operatorAssigned === false ? [] : mission().crew,
      dataSnapshots: fixture.snapshot === undefined ? [] : [fixture.snapshot],
      route: { ...mission().route, ...(fixture.routeStatus === undefined ? {} : { airspaceStatus: fixture.routeStatus }) },
    });
    const expression = fixture.kind === "automation" ? "autonomous_flight" : fixture.kind === "qualified-review" ? "airspace_conflict" : "state_aviation";
    const evaluatedRequirement = requirement(fixture.id, expression, fixture.kind === "qualified-review" ? "qualified-review" : "approved");
    const policy = fixture.automationMode === undefined ? basePolicy : { ...basePolicy, automationMode: fixture.automationMode };

    const result = evaluateMission({ mission: candidate, requirements: [evaluatedRequirement], policy, nowUtc });

    expect(result.status).not.toBe("ready");
    if (fixture.expectedCode !== undefined) expect(result.blockers).toContainEqual(expect.objectContaining({ code: fixture.expectedCode }));
    if (fixture.expectedReason !== undefined) expect(result.evaluations).toContainEqual(expect.objectContaining({ reason: fixture.expectedReason }));
    if (fixture.kind === "qualified-review") expect(fixture.limitation).toEqual(expect.any(String));
  });
});
