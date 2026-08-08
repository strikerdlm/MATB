import { describe, expect, it } from "vitest";
import { buildHardBlockers, evaluateApplicability, getClassBand, type ApplicabilityFacts } from "../src/applicability.js";
import type { MissionRevision } from "../src/types.js";

const mission = (overrides: Partial<MissionRevision> = {}): MissionRevision => ({
  id: "mr-1", missionId: "m-1", revision: 1, profileId: "fac-state-aviation", state: "Planned",
  aircraft: [{ aircraftId: "ac-1", aircraftClass: "IC", configuration: "unarmed-isr", operatorUserId: "op-1" }],
  flightRule: "VFR", visualCondition: "VLOS", configuration: "unarmed-isr",
  route: { areaId: "area-1", routeHash: "route-1", terrainStatus: "pass", obstacleStatus: "pass", airspaceStatus: "pass", notamStatus: "pass", visualConditionStatus: "pass" },
  crew: [{ userId: "op-1", role: "operator", aircraftId: "ac-1", qualified: true, recencyCurrent: true, dutyStatus: "available" }],
  evidenceSnapshotId: "snapshot-1", dataSnapshots: [], riskAssessment: { hazardIds: [], mitigationIds: [], status: "complete" }, ...overrides,
});

describe("RACAE class boundaries", () => {
  it.each([[0.015, "IA"], [6.999, "IA"], [7, "IB"], [14.999, "IB"], [15, "IC"], [149.999, "IC"], [150.001, "II"], [600, "II"], [600.001, "III"]] as const)("maps %s kg to class %s", (mtow, expected) => expect(getClassBand(mtow)).toBe(expected));
  it("rejects the unclassified 150 kg boundary", () => expect(() => getClassBand(150)).toThrow("unclassified"));
  it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY])("rejects invalid MTOW %s", (mtow) => expect(() => getClassBand(mtow)).toThrow());
  it("is monotonic away from the reserved boundary", () => expect([0.015, 7, 15, 150.001, 600, 600.001].map(getClassBand)).toEqual(["IA", "IB", "IC", "II", "II", "III"]));
});

describe("hard operational blockers", () => {
  it.each([["armed", "CONFIGURATION_OUT_OF_SCOPE"], ["strike", "CONFIGURATION_OUT_OF_SCOPE"]] as const)("blocks %s", (configuration, code) => {
    expect(buildHardBlockers(mission({ configuration, aircraft: [{ aircraftId: "ac-1", aircraftClass: "IC", configuration }] }), {})).toContainEqual(expect.objectContaining({ code }));
  });
  it("keeps the FAC configuration allowlist invariant when operational facts are false", () => {
    expect(buildHardBlockers(mission({ configuration: "armed", aircraft: [{ aircraftId: "ac-1", aircraftClass: "IC", configuration: "armed" }] }), { operational: false })).toContainEqual(expect.objectContaining({ code: "CONFIGURATION_OUT_OF_SCOPE" }));
  });
  it("requires one qualified available operator per aircraft", () => {
    const result = buildHardBlockers(mission({ aircraft: [
      { aircraftId: "ac-1", aircraftClass: "IC", configuration: "unarmed-isr", operatorUserId: "op-1" },
      { aircraftId: "ac-2", aircraftClass: "IC", configuration: "unarmed-isr" },
    ] }), { swarm: true, researchOnly: true });
    expect(result).toContainEqual(expect.objectContaining({ code: "MISSING_OPERATOR_PER_AIRCRAFT" }));
    expect(result).toContainEqual(expect.objectContaining({ code: "SWARM_RESEARCH_NON_DISPATCHABLE" }));
  });
});

describe("automation and IFR applicability", () => {
  const approved = { status: "approved", autonomousFlightProhibited: true, supervisedAutomationApproved: true, ifrApproved: true } as ApplicabilityFacts["policy"];
  it("hard-blocks autonomous mode", () => expect(evaluateApplicability(mission(), { requirementId: "r-autonomous", sourceRefs: [], Spanish: "", EnglishControlled: "", applicabilityExpression: "autonomous_flight", severity: "hard", evidenceRequired: true, effectiveFromUtc: "2025-01-01T00:00:00Z", interpretationStatus: "approved", reviewerIds: [] }, { ...approved, automationMode: "autonomous" })).toMatchObject({ applicable: true, result: "fail" }));
  it.each([undefined, "draft"] as const)("hard-blocks autonomous mode with %s policy", (status) => expect(evaluateApplicability(mission(), { requirementId: "r-autonomous", sourceRefs: [], Spanish: "", EnglishControlled: "", applicabilityExpression: "autonomous_flight", severity: "hard", evidenceRequired: true, effectiveFromUtc: "2025-01-01T00:00:00Z", interpretationStatus: "approved", reviewerIds: [] }, { status, automationMode: "autonomous" })).toMatchObject({ applicable: true, result: "fail", reason: "AUTONOMOUS_FLIGHT_PROHIBITED" }));
  it("keeps supervised automation conditional without intervention evidence", () => expect(evaluateApplicability(mission(), { requirementId: "r-auto", sourceRefs: [], Spanish: "", EnglishControlled: "", applicabilityExpression: "supervised_automation", severity: "hard", evidenceRequired: true, effectiveFromUtc: "2025-01-01T00:00:00Z", interpretationStatus: "approved", reviewerIds: [] }, { ...approved, automationMode: "supervised" })).toMatchObject({ applicable: true, result: "unknown" }));
  it("requires explicit IFR package, equipment, segregated airspace, and authorization", () => {
    const req = { requirementId: "r-ifr", sourceRefs: [], Spanish: "", EnglishControlled: "", applicabilityExpression: "ifr", severity: "hard" as const, evidenceRequired: true, effectiveFromUtc: "2025-01-01T00:00:00Z", interpretationStatus: "approved" as const, reviewerIds: [] };
    expect(evaluateApplicability(mission({ flightRule: "IFR" }), req, { ...approved, flightRuleApproved: true, aircraftEquipmentCapable: true, segregatedAirspace: true, authorizationEvidence: true })).toMatchObject({ applicable: true, result: "pass" });
    expect(evaluateApplicability(mission({ flightRule: "IFR" }), req, { ...approved, flightRuleApproved: true })).toMatchObject({ applicable: true, result: "unknown" });
  });
  it("does not pass an ordinary qualified-review requirement as ready", () => {
    const req = { requirementId: "r-qualified", sourceRefs: [], Spanish: "", EnglishControlled: "", applicabilityExpression: "state_aviation", severity: "hard" as const, evidenceRequired: true, effectiveFromUtc: "2025-01-01T00:00:00Z", interpretationStatus: "qualified-review" as const, reviewerIds: [] };
    expect(evaluateApplicability(mission(), req, { status: "approved" })).toMatchObject({ applicable: true, result: "unknown", reason: "REQUIREMENT_SOURCE_REVIEW_PENDING" });
  });
});
