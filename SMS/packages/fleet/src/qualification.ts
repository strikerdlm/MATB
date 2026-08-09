import type { SafetyBlocker } from "@fac-isr/safety-kernel";

export type OperationalCrewStatus = "available" | "restricted" | "unavailable" | "unknown";

export interface DutyPeriod {
  startedAtUtc: string;
  previousDutyEndedAtUtc: string;
  cumulativeWorkloadMinutes: number;
  cumulativeScreenExposureMinutes: number;
  evidenceRefs: readonly string[];
}

export interface DutyPolicy {
  policyId: string;
  edition: string;
  maxDutyMinutes: number;
  minimumRestMinutes: number;
  maxCumulativeWorkloadMinutes: number;
  maxScreenExposureMinutes: number;
  evidenceRefs: readonly string[];
}

export interface DutyEvaluation {
  status: OperationalCrewStatus;
  blockers: readonly SafetyBlocker[];
  evidenceRefs: readonly string[];
}

export type CrewRole = "operator" | "observer" | "maintainer" | "safety" | "commander";

export interface QualificationRecord {
  userId: string;
  role: CrewRole;
  edition: string;
  validUntilUtc: string;
  recencyValidUntilUtc: string;
  evidenceRefs: readonly string[];
}

export interface CrewAssignmentEvaluationInput {
  assignment: {
    userId: string;
    role: CrewRole;
    aircraftId?: string;
    requiredQualificationEdition: string;
    evidenceRefs: readonly string[];
  };
  qualification?: QualificationRecord;
  dutyPeriod?: DutyPeriod;
  dutyPolicy?: DutyPolicy;
  operationalSafetyStatus: OperationalCrewStatus;
  nowUtc: string;
}

export interface CrewEvaluation {
  status: OperationalCrewStatus;
  blockers: readonly SafetyBlocker[];
  evidenceRefs: readonly string[];
}

export interface StaffingAssignment {
  aircraftId: string;
  role: CrewRole;
  userId: string;
  qualified: boolean;
  evidenceRefs?: readonly string[];
}

const statusRank: Record<OperationalCrewStatus, number> = {
  available: 0,
  restricted: 1,
  unknown: 2,
  unavailable: 3,
};

function parseUtc(value: string): number | undefined {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/.exec(value);
  if (!match) return undefined;
  const [, year, month, day, hour, minute, second, fraction = ""] = match;
  const date = new Date(value);
  if (
    !Number.isFinite(date.getTime())
    || date.getUTCFullYear() !== Number(year)
    || date.getUTCMonth() + 1 !== Number(month)
    || date.getUTCDate() !== Number(day)
    || date.getUTCHours() !== Number(hour)
    || date.getUTCMinutes() !== Number(minute)
    || date.getUTCSeconds() !== Number(second)
    || date.getUTCMilliseconds() !== Number(fraction.padEnd(3, "0") || 0)
  ) return undefined;
  return date.getTime();
}

function isFiniteNonnegative(value: number): boolean {
  return Number.isFinite(value) && value >= 0;
}

function isCanonicalIdentifier(value: string): boolean {
  return value !== "" && value === value.trim();
}

function collectEvidence(...groups: readonly (readonly string[])[]): string[] {
  const refs: string[] = [];
  const seen = new Set<string>();
  for (const group of groups) {
    for (const value of group) {
      const ref = value.trim();
      if (ref === "" || seen.has(ref)) continue;
      seen.add(ref);
      refs.push(ref);
    }
  }
  return refs;
}

function createBlocker(
  code: string,
  severity: SafetyBlocker["severity"],
  evidenceRefs: readonly string[],
): SafetyBlocker {
  const key = code.toLowerCase().replaceAll("_", "-");
  return {
    code,
    conceptId: `crew.${key}`,
    severity,
    explanationKey: `crew.${key}`,
    evidenceRefs: collectEvidence(evidenceRefs),
  };
}

function resolveStatus(statuses: readonly OperationalCrewStatus[]): OperationalCrewStatus {
  return statuses.reduce<OperationalCrewStatus>(
    (result, status) => statusRank[status] > statusRank[result] ? status : result,
    "available",
  );
}

const crewRoles: readonly CrewRole[] = ["operator", "observer", "maintainer", "safety", "commander"];

export function evaluateDutyAndRest(
  dutyPeriod: DutyPeriod,
  policy: DutyPolicy,
  nowUtc: string,
): DutyEvaluation {
  const blockers: SafetyBlocker[] = [];
  const statuses: OperationalCrewStatus[] = [];
  const dutyEvidence = collectEvidence(dutyPeriod.evidenceRefs);
  const policyEvidence = collectEvidence(policy.evidenceRefs);
  const evidenceRefs = collectEvidence(dutyEvidence, policyEvidence);
  const startedAt = parseUtc(dutyPeriod.startedAtUtc);
  const previousDutyEndedAt = parseUtc(dutyPeriod.previousDutyEndedAtUtc);
  const now = parseUtc(nowUtc);
  const validPolicyNumbers = [
    policy.maxDutyMinutes,
    policy.minimumRestMinutes,
    policy.maxCumulativeWorkloadMinutes,
    policy.maxScreenExposureMinutes,
  ].every(isFiniteNonnegative);
  const validDutyNumbers = [
    dutyPeriod.cumulativeWorkloadMinutes,
    dutyPeriod.cumulativeScreenExposureMinutes,
  ].every(isFiniteNonnegative);
  const validPolicyIdentity = isCanonicalIdentifier(policy.policyId)
    && isCanonicalIdentifier(policy.edition);
  const usablePolicy = validPolicyIdentity && validPolicyNumbers && policyEvidence.length > 0;
  const usableDutyFacts = validDutyNumbers && dutyEvidence.length > 0;

  if (
    startedAt === undefined
    || previousDutyEndedAt === undefined
    || now === undefined
    || previousDutyEndedAt > startedAt
    || startedAt > now
  ) {
    statuses.push("unknown");
    blockers.push(createBlocker("DUTY_TIME_DATA_INVALID", "data", evidenceRefs));
  }

  if (!validPolicyIdentity || !validPolicyNumbers) {
    statuses.push("unknown");
    blockers.push(createBlocker("DUTY_POLICY_INVALID", "policy", policyEvidence));
  }

  if (!validDutyNumbers) {
    statuses.push("unknown");
    blockers.push(createBlocker("DUTY_DATA_INVALID", "data", dutyEvidence));
  }

  if (dutyEvidence.length === 0 || policyEvidence.length === 0) {
    statuses.push("unknown");
    blockers.push(createBlocker("DUTY_EVIDENCE_REQUIRED", "data", evidenceRefs));
  }

  if (
    startedAt !== undefined
    && now !== undefined
    && startedAt <= now
    && usablePolicy
    && dutyEvidence.length > 0
  ) {
    const dutyMinutes = (now - startedAt) / 60_000;
    if (dutyMinutes > policy.maxDutyMinutes) {
      statuses.push("unavailable");
      blockers.push(createBlocker("DUTY_LIMIT_EXCEEDED", "policy", evidenceRefs));
    }
  }

  if (
    startedAt !== undefined
    && previousDutyEndedAt !== undefined
    && previousDutyEndedAt <= startedAt
    && usablePolicy
    && dutyEvidence.length > 0
  ) {
    const restMinutes = (startedAt - previousDutyEndedAt) / 60_000;
    if (restMinutes < policy.minimumRestMinutes) {
      statuses.push("unavailable");
      blockers.push(createBlocker("MINIMUM_REST_NOT_MET", "policy", evidenceRefs));
    }
  }

  if (usablePolicy && usableDutyFacts) {
    if (dutyPeriod.cumulativeWorkloadMinutes > policy.maxCumulativeWorkloadMinutes) {
      statuses.push("restricted");
      blockers.push(createBlocker("WORKLOAD_LIMIT_EXCEEDED", "policy", evidenceRefs));
    }
    if (dutyPeriod.cumulativeScreenExposureMinutes > policy.maxScreenExposureMinutes) {
      statuses.push("restricted");
      blockers.push(createBlocker("SCREEN_EXPOSURE_LIMIT_EXCEEDED", "policy", evidenceRefs));
    }
  }

  return { status: resolveStatus(statuses), blockers, evidenceRefs };
}

export function evaluateCrewAssignment(input: CrewAssignmentEvaluationInput): CrewEvaluation {
  const blockers: SafetyBlocker[] = [];
  const statuses: OperationalCrewStatus[] = [];
  const assignmentEvidence = collectEvidence(input.assignment.evidenceRefs);
  const qualificationEvidence = collectEvidence(input.qualification?.evidenceRefs ?? []);
  const dutyEvidence = collectEvidence(input.dutyPeriod?.evidenceRefs ?? []);
  const policyEvidence = collectEvidence(input.dutyPolicy?.evidenceRefs ?? []);
  const evidenceRefs = collectEvidence(
    assignmentEvidence,
    qualificationEvidence,
    dutyEvidence,
    policyEvidence,
  );
  const now = parseUtc(input.nowUtc);

  if (
    !isCanonicalIdentifier(input.assignment.userId)
    || !crewRoles.includes(input.assignment.role)
    || !isCanonicalIdentifier(input.assignment.requiredQualificationEdition)
    || (input.assignment.aircraftId !== undefined && !isCanonicalIdentifier(input.assignment.aircraftId))
  ) {
    statuses.push("unknown");
    blockers.push(createBlocker("CREW_ASSIGNMENT_INVALID", "data", assignmentEvidence));
  }

  if (input.assignment.role === "operator" && (input.assignment.aircraftId?.trim() ?? "") === "") {
    statuses.push("unavailable");
    blockers.push(createBlocker("OPERATOR_AIRCRAFT_ASSIGNMENT_REQUIRED", "hard", assignmentEvidence));
  }

  if (assignmentEvidence.length === 0) {
    statuses.push("unknown");
    blockers.push(createBlocker("ASSIGNMENT_EVIDENCE_REQUIRED", "data", assignmentEvidence));
  }

  if (now === undefined) {
    statuses.push("unknown");
    blockers.push(createBlocker("CREW_REFERENCE_TIME_INVALID", "data", evidenceRefs));
  }

  if (input.qualification === undefined) {
    statuses.push("unknown");
    blockers.push(createBlocker("QUALIFICATION_RECORD_MISSING", "data", evidenceRefs));
  } else {
    const qualification = input.qualification;
    if (qualification.userId !== input.assignment.userId) {
      statuses.push("unavailable");
      blockers.push(createBlocker("QUALIFICATION_USER_MISMATCH", "hard", qualificationEvidence));
    }
    if (qualification.role !== input.assignment.role) {
      statuses.push("unavailable");
      blockers.push(createBlocker("QUALIFICATION_ROLE_MISMATCH", "hard", qualificationEvidence));
    }
    if (qualification.edition !== input.assignment.requiredQualificationEdition) {
      statuses.push("unavailable");
      blockers.push(createBlocker("QUALIFICATION_EDITION_STALE", "policy", qualificationEvidence));
    }
    if (qualificationEvidence.length === 0) {
      statuses.push("unknown");
      blockers.push(createBlocker("QUALIFICATION_EVIDENCE_REQUIRED", "data", qualificationEvidence));
    }

    const qualificationValidUntil = parseUtc(qualification.validUntilUtc);
    const recencyValidUntil = parseUtc(qualification.recencyValidUntilUtc);
    if (qualificationValidUntil === undefined || recencyValidUntil === undefined) {
      statuses.push("unknown");
      blockers.push(createBlocker("QUALIFICATION_TIME_DATA_INVALID", "data", qualificationEvidence));
    }
    if (now !== undefined && qualificationValidUntil !== undefined && now >= qualificationValidUntil) {
      statuses.push("unavailable");
      blockers.push(createBlocker("QUALIFICATION_EXPIRED", "policy", qualificationEvidence));
    }
    if (now !== undefined && recencyValidUntil !== undefined && now >= recencyValidUntil) {
      statuses.push("unavailable");
      blockers.push(createBlocker("RECENCY_EXPIRED", "policy", qualificationEvidence));
    }
  }

  if (input.dutyPeriod === undefined || input.dutyPolicy === undefined) {
    statuses.push("unknown");
    blockers.push(createBlocker("DUTY_FACTS_REQUIRED", "data", evidenceRefs));
  } else {
    const duty = evaluateDutyAndRest(input.dutyPeriod, input.dutyPolicy, input.nowUtc);
    statuses.push(duty.status);
    blockers.push(...duty.blockers);
  }

  switch (input.operationalSafetyStatus) {
    case "available":
      break;
    case "restricted":
      statuses.push("restricted");
      blockers.push(createBlocker("OPERATIONAL_SAFETY_STATUS_RESTRICTED", "policy", assignmentEvidence));
      break;
    case "unavailable":
      statuses.push("unavailable");
      blockers.push(createBlocker("OPERATIONAL_SAFETY_STATUS_UNAVAILABLE", "hard", assignmentEvidence));
      break;
    case "unknown":
      statuses.push("unknown");
      blockers.push(createBlocker("OPERATIONAL_SAFETY_STATUS_UNKNOWN", "data", assignmentEvidence));
      break;
    default:
      statuses.push("unknown");
      blockers.push(createBlocker("OPERATIONAL_SAFETY_STATUS_INVALID", "data", assignmentEvidence));
  }

  return { status: resolveStatus(statuses), blockers, evidenceRefs };
}

export function requireOneOperatorPerAircraft(
  assignments: readonly StaffingAssignment[],
  requiredAircraftIds?: readonly string[],
): SafetyBlocker[] {
  const blockers: SafetyBlocker[] = [];
  const validAssignments: StaffingAssignment[] = [];

  for (const assignment of assignments) {
    if (
      !isCanonicalIdentifier(assignment.aircraftId)
      || !isCanonicalIdentifier(assignment.userId)
      || !crewRoles.includes(assignment.role)
    ) {
      blockers.push(createBlocker(
        "CREW_ASSIGNMENT_INVALID",
        "data",
        assignment.evidenceRefs ?? [],
      ));
      continue;
    }
    validAssignments.push(assignment);
  }

  const validRequiredAircraftIds: string[] = [];
  if (requiredAircraftIds !== undefined) {
    for (const aircraftId of requiredAircraftIds) {
      if (!isCanonicalIdentifier(aircraftId)) {
        blockers.push(createBlocker("CREW_ASSIGNMENT_INVALID", "data", []));
      } else {
        validRequiredAircraftIds.push(aircraftId);
      }
    }
  }
  const aircraftIds = [...new Set(
    requiredAircraftIds === undefined
      ? validAssignments.map(({ aircraftId }) => aircraftId)
      : validRequiredAircraftIds,
  )].sort();

  for (const aircraftId of aircraftIds) {
    const aircraftAssignments = validAssignments.filter((assignment) => assignment.aircraftId === aircraftId);
    const operatorAssignments = aircraftAssignments.filter((assignment) => assignment.role === "operator");
    const evidenceRefs = collectEvidence(
      ...aircraftAssignments.map((assignment) => assignment.evidenceRefs ?? []),
    );
    if (operatorAssignments.length === 0) {
      blockers.push(createBlocker("OPERATOR_ASSIGNMENT_MISSING", "hard", evidenceRefs));
    } else if (operatorAssignments.length > 1) {
      blockers.push(createBlocker("MULTIPLE_OPERATORS_ASSIGNED_TO_AIRCRAFT", "hard", evidenceRefs));
    } else if (!operatorAssignments[0].qualified) {
      blockers.push(createBlocker("QUALIFIED_OPERATOR_REQUIRED", "hard", evidenceRefs));
    }
  }

  const operatorUserIds = [...new Set(
    validAssignments
      .filter((assignment) => assignment.role === "operator")
      .map((assignment) => assignment.userId),
  )].sort();

  for (const userId of operatorUserIds) {
    const userAssignments = validAssignments.filter(
      (assignment) => assignment.role === "operator" && assignment.userId === userId,
    );
    const assignedAircraftIds = new Set(userAssignments.map(({ aircraftId }) => aircraftId));
    if (assignedAircraftIds.size > 1) {
      blockers.push(createBlocker(
        "OPERATOR_ASSIGNED_TO_MULTIPLE_AIRCRAFT",
        "hard",
        collectEvidence(...userAssignments.map((assignment) => assignment.evidenceRefs ?? [])),
      ));
    }
  }

  return blockers;
}
