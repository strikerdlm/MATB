import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { buildHardBlockers, evaluateApplicability, evaluateMission, evaluateRisk, explainEvaluation, type MissionRevision, type PolicyPackage } from "../src/index.js";
import type { NormalizedRequirement } from "@fac-isr/evidence";

const nowUtc = "2026-08-08T17:00:00Z";
const sourceRef = { evidenceId: "golden-evidence", sourceId: "golden-source", edition: "reviewed-p0", locator: { section: "golden" }, quoteLanguage: "es", extractionSha256: "golden-hash", reviewState: "accepted" } as NormalizedRequirement["sourceRefs"][number];
const policy: PolicyPackage = { packageId: "golden-policy", version: "0.1.0", status: "approved", signature: "signed-policy", freshness: { aip: { maxAgeMinutes: 60, critical: true }, notam: { maxAgeMinutes: 60, critical: true }, weather: { maxAgeMinutes: 60, critical: true }, terrain: { maxAgeMinutes: 60, critical: true }, airspace: { maxAgeMinutes: 60, critical: true }, policy: { maxAgeMinutes: 60, critical: true }, regulation: { maxAgeMinutes: 60, critical: true } }, delegatedAuthorities: [] };
const req = (id: string, expression = "state_aviation"): NormalizedRequirement => ({ requirementId: id, sourceRefs: [sourceRef], Spanish: "Requisito revisado", EnglishControlled: "Reviewed requirement", applicabilityExpression: expression, severity: "hard", evidenceRequired: true, effectiveFromUtc: "2026-01-01T00:00:00Z", interpretationStatus: "approved", reviewerIds: ["qualified-reviewer"] });
const baseMission = (fixture: Record<string, unknown>): MissionRevision => { const multi = fixture.kind === "one-to-many-staffing"; const aircraft = [{ aircraftId: "aircraft-1", aircraftClass: fixture.aircraftClass as MissionRevision["aircraft"][number]["aircraftClass"], configuration: fixture.configuration as MissionRevision["configuration"], operatorUserId: fixture.operatorAssigned === false ? undefined : "operator-1" }, ...(multi ? [{ aircraftId: "aircraft-2", aircraftClass: fixture.aircraftClass as MissionRevision["aircraft"][number]["aircraftClass"], configuration: fixture.configuration as MissionRevision["configuration"], operatorUserId: "operator-1" }] : [])]; return ({ id: String(fixture.id), missionId: String(fixture.id), revision: 1, profileId: "fac-state-aviation", state: "Planned", aircraft, flightRule: fixture.flightRule as MissionRevision["flightRule"], visualCondition: fixture.visualCondition as MissionRevision["visualCondition"], configuration: fixture.configuration as MissionRevision["configuration"], route: { areaId: "area-1", routeHash: "route-1", terrainStatus: "pass", obstacleStatus: "pass", airspaceStatus: "pass", notamStatus: "pass", visualConditionStatus: "pass" }, crew: fixture.operatorAssigned === false ? [] : [{ userId: "operator-1", role: "operator", aircraftId: undefined, qualified: fixture.operatorQualified !== false, recencyCurrent: fixture.operatorRecencyCurrent !== false, dutyStatus: "available" }], evidenceSnapshotId: "golden-snapshot", dataSnapshots: [], riskAssessment: { hazardIds: ["hazard-1"], mitigationIds: ["mitigation-1"], status: "complete" }, ...(fixture.dataSnapshot ? { dataSnapshots: [fixture.dataSnapshot as MissionRevision["dataSnapshots"][number]] } : {}) }); };
const allClasses = JSON.parse(readFileSync(fileURLToPath(new URL("./fixtures/all-racae-classes.json", import.meta.url)), "utf8")) as readonly Record<string, unknown>[];
const blockedCases = JSON.parse(readFileSync(fileURLToPath(new URL("./fixtures/golden-blocked-cases.json", import.meta.url)), "utf8")) as readonly Record<string, unknown>[];

describe("class-complete State Aviation golden fixtures", () => {
  it("covers IA, IB, IC, II, III and required operation profiles", () => {
    expect(new Set(allClasses.map((item) => item.aircraftClass))).toEqual(new Set(["IA", "IB", "IC", "II", "III"]));
    expect(allClasses.some((item) => item.flightRule === "IFR" && item.ifrEvidence === "explicit-complete")).toBe(true);
    expect(allClasses.some((item) => item.researchOnly === true)).toBe(true);
    for (const fixture of allClasses) {
      const mission = baseMission(fixture);
      const expression = fixture.flightRule === "IFR" ? "ifr" : "state_aviation";
      const applicability = evaluateApplicability(mission, req(String(fixture.id), expression), fixture.ifrEvidence === "explicit-complete" ? { ...policy, ifrApproved: true, aircraftEquipmentCapable: true, segregatedAirspace: true, authorizationEvidence: true } : policy);
      if (fixture.flightRule === "IFR") expect(applicability.result).toBe("pass");
      if (fixture.researchOnly === true) { const researchMission = { ...mission, aircraft: [...mission.aircraft, { ...mission.aircraft[0], aircraftId: "aircraft-2" }] }; expect(buildHardBlockers(researchMission, { swarm: true, researchOnly: true, operational: false })).toContainEqual(expect.objectContaining({ code: "SWARM_RESEARCH_NON_DISPATCHABLE" })); const researchResult = evaluateMission({ mission: researchMission, requirements: [req(String(fixture.id))], policy, nowUtc }); expect(researchResult.status).toBe("blocked"); expect(researchResult.blockers).toContainEqual(expect.objectContaining({ code: "SWARM_RESEARCH_NON_DISPATCHABLE" })); }
    }
  });

  it("keeps every named blocked case non-ready with evidence-bearing evaluations", () => {
    for (const fixture of blockedCases) {
      const mission = baseMission(fixture);
      const blockers = buildHardBlockers(mission, { automationMode: fixture.automationMode as "autonomous" | undefined, swarm: fixture.kind === "one-to-many-staffing" || fixture.kind === "research-swarm", researchOnly: fixture.kind === "research-swarm" });
      if (fixture.kernelCode) expect(blockers).toContainEqual(expect.objectContaining({ code: fixture.kernelCode }));
      const requirement = req(String(fixture.id), fixture.requirementExpression as string ?? "state_aviation");
      const evaluatedRequirement = fixture.unsupported === true ? { ...requirement, interpretationStatus: "qualified-review" as const } : requirement;
      const evaluationPolicy = fixture.policyStatus === "unsigned" ? undefined : fixture.automationMode === "autonomous" ? { ...policy, automationMode: "autonomous" as const } : policy;
      const result = evaluateMission({ mission, requirements: [evaluatedRequirement], policy: evaluationPolicy, nowUtc });
      if (fixture.expectedReason) { expect(result.evaluations[0]).toMatchObject({ reason: fixture.expectedReason }); expect(result.evaluations[0]?.evidenceRefs).toContain("golden-evidence"); if (fixture.dataSnapshot && typeof fixture.dataSnapshot === "object") expect(result.evaluations[0]?.evidenceRefs).toContain((fixture.dataSnapshot as { snapshotId: string }).snapshotId); }
      if (fixture.kind === "missing-risk-matrix") expect(evaluateRisk({ hazardIds: ["h-1"], mitigationIds: ["m-1"], status: "complete", probabilityLevel: 1, severity: 1, residualRiskBand: "low", acceptanceAuthorityId: "safety-1", policy, nowUtc })).toMatchObject({ status: "blocked", reason: "APPROVED_RISK_MATRIX_REQUIRED" });
      if (fixture.kind === "unacceptable-residual-risk") { const riskPolicy = { ...policy, riskMatrix: { probabilityLevels: 1, severityLevels: 1, cells: ["low"] }, nasoThresholds: [{ band: "low" }], delegatedAuthorities: [{ role: "safety" as const, userRole: "safety-1", bands: ["low"] }] }; expect(evaluateRisk({ hazardIds: ["h-1"], mitigationIds: ["m-1"], status: "complete", probabilityLevel: 1, severity: 1, residualRiskBand: "high", acceptanceAuthorityId: "safety-1", policy: riskPolicy, nowUtc })).toMatchObject({ status: "blocked", reason: "RESIDUAL_RISK_BAND_MISMATCH" }); }
      expect(result.status).not.toBe("ready");
      expect(result.evaluations.every((evaluation) => Array.isArray(evaluation.evidenceRefs))).toBe(true);
      expect(explainEvaluation(result, "es").conceptIds).toEqual(explainEvaluation(result, "en").conceptIds);
    }
  });
});
