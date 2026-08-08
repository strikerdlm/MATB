import { describe, expect, it } from "vitest";
import { createMissionRevision, transitionMission, type GateApproval, type MissionRevision, type MissionRevisionChange, type SafetyEvaluationResult } from "../src/index.js";

const nowUtc = "2026-08-08T17:00:00Z";
const actor = { userId: "commander-1", role: "commander" as const };

const mission = (overrides: Partial<MissionRevision> = {}): MissionRevision => ({
  id: "mr-lifecycle-1", missionId: "m-lifecycle-1", revision: 3, profileId: "fac-state-aviation", state: "Released",
  aircraft: [{ aircraftId: "ac-1", aircraftClass: "IC", configuration: "unarmed-isr", operatorUserId: "operator-1" }],
  flightRule: "VFR", visualCondition: "VLOS", configuration: "unarmed-isr",
  route: { areaId: "area-1", routeHash: "route-1", terrainStatus: "pass", obstacleStatus: "pass", airspaceStatus: "pass", notamStatus: "pass", visualConditionStatus: "pass" },
  crew: [{ userId: "operator-1", role: "operator", aircraftId: "ac-1", qualified: true, recencyCurrent: true, dutyStatus: "available" }],
  evidenceSnapshotId: "evidence-1", dataSnapshots: [], riskAssessment: { hazardIds: [], mitigationIds: [], status: "complete" },
  ...overrides,
});

const readyEvaluation = (overrides: Partial<SafetyEvaluationResult> = {}): SafetyEvaluationResult => ({
  missionRevisionId: "mr-lifecycle-1", status: "ready", evaluations: [], blockers: [], invalidatedGates: [], kernelVersion: "0.1.0", ...overrides,
});

const fourAcceptedGates: readonly GateApproval[] = [
  { missionRevisionId: "mr-lifecycle-1", gate: "maintenance", actorUserId: "maintainer-1", actorRole: "maintainer", decision: "accept", valid: true, occurredAtUtc: nowUtc, evidenceSnapshotId: "evidence-1", policyVersion: "policy-1", reason: "APPROVED" },
  { missionRevisionId: "mr-lifecycle-1", gate: "operator", actorUserId: "operator-1", actorRole: "operator", aircraftId: "ac-1", decision: "accept", valid: true, occurredAtUtc: nowUtc, evidenceSnapshotId: "evidence-1", policyVersion: "policy-1", reason: "APPROVED" },
  { missionRevisionId: "mr-lifecycle-1", gate: "safety", actorUserId: "safety-1", actorRole: "safety", decision: "accept", valid: true, occurredAtUtc: nowUtc, evidenceSnapshotId: "evidence-1", policyVersion: "policy-1", reason: "APPROVED" },
  { missionRevisionId: "mr-lifecycle-1", gate: "commander", actorUserId: "commander-1", actorRole: "commander", decision: "accept", valid: true, occurredAtUtc: nowUtc, evidenceSnapshotId: "evidence-1", policyVersion: "policy-1", reason: "APPROVED" },
];

describe("authoritative mission lifecycle", () => {
  it("does not permit UnderReview to skip the four gates", () => {
    expect(() => transitionMission({ missionRevisionId: "mr-lifecycle-1", current: "UnderReview", event: "activate", actor, nowUtc, evaluation: readyEvaluation(), approvals: fourAcceptedGates })).toThrow("gate");
  });

  it("requires all four valid accepted gates before entering ReadyForRelease", () => {
    expect(() => transitionMission({ missionRevisionId: "mr-lifecycle-1", current: "UnderReview", event: "gates-complete", actor, nowUtc, evaluation: readyEvaluation(), approvals: fourAcceptedGates.slice(0, 3) })).toThrow("gate");

    const result = transitionMission({ missionRevisionId: "mr-lifecycle-1", current: "UnderReview", event: "gates-complete", actor, nowUtc, evaluation: readyEvaluation(), approvals: fourAcceptedGates });
    expect(result).toMatchObject({ state: "ReadyForRelease", auditEvent: { missionRevisionId: "mr-lifecycle-1", actorUserId: "commander-1", occurredAtUtc: nowUtc } });
    expect(Object.isFrozen(result)).toBe(true);
  });

  it("rejects activation with unresolved hard blockers even when four approvals are supplied", () => {
    const evaluation = readyEvaluation({ status: "blocked", blockers: [{ code: "BLOCKED", conceptId: "test.blocked", severity: "hard", explanationKey: "BLOCKED", evidenceRefs: [] }] });
    expect(() => transitionMission({ missionRevisionId: "mr-lifecycle-1", current: "Released", event: "activate", actor, nowUtc, evaluation, approvals: fourAcceptedGates })).toThrow("blocker");
  });

  it("uses caller-supplied deterministic audit time and rejects an invalid timestamp", () => {
    const result = transitionMission({ missionRevisionId: "mr-lifecycle-1", current: "Released", event: "activate", actor, nowUtc, evaluation: readyEvaluation(), approvals: fourAcceptedGates });
    expect(result.auditEvent.occurredAtUtc).toBe(nowUtc);
    expect(() => transitionMission({ missionRevisionId: "mr-lifecycle-1", current: "Released", event: "activate", actor, nowUtc: "2026-08-08", evaluation: readyEvaluation(), approvals: fourAcceptedGates })).toThrow("UTC ISO-8601");
  });
});

describe("mission revisions", () => {
  it("creates a new revision when the route changes and invalidates release state", () => {
    const releasedMission = mission();
    const changedRoute = { ...releasedMission.route, routeHash: "route-2" };

    const result = createMissionRevision(releasedMission, { field: "route", previous: releasedMission.route, next: changedRoute });

    expect(result.revision).toBe(releasedMission.revision + 1);
    expect(result.state).toBe("Planned");
    expect(result.id).not.toBe(releasedMission.id);
    expect(result.missionId).toBe(releasedMission.missionId);
    expect(result.evidenceSnapshotId).toBe(releasedMission.evidenceSnapshotId);
    expect(result.route).toEqual(changedRoute);
    expect(releasedMission.state).toBe("Released");
    expect(Object.isFrozen(result)).toBe(true);
  });

  const addedFactChanges: readonly (MissionRevisionChange & { readonly property: keyof MissionRevision })[] = [
    { field: "gcs", previous: undefined, next: { gcsId: "gcs-2", configurationHash: "gcs-config-2" }, property: "gcs" },
    { field: "payload", previous: undefined, next: { payloadId: "payload-2", configurationHash: "payload-config-2" }, property: "payload" },
    { field: "battery", previous: undefined, next: { batteryId: "battery-2", chemistry: "li-ion", capacityWh: 500, cycleCount: 4 }, property: "battery" },
    { field: "software", previous: undefined, next: { componentId: "autopilot", version: "2.0.0", integrityHash: "software-hash-2" }, property: "software" },
    { field: "altitude", previous: undefined, next: { minimumMetersAgl: 30, maximumMetersAgl: 120 }, property: "altitude" },
    { field: "schedule", previous: undefined, next: { plannedStartUtc: "2026-08-09T17:00:00Z", plannedEndUtc: "2026-08-09T18:00:00Z" }, property: "schedule" },
  ];

  it.each(addedFactChanges)("creates a frozen Planned revision for material $field", (change) => {
    const releasedMission = mission();

    const result = createMissionRevision(releasedMission, change);

    expect(result).toMatchObject({ revision: releasedMission.revision + 1, state: "Planned" });
    expect(result[change.property]).toEqual(change.next);
    expect(Object.isFrozen(result)).toBe(true);
  });

  it("rejects a battery revision when the supplied previous fact is stale", () => {
    const releasedMission = mission({ battery: { batteryId: "battery-1", chemistry: "li-ion", capacityWh: 450, cycleCount: 3 } });
    expect(() => createMissionRevision(releasedMission, {
      field: "battery",
      previous: { batteryId: "battery-0", chemistry: "li-ion", capacityWh: 450, cycleCount: 3 },
      next: { batteryId: "battery-2", chemistry: "li-ion", capacityWh: 500, cycleCount: 4 },
    })).toThrow("previous battery");
  });
});

describe("revision-bound release decisions", () => {
  it("rejects an evaluation belonging to the prior revision", () => {
    const releasedMission = mission();
    const changedMission = createMissionRevision(releasedMission, {
      field: "route", previous: releasedMission.route, next: { ...releasedMission.route, routeHash: "route-2" },
    });
    const changedApprovals = fourAcceptedGates.map((approval) => ({ ...approval, missionRevisionId: changedMission.id }));

    expect(() => transitionMission({
      current: "Released" as const,
      event: "activate" as const,
      actor,
      nowUtc,
      missionRevisionId: changedMission.id,
      evaluation: readyEvaluation({ missionRevisionId: releasedMission.id }),
      approvals: changedApprovals,
    })).toThrow("evaluation revision");
  });

  it("rejects even one gate approval belonging to the prior revision", () => {
    const releasedMission = mission();
    const changedMission = createMissionRevision(releasedMission, {
      field: "route", previous: releasedMission.route, next: { ...releasedMission.route, routeHash: "route-2" },
    });
    const approvals = fourAcceptedGates.map((approval) => ({ ...approval, missionRevisionId: changedMission.id }));
    approvals[0] = { ...approvals[0]!, missionRevisionId: releasedMission.id };

    expect(() => transitionMission({
      current: "ReadyForRelease",
      event: "release",
      actor,
      nowUtc,
      missionRevisionId: changedMission.id,
      evaluation: readyEvaluation({ missionRevisionId: changedMission.id }),
      approvals,
    })).toThrow("gate approval revision");
  });
});
