import type { AuditEventInput } from "./ledger.js";

export const OPERATIONAL_AUDIT_EVENT_TYPES = Object.freeze([
  "authentication.succeeded",
  "authentication.failed",
  "identity.locked",
  "session.locked",
  "checklist.response",
  "gate.accepted",
  "gate.blocked",
  "gate.escalated",
  "mission.created",
  "mission.revised",
  "telemetry.observed",
  "export.created",
]) as readonly string[];

export type OperationalAuditEventType = (typeof OPERATIONAL_AUDIT_EVENT_TYPES)[number];

export interface GateDecisionAuditInput extends Omit<AuditEventInput, "type" | "action"> {
  readonly gate: "maintenance" | "operator" | "safety" | "commander";
  readonly decision: "accept" | "block" | "escalate";
}

/** Creates the common gate-decision envelope without assigning ledger fields. */
export function createGateDecisionEvent(input: GateDecisionAuditInput): AuditEventInput {
  const { gate, decision, payload, ...event } = input;
  return Object.freeze({
    ...event,
    type: `gate.${decision}`,
    action: decision,
    payload: Object.freeze({ gate, decision, ...(payload ?? {}) }),
  });
}

export function createGateAcceptedEvent(input: Omit<GateDecisionAuditInput, "decision">): AuditEventInput {
  return createGateDecisionEvent({ ...input, decision: "accept" });
}

export function createGateBlockedEvent(input: Omit<GateDecisionAuditInput, "decision">): AuditEventInput {
  return createGateDecisionEvent({ ...input, decision: "block" });
}
