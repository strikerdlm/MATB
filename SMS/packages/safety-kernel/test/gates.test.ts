import { describe, expect, it } from "vitest";
import { evaluateFourGates, type GateApproval, type GateEvaluationInput, type MissionRevision, type SafetyEvaluationResult } from "../src/index.js";

const nowUtc = "2026-08-08T17:00:00Z";

const mission = (overrides: Partial<MissionRevision> = {}): MissionRevision => ({
  id: "mr-gates-1", missionId: "m-gates-1", revision: 1, profileId: "fac-state-aviation", state: "UnderReview",
  aircraft: [
    { aircraftId: "aircraft-1", aircraftClass: "IC", configuration: "unarmed-isr", operatorUserId: "operator-1" },
    { aircraftId: "aircraft-2", aircraftClass: "IC", configuration: "unarmed-isr", operatorUserId: "operator-2" },
  ],
  flightRule: "VFR", visualCondition: "VLOS", configuration: "unarmed-isr",
  route: { areaId: "area-1", routeHash: "route-1", terrainStatus: "pass", obstacleStatus: "pass", airspaceStatus: "pass", notamStatus: "pass", visualConditionStatus: "pass" },
  crew: [
    { userId: "maintainer-1", role: "maintainer", qualified: true, recencyCurrent: true, dutyStatus: "available" },
    { userId: "operator-1", role: "operator", aircraftId: "aircraft-1", qualified: true, recencyCurrent: true, dutyStatus: "available" },
    { userId: "operator-2", role: "operator", aircraftId: "aircraft-2", qualified: true, recencyCurrent: true, dutyStatus: "available" },
    { userId: "safety-1", role: "safety", qualified: true, recencyCurrent: true, dutyStatus: "available" },
    { userId: "commander-1", role: "commander", qualified: true, recencyCurrent: true, dutyStatus: "available" },
  ],
  evidenceSnapshotId: "evidence-1", dataSnapshots: [], riskAssessment: { hazardIds: [], mitigationIds: [], status: "complete" },
  ...overrides,
});

const evaluation = (missionRevisionId = "mr-gates-1", overrides: Partial<SafetyEvaluationResult> = {}): SafetyEvaluationResult => ({
  missionRevisionId, status: "ready", evaluations: [], blockers: [], invalidatedGates: [], kernelVersion: "0.1.0", ...overrides,
});

const approval = (gate: GateApproval["gate"], actorUserId: string, actorRole: GateApproval["actorRole"], aircraftId?: string): GateApproval => ({
  missionRevisionId: "mr-gates-1", gate, actorUserId, actorRole, aircraftId,
  decision: "accept", valid: true, occurredAtUtc: nowUtc, evidenceSnapshotId: "evidence-1", policyVersion: "policy-1", reason: "APPROVED",
});

const acceptedApprovals = (): readonly GateApproval[] => [
  approval("maintenance", "maintainer-1", "maintainer"),
  approval("operator", "operator-1", "operator", "aircraft-1"),
  approval("operator", "operator-2", "operator", "aircraft-2"),
  approval("safety", "safety-1", "safety"),
  approval("commander", "commander-1", "commander"),
];

const input = (overrides: Partial<GateEvaluationInput> = {}): GateEvaluationInput => ({
  mission: mission(), evaluation: evaluation(), approvals: acceptedApprovals(), nowUtc, ...overrides,
});

describe("four-gate release authority", () => {
  it("requires every assigned operator acceptance", () => {
    const result = evaluateFourGates(input({ approvals: acceptedApprovals().filter((item) => item.aircraftId !== "aircraft-2") }));

    expect(result.status).toBe("blocked");
    expect(result.blockers.map(({ code }) => code)).toContain("MISSING_OPERATOR_PER_AIRCRAFT");
  });

  it("does not let commander authorization override an operator no-go", () => {
    const approvals = acceptedApprovals().map((item) => item.aircraftId === "aircraft-1" ? { ...item, decision: "block" as const, reason: "OPERATOR_NO_GO" } : item);

    const result = evaluateFourGates(input({ approvals }));

    expect(result.status).toBe("blocked");
    expect(result.gates.find((gate) => gate.gate === "operator")?.status).toBe("blocked");
  });

  it("rejects a commander signing the maintenance gate", () => {
    const approvals = acceptedApprovals().map((item) => item.gate === "maintenance" ? { ...item, actorUserId: "commander-1", actorRole: "commander" as const } : item);

    expect(evaluateFourGates(input({ approvals })).blockers.map(({ code }) => code)).toContain("UNAUTHORIZED_GATE_ROLE");
  });

  it("fails closed when the evaluation invalidates a gate", () => {
    const result = evaluateFourGates(input({ evaluation: evaluation("mr-gates-1", { invalidatedGates: ["safety"] }) }));

    expect(result.status).toBe("blocked");
    expect(result.gates.find((gate) => gate.gate === "safety")?.status).toBe("invalid");
  });
});
