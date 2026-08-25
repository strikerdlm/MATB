import type { MissionState } from "../src/api/types.js";

export const e2eNowUtc = "2026-08-25T12:00:00.000Z";

export function missionFixture(missionId: string, state: MissionState = "Draft", aircraftId = "aircraft-1") {
  return {
    id: `${missionId}:r0`, missionId, revision: 0, profileId: "fac-state-aviation", state,
    aircraft: [{ aircraftId, aircraftClass: "II", configuration: "unarmed-isr", operatorUserId: "operator-1", maintenanceReleaseId: "maintenance-1" }],
    gcs: { gcsId: "gcs-1", configurationHash: "gcs-hash-1" }, payload: { payloadId: "payload-1", configurationHash: "payload-hash-1" },
    battery: { batteryId: "battery-1", chemistry: "li-po", capacityWh: 500, cycleCount: 12 }, software: { componentId: "flight-software", version: "1.0.0", integrityHash: "software-hash-1" },
    flightRule: "VFR", visualCondition: "VLOS", altitude: { minimumMetersAgl: 30, maximumMetersAgl: 120 }, schedule: { plannedStartUtc: e2eNowUtc, plannedEndUtc: "2026-08-25T13:00:00.000Z" }, configuration: "unarmed-isr",
    route: { areaId: "area-1", routeHash: `route-hash-${missionId}`, terrainStatus: "pass", obstacleStatus: "pass", airspaceStatus: "pass", notamStatus: "pass", visualConditionStatus: "pass" },
    crew: [{ userId: "operator-1", role: "operator", aircraftId, qualified: true, recencyCurrent: true, dutyStatus: "available" }, { userId: "maintainer-1", role: "maintainer", qualified: true, recencyCurrent: true, dutyStatus: "available" }, { userId: "safety-1", role: "safety", qualified: true, recencyCurrent: true, dutyStatus: "available" }, { userId: "commander-1", role: "commander", qualified: true, recencyCurrent: true, dutyStatus: "available" }],
    evidenceSnapshotId: "evidence-1", policyPackageId: "policy-console-e2e", dataSnapshots: [{ snapshotId: "weather-1", kind: "weather", packageId: "weather-pack", status: "current", capturedAtUtc: e2eNowUtc }],
    riskAssessment: { hazardIds: ["hazard-1"], mitigationIds: ["mitigation-1"], status: "complete", reserve: { recoveryPercent: 30, diversionPercent: 20, contingencyPercent: 10 } },
  };
}
