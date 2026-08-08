import { invalidateForChange } from "./dependencies.js";
import { createTransitionResult, parseMissionRevision, type GateApproval, type GateName, type MissionRevision, type MissionRevisionChange, type MissionState, type TransitionInput, type TransitionResult } from "./types.js";

const GATE_ORDER: readonly GateName[] = ["maintenance", "operator", "safety", "commander"];
const UTC_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/;

const TRANSITIONS: Readonly<Record<MissionState, Readonly<Partial<Record<TransitionInput["event"], MissionState>>>>> = {
  Draft: { plan: "Planned", abort: "Aborted" },
  Planned: { "submit-review": "UnderReview", abort: "Aborted" },
  UnderReview: { "gates-complete": "ReadyForRelease", abort: "Aborted" },
  ReadyForRelease: { release: "Released", abort: "Aborted" },
  Released: { activate: "Active", abort: "Aborted" },
  Active: { complete: "Completed", suspend: "Suspended", abort: "Aborted" },
  Completed: { "post-flight": "PostFlightReview" },
  Suspended: { activate: "Active", abort: "Aborted" },
  Aborted: {},
  PostFlightReview: { close: "Closed" },
  Closed: {},
};

function assertUtc(value: string): void {
  const match = UTC_PATTERN.exec(value);
  if (!match) throw new RangeError("timestamp must be a valid UTC ISO-8601 instant");
  const [, year, month, day, hour, minute, second, fraction = ""] = match;
  const instant = Date.parse(value);
  const date = new Date(instant);
  if (!Number.isFinite(instant)
    || date.getUTCFullYear() !== Number(year)
    || date.getUTCMonth() + 1 !== Number(month)
    || date.getUTCDate() !== Number(day)
    || date.getUTCHours() !== Number(hour)
    || date.getUTCMinutes() !== Number(minute)
    || date.getUTCSeconds() !== Number(second)
    || date.getUTCMilliseconds() !== Number(fraction.padEnd(3, "0") || 0)) {
    throw new RangeError("timestamp must be a valid UTC ISO-8601 instant");
  }
}

function hasFourAcceptedGates(approvals: readonly GateApproval[] | undefined): boolean {
  if (!approvals) return false;
  return GATE_ORDER.every((gate) => approvals.filter((approval) => approval.gate === gate).length === 1
    && approvals.some((approval) => approval.gate === gate && approval.decision === "accept" && approval.valid));
}

function assertReleaseReady(input: TransitionInput): void {
  if (!input.evaluation || input.evaluation.status !== "ready" || input.evaluation.blockers.length > 0) {
    throw new RangeError("unresolved blocker prevents release transition");
  }
  if (input.evaluation.invalidatedGates.length > 0 || !hasFourAcceptedGates(input.approvals)) {
    throw new RangeError("four valid accepted gates are required for release transition");
  }
}

/** Applies the finite-state lifecycle without clocks, storage, or implicit approval state. */
export function transitionMission(input: TransitionInput): TransitionResult {
  assertUtc(input.nowUtc);
  if (input.actor.userId.trim().length === 0) throw new RangeError("transition actor user ID must not be empty");
  const state = TRANSITIONS[input.current][input.event];
  if (!state) throw new RangeError(`gate-controlled transition ${input.event} is not permitted from ${input.current}`);
  if (input.event === "gates-complete" || input.event === "release" || input.event === "activate") assertReleaseReady(input);
  return createTransitionResult({
    state,
    auditEvent: { type: `mission.${input.event}`, actorUserId: input.actor.userId, occurredAtUtc: input.nowUtc },
  });
}

type RevisionProperty = "aircraft" | "crew" | "route" | "visualCondition" | "riskAssessment" | "policyPackageId" | "evidenceSnapshotId" | "dataSnapshots";

const REVISION_PROPERTIES: Readonly<Partial<Record<MissionRevisionChange["field"], RevisionProperty>>> = {
  aircraft: "aircraft",
  crew: "crew",
  route: "route",
  "visual-condition": "visualCondition",
  risk: "riskAssessment",
  mitigation: "riskAssessment",
  exception: "riskAssessment",
  policy: "policyPackageId",
  evidence: "evidenceSnapshotId",
  weather: "dataSnapshots",
  notam: "dataSnapshots",
  aip: "dataSnapshots",
};

/**
 * Produces a distinct, validated revision. Only facts represented by the strict
 * MissionRevision contract can be changed here; callers must not drop other
 * material facts through an unmodelled patch.
 */
export function createMissionRevision(mission: MissionRevision, change: MissionRevisionChange): MissionRevision {
  const property = REVISION_PROPERTIES[change.field];
  if (!property) throw new RangeError(`mission revision cannot represent material field ${change.field}`);
  const invalidation = invalidateForChange({ mission, ...change, dependencyGraph: { entries: [] } });
  if (!invalidation.material) return parseMissionRevision({ ...mission, revision: mission.revision + 1, id: `${mission.id}:r${mission.revision + 1}` });
  const currentValue = (mission as unknown as Record<RevisionProperty, unknown>)[property];
  const previousMatches = !invalidateForChange({
    mission,
    field: change.field,
    previous: currentValue,
    next: change.previous,
    dependencyGraph: { entries: [] },
  }).material;
  if (!previousMatches) {
    throw new RangeError(`previous ${change.field} value does not match the mission revision`);
  }
  return parseMissionRevision({
    ...mission,
    id: `${mission.id}:r${mission.revision + 1}`,
    revision: mission.revision + 1,
    state: "Planned",
    [property]: change.next,
  });
}
