import { describe, expect, it } from "vitest";
import { invalidateForChange, type MissionRevision } from "../src/index.js";

const mission: MissionRevision = {
  id: "mr-dependency-1", missionId: "m-dependency-1", revision: 1, profileId: "fac-state-aviation", state: "Planned",
  aircraft: [{ aircraftId: "ac-1", aircraftClass: "IA", configuration: "unarmed-isr" }], flightRule: "VFR", visualCondition: "VLOS", configuration: "unarmed-isr",
  route: { areaId: "area-1", routeHash: "route-1", terrainStatus: "pass", obstacleStatus: "pass", airspaceStatus: "pass", notamStatus: "pass", visualConditionStatus: "pass" },
  crew: [], evidenceSnapshotId: "evidence-1", dataSnapshots: [], riskAssessment: { hazardIds: [], mitigationIds: [], status: "complete" },
};

const dependencyGraph = {
  entries: [
    { field: "battery", affectedRequirementIds: ["energy.reserve", "energy.diversion"] },
    { field: "route", affectedRequirementIds: ["route.terrain", "route.airspace"] },
  ],
} as const;

describe("material change dependencies", () => {
  it("invalidates energy evaluations and affected gates when a battery changes", () => {
    const result = invalidateForChange({
      mission, field: "battery", previous: { packId: "bat-1" }, next: { packId: "bat-2" }, dependencyGraph,
    });

    expect(result).toEqual({
      material: true,
      affectedRequirementIds: ["energy.diversion", "energy.reserve"],
      invalidatedGates: ["maintenance", "operator", "safety", "commander"],
      reason: "MATERIAL_CHANGE_BATTERY",
    });
    expect(Object.isFrozen(result)).toBe(true);
  });

  it("does not invalidate approvals for a non-material display note", () => {
    const result = invalidateForChange({
      mission, field: "display-note", previous: "initial note", next: "clarified note", dependencyGraph,
    });

    expect(result).toEqual({ material: false, affectedRequirementIds: [], invalidatedGates: [], reason: "NON_MATERIAL_DISPLAY_NOTE" });
  });

  it("does not invalidate when a material field is unchanged", () => {
    const result = invalidateForChange({ mission, field: "route", previous: { routeHash: "same" }, next: { routeHash: "same" }, dependencyGraph });
    expect(result).toEqual({ material: false, affectedRequirementIds: [], invalidatedGates: [], reason: "NO_EFFECTIVE_CHANGE" });
  });
});
