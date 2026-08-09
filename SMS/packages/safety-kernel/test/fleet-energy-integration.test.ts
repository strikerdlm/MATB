import { describe, expect, it } from "vitest";
import {
  buildFleetSafetyFacts,
  evaluateMission,
  type MissionRevision,
} from "../src/index.js";

const nowUtc = "2026-08-09T12:00:00Z";
const mission: MissionRevision = {
  id: "mission-fleet-1",
  missionId: "mission-1",
  revision: 1,
  profileId: "fac-state-aviation",
  state: "Planned",
  aircraft: [{ aircraftId: "aircraft-1", aircraftClass: "IC", configuration: "unarmed-isr", operatorUserId: "operator-1" }],
  flightRule: "VFR",
  visualCondition: "VLOS",
  configuration: "unarmed-isr",
  route: { areaId: "area-1", routeHash: "route-1", terrainStatus: "pass", obstacleStatus: "pass", airspaceStatus: "pass", notamStatus: "pass", visualConditionStatus: "pass" },
  crew: [{ userId: "operator-1", role: "operator", aircraftId: "aircraft-1", qualified: true, recencyCurrent: true, dutyStatus: "available" }],
  evidenceSnapshotId: "mission-evidence-1",
  dataSnapshots: [],
  riskAssessment: { hazardIds: [], mitigationIds: [], status: "complete" },
};

const fleet = [{ id: "aircraft-1" }];
const maintenance = [{ aircraftId: "aircraft-1", status: "pass" as const, evidenceRefs: ["maintenance-evidence-1"] }];

describe("fleet and energy safety-kernel integration", () => {
  it("blocks release for insufficient reserve and links the energy evidence", () => {
    const facts = buildFleetSafetyFacts(
      fleet,
      maintenance,
      mission.crew,
      [{ aircraftId: "aircraft-1", status: "blocked" as const, evidenceRefs: ["energy-model-fixture-1"] }],
    );
    expect(facts.energy).toEqual([{ aircraftId: "aircraft-1", status: "blocked", evidenceRef: "energy-model-fixture-1" }]);

    const result = evaluateMission({ mission, requirements: [], policy: undefined, nowUtc, fleetFacts: facts });
    expect(result.status).toBe("blocked");
    expect(result.blockers).toContainEqual(expect.objectContaining({ code: "INSUFFICIENT_RESERVE", evidenceRefs: ["energy-model-fixture-1"] }));
    expect(result.evaluations.find(({ requirementId }) => requirementId === "energy.reserve")).toMatchObject({
      result: "fail",
      reason: "INSUFFICIENT_RESERVE",
      evidenceRefs: ["energy-model-fixture-1"],
    });
  });

  it("fails closed for unknown energy and blocked maintenance evidence", () => {
    const facts = buildFleetSafetyFacts(
      fleet,
      [{ aircraftId: "aircraft-1", status: "blocked" as const, evidenceRefs: ["maintenance-evidence-1"] }],
      mission.crew,
      [{ aircraftId: "aircraft-1", status: "unknown" as const, evidenceRefs: ["energy-unknown-1"] }],
    );
    const result = evaluateMission({ mission, requirements: [], policy: undefined, nowUtc, fleetFacts: facts });
    expect(result.blockers).toEqual(expect.arrayContaining([
      expect.objectContaining({ code: "INVALID_MAINTENANCE_RELEASE", evidenceRefs: ["maintenance-evidence-1"] }),
      expect.objectContaining({ code: "ENERGY_EVIDENCE_UNKNOWN", evidenceRefs: ["energy-unknown-1"] }),
    ]));
    expect(result.evaluations).toEqual(expect.arrayContaining([
      expect.objectContaining({ requirementId: "maintenance.release", result: "fail" }),
      expect.objectContaining({ requirementId: "energy.reserve", result: "unknown" }),
    ]));
  });
});
