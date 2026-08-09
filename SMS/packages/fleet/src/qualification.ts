import type { CrewAssignment, SafetyBlocker } from "@fac-isr/safety-kernel";

export type CrewAvailability = "available" | "restricted" | "unavailable" | "unknown";
export type SelfDeclaredSafetyStatus = "able" | "not-able" | "not-recorded";

export interface QualificationRecord {
  id: string;
  edition: string;
  validFromUtc: string;
  expiresAtUtc: string;
  evidenceRefs: readonly string[];
}

export interface RecencyRecord {
  validUntilUtc: string;
  evidenceRefs: readonly string[];
  current?: boolean;
}

export interface DutyPeriod {
  id: string;
  userId: string;
  startUtc: string;
  endUtc?: string;
  priorDutyEndUtc?: string;
  cumulativeDutyMinutes?: number;
  cumulativeWorkloadMinutes?: number;
  screenExposureMinutes?: number;
  selfDeclaredSafetyStatus?: SelfDeclaredSafetyStatus;
  evidenceRefs: readonly string[];
}

export interface DutyPolicy {
  maxDutyMinutes: number;
  minimumRestMinutes: number;
  maxCumulativeWorkloadMinutes?: number;
  maxScreenExposureMinutes?: number;
  requireSafetyDeclaration?: boolean;
  evidenceRefs: readonly string[];
}

export interface CrewAssignmentInput {
  userId: string;
  aircraftId: string;
  role: CrewAssignment["role"];
  nowUtc: string;
  requiredQualificationEdition?: string;
  qualification: QualificationRecord;
  recency: RecencyRecord;
  dutyPeriod: DutyPeriod;
  dutyPolicy: DutyPolicy;
  evidenceRefs: readonly string[];
}

export interface CrewEvaluation {
  status: CrewAvailability;
  blockers: readonly string[];
  evidenceRefs: readonly string[];
}

export interface DutyEvaluation {
  status: CrewAvailability;
  reason: string;
  blockers: readonly string[];
  evidenceRefs: readonly string[];
}

export interface StaffingAssignment {
  aircraftId: string;
  role: CrewAssignment["role"];
  userId: string;
  qualified?: boolean;
  recencyCurrent?: boolean;
  dutyStatus?: CrewAssignment["dutyStatus"];
  evidenceRefs?: readonly string[];
}

const UTC_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/;
const CREW_ROLES = new Set<CrewAssignment["role"]>(["operator", "observer", "maintainer", "safety", "commander"]);

function parseUtc(value: unknown): number | undefined {
  if (typeof value !== "string") return undefined;
  const match = UTC_PATTERN.exec(value);
  if (!match) return undefined;
  const [, year, month, day, hour, minute, second, fraction = ""] = match;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return undefined;
  if (date.getUTCFullYear() !== Number(year)
    || date.getUTCMonth() + 1 !== Number(month)
    || date.getUTCDate() !== Number(day)
    || date.getUTCHours() !== Number(hour)
    || date.getUTCMinutes() !== Number(minute)
    || date.getUTCSeconds() !== Number(second)
    || date.getUTCMilliseconds() !== Number(fraction.padEnd(3, "0") || 0)) return undefined;
  return date.getTime();
}

function finiteNonnegative(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function nonempty(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function refsFrom(...sources: readonly (readonly string[] | undefined)[]): string[] {
  const refs: string[] = [];
  for (const source of sources) {
    for (const ref of source ?? []) {
      if (nonempty(ref) && !refs.includes(ref)) refs.push(ref);
    }
  }
  return refs;
}

function validRefs(value: unknown): value is readonly string[] {
  return Array.isArray(value) && value.length > 0 && value.every(nonempty);
}

function unknownDuty(reason: string, evidenceRefs: readonly string[] = []): DutyEvaluation {
  return { status: "unknown", reason, blockers: [reason], evidenceRefs: refsFrom(evidenceRefs) };
}

function dutyResult(
  status: CrewAvailability,
  blockers: readonly string[],
  evidenceRefs: readonly string[],
): DutyEvaluation {
  return {
    status,
    reason: blockers[0] ?? "DUTY_WITHIN_POLICY",
    blockers,
    evidenceRefs: refsFrom(evidenceRefs),
  };
}

export function evaluateDutyAndRest(
  dutyPeriod: DutyPeriod,
  policy: DutyPolicy,
  nowUtc: string,
): DutyEvaluation {
  const evidenceRefs = refsFrom(dutyPeriod.evidenceRefs, policy.evidenceRefs);
  const now = parseUtc(nowUtc);
  const start = parseUtc(dutyPeriod.startUtc);
  if (now === undefined || start === undefined) return unknownDuty("DUTY_TIMESTAMP_INVALID", evidenceRefs);
  if (!nonempty(dutyPeriod.id) || !nonempty(dutyPeriod.userId)) return unknownDuty("DUTY_ID_INVALID", evidenceRefs);
  if (!validRefs(dutyPeriod.evidenceRefs) || !validRefs(policy.evidenceRefs)) return unknownDuty("DUTY_EVIDENCE_REQUIRED", evidenceRefs);
  if (!finiteNonnegative(policy.maxDutyMinutes) || policy.maxDutyMinutes <= 0 || !finiteNonnegative(policy.minimumRestMinutes)) {
    return unknownDuty("DUTY_POLICY_INVALID", evidenceRefs);
  }
  if (policy.maxCumulativeWorkloadMinutes !== undefined && !finiteNonnegative(policy.maxCumulativeWorkloadMinutes)) {
    return unknownDuty("WORKLOAD_POLICY_INVALID", evidenceRefs);
  }
  if (policy.maxScreenExposureMinutes !== undefined && !finiteNonnegative(policy.maxScreenExposureMinutes)) {
    return unknownDuty("SCREEN_POLICY_INVALID", evidenceRefs);
  }
  if (now < start) return unknownDuty("DUTY_NOT_STARTED", evidenceRefs);

  const end = dutyPeriod.endUtc === undefined ? undefined : parseUtc(dutyPeriod.endUtc);
  if (dutyPeriod.endUtc !== undefined && end === undefined) return unknownDuty("DUTY_TIMESTAMP_INVALID", evidenceRefs);
  if (end !== undefined && end <= start) return unknownDuty("DUTY_INTERVAL_INVALID", evidenceRefs);

  const blockers: string[] = [];
  const dutyMinutes = (now - start) / 60_000;
  if (dutyMinutes >= policy.maxDutyMinutes) blockers.push("DUTY_LIMIT_EXCEEDED");
  if (end !== undefined && now >= end) blockers.push("DUTY_PERIOD_ENDED");

  if (dutyPeriod.priorDutyEndUtc !== undefined) {
    const priorEnd = parseUtc(dutyPeriod.priorDutyEndUtc);
    if (priorEnd === undefined || priorEnd > start) return unknownDuty("REST_TIMESTAMP_INVALID", evidenceRefs);
    const restMinutes = (start - priorEnd) / 60_000;
    if (restMinutes < policy.minimumRestMinutes) blockers.push("MINIMUM_REST_NOT_MET");
  }

  if (dutyPeriod.cumulativeDutyMinutes !== undefined && !finiteNonnegative(dutyPeriod.cumulativeDutyMinutes)) {
    return unknownDuty("DUTY_TOTAL_INVALID", evidenceRefs);
  }
  if (dutyPeriod.cumulativeWorkloadMinutes !== undefined && !finiteNonnegative(dutyPeriod.cumulativeWorkloadMinutes)) {
    return unknownDuty("WORKLOAD_TOTAL_INVALID", evidenceRefs);
  }
  if (dutyPeriod.screenExposureMinutes !== undefined && !finiteNonnegative(dutyPeriod.screenExposureMinutes)) {
    return unknownDuty("SCREEN_TOTAL_INVALID", evidenceRefs);
  }
  if (policy.maxCumulativeWorkloadMinutes !== undefined
    && dutyPeriod.cumulativeWorkloadMinutes !== undefined
    && dutyPeriod.cumulativeWorkloadMinutes > policy.maxCumulativeWorkloadMinutes) {
    blockers.push("CUMULATIVE_WORKLOAD_LIMIT_EXCEEDED");
  }
  if (policy.maxScreenExposureMinutes !== undefined
    && dutyPeriod.screenExposureMinutes !== undefined
    && dutyPeriod.screenExposureMinutes > policy.maxScreenExposureMinutes) {
    blockers.push("SCREEN_EXPOSURE_LIMIT_EXCEEDED");
  }

  const safetyStatus = dutyPeriod.selfDeclaredSafetyStatus ?? "not-recorded";
  if (safetyStatus === "not-able") blockers.push("SAFETY_SELF_DECLARATION_NOT_ABLE");
  if (policy.requireSafetyDeclaration && safetyStatus === "not-recorded") blockers.push("SAFETY_SELF_DECLARATION_REQUIRED");

  if (blockers.some((code) => code === "DUTY_LIMIT_EXCEEDED" || code === "DUTY_PERIOD_ENDED" || code === "SAFETY_SELF_DECLARATION_NOT_ABLE")) {
    return dutyResult("unavailable", blockers, evidenceRefs);
  }
  if (blockers.length > 0) return dutyResult("restricted", blockers, evidenceRefs);
  return dutyResult("available", [], evidenceRefs);
}

function evaluateQualification(input: CrewAssignmentInput): { status: CrewAvailability; blockers: string[] } {
  const now = parseUtc(input.nowUtc);
  const validFrom = parseUtc(input.qualification.validFromUtc);
  const expires = parseUtc(input.qualification.expiresAtUtc);
  const recencyUntil = parseUtc(input.recency.validUntilUtc);
  if (now === undefined || validFrom === undefined || expires === undefined || recencyUntil === undefined) {
    return { status: "unknown", blockers: ["QUALIFICATION_TIMESTAMP_INVALID"] };
  }
  if (!nonempty(input.qualification.id) || !nonempty(input.qualification.edition)) {
    return { status: "unknown", blockers: ["QUALIFICATION_ID_INVALID"] };
  }
  if (!validRefs(input.qualification.evidenceRefs) || !validRefs(input.recency.evidenceRefs)) {
    return { status: "unknown", blockers: ["QUALIFICATION_EVIDENCE_REQUIRED"] };
  }
  if (expires <= validFrom || now < validFrom) return { status: "unavailable", blockers: ["QUALIFICATION_NOT_CURRENT"] };
  if (now >= expires) return { status: "unavailable", blockers: ["QUALIFICATION_EXPIRED"] };
  if (input.requiredQualificationEdition !== undefined
    && input.requiredQualificationEdition !== input.qualification.edition) {
    return { status: "unavailable", blockers: ["QUALIFICATION_EDITION_MISMATCH"] };
  }
  if (input.recency.current === false || now >= recencyUntil) {
    return { status: "unavailable", blockers: [input.recency.current === false ? "RECENCY_NOT_CURRENT" : "RECENCY_EXPIRED"] };
  }
  return { status: "available", blockers: [] };
}

export function evaluateCrewAssignment(input: CrewAssignmentInput): CrewEvaluation {
  const evidenceRefs = refsFrom(
    input.evidenceRefs,
    input.qualification?.evidenceRefs,
    input.recency?.evidenceRefs,
    input.dutyPeriod?.evidenceRefs,
    input.dutyPolicy?.evidenceRefs,
  );
  if (!nonempty(input.userId) || !nonempty(input.aircraftId) || !CREW_ROLES.has(input.role) || !validRefs(input.evidenceRefs)) {
    return { status: "unknown", blockers: ["CREW_ASSIGNMENT_DATA_INVALID"], evidenceRefs };
  }
  if (input.role !== "operator") return { status: "unavailable", blockers: ["CREW_ROLE_NOT_OPERATOR"], evidenceRefs };
  if (input.dutyPeriod.userId !== input.userId) return { status: "unavailable", blockers: ["DUTY_USER_MISMATCH"], evidenceRefs };

  const qualification = evaluateQualification(input);
  if (qualification.status === "unknown") return { status: "unknown", blockers: qualification.blockers, evidenceRefs };

  const duty = evaluateDutyAndRest(input.dutyPeriod, input.dutyPolicy, input.nowUtc);
  const blockers = [...qualification.blockers, ...duty.blockers];
  const statuses: CrewAvailability[] = [qualification.status, duty.status];
  if (statuses.includes("unknown")) return { status: "unknown", blockers, evidenceRefs };
  if (statuses.includes("unavailable")) return { status: "unavailable", blockers, evidenceRefs };
  if (statuses.includes("restricted")) return { status: "restricted", blockers, evidenceRefs };
  return { status: "available", blockers, evidenceRefs };
}

function staffingBlocker(code: string, evidenceRefs: readonly string[]): SafetyBlocker {
  return {
    code,
    conceptId: "crew.assignment",
    severity: "hard",
    explanationKey: `crew.${code.toLowerCase()}`,
    evidenceRefs: refsFrom(evidenceRefs),
  };
}

function isEligibleOperator(assignment: StaffingAssignment): boolean {
  return assignment.role === "operator"
    && assignment.qualified !== false
    && assignment.recencyCurrent !== false
    && (assignment.dutyStatus === undefined || assignment.dutyStatus === "available");
}

export function requireOneOperatorPerAircraft(assignments: readonly StaffingAssignment[]): SafetyBlocker[] {
  const aircraftIds: string[] = [];
  const operatorsByUser = new Map<string, Set<string>>();
  const byAircraft = new Map<string, StaffingAssignment[]>();
  for (const assignment of assignments) {
    if (!nonempty(assignment.aircraftId) || !nonempty(assignment.userId)) continue;
    if (!aircraftIds.includes(assignment.aircraftId)) aircraftIds.push(assignment.aircraftId);
    const aircraftAssignments = byAircraft.get(assignment.aircraftId) ?? [];
    aircraftAssignments.push(assignment);
    byAircraft.set(assignment.aircraftId, aircraftAssignments);
    if (assignment.role === "operator") {
      const assignedAircraft = operatorsByUser.get(assignment.userId) ?? new Set<string>();
      assignedAircraft.add(assignment.aircraftId);
      operatorsByUser.set(assignment.userId, assignedAircraft);
    }
  }

  const blockers: SafetyBlocker[] = [];
  const assignmentRefs = assignments.flatMap((assignment) => assignment.evidenceRefs ?? []);
  for (const assignedAircraft of operatorsByUser.values()) {
    if (assignedAircraft.size > 1) blockers.push(staffingBlocker("OPERATOR_ASSIGNED_TO_MULTIPLE_AIRCRAFT", assignmentRefs));
  }
  for (const aircraftId of aircraftIds) {
    const operators = (byAircraft.get(aircraftId) ?? []).filter((assignment) => assignment.role === "operator");
    const eligible = operators.filter(isEligibleOperator);
    if (eligible.length === 0) {
      blockers.push(staffingBlocker(
        operators.length === 0 ? "MISSING_OPERATOR_PER_AIRCRAFT" : "OPERATOR_NOT_AVAILABLE",
        operators.flatMap((assignment) => assignment.evidenceRefs ?? []),
      ));
    } else if (eligible.length > 1) {
      blockers.push(staffingBlocker("MULTIPLE_OPERATORS_PER_AIRCRAFT", eligible.flatMap((assignment) => assignment.evidenceRefs ?? [])));
    }
  }
  return blockers;
}
