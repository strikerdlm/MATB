import { canonicalJson } from "@fac-isr/evidence";
import { createHash } from "node:crypto";
import {
  parseGateApprovalEvent,
  parseGateDecisionInput,
  parseGateInvalidationInput,
  type GateApprovalEvent,
  type GateDecisionEvent,
  type GateDecisionInput,
  type GateInvalidationEvent,
  type GateInvalidationInput,
  type GateName,
} from "./types.js";

const GATE_ORDER: readonly GateName[] = ["maintenance", "operator", "safety", "commander"];

type HashPayload = Omit<GateDecisionEvent, "eventHash"> | Omit<GateInvalidationEvent, "eventHash">;

function eventPayload(event: GateApprovalEvent): HashPayload {
  if (event.eventType === "gate.decision") {
    const { eventHash: _eventHash, ...payload } = event;
    return payload;
  }
  const { eventHash: _eventHash, ...payload } = event;
  return payload;
}

function eventHash(event: GateApprovalEvent): string {
  return createHash("sha256").update(canonicalJson(eventPayload(event))).digest("hex");
}

/**
 * Creates one immutable, caller-timestamped decision record. The event remains
 * untrusted until it is checked as part of a complete chain.
 */
export function recordGateDecision(input: GateDecisionInput): GateDecisionEvent {
  const decision = parseGateDecisionInput(input);
  const event = {
    eventType: "gate.decision" as const,
    ...decision,
    eventHash: "0".repeat(64),
  };
  return parseGateApprovalEvent({ ...event, eventHash: eventHash(event) }) as GateDecisionEvent;
}

/**
 * Produces only invalidation records for a material change. It never synthesizes
 * an approval; a later acceptance must be represented by a new decision event.
 */
export function invalidateGateApprovals(input: GateInvalidationInput): GateApprovalEvent[] {
  const invalidationInput = parseGateInvalidationInput(input);
  const { invalidation } = invalidationInput;
  if (!invalidation.material) return Object.freeze([]) as unknown as GateApprovalEvent[];
  const uniqueGates = new Set(invalidation.invalidatedGates);
  if (uniqueGates.size !== invalidation.invalidatedGates.length) throw new RangeError("invalidation gates must be unique");
  if (uniqueGates.size === 0) throw new RangeError("material change must invalidate at least one gate");

  let previousHash = invalidationInput.previousHash;
  const events = GATE_ORDER.filter((gate) => uniqueGates.has(gate)).map((gate, index) => {
    const event = {
      eventType: "gate.invalidation" as const,
      sequence: invalidationInput.sequence + index,
      previousHash,
      eventHash: "0".repeat(64),
      missionRevisionId: invalidationInput.missionRevisionId,
      gate,
      actorUserId: invalidationInput.actorUserId,
      actorRole: invalidationInput.actorRole,
      occurredAtUtc: invalidationInput.nowUtc,
      affectedRequirementIds: invalidation.affectedRequirementIds,
      reason: invalidation.reason,
    };
    const signed = parseGateApprovalEvent({ ...event, eventHash: eventHash(event) }) as GateInvalidationEvent;
    previousHash = signed.eventHash;
    return signed;
  });
  return Object.freeze(events) as unknown as GateApprovalEvent[];
}

/** Validates complete ordering, predecessor links, and canonical event hashes. */
export function assertGateApprovalEventChain(events: readonly GateApprovalEvent[]): void {
  let previousHash: string | null = null;
  for (let index = 0; index < events.length; index += 1) {
    const event = parseGateApprovalEvent(events[index]);
    if (event.sequence !== index) throw new RangeError("audit event sequence is not contiguous");
    if (event.previousHash !== previousHash) throw new RangeError("audit event previous hash does not match the chain");
    if (event.eventHash !== eventHash(event)) throw new RangeError("audit event hash does not match canonical event content");
    previousHash = event.eventHash;
  }
}
