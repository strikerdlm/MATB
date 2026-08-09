import { describe, expect, it } from "vitest";
import type { NormalizedRequirement } from "@fac-isr/evidence";
import {
  buildFleetSafetyFacts,
  evaluateMission,
  type FleetSafetyFacts,
  type MissionRevision,
} from "../src/index.js";

const nowUtc = "2026-08-09T08:00:00Z";

const mission = (overrides: Partial<MissionRevision> = {}): MissionRevision => ({
  id: "mr-fleet-energy-1",
  missionId: "m-fleet-energy-1",
  revision: 1,
  profileId: "fac-state-aviation",
  state: "Planned",
  aircraft: [{ aircraftId: "ac-1", aircraftClass: "IC", configuration: "unarmed-isr", operatorUserId: "op-1" }],
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
  crew: [{ userId: "op-1", role: "operator", aircraftId: "ac-1", qualified: true, recencyCurrent: true, dutyStatus: "available" }],
  evidenceSnapshotId: "mission-evidence-1",
  dataSnapshots: [],
  riskAssessment: { hazardIds: [], mitigationIds: [], status: "complete" },
  ...overrides,
});

const acceptedEvidence = {
  evidenceId: "requirement-evidence-1",
  sourceId: "source-1",
  edition: "edition-1",
  locator: { section: "1" },
  quoteLanguage: "es",
  extractionSha256: "sha-1",
  reviewState: "accepted",
} as NormalizedRequirement["sourceRefs"][number];

const acceptedRequirement: NormalizedRequirement = {
  requirementId: "req-fleet-energy",
  sourceRefs: [acceptedEvidence],
  Spanish: "Requisito",
  EnglishControlled: "Requirement",
  applicabilityExpression: "state_aviation",
  severity: "hard",
  evidenceRequired: true,
  effectiveFromUtc: "2026-01-01T00:00:00Z",
  interpretationStatus: "approved",
  reviewerIds: ["reviewer-1"],
};

const approvedPolicy = {
  packageId: "policy-1",
  version: "1.0.0",
  status: "approved" as const,
  signature: "signature-1",
  freshness: {
    aip: { maxAgeMinutes: 60, critical: true },
    notam: { maxAgeMinutes: 60, critical: true },
    weather: { maxAgeMinutes: 60, critical: true },
    terrain: { maxAgeMinutes: 60, critical: true },
    airspace: { maxAgeMinutes: 60, critical: true },
    policy: { maxAgeMinutes: 60, critical: true },
    regulation: { maxAgeMinutes: 60, critical: true },
  },
  delegatedAuthorities: [],
};

const aircraftFact = (status: "pass" | "blocked" | "unknown" = "pass") => ({
  aircraftId: "ac-1",
  status,
  blockers: status === "pass" ? [] : ["FACT_BLOCKED"],
  evidenceRefs: ["aircraft-ev", "shared-ev"],
});

const fleet = {
  aircraft: [aircraftFact()],
  capability: [{ ...aircraftFact(), evidenceRefs: ["capability-ev", "shared-ev"] }],
  battery: [{ ...aircraftFact(), evidenceRefs: ["battery-ev", "shared-ev"] }],
};

const maintenance = [{
  aircraftId: "ac-1",
  status: "pass" as const,
  blockers: [],
  evidenceRefs: ["maintenance-ev", "shared-ev"],
}];

const crew = {
  assignments: mission().crew,
  evaluations: [{
    aircraftId: "ac-1",
    status: "pass" as const,
    blockers: [],
    evidenceRefs: ["crew-ev", "shared-ev"],
  }],
};

const energy = (status: "pass" | "blocked" | "unknown" = "pass") => [{
  aircraftId: "ac-1",
  status,
  evidenceRefs: ["energy-model-fixture-1", "shared-ev"],
  predictedAtRecoveryPercent: status === "pass" ? 30 : 0,
  diversionReservePercent: status === "pass" ? 20 : 0,
  contingencyReservePercent: status === "pass" ? 10 : 0,
  uncertaintyPercent: 8,
  limitingAssumption: status === "pass" ? "fixture approved model" : "energy evidence is not usable",
}];

const facts = (energyStatus: "pass" | "blocked" | "unknown" = "pass"): FleetSafetyFacts =>
  buildFleetSafetyFacts(fleet, maintenance, crew, energy(energyStatus));

const evaluate = (fleetSafetyFacts: FleetSafetyFacts) => evaluateMission({
  mission: mission(),
  requirements: [acceptedRequirement],
  policy: approvedPolicy,
  nowUtc,
  fleetSafetyFacts,
});

describe("fleet and energy safety-kernel integration", () => {
  it("normalizes fleet evidence and preserves first-seen references", () => {
    const result = facts();

    expect(result.maintenance[0]).toMatchObject({ aircraftId: "ac-1", status: "pass" });
    expect(result.crewEvaluations?.[0]).toMatchObject({ aircraftId: "ac-1", status: "pass" });
    expect(result.energy[0]).toMatchObject({ aircraftId: "ac-1", status: "pass" });
    expect(result.energy[0]?.evidenceRefs).toEqual(["energy-model-fixture-1", "shared-ev"]);
    expect(result.crew).toEqual(mission().crew);
  });

  it("blocks release for insufficient reserve and links the energy evidence", () => {
    const result = evaluate(facts("blocked"));

    expect(result.status).toBe("blocked");
    expect(result.blockers).toContainEqual(expect.objectContaining({
      code: "INSUFFICIENT_RESERVE",
      evidenceRefs: ["energy-model-fixture-1", "shared-ev"],
    }));
    expect(result.evaluations.find(({ requirementId }) => requirementId === "energy.reserve")).toMatchObject({
      result: "fail",
      evidenceRefs: ["energy-model-fixture-1", "shared-ev"],
    });
  });

  it("fails closed with an explicit data blocker when energy evidence is unknown", () => {
    const result = evaluate(facts("unknown"));

    expect(result.status).toBe("blocked");
    expect(result.blockers).toContainEqual(expect.objectContaining({
      code: "ENERGY_EVIDENCE_UNKNOWN",
      severity: "data",
      evidenceRefs: ["energy-model-fixture-1", "shared-ev"],
    }));
    expect(result.evaluations.find(({ requirementId }) => requirementId === "energy.reserve")).toMatchObject({
      result: "unknown",
      reason: "ENERGY_EVIDENCE_UNKNOWN",
    });
  });

  it("keeps a complete passing fact bundle ready when energy reserves pass", () => {
    const result = evaluate(facts());

    expect(result.status).toBe("ready");
    expect(result.blockers).not.toContainEqual(expect.objectContaining({ code: "INSUFFICIENT_RESERVE" }));
    expect(result.evaluations.find(({ requirementId }) => requirementId === "energy.reserve")).toMatchObject({ result: "pass" });
  });

  it("blocks when a supplied fact bundle has no record for a mission aircraft", () => {
    const missingAircraftFacts = buildFleetSafetyFacts(
      { ...fleet, aircraft: [], capability: [], battery: [] },
      [],
      { assignments: mission().crew, evaluations: [] },
      [],
    );
    const result = evaluate(missingAircraftFacts);

    expect(result.status).toBe("blocked");
    expect(result.blockers).toContainEqual(expect.objectContaining({ code: "FLEET_FACTS_UNKNOWN" }));
  });
});
