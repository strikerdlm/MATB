import { describe, expect, it } from "vitest";
import { createMissionRevision, transitionMission, type MissionRevision, type SafetyEvaluationResult } from "../src/index.js";

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

const fourAcceptedGates = ["maintenance", "operator", "safety", "commander"].map((gate) => ({ gate: gate as "maintenance" | "operator" | "safety" | "commander", decision: "accept" as const, valid: true }));

describe("authoritative mission lifecycle", () => {
  it("does not permit UnderReview to skip the four gates", () => {
    expect(() => transitionMission({ current: "UnderReview", event: "activate", actor, nowUtc, evaluation: readyEvaluation(), approvals: fourAcceptedGates })).toThrow("gate");
  });

  it("requires all four valid accepted gates before entering ReadyForRelease", () => {
    expect(() => transitionMission({ current: "UnderReview", event: "gates-complete", actor, nowUtc, evaluation: readyEvaluation(), approvals: fourAcceptedGates.slice(0, 3) })).toThrow("gate");

    const result = transitionMission({ current: "UnderReview", event: "gates-complete", actor, nowUtc, evaluation: readyEvaluation(), approvals: fourAcceptedGates });
    expect(result).toMatchObject({ state: "ReadyForRelease", auditEvent: { actorUserId: "commander-1", occurredAtUtc: nowUtc } });
    expect(Object.isFrozen(result)).toBe(true);
  });

  it("rejects activation with unresolved hard blockers even when four approvals are supplied", () => {
    const evaluation = readyEvaluation({ status: "blocked", blockers: [{ code: "BLOCKED", conceptId: "test.blocked", severity: "hard", explanationKey: "BLOCKED", evidenceRefs: [] }] });
    expect(() => transitionMission({ current: "Released", event: "activate", actor, nowUtc, evaluation, approvals: fourAcceptedGates })).toThrow("blocker");
  });

  it("uses caller-supplied deterministic audit time and rejects an invalid timestamp", () => {
    const result = transitionMission({ current: "Released", event: "activate", actor, nowUtc, evaluation: readyEvaluation(), approvals: fourAcceptedGates });
    expect(result.auditEvent.occurredAtUtc).toBe(nowUtc);
    expect(() => transitionMission({ current: "Released", event: "activate", actor, nowUtc: "2026-08-08", evaluation: readyEvaluation(), approvals: fourAcceptedGates })).toThrow("UTC ISO-8601");
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
});
