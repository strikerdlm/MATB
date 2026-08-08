import { sameMissionFact } from "./dependencies.js";
import {
  createTransitionResult,
  parseMissionRevision,
  type GateApproval,
  type GateName,
  type MissionRevision,
  type MissionRevisionChange,
  type MissionState,
  type OperationalDataSnapshot,
  type OperationalSnapshotKind,
  type TransitionInput,
  type TransitionResult,
} from "./types.js";

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

function daysInMonth(year: number, month: number): number {
  if (month === 2) return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0) ? 29 : 28;
  return [4, 6, 9, 11].includes(month) ? 30 : 31;
}

/** Validates the supplied deterministic UTC fact without consulting a clock. */
function assertUtc(value: string): void {
  const match = UTC_PATTERN.exec(value);
  if (!match) throw new RangeError("timestamp must be a valid UTC ISO-8601 instant");
  const [, yearText, monthText, dayText, hourText, minuteText, secondText] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  if (month < 1 || month > 12 || day < 1 || day > daysInMonth(year, month)
    || hour > 23 || minute > 59 || second > 59) {
    throw new RangeError("timestamp must be a valid UTC ISO-8601 instant");
  }
}

function hasFourAcceptedGates(approvals: readonly GateApproval[] | undefined): boolean {
  if (!approvals) return false;
  return GATE_ORDER.every((gate) => approvals.filter((approval) => approval.gate === gate).length === 1
    && approvals.some((approval) => approval.gate === gate && approval.decision === "accept" && approval.valid));
}

function assertReleaseReady(input: TransitionInput): void {
  if (!input.evaluation) throw new RangeError("release transition requires an evaluation");
  if (input.evaluation.missionRevisionId !== input.missionRevisionId) {
    throw new RangeError("evaluation revision does not match the transition target revision");
  }
  if (!input.approvals || input.approvals.some((approval) => approval.missionRevisionId !== input.missionRevisionId)) {
    throw new RangeError("gate approval revision does not match the transition target revision");
  }
  if (input.evaluation.status !== "ready" || input.evaluation.blockers.length > 0) {
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
  if (input.missionRevisionId.trim().length === 0) throw new RangeError("transition mission revision ID must not be empty");
  const state = TRANSITIONS[input.current][input.event];
  if (!state) throw new RangeError(`gate-controlled transition ${input.event} is not permitted from ${input.current}`);
  if (input.event === "gates-complete" || input.event === "release" || input.event === "activate") assertReleaseReady(input);
  return createTransitionResult({
    state,
    auditEvent: { type: `mission.${input.event}`, missionRevisionId: input.missionRevisionId, actorUserId: input.actor.userId, occurredAtUtc: input.nowUtc },
  });
}

function revisionIdentity(mission: MissionRevision): Pick<MissionRevision, "id" | "revision"> {
  const revision = mission.revision + 1;
  return { id: `${mission.id}:r${revision}`, revision };
}

function revisionFor<T>(
  mission: MissionRevision,
  change: Readonly<{ field: MissionRevisionChange["field"]; previous: T; next: T }>,
  current: T,
  update: (next: T) => Partial<MissionRevision>,
): MissionRevision {
  if (!sameMissionFact(current, change.previous)) {
    throw new RangeError(`previous ${change.field} value does not match the mission revision`);
  }
  const changed = !sameMissionFact(current, change.next);
  return parseMissionRevision({
    ...mission,
    ...revisionIdentity(mission),
    ...(changed ? { state: "Planned" as const } : {}),
    ...update(change.next),
  });
}

function snapshotForKind<K extends OperationalSnapshotKind>(mission: MissionRevision, kind: K): OperationalDataSnapshot<K> | undefined {
  const matches = mission.dataSnapshots.filter((snapshot) => snapshot.kind === kind);
  if (matches.length > 1) throw new RangeError(`mission revision has multiple ${kind} snapshots`);
  return matches[0] as OperationalDataSnapshot<K> | undefined;
}

function replaceSnapshot<K extends OperationalSnapshotKind>(
  mission: MissionRevision,
  kind: K,
  next: OperationalDataSnapshot<K> | undefined,
): readonly MissionRevision["dataSnapshots"][number][] {
  const otherSnapshots = mission.dataSnapshots.filter((snapshot) => snapshot.kind !== kind);
  return next ? [...otherSnapshots, next] : otherSnapshots;
}

/**
 * Produces a distinct, validated revision for every explicitly modelled material
 * fact. A changed material fact always returns to Planned, so no release approval
 * can survive into the new revision.
 */
export function createMissionRevision(mission: MissionRevision, change: MissionRevisionChange): MissionRevision {
  switch (change.field) {
    case "aircraft": return revisionFor(mission, change, mission.aircraft, (next) => ({ aircraft: next }));
    case "gcs": return revisionFor(mission, change, mission.gcs, (next) => ({ gcs: next }));
    case "payload": return revisionFor(mission, change, mission.payload, (next) => ({ payload: next }));
    case "battery": return revisionFor(mission, change, mission.battery, (next) => ({ battery: next }));
    case "software": return revisionFor(mission, change, mission.software, (next) => ({ software: next }));
    case "crew": return revisionFor(mission, change, mission.crew, (next) => ({ crew: next }));
    case "route": return revisionFor(mission, change, mission.route, (next) => ({ route: next }));
    case "altitude": return revisionFor(mission, change, mission.altitude, (next) => ({ altitude: next }));
    case "visual-condition": return revisionFor(mission, change, mission.visualCondition, (next) => ({ visualCondition: next }));
    case "schedule": return revisionFor(mission, change, mission.schedule, (next) => ({ schedule: next }));
    case "weather": return revisionFor(mission, change, snapshotForKind(mission, "weather"), (next) => ({ dataSnapshots: replaceSnapshot(mission, "weather", next) }));
    case "notam": return revisionFor(mission, change, snapshotForKind(mission, "notam"), (next) => ({ dataSnapshots: replaceSnapshot(mission, "notam", next) }));
    case "aip": return revisionFor(mission, change, snapshotForKind(mission, "aip"), (next) => ({ dataSnapshots: replaceSnapshot(mission, "aip", next) }));
    case "risk": return revisionFor(mission, change, mission.riskAssessment, (next) => ({ riskAssessment: next }));
    case "mitigation": return revisionFor(mission, change, mission.riskAssessment, (next) => ({ riskAssessment: next }));
    case "exception": return revisionFor(mission, change, mission.riskAssessment, (next) => ({ riskAssessment: next }));
    case "policy": return revisionFor(mission, change, mission.policyPackageId, (next) => ({ policyPackageId: next }));
    case "evidence": return revisionFor(mission, change, mission.evidenceSnapshotId, (next) => ({ evidenceSnapshotId: next }));
    case "display-note": throw new RangeError("display-note is non-material and is not stored in a mission revision");
  }
}
