import { buildHardBlockers } from "./applicability.js";
import { CONCEPT_IDS } from "./terminology.js";
import {
  parseGateApproval,
  parseMissionRevision,
  parseSafetyEvaluationResult,
  type FourGateResult,
  type GateActorRole,
  type GateApproval,
  type GateEvaluationInput,
  type GateName,
  type SafetyBlocker,
} from "./types.js";

const GATE_ORDER: readonly GateName[] = ["maintenance", "operator", "safety", "commander"];
const ROLE_BY_GATE: Readonly<Record<GateName, GateActorRole>> = {
  maintenance: "maintainer",
  operator: "operator",
  safety: "safety",
  commander: "commander",
};
const UTC_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/;

function freeze<T>(value: T): T {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value as Record<string, unknown>)) freeze(child);
  }
  return value;
}

function utcTimestamp(value: string): number {
  const match = UTC_PATTERN.exec(value);
  if (!match) throw new RangeError("timestamp must be a valid UTC ISO-8601 instant");
  const [, year, month, day, hour, minute, second, fraction = ""] = match;
  const timestamp = Date.parse(value);
  const date = new Date(timestamp);
  if (!Number.isFinite(timestamp)
    || date.getUTCFullYear() !== Number(year)
    || date.getUTCMonth() + 1 !== Number(month)
    || date.getUTCDate() !== Number(day)
    || date.getUTCHours() !== Number(hour)
    || date.getUTCMinutes() !== Number(minute)
    || date.getUTCSeconds() !== Number(second)
    || date.getUTCMilliseconds() !== Number(fraction.padEnd(3, "0") || 0)) {
    throw new RangeError("timestamp must be a valid UTC ISO-8601 instant");
  }
  return timestamp;
}

function authorityBlocker(code: string, evidenceRefs: readonly string[] = []): SafetyBlocker {
  return { code, conceptId: CONCEPT_IDS.gateAuthority, severity: "authority", explanationKey: code, evidenceRefs };
}

function actorMatchesMission(approval: GateApproval, input: GateEvaluationInput): boolean {
  if (approval.gate === "operator") {
    const aircraft = input.mission.aircraft.find((item) => item.aircraftId === approval.aircraftId);
    if (!aircraft || aircraft.operatorUserId !== approval.actorUserId) return false;
    return input.mission.crew.some((member) => member.userId === approval.actorUserId
      && member.role === "operator" && member.aircraftId === approval.aircraftId
      && member.qualified && member.recencyCurrent && member.dutyStatus === "available");
  }
  return input.mission.crew.some((member) => member.userId === approval.actorUserId
    && member.role === approval.actorRole && member.qualified && member.recencyCurrent && member.dutyStatus === "available");
}

function validateDecision(
  approval: GateApproval,
  gate: GateName,
  missionRevisionId: string,
  evidenceSnapshotId: string,
  now: number,
  input: GateEvaluationInput,
  blockers: SafetyBlocker[],
): "accepted" | "blocked" | "invalid" {
  if (approval.actorRole !== ROLE_BY_GATE[gate]) {
    blockers.push(authorityBlocker("UNAUTHORIZED_GATE_ROLE", [approval.actorUserId]));
    return "invalid";
  }
  if (!actorMatchesMission(approval, input)) {
    blockers.push(authorityBlocker("UNAUTHORIZED_GATE_IDENTITY", [approval.actorUserId]));
    return "invalid";
  }
  if (approval.missionRevisionId !== missionRevisionId || approval.evidenceSnapshotId !== evidenceSnapshotId || utcTimestamp(approval.occurredAtUtc) > now) {
    blockers.push(authorityBlocker("STALE_GATE_APPROVAL", [approval.missionRevisionId, approval.evidenceSnapshotId]));
    return "invalid";
  }
  if (!approval.valid) {
    blockers.push(authorityBlocker("INVALID_GATE_APPROVAL", [approval.actorUserId]));
    return "invalid";
  }
  if (approval.decision !== "accept") {
    blockers.push(authorityBlocker(approval.decision === "block" ? "GATE_DECISION_BLOCK" : "GATE_DECISION_ESCALATE", [approval.actorUserId]));
    return "blocked";
  }
  return "accepted";
}

/**
 * Independently evaluates maintenance, per-aircraft operator, safety, and
 * commander authority. No approval can compensate for a missing or invalid
 * approval in another gate.
 */
export function evaluateFourGates(input: GateEvaluationInput): FourGateResult {
  const mission = parseMissionRevision(input.mission);
  const evaluation = parseSafetyEvaluationResult(input.evaluation);
  const approvals = input.approvals.map((approval) => parseGateApproval(approval));
  const now = utcTimestamp(input.nowUtc);
  const blockers: SafetyBlocker[] = [...buildHardBlockers(mission), ...evaluation.blockers];
  const invalidated = new Set(evaluation.invalidatedGates);

  if (evaluation.missionRevisionId !== mission.id) blockers.push(authorityBlocker("STALE_SAFETY_EVALUATION", [evaluation.missionRevisionId]));
  if (evaluation.status !== "ready") blockers.push(authorityBlocker("SAFETY_EVALUATION_NOT_READY"));

  const assignedOperatorIds = mission.aircraft.map((aircraft) => aircraft.operatorUserId);
  if (assignedOperatorIds.some((operatorId) => !operatorId) || new Set(assignedOperatorIds).size !== assignedOperatorIds.length) {
    blockers.push(authorityBlocker("ONE_OPERATOR_PER_AIRCRAFT_REQUIRED"));
  }

  const gates = GATE_ORDER.map((gate) => {
    if (invalidated.has(gate)) {
      blockers.push(authorityBlocker("GATE_INVALIDATED", [gate]));
      return { gate, status: "invalid" as const };
    }
    const decisions = approvals.filter((approval) => approval.gate === gate);
    if (gate !== "operator") {
      if (decisions.length === 0) {
        blockers.push(authorityBlocker("MISSING_GATE_APPROVAL", [gate]));
        return { gate, status: "pending" as const };
      }
      if (decisions.length > 1) {
        blockers.push(authorityBlocker("DUPLICATE_GATE_APPROVAL", [gate]));
        return { gate, status: "invalid" as const };
      }
      const decision = decisions[0]!;
      if (decision.aircraftId !== undefined) {
        blockers.push(authorityBlocker("INVALID_GATE_AIRCRAFT_SCOPE", [gate, decision.aircraftId]));
        return { gate, status: "invalid" as const };
      }
      return { gate, status: validateDecision(decision, gate, mission.id, mission.evidenceSnapshotId, now, input, blockers) };
    }

    let status: "accepted" | "blocked" | "pending" | "invalid" = "accepted";
    const expectedAircraft = new Set(mission.aircraft.map((aircraft) => aircraft.aircraftId));
    for (const decision of decisions) {
      if (!decision.aircraftId || !expectedAircraft.has(decision.aircraftId)) {
        blockers.push(authorityBlocker("INVALID_OPERATOR_AIRCRAFT_SCOPE", [decision.actorUserId]));
        status = "invalid";
      }
    }
    for (const aircraft of mission.aircraft) {
      const perAircraft = decisions.filter((decision) => decision.aircraftId === aircraft.aircraftId);
      if (perAircraft.length === 0) {
        blockers.push(authorityBlocker("MISSING_OPERATOR_PER_AIRCRAFT", [aircraft.aircraftId]));
        if (status === "accepted") status = "pending";
        continue;
      }
      if (perAircraft.length > 1) {
        blockers.push(authorityBlocker("DUPLICATE_GATE_APPROVAL", [aircraft.aircraftId]));
        status = "invalid";
        continue;
      }
      const decisionStatus = validateDecision(perAircraft[0]!, gate, mission.id, mission.evidenceSnapshotId, now, input, blockers);
      if (decisionStatus === "invalid") status = "invalid";
      else if (decisionStatus === "blocked" && status !== "invalid") status = "blocked";
    }
    return { gate, status };
  });

  const blocked = blockers.length > 0 || gates.some((gate) => gate.status !== "accepted");
  return freeze({ status: blocked ? "blocked" as const : "ready" as const, gates, blockers });
}
