import { describe, expect, it } from "vitest";
import { invalidateForChange } from "../src/index.js";

const dependencyGraph = {
  entries: [
    { field: "battery", affectedRequirementIds: ["energy.reserve", "energy.diversion"] },
    { field: "route", affectedRequirementIds: ["route.terrain", "route.airspace"] },
  ],
} as const;

describe("material change dependencies", () => {
  it("invalidates energy evaluations and affected gates when a battery changes", () => {
    const result = invalidateForChange({
      field: "battery",
      previous: { batteryId: "bat-1", chemistry: "li-ion", capacityWh: 450, cycleCount: 3 },
      next: { batteryId: "bat-2", chemistry: "li-ion", capacityWh: 500, cycleCount: 4 },
      dependencyGraph,
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
      field: "display-note", previous: "initial note", next: "clarified note", dependencyGraph,
    });

    expect(result).toEqual({ material: false, affectedRequirementIds: [], invalidatedGates: [], reason: "NON_MATERIAL_DISPLAY_NOTE" });
  });

  it("does not invalidate when a material field is unchanged", () => {
    const route = { areaId: "area-1", routeHash: "route-1", terrainStatus: "pass" as const, obstacleStatus: "pass" as const, airspaceStatus: "pass" as const, notamStatus: "pass" as const, visualConditionStatus: "pass" as const };
    const result = invalidateForChange({ field: "route", previous: route, next: { ...route }, dependencyGraph });
    expect(result).toEqual({ material: false, affectedRequirementIds: [], invalidatedGates: [], reason: "NO_EFFECTIVE_CHANGE" });
  });
});
