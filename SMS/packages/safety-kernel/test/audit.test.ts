import { describe, expect, it } from "vitest";
import { assertGateApprovalEventChain, invalidateGateApprovals, recordGateDecision, type GateDecisionInput } from "../src/index.js";

const decision = (overrides: Partial<GateDecisionInput> = {}): GateDecisionInput => ({
  missionRevisionId: "mr-audit-1", gate: "maintenance", actorUserId: "maintainer-1", actorRole: "maintainer",
  decision: "accept", valid: true, occurredAtUtc: "2026-08-08T17:00:00Z", evidenceSnapshotId: "evidence-1", policyVersion: "policy-1", reason: "APPROVED",
  sequence: 0, previousHash: null,
  ...overrides,
});

describe("append-only gate audit events", () => {
  it("commits a decision and its previous hash through canonical SHA-256", () => {
    const first = recordGateDecision(decision());
    const second = recordGateDecision(decision({ gate: "safety", actorUserId: "safety-1", actorRole: "safety", sequence: 1, previousHash: first.eventHash }));

    expect(first.eventHash).toMatch(/^[a-f0-9]{64}$/);
    expect(second.previousHash).toBe(first.eventHash);
    expect(() => assertGateApprovalEventChain([first, second])).not.toThrow();
  });

  it("detects a changed decision even when its stored digest is retained", () => {
    const event = recordGateDecision(decision());

    expect(() => assertGateApprovalEventChain([{ ...event, reason: "ALTERED" }])).toThrow("event hash");
  });

  it("detects duplicate sequences and a wrong chain predecessor", () => {
    const first = recordGateDecision(decision());
    const duplicateSequence = recordGateDecision(decision({ gate: "safety", actorUserId: "safety-1", actorRole: "safety", sequence: 0, previousHash: first.eventHash }));
    const wrongPredecessor = recordGateDecision(decision({ gate: "safety", actorUserId: "safety-1", actorRole: "safety", sequence: 1, previousHash: "a".repeat(64) }));

    expect(() => assertGateApprovalEventChain([first, duplicateSequence])).toThrow("sequence");
    expect(() => assertGateApprovalEventChain([first, wrongPredecessor])).toThrow("previous hash");
  });

  it("emits only explicit invalidations for material changes", () => {
    const events = invalidateGateApprovals({
      missionRevisionId: "mr-audit-1", nowUtc: "2026-08-08T18:00:00Z", actorUserId: "safety-1", actorRole: "safety", sequence: 3, previousHash: "b".repeat(64),
      invalidation: { material: true, affectedRequirementIds: ["req-1"], invalidatedGates: ["operator", "safety"], reason: "MATERIAL_CHANGE_ROUTE" },
    });

    expect(events).toHaveLength(2);
    expect(events.map((event) => event.eventType)).toEqual(["gate.invalidation", "gate.invalidation"]);
    expect(events.map((event) => event.gate)).toEqual(["operator", "safety"]);
    expect(events[1]?.previousHash).toBe(events[0]?.eventHash);
  });
});
