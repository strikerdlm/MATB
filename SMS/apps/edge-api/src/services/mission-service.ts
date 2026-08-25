import {
  createMissionRevision,
  evaluateFourGates,
  parseGateApproval,
  parseMissionRevision,
  parseSafetyEvaluationResult,
  type GateApproval,
  type GateActorRole,
  type GateName,
  type MissionRevision,
  type MissionRevisionChange,
  type SafetyEvaluationResult,
} from "@fac-isr/safety-kernel";
import type { EdgeDatabase } from "../db/migrate.js";
import { AuditLedger } from "../audit/ledger.js";

const GATES: readonly GateName[] = ["maintenance", "operator", "safety", "commander"];
const ROLE_BY_GATE: Readonly<Record<GateName, GateActorRole>> = {
  maintenance: "maintainer",
  operator: "operator",
  safety: "safety",
  commander: "commander",
};
const UTC_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/;

export interface ChecklistResponse {
  readonly responseId: string;
  readonly revisionId: string;
  readonly itemId: string;
  readonly response: string;
  readonly actorUserId: string;
  readonly occurredAtUtc: string;
  readonly evidenceRef?: string;
  readonly reason?: string;
}

export interface GateApprovalRecord extends GateApproval {
  readonly checklistResponseIds: readonly string[];
}

export interface PostflightRecord {
  readonly revisionId: string;
  readonly recordedAtUtc: string;
  readonly recovery: Record<string, unknown>;
  readonly battery: Record<string, unknown>;
  readonly telemetry: Record<string, unknown>;
  readonly debrief: Record<string, unknown>;
}

export interface OccurrenceRecord {
  readonly revisionId: string;
  readonly occurrenceId: string;
  readonly screenedAtUtc: string;
  readonly reportable: boolean;
  readonly disposition: string;
  readonly details?: string;
}

interface StoredMission {
  readonly missionId: string;
  revisions: MissionRevision[];
  safetyResults: SafetyEvaluationResult[];
  checklistResponses: ChecklistResponse[];
  approvals: GateApprovalRecord[];
  postflight?: PostflightRecord;
  occurrences: OccurrenceRecord[];
}

export interface MissionServiceOptions {
  readonly auditLedger?: AuditLedger;
  readonly database?: EdgeDatabase;
  readonly now?: () => string;
}

export interface ServiceActorContext {
  readonly actorUserId: string;
  readonly clientSessionId: string;
  readonly occurredAtUtc: string;
}

export interface GateActorContext extends ServiceActorContext {
  readonly actorRole: GateActorRole;
}

export class MissionServiceError extends Error {
  public constructor(
    public readonly statusCode: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "MissionServiceError";
  }
}

export class MissionService {
  private readonly missions = new Map<string, StoredMission>();
  private readonly audit: AuditLedger;
  private readonly database?: EdgeDatabase;
  private readonly now: () => string;

  public constructor(options: MissionServiceOptions = {}) {
    this.audit = options.auditLedger ?? new AuditLedger({ database: options.database });
    this.database = options.database;
    this.now = options.now ?? (() => new Date().toISOString());
    this.load();
  }

  public async createMission(input: unknown, context: ServiceActorContext): Promise<MissionRevision> {
    const envelope = objectInput(input);
    const rawRevision = isObject(envelope.revision)
      ? envelope.revision
      : isObject(envelope.mission)
        ? envelope.mission
        : input;
    const revision = this.parseMission(rawRevision);
    if (revision.revision !== 0 || revision.state !== "Draft") {
      throw new MissionServiceError(400, "INVALID_INITIAL_REVISION", "missions must start at Draft revision zero");
    }
    if (this.missions.has(revision.missionId)) {
      throw new MissionServiceError(409, "MISSION_ALREADY_EXISTS", "mission already exists");
    }
    const safetyResult = envelope.safetyResult === undefined
      ? undefined
      : this.parseSafety(envelope.safetyResult, revision.id);
    const stored: StoredMission = {
      missionId: revision.missionId,
      revisions: [revision],
      safetyResults: safetyResult === undefined ? [] : [safetyResult],
      checklistResponses: [],
      approvals: [],
      occurrences: [],
    };
    await this.appendAudit({
      type: "mission.created",
      action: "create",
      reason: "mission revision created",
      actorUserId: context.actorUserId,
      missionRevisionId: revision.id,
      clientSessionId: context.clientSessionId,
      occurredAtUtc: this.timestamp(context.occurredAtUtc),
      payload: { missionId: revision.missionId, revision: revision.revision },
    });
    this.missions.set(revision.missionId, stored);
    this.persist();
    return revision;
  }

  public getMission(missionId: string): Record<string, unknown> {
    const stored = this.requireMission(missionId);
    const currentRevision = stored.revisions.at(-1)!;
    return {
      missionId: stored.missionId,
      currentRevisionId: currentRevision.id,
      currentRevision,
      revisions: [...stored.revisions],
      safetyResults: [...stored.safetyResults],
      checklistResponses: [...stored.checklistResponses],
      gateApprovals: [...stored.approvals],
      postflight: stored.postflight,
      occurrences: [...stored.occurrences],
    };
  }

  public missionIdForRevision(revisionId: string): string {
    return this.requireRevision(revisionId).stored.missionId;
  }

  public async createRevision(missionId: string, input: unknown, context: ServiceActorContext): Promise<MissionRevision> {
    const stored = this.requireMission(missionId);
    const current = stored.revisions.at(-1)!;
    const envelope = objectInput(input);
    const expectedRevisionId = envelope.expectedRevisionId ?? envelope.revisionId;
    if (expectedRevisionId !== undefined && expectedRevisionId !== current.id) {
      throw new MissionServiceError(409, "STALE_REVISION", "mission revision has changed");
    }
    if (envelope.expectedRevision !== undefined) {
      if (typeof envelope.expectedRevision !== "number" || !Number.isInteger(envelope.expectedRevision)) {
        throw new MissionServiceError(400, "INVALID_EXPECTED_REVISION", "expectedRevision must be an integer");
      }
      if (envelope.expectedRevision !== current.revision) throw new MissionServiceError(409, "STALE_REVISION", "mission revision has changed");
    }

    let next: MissionRevision;
    if (envelope.revision !== undefined || envelope.missionRevision !== undefined) {
      const candidate = this.parseMission(envelope.revision ?? envelope.missionRevision);
      if (candidate.missionId !== missionId || candidate.revision !== current.revision + 1) {
        throw new MissionServiceError(409, "REVISION_CONFLICT", "revision identity does not follow the current mission");
      }
      if (["ReadyForRelease", "Released", "Active", "Completed", "PostFlightReview", "Closed"].includes(candidate.state)) {
        throw new MissionServiceError(400, "INVALID_REVISION_STATE", "clients cannot set a release or post-flight state directly");
      }
      next = this.parseMission({ ...candidate, state: "Planned" });
    } else {
      const change = envelope.change;
      if (change === undefined) throw new MissionServiceError(400, "REVISION_CHANGE_REQUIRED", "revision change is required");
      try {
        const generated = createMissionRevision(current, change as MissionRevisionChange);
        next = this.parseMission({ ...generated, id: `${missionId}:r${current.revision + 1}` });
      } catch (error) {
        throw new MissionServiceError(400, "INVALID_REVISION_CHANGE", errorMessage(error));
      }
    }

    const safetyResult = envelope.safetyResult === undefined
      ? undefined
      : this.parseSafety(envelope.safetyResult, next.id);
    const invalidated = stored.approvals.filter((approval) => approval.missionRevisionId === current.id);
    for (const approval of invalidated) {
      await this.appendAudit({
        type: "gate.invalidated",
        action: "invalidate",
        reason: "material mission revision invalidated the prior approval",
        actorUserId: context.actorUserId,
        missionRevisionId: current.id,
        clientSessionId: context.clientSessionId,
        occurredAtUtc: this.timestamp(context.occurredAtUtc),
        payload: { gate: approval.gate, priorApprovalId: `${approval.gate}:${approval.actorUserId}` },
      });
    }
    await this.appendAudit({
      type: "mission.revised",
      action: "revise",
      reason: "material mission fact changed",
      actorUserId: context.actorUserId,
      missionRevisionId: next.id,
      clientSessionId: context.clientSessionId,
      occurredAtUtc: this.timestamp(context.occurredAtUtc),
      payload: { previousRevisionId: current.id, revision: next.revision },
    });

    stored.revisions.push(next);
    stored.approvals = stored.approvals.filter((approval) => approval.missionRevisionId !== current.id);
    stored.checklistResponses = stored.checklistResponses.filter((response) => response.revisionId !== current.id);
    stored.safetyResults = stored.safetyResults.filter((result) => result.missionRevisionId !== current.id);
    if (safetyResult !== undefined) stored.safetyResults.push(safetyResult);
    this.persist();
    return next;
  }

  public async recordChecklistResponse(revisionId: string, input: unknown, context: ServiceActorContext): Promise<ChecklistResponse> {
    const envelope = objectInput(input);
    const stored = this.requireRevision(revisionId).stored;
    if (envelope.checkAll === true) {
      throw new MissionServiceError(400, "BULK_CHECKLIST_FORBIDDEN", "checklist responses must be recorded one item at a time");
    }
    const responseId = required(envelope.responseId, "responseId");
    const itemId = required(envelope.itemId, "itemId");
    const response = required(envelope.response, "response");
    const actorUserId = context.actorUserId;
    const occurredAtUtc = this.timestamp(context.occurredAtUtc);
    this.assertExpectedRevision(envelope, revisionId);
    if (stored.checklistResponses.some((item) => item.responseId === responseId || (item.revisionId === revisionId && item.itemId === itemId))) {
      throw new MissionServiceError(409, "CHECKLIST_RESPONSE_EXISTS", "checklist item already has a response");
    }
    const revision = this.requireRevision(revisionId).revision;
    if (!revision.crew.some((member) => member.userId === actorUserId)) {
      throw new MissionServiceError(403, "CHECKLIST_ACTOR_NOT_ASSIGNED", "checklist actor is not assigned to the mission");
    }
    const record: ChecklistResponse = Object.freeze({
      responseId,
      revisionId,
      itemId,
      response,
      actorUserId,
      occurredAtUtc,
      ...(envelope.evidenceRef === undefined ? {} : { evidenceRef: required(envelope.evidenceRef, "evidenceRef") }),
      ...(envelope.reason === undefined ? {} : { reason: required(envelope.reason, "reason") }),
    });
    await this.appendAudit({
      type: "checklist.response",
      action: "record",
      reason: record.reason ?? "checklist response recorded",
      actorUserId,
      missionRevisionId: revisionId,
      clientSessionId: context.clientSessionId,
      occurredAtUtc,
      payload: record as unknown as Record<string, unknown>,
    });
    stored.checklistResponses.push(record);
    this.persist();
    return record;
  }

  public getSafetyResult(revisionId: string): SafetyEvaluationResult {
    const stored = this.requireRevision(revisionId).stored;
    const result = stored.safetyResults.find((item) => item.missionRevisionId === revisionId);
    if (result !== undefined) return result;
    return this.parseSafety({
      missionRevisionId: revisionId,
      status: "blocked",
      evaluations: [],
      blockers: [{ code: "SAFETY_RESULT_MISSING", conceptId: "safety.result.missing", severity: "data", explanationKey: "SAFETY_RESULT_MISSING", evidenceRefs: [] }],
      invalidatedGates: [],
      kernelVersion: "0.1.0",
    }, revisionId);
  }

  public async recordGateDecision(revisionId: string, gateInput: string, input: unknown, context: GateActorContext): Promise<GateApprovalRecord> {
    if (!GATES.includes(gateInput as GateName)) throw new MissionServiceError(400, "INVALID_GATE", "gate is not supported");
    const gate = gateInput as GateName;
    const envelope = objectInput(input);
    const resolved = this.requireRevision(revisionId);
    const stored = resolved.stored;
    const revision = resolved.revision;
    this.assertExpectedRevision(envelope, revisionId);
    const decision = required(envelope.decision, "decision");
    if (!(["accept", "block", "escalate"] as readonly string[]).includes(decision)) {
      throw new MissionServiceError(400, "INVALID_GATE_DECISION", "decision must be accept, block, or escalate");
    }
    const actorUserId = context.actorUserId;
    const actorRole = context.actorRole;
    if (actorRole !== ROLE_BY_GATE[gate]) throw new MissionServiceError(403, "GATE_ROLE_FORBIDDEN", "actor role cannot sign this gate");
    const crew = revision.crew.find((member) => member.userId === actorUserId && member.role === actorRole);
    const aircraftId = envelope.aircraftId === undefined ? undefined : required(envelope.aircraftId, "aircraftId");
    if (crew === undefined || !crew.qualified || !crew.recencyCurrent || crew.dutyStatus !== "available") {
      throw new MissionServiceError(403, "GATE_ACTOR_NOT_QUALIFIED", "actor is not qualified and available for this gate");
    }
    if (gate === "operator" && (aircraftId === undefined || crew.aircraftId !== aircraftId)) {
      throw new MissionServiceError(403, "GATE_AIRCRAFT_FORBIDDEN", "operator approval must name the assigned aircraft");
    }
    if (gate !== "operator" && aircraftId !== undefined) {
      throw new MissionServiceError(400, "GATE_AIRCRAFT_SCOPE_INVALID", "only operator approvals may name an aircraft");
    }
    const checklistResponseIds = arrayOfText(envelope.checklistResponseIds, "checklistResponseIds");
    if (checklistResponseIds.length === 0) throw new MissionServiceError(400, "CHECKLIST_REQUIRED", "gate signing requires checklist response IDs");
    const knownChecklist = new Set(stored.checklistResponses.filter((item) => item.revisionId === revisionId).map((item) => item.responseId));
    if (checklistResponseIds.some((id) => !knownChecklist.has(id))) {
      throw new MissionServiceError(409, "CHECKLIST_RESPONSE_MISSING", "gate signing references an unknown checklist response");
    }
    const duplicate = stored.approvals.some((approval) => approval.missionRevisionId === revisionId
      && approval.gate === gate && approval.aircraftId === aircraftId);
    if (duplicate) throw new MissionServiceError(409, "GATE_ALREADY_SIGNED", "gate already has a decision for this scope");
    const occurredAtUtc = this.timestamp(context.occurredAtUtc);
    const evidenceSnapshotId = required(envelope.evidenceSnapshotId, "evidenceSnapshotId");
    const reason = required(envelope.reason, "reason");
    const approval = parseGateApproval({
      missionRevisionId: revisionId,
      gate,
      actorUserId,
      actorRole,
      ...(aircraftId === undefined ? {} : { aircraftId }),
      decision,
      valid: envelope.valid ?? true,
      occurredAtUtc,
      evidenceSnapshotId,
      policyVersion: textOr(envelope.policyVersion, "edge-api"),
      reason,
    });
    if (decision === "accept") {
      const safety = this.getSafetyResult(revisionId);
      if (safety.status !== "ready") throw new MissionServiceError(409, "SAFETY_RESULT_BLOCKED", "gate cannot be accepted while safety evaluation is not ready");
      const priorOperatorBlock = stored.approvals.some((item) => item.missionRevisionId === revisionId
        && item.gate === "operator" && item.decision !== "accept");
      if (priorOperatorBlock) throw new MissionServiceError(409, "OPERATOR_GATE_BLOCKED", "commander acceptance is blocked by an operator no-go");
      if (gate === "commander") {
        const priorApprovals = stored.approvals
          .filter((item) => item.missionRevisionId === revisionId)
          .map(({ checklistResponseIds: _checklistResponseIds, ...baseApproval }) => baseApproval);
        const gateResult = evaluateFourGates({ mission: revision, evaluation: safety, approvals: [...priorApprovals, approval], nowUtc: occurredAtUtc });
        if (gateResult.status !== "ready") throw new MissionServiceError(409, "GATE_DEPENDENCY_BLOCKED", "commander acceptance requires all other gates to be accepted");
      }
    }
    const record: GateApprovalRecord = Object.freeze({ ...approval, checklistResponseIds: Object.freeze(checklistResponseIds) });
    await this.appendAudit({
      type: `gate.${decision}`,
      action: decision,
      reason,
      actorUserId,
      missionRevisionId: revisionId,
      evidenceSnapshotId,
      clientSessionId: context.clientSessionId,
      occurredAtUtc,
      payload: { gate, decision, ...(aircraftId === undefined ? {} : { aircraftId }), checklistResponseIds },
    });
    stored.approvals.push(record);
    this.persist();
    return record;
  }

  public async recordPostflight(revisionId: string, input: unknown, context: ServiceActorContext): Promise<PostflightRecord> {
    const envelope = objectInput(input);
    const stored = this.requireRevision(revisionId).stored;
    if (stored.postflight !== undefined) throw new MissionServiceError(409, "POSTFLIGHT_ALREADY_RECORDED", "post-flight record already exists");
    const recovery = objectRequired(envelope.recovery, "recovery");
    const battery = objectRequired(envelope.battery, "battery");
    const telemetry = objectRequired(envelope.telemetry, "telemetry");
    const debrief = objectRequired(envelope.debrief, "debrief");
    if (telemetry.preserved !== true || !/^[a-f0-9]{64}$/.test(required(telemetry.checksum, "telemetry.checksum"))) {
      throw new MissionServiceError(400, "TELEMETRY_PRESERVATION_REQUIRED", "post-flight telemetry must be preserved with a SHA-256 checksum");
    }
    const record: PostflightRecord = Object.freeze({ revisionId, recordedAtUtc: this.timestamp(envelope.recordedAtUtc), recovery, battery, telemetry, debrief });
    await this.appendAudit({ type: "mission.postflight", action: "record", reason: "post-flight evidence recorded", actorUserId: context.actorUserId, clientSessionId: context.clientSessionId, missionRevisionId: revisionId, occurredAtUtc: record.recordedAtUtc, payload: record as unknown as Record<string, unknown> });
    stored.postflight = record;
    this.persist();
    return record;
  }

  public async recordOccurrence(revisionId: string, input: unknown, context: ServiceActorContext): Promise<OccurrenceRecord> {
    const envelope = objectInput(input);
    const stored = this.requireRevision(revisionId).stored;
    const occurrenceId = required(envelope.occurrenceId, "occurrenceId");
    if (stored.occurrences.some((item) => item.occurrenceId === occurrenceId)) throw new MissionServiceError(409, "OCCURRENCE_ALREADY_EXISTS", "occurrence already exists");
    if (typeof envelope.reportable !== "boolean") throw new MissionServiceError(400, "OCCURRENCE_REPORTABILITY_REQUIRED", "occurrence reportability is required");
    const record: OccurrenceRecord = Object.freeze({ revisionId, occurrenceId, screenedAtUtc: this.timestamp(envelope.screenedAtUtc), reportable: envelope.reportable, disposition: required(envelope.disposition, "disposition"), ...(envelope.details === undefined ? {} : { details: required(envelope.details, "details") }) });
    await this.appendAudit({ type: "occurrence.screened", action: "screen", reason: "occurrence screening recorded", actorUserId: context.actorUserId, clientSessionId: context.clientSessionId, missionRevisionId: revisionId, occurredAtUtc: record.screenedAtUtc, payload: record as unknown as Record<string, unknown> });
    stored.occurrences.push(record);
    this.persist();
    return record;
  }

  public getAuditLedger(): AuditLedger {
    return this.audit;
  }

  private parseMission(value: unknown): MissionRevision {
    try {
      return parseMissionRevision(value);
    } catch (error) {
      throw new MissionServiceError(400, "INVALID_MISSION_REVISION", errorMessage(error));
    }
  }

  private parseSafety(value: unknown, revisionId: string): SafetyEvaluationResult {
    try {
      const result = parseSafetyEvaluationResult(value);
      if (result.missionRevisionId !== revisionId) throw new Error("safety result revision does not match the target");
      return result;
    } catch (error) {
      throw new MissionServiceError(400, "INVALID_SAFETY_RESULT", errorMessage(error));
    }
  }

  private requireMission(missionId: string): StoredMission {
    const stored = this.missions.get(missionId);
    if (stored === undefined) throw new MissionServiceError(404, "MISSION_NOT_FOUND", "mission does not exist");
    return stored;
  }

  private requireRevision(revisionId: string): { stored: StoredMission; revision: MissionRevision } {
    for (const stored of this.missions.values()) {
      const revision = stored.revisions.find((item) => item.id === revisionId);
      if (revision !== undefined) return { stored, revision };
    }
    throw new MissionServiceError(404, "REVISION_NOT_FOUND", "mission revision does not exist");
  }

  private assertExpectedRevision(input: Record<string, unknown>, revisionId: string): void {
    const expected = input.expectedRevisionId ?? input.revisionId;
    if (expected !== undefined && expected !== revisionId) throw new MissionServiceError(409, "STALE_REVISION", "mission revision has changed");
    if (input.expectedRevision !== undefined) {
      if (typeof input.expectedRevision !== "number" || !Number.isInteger(input.expectedRevision)) {
        throw new MissionServiceError(400, "INVALID_EXPECTED_REVISION", "expectedRevision must be an integer");
      }
      const currentRevision = this.requireRevision(revisionId).revision.revision;
      if (input.expectedRevision !== currentRevision) throw new MissionServiceError(409, "STALE_REVISION", "mission revision has changed");
    }
  }

  private timestamp(value: unknown): string {
    const candidate = value === undefined ? this.now() : required(value, "occurredAtUtc");
    if (!UTC_PATTERN.test(candidate) || !Number.isFinite(new Date(candidate).getTime())) throw new MissionServiceError(400, "INVALID_UTC", "timestamp must be a valid UTC ISO-8601 instant");
    return new Date(candidate).toISOString();
  }

  private async appendAudit(input: Parameters<AuditLedger["append"]>[0]): Promise<void> {
    try {
      await this.audit.append(input);
    } catch (error) {
      if (error instanceof MissionServiceError) throw error;
      throw new MissionServiceError(503, "AUDIT_LEDGER_UNAVAILABLE", errorMessage(error));
    }
  }

  private load(): void {
    if (this.database === undefined) return;
    const row = this.database.sql().prepare("SELECT value FROM service_state WHERE key = ?").get("mission_store") as { value?: unknown } | undefined;
    if (row?.value === undefined) return;
    try {
      const parsed = JSON.parse(String(row.value)) as StoredMission[];
      for (const raw of parsed) {
        const revisions = raw.revisions.map((revision) => this.parseMission(revision));
        const safetyResults = raw.safetyResults.map((result) => this.parseSafety(result, result.missionRevisionId));
        const approvals = raw.approvals.map((approval) => {
          const { checklistResponseIds, ...baseApproval } = approval;
          return Object.freeze({ ...parseGateApproval(baseApproval), checklistResponseIds: Object.freeze([...checklistResponseIds]) });
        });
        this.missions.set(raw.missionId, { ...raw, revisions, safetyResults, approvals });
      }
    } catch (error) {
      throw new Error(`mission store is corrupt: ${errorMessage(error)}`);
    }
  }

  private persist(): void {
    if (this.database === undefined) return;
    const value = JSON.stringify([...this.missions.values()]);
    try {
      this.database.sql().prepare("INSERT INTO service_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value").run("mission_store", value);
    } catch (error) {
      void this.audit.simulateWriteFailure();
      throw new MissionServiceError(503, "MISSION_STORE_UNAVAILABLE", errorMessage(error));
    }
  }
}

function objectInput(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new MissionServiceError(400, "INVALID_REQUEST", "request payload must be an object");
  return value as Record<string, unknown>;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function objectRequired(value: unknown, field: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new MissionServiceError(400, "INVALID_REQUEST", `${field} must be an object`);
  return value as Record<string, unknown>;
}

function required(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "" || value !== value.trim() || value.includes("\0")) throw new MissionServiceError(400, "INVALID_REQUEST", `${field} is required`);
  return value;
}

function textOr(value: unknown, fallback: string): string {
  return value === undefined ? fallback : required(value, "text");
}

function arrayOfText(value: unknown, field: string): string[] {
  if (!Array.isArray(value)) throw new MissionServiceError(400, "INVALID_REQUEST", `${field} must be an array`);
  return value.map((item) => required(item, field));
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
