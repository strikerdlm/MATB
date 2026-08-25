import { DeterministicSafetyEvaluationProvider } from "../src/services/safety-evaluation.js";

export const nowUtc = "2026-08-09T18:00:00.000Z";

export function missionFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: "mission-1:r0",
    missionId: "mission-1",
    revision: 0,
    profileId: "fac-state-aviation",
    state: "Draft",
    aircraft: [{
      aircraftId: "aircraft-1",
      aircraftClass: "II",
      configuration: "unarmed-isr",
      operatorUserId: "operator-1",
      maintenanceReleaseId: "maintenance-1",
    }],
    gcs: { gcsId: "gcs-1", configurationHash: "gcs-hash-1" },
    payload: { payloadId: "payload-1", configurationHash: "payload-hash-1" },
    battery: { batteryId: "battery-1", chemistry: "li-po", capacityWh: 500, cycleCount: 12 },
    software: { componentId: "flight-software", version: "1.0.0", integrityHash: "software-hash-1" },
    flightRule: "VFR",
    visualCondition: "VLOS",
    altitude: { minimumMetersAgl: 30, maximumMetersAgl: 120 },
    schedule: { plannedStartUtc: nowUtc, plannedEndUtc: "2026-08-09T19:00:00.000Z" },
    configuration: "unarmed-isr",
    route: {
      areaId: "area-1",
      routeHash: "route-hash-1",
      terrainStatus: "pass",
      obstacleStatus: "pass",
      airspaceStatus: "pass",
      notamStatus: "pass",
      visualConditionStatus: "pass",
    },
    crew: [
      { userId: "operator-1", role: "operator", aircraftId: "aircraft-1", qualified: true, recencyCurrent: true, dutyStatus: "available" },
      { userId: "maintainer-1", role: "maintainer", qualified: true, recencyCurrent: true, dutyStatus: "available" },
      { userId: "safety-1", role: "safety", qualified: true, recencyCurrent: true, dutyStatus: "available" },
      { userId: "commander-1", role: "commander", qualified: true, recencyCurrent: true, dutyStatus: "available" },
    ],
    evidenceSnapshotId: "evidence-1",
    policyPackageId: "policy-1",
    dataSnapshots: [{ snapshotId: "weather-1", kind: "weather", packageId: "weather-pack", status: "current", capturedAtUtc: nowUtc }],
    riskAssessment: {
      hazardIds: ["hazard-1"],
      mitigationIds: ["mitigation-1"],
      status: "complete",
      reserve: { recoveryPercent: 30, diversionPercent: 20, contingencyPercent: 10 },
    },
    ...overrides,
  };
}

export function safetyResult(revisionId = "mission-1:r0") {
  return {
    missionRevisionId: revisionId,
    status: "ready",
    evaluations: [],
    blockers: [],
    invalidatedGates: [],
    kernelVersion: "0.1.0",
  };
}

export function testSafetyEvaluationProvider() {
  return new DeterministicSafetyEvaluationProvider({
    now: () => nowUtc,
    resolve: async () => ({
      requirements: [],
      policy: {
        packageId: "policy-fixture",
        version: "1.0.0",
        status: "approved",
        delegatedAuthorities: [],
        freshness: {
          aip: { maxAgeMinutes: 120, critical: true },
          notam: { maxAgeMinutes: 120, critical: true },
          weather: { maxAgeMinutes: 120, critical: true },
          terrain: { maxAgeMinutes: 120, critical: true },
          airspace: { maxAgeMinutes: 120, critical: true },
          policy: { maxAgeMinutes: 120, critical: true },
          regulation: { maxAgeMinutes: 120, critical: true },
        },
        signature: "test-fixture-signature",
      },
      evidenceSnapshot: { snapshotId: "evidence-1", acceptedEvidenceIds: [] },
      policyPackage: { packageId: "policy-fixture", version: "1.0.0" },
      terminologyPackage: { packageId: "terminology-fixture", version: "1.0.0" },
      evidencePackage: { packageId: "evidence-fixture", version: "1.0.0" },
    }),
  });
}
