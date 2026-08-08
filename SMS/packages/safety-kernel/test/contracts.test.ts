import { describe, expect, it } from "vitest";
import { parseMissionRevision, parseSafetyEvaluationResult, type MissionRevision } from "../src/index.js";

const validMission: MissionRevision = {
  id: "mr-1", missionId: "m-1", revision: 1, profileId: "fac-state-aviation", state: "Planned",
  aircraft: [{ aircraftId: "ac-1", aircraftClass: "IA", configuration: "unarmed-isr" }], flightRule: "VFR", visualCondition: "VLOS", configuration: "unarmed-isr",
  route: { areaId: "area-1", routeHash: "hash-1", terrainStatus: "pass", obstacleStatus: "pass", airspaceStatus: "pass", notamStatus: "pass", visualConditionStatus: "pass" },
  crew: [], evidenceSnapshotId: "snapshot-1", dataSnapshots: [], riskAssessment: { hazardIds: [], mitigationIds: [], status: "draft" }
};

it("freezes evaluation results and preserves stable IDs", () => {
  const result = parseSafetyEvaluationResult({ missionRevisionId: "mr-1", status: "blocked", evaluations: [], blockers: [{ code: "missing-evidence", conceptId: "evidence.missing", severity: "data", explanationKey: "missingEvidence", evidenceRefs: [] }], invalidatedGates: [], kernelVersion: "0.1.0" });
  expect(Object.isFrozen(result)).toBe(true);
  expect(result.status).toBe("blocked");
  expect(result.kernelVersion).toMatch(/^0\./);
});

it("rejects a mission with no evidence snapshot", () => {
  expect(() => parseMissionRevision({ ...validMission, evidenceSnapshotId: "" })).toThrow();
});

describe("safety contract validation", () => {
  it("rejects local timestamps, duplicate aircraft and unknown fields", () => {
    expect(() => parseMissionRevision({ ...validMission, route: { ...validMission.route, areaId: "x", routeHash: "x", terrainStatus: "pass", obstacleStatus: "pass", airspaceStatus: "pass", notamStatus: "pass", visualConditionStatus: "pass", extra: true } })).toThrow();
    expect(() => parseMissionRevision({ ...validMission, aircraft: [validMission.aircraft[0], validMission.aircraft[0]] })).toThrow();
    expect(() => parseMissionRevision({ ...validMission, dataSnapshots: [{ snapshotId: "s", kind: "weather", packageId: "p", status: "current", capturedAtUtc: "2026-08-08T12:00:00" }] })).toThrow();
  });
});
