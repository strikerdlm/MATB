import {
  createMissionRevision,
  evaluateFourGates,
  parseGateApproval,
  parseMissionRevision,
  type GateApproval,
  type GateActorRole,
  type GateName,
  type MissionRevision,
  type MissionRevisionChange,
} from "@fac-isr/safety-kernel";
import type { EdgeDatabase } from "../db/migrate.js";
import { AtomicConflictError, AtomicDomainWriteError, AuditLedger, type AuditEventInput } from "../audit/ledger.js";
import { loadMissionSnapshots, MissionSnapshotConflictError, writeMissionSnapshot } from "../db/operational-repository.js";
import {
  asSafetyEvaluationResult,
  UnavailableSafetyEvaluationProvider,
  validateSafetyEvaluationEnvelope,
  type SafetyEvaluationEnvelope,
  type SafetyEvaluationProvider,
  type SafetyEvaluationView,
} from "./safety-evaluation.js";
import { validateGateAuthorityScope } from "./gate-authority.js";

const GATES: readonly GateName[] = ["maintenance", "operator", "safety", "commander"];
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
  persistenceVersion: number;
  revisions: MissionRevision[];
  safetyResults: StoredSafetyEvaluation[];
  checklistResponses: ChecklistResponse[];
  approvals: GateApprovalRecord[];
  postflight?: PostflightRecord;
  occurrences: OccurrenceRecord[];
}

interface StoredSafetyEvaluation {
  readonly envelope: SafetyEvaluationEnvelope;
  stale: boolean;
}

export interface MissionServiceOptions {
  readonly auditLedger?: AuditLedger;
  readonly database?: EdgeDatabase;
  readonly now?: () => string;
  readonly safetyEvaluationProvider?: SafetyEvaluationProvider;
}

export interface ServiceActorContext {
  readonly actorUserId: string;
  readonly clientSessionId: string;
  readonly occurredAtUtc: string;
}

export interface GateActorContext extends ServiceActorContext {
  readonly actorRole: GateActorRole;
}

export interface StagedMissionMutation {
  readonly auditInputs: readonly AuditEventInput[];
  writeDomain(): void;
  publish(): void;
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
  private readonly safetyEvaluationProvider: SafetyEvaluationProvider;
  private safetyIntegrityFailure = false;
  private mutationTail: Promise<void> = Promise.resolve();

  public constructor(options: MissionServiceOptions = {}) {
    this.audit = options.auditLedger ?? new AuditLedger({ database: options.database });
    this.database = options.database;
    this.now = options.now ?? (() => new Date().toISOString());
    this.safetyEvaluationProvider = options.safetyEvaluationProvider ?? new UnavailableSafetyEvaluationProvider(this.now);
    this.load();
  }

  public async createMission(input: unknown, context: ServiceActorContext): Promise<MissionRevision> {
    const envelope = objectInput(input);
    this.rejectCallerSafetyResult(envelope);
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
    const safetyResult = await this.evaluateSafety(revision);
    const stored: StoredMission = {
      missionId: revision.missionId,
      persistenceVersion: 0,
      revisions: [revision],
      safetyResults: [{ envelope: safetyResult, stale: false }],
      checklistResponses: [],
      approvals: [],
      occurrences: [],
    };
    const audit: AuditEventInput = {
      type: "mission.created",
      action: "create",
      reason: "mission revision created",
      actorUserId: context.actorUserId,
      missionRevisionId: revision.id,
      clientSessionId: context.clientSessionId,
      occurredAtUtc: this.timestamp(context.occurredAtUtc),
      payload: { missionId: revision.missionId, revision: revision.revision },
    };
    await this.commitMission(stored, [audit]);
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
      safetyResults: stored.safetyResults.map((result) => this.evaluationView(result)),
      checklistResponses: [...stored.checklistResponses],
      gateApprovals: [...stored.approvals],
      postflight: stored.postflight,
      occurrences: [...stored.occurrences],
    };
  }

  public listMissions(visibleMissionIds?: ReadonlySet<string>): readonly Record<string, unknown>[] {
    return Object.freeze([...this.missions.keys()]
      .filter((missionId) => visibleMissionIds === undefined || visibleMissionIds.has(missionId))
      .sort((left, right) => left.localeCompare(right))
      .map((missionId) => this.getMission(missionId)));
  }

  public missionIdForRevision(revisionId: string): string {
    return this.requireRevision(revisionId).stored.missionId;
  }

  public aircraftIdsForRevision(revisionId: string): readonly string[] {
    return Object.freeze(this.requireRevision(revisionId).revision.aircraft.map(({ aircraftId }) => aircraftId));
  }

  public createRevision(missionId: string, input: unknown, context: ServiceActorContext): Promise<MissionRevision> {
    return this.enqueueMutation(() => this.createRevisionInternal(missionId, input, context));
  }

  private async createRevisionInternal(missionId: string, input: unknown, context: ServiceActorContext): Promise<MissionRevision> {
    const stored = cloneStoredMission(this.requireMission(missionId));
    const current = stored.revisions.at(-1)!;
    const envelope = objectInput(input);
    this.rejectCallerSafetyResult(envelope);
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

    const safetyResult = await this.evaluateSafety(next);
    const invalidated = stored.approvals.filter((approval) => approval.missionRevisionId === current.id);
    const audits: AuditEventInput[] = [];
    for (const approval of invalidated) {
      audits.push({
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
    audits.push({
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
    for (const result of stored.safetyResults) {
      if (result.envelope.revisionId === current.id) result.stale = true;
    }
    stored.safetyResults.push({ envelope: safetyResult, stale: false });
    await this.commitMission(stored, audits);
    return next;
  }

  public async recordChecklistResponse(revisionId: string, input: unknown, context: ServiceActorContext): Promise<ChecklistResponse> {
    const envelope = objectInput(input);
    const live = this.requireRevision(revisionId).stored;
    const stored = cloneStoredMission(live);
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
    const audit: AuditEventInput = {
      type: "checklist.response",
      action: "record",
      reason: record.reason ?? "checklist response recorded",
      actorUserId,
      missionRevisionId: revisionId,
      clientSessionId: context.clientSessionId,
      occurredAtUtc,
      payload: record as unknown as Record<string, unknown>,
    };
    stored.checklistResponses.push(record);
    await this.commitMission(stored, [audit]);
    return record;
  }

  public getSafetyResult(revisionId: string): SafetyEvaluationView {
    if (this.safetyIntegrityFailure) throw new MissionServiceError(503, "SAFETY_EVALUATION_INTEGRITY_FAILURE", "safety evaluation authority is in fail-closed safe mode");
    const stored = this.requireRevision(revisionId).stored;
    const result = stored.safetyResults.find((item) => item.envelope.revisionId === revisionId);
    if (result === undefined) throw new MissionServiceError(409, "SAFETY_EVALUATION_MISSING", "server safety evaluation is missing");
    return this.evaluationView(result);
  }

  public async recomputeSafetyEvaluation(revisionId: string, context?: ServiceActorContext): Promise<SafetyEvaluationView> {
    const resolved = this.requireRevision(revisionId);
    const storedMission = cloneStoredMission(resolved.stored);
    const stagedRevision = storedMission.revisions.find((revision) => revision.id === revisionId)!;
    const envelope = await this.evaluateSafety(stagedRevision);
    const invalidated = storedMission.approvals.filter((approval) => approval.missionRevisionId === revisionId);
    const auditContext = context ?? { actorUserId: "safety-evaluation-service", clientSessionId: "server-recompute", occurredAtUtc: this.now() };
    const audits: AuditEventInput[] = [];
    for (const approval of invalidated) {
      audits.push({
        type: "gate.invalidated",
        action: "invalidate",
        reason: "safety evaluation recomputation invalidated the prior approval",
        actorUserId: auditContext.actorUserId,
        missionRevisionId: revisionId,
        clientSessionId: auditContext.clientSessionId,
        occurredAtUtc: this.timestamp(auditContext.occurredAtUtc),
        payload: { gate: approval.gate, cause: "safety.recomputed" },
      });
    }
    storedMission.approvals = storedMission.approvals.filter((approval) => approval.missionRevisionId !== revisionId);
    storedMission.safetyResults = storedMission.safetyResults.filter((item) => item.envelope.revisionId !== revisionId);
    const stored = { envelope, stale: false };
    storedMission.safetyResults.push(stored);
    await this.commitMission(storedMission, audits);
    return this.evaluationView(stored);
  }

  public async markSafetyEvaluationsStale(context: ServiceActorContext, reason: string): Promise<void> {
    const staged = this.stageSafetyEvaluationsStale(context, reason);
    if (this.database === undefined) {
      for (const input of staged.auditInputs) await this.audit.append(input);
      staged.publish();
      return;
    }
    try {
      await this.audit.commitAtomic(staged.auditInputs, staged.writeDomain);
      staged.publish();
    } catch (error) {
      if (error instanceof AtomicConflictError) throw new MissionServiceError(409, "CONCURRENT_MISSION_WRITE", error.message);
      if (error instanceof AtomicDomainWriteError) throw new MissionServiceError(503, "MISSION_STORE_UNAVAILABLE", errorMessage(error.cause ?? error));
      throw new MissionServiceError(503, "AUDIT_LEDGER_UNAVAILABLE", errorMessage(error));
    }
  }

  public stageSafetyEvaluationsStale(context: ServiceActorContext, reason: string): StagedMissionMutation {
    const stagedMissions = [...this.missions.values()].map(cloneStoredMission);
    const audits: AuditEventInput[] = [];
    for (const stored of stagedMissions) {
      const affectedRevisionIds = new Set<string>();
      for (const evaluation of stored.safetyResults) {
        if (evaluation.stale) continue;
        evaluation.stale = true;
        affectedRevisionIds.add(evaluation.envelope.revisionId);
      }
      const invalidated = stored.approvals.filter((approval) => affectedRevisionIds.has(approval.missionRevisionId));
      for (const approval of invalidated) {
        audits.push({
          type: "gate.invalidated",
          action: "invalidate",
          reason,
          actorUserId: context.actorUserId,
          missionRevisionId: approval.missionRevisionId,
          clientSessionId: context.clientSessionId,
          occurredAtUtc: this.timestamp(context.occurredAtUtc),
          payload: { gate: approval.gate, cause: "package.activation" },
        });
      }
      stored.approvals = stored.approvals.filter((approval) => !affectedRevisionIds.has(approval.missionRevisionId));
    }
    return {
      auditInputs: audits,
      writeDomain: () => {
        if (this.database === undefined) return;
        try {
          for (const stored of stagedMissions) writeMissionSnapshot(this.database.sql(), stored as unknown as Parameters<typeof writeMissionSnapshot>[1]);
        } catch (error) {
          if (error instanceof MissionSnapshotConflictError) throw new AtomicConflictError(error.message, { cause: error });
          throw new AtomicDomainWriteError("normalized mission persistence failed", { cause: error });
        }
      },
      publish: () => {
        for (const stored of stagedMissions) {
          if (this.database !== undefined) stored.persistenceVersion += 1;
          this.missions.set(stored.missionId, stored);
        }
      },
    };
  }

  public recordGateDecision(revisionId: string, gateInput: string, input: unknown, context: GateActorContext): Promise<GateApprovalRecord> {
    return this.enqueueMutation(() => this.recordGateDecisionInternal(revisionId, gateInput, input, context));
  }

  private async recordGateDecisionInternal(revisionId: string, gateInput: string, input: unknown, context: GateActorContext): Promise<GateApprovalRecord> {
    if (!GATES.includes(gateInput as GateName)) throw new MissionServiceError(400, "INVALID_GATE", "gate is not supported");
    const gate = gateInput as GateName;
    const envelope = objectInput(input);
    const resolved = this.requireRevision(revisionId);
    const stored = cloneStoredMission(resolved.stored);
    const revision = resolved.revision;
    this.assertExpectedRevision(envelope, revisionId);
    const decision = required(envelope.decision, "decision");
    if (!(["accept", "block", "escalate"] as readonly string[]).includes(decision)) {
      throw new MissionServiceError(400, "INVALID_GATE_DECISION", "decision must be accept, block, or escalate");
    }
    const actorUserId = context.actorUserId;
    const actorRole = context.actorRole;
    const aircraftId = envelope.aircraftId === undefined ? undefined : required(envelope.aircraftId, "aircraftId");
    try {
      validateGateAuthorityScope(revision, { gate, actorUserId, actorRole, ...(aircraftId === undefined ? {} : { aircraftId }) });
    } catch (error) {
      throw new MissionServiceError(403, "GATE_AUTHORITY_FORBIDDEN", error instanceof Error ? error.message : String(error));
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
    const safety = await this.currentSafetyForGate(revision, stored, context);
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
      policyVersion: safety.policyPackage.version,
      reason,
    });
    if (decision === "accept") {
      if (safety.status !== "ready") throw new MissionServiceError(409, "SAFETY_RESULT_BLOCKED", "gate cannot be accepted while safety evaluation is not ready");
      const priorOperatorBlock = stored.approvals.some((item) => item.missionRevisionId === revisionId
        && item.gate === "operator" && item.decision !== "accept");
      if (priorOperatorBlock) throw new MissionServiceError(409, "OPERATOR_GATE_BLOCKED", "commander acceptance is blocked by an operator no-go");
      if (gate === "commander") {
        const priorApprovals = stored.approvals
          .filter((item) => item.missionRevisionId === revisionId)
          .map(({ checklistResponseIds: _checklistResponseIds, ...baseApproval }) => baseApproval);
        const gateResult = evaluateFourGates({ mission: revision, evaluation: asSafetyEvaluationResult(safety), approvals: [...priorApprovals, approval], nowUtc: occurredAtUtc });
        if (gateResult.status !== "ready") throw new MissionServiceError(409, "GATE_DEPENDENCY_BLOCKED", "commander acceptance requires all other gates to be accepted");
      }
    }
    const record: GateApprovalRecord = Object.freeze({ ...approval, checklistResponseIds: Object.freeze(checklistResponseIds) });
    const audit: AuditEventInput = {
      type: `gate.${decision}`,
      action: decision,
      reason,
      actorUserId,
      missionRevisionId: revisionId,
      evidenceSnapshotId,
      clientSessionId: context.clientSessionId,
      occurredAtUtc,
      payload: { gate, decision, ...(aircraftId === undefined ? {} : { aircraftId }), checklistResponseIds },
    };
    stored.approvals.push(record);
    await this.commitMission(stored, [audit]);
    return record;
  }

  public async recordPostflight(revisionId: string, input: unknown, context: ServiceActorContext): Promise<PostflightRecord> {
    const envelope = objectInput(input);
    const stored = cloneStoredMission(this.requireRevision(revisionId).stored);
    if (stored.postflight !== undefined) throw new MissionServiceError(409, "POSTFLIGHT_ALREADY_RECORDED", "post-flight record already exists");
    const recovery = objectRequired(envelope.recovery, "recovery");
    const battery = objectRequired(envelope.battery, "battery");
    const telemetry = objectRequired(envelope.telemetry, "telemetry");
    const debrief = objectRequired(envelope.debrief, "debrief");
    if (telemetry.preserved !== true || !/^[a-f0-9]{64}$/.test(required(telemetry.checksum, "telemetry.checksum"))) {
      throw new MissionServiceError(400, "TELEMETRY_PRESERVATION_REQUIRED", "post-flight telemetry must be preserved with a SHA-256 checksum");
    }
    const record: PostflightRecord = Object.freeze({ revisionId, recordedAtUtc: this.timestamp(envelope.recordedAtUtc), recovery, battery, telemetry, debrief });
    const audit: AuditEventInput = { type: "mission.postflight", action: "record", reason: "post-flight evidence recorded", actorUserId: context.actorUserId, clientSessionId: context.clientSessionId, missionRevisionId: revisionId, occurredAtUtc: record.recordedAtUtc, payload: record as unknown as Record<string, unknown> };
    stored.postflight = record;
    await this.commitMission(stored, [audit]);
    return record;
  }

  public async recordOccurrence(revisionId: string, input: unknown, context: ServiceActorContext): Promise<OccurrenceRecord> {
    const envelope = objectInput(input);
    const stored = cloneStoredMission(this.requireRevision(revisionId).stored);
    const occurrenceId = required(envelope.occurrenceId, "occurrenceId");
    if (stored.occurrences.some((item) => item.occurrenceId === occurrenceId)) throw new MissionServiceError(409, "OCCURRENCE_ALREADY_EXISTS", "occurrence already exists");
    if (typeof envelope.reportable !== "boolean") throw new MissionServiceError(400, "OCCURRENCE_REPORTABILITY_REQUIRED", "occurrence reportability is required");
    const record: OccurrenceRecord = Object.freeze({ revisionId, occurrenceId, screenedAtUtc: this.timestamp(envelope.screenedAtUtc), reportable: envelope.reportable, disposition: required(envelope.disposition, "disposition"), ...(envelope.details === undefined ? {} : { details: required(envelope.details, "details") }) });
    const audit: AuditEventInput = { type: "occurrence.screened", action: "screen", reason: "occurrence screening recorded", actorUserId: context.actorUserId, clientSessionId: context.clientSessionId, missionRevisionId: revisionId, occurredAtUtc: record.screenedAtUtc, payload: record as unknown as Record<string, unknown> };
    stored.occurrences.push(record);
    await this.commitMission(stored, [audit]);
    return record;
  }

  public getAuditLedger(): AuditLedger {
    return this.audit;
  }

  public isReadOnlySafeMode(): boolean {
    return this.safetyIntegrityFailure;
  }

  private parseMission(value: unknown): MissionRevision {
    try {
      return parseMissionRevision(value);
    } catch (error) {
      throw new MissionServiceError(400, "INVALID_MISSION_REVISION", errorMessage(error));
    }
  }

  private async evaluateSafety(revision: MissionRevision): Promise<SafetyEvaluationEnvelope> {
    let candidate: SafetyEvaluationEnvelope;
    try {
      candidate = await this.safetyEvaluationProvider.evaluate(revision);
    } catch (error) {
      throw new MissionServiceError(503, "SAFETY_EVALUATION_UNAVAILABLE", errorMessage(error));
    }
    try {
      return validateSafetyEvaluationEnvelope(candidate, revision.id);
    } catch (error) {
      this.safetyIntegrityFailure = true;
      await this.audit.simulateWriteFailure();
      throw new MissionServiceError(503, "SAFETY_EVALUATION_INTEGRITY_FAILURE", errorMessage(error));
    }
  }

  private async currentSafetyForGate(revision: MissionRevision, stored: StoredMission, context: ServiceActorContext): Promise<SafetyEvaluationView> {
    const record = stored.safetyResults.find((item) => item.envelope.revisionId === revision.id);
    if (record === undefined) throw new MissionServiceError(409, "SAFETY_EVALUATION_MISSING", "server safety evaluation is missing");
    if (this.safetyIntegrityFailure) throw new MissionServiceError(503, "SAFETY_EVALUATION_INTEGRITY_FAILURE", "safety evaluation authority is in fail-closed safe mode");
    try {
      validateSafetyEvaluationEnvelope(record.envelope, revision.id);
    } catch (error) {
      this.safetyIntegrityFailure = true;
      await this.audit.simulateWriteFailure();
      throw new MissionServiceError(503, "SAFETY_EVALUATION_INTEGRITY_FAILURE", errorMessage(error));
    }
    let current = false;
    if (!record.stale) {
      try {
        current = await this.safetyEvaluationProvider.isCurrent(revision, record.envelope, this.now());
      } catch {
        current = false;
      }
    }
    if (!current) {
      record.stale = true;
      const invalidated = stored.approvals.filter((approval) => approval.missionRevisionId === revision.id);
      const audits: AuditEventInput[] = [];
      for (const approval of invalidated) {
        audits.push({
          type: "gate.invalidated",
          action: "invalidate",
          reason: "trusted safety inputs changed after evaluation",
          actorUserId: context.actorUserId,
          missionRevisionId: revision.id,
          clientSessionId: context.clientSessionId,
          occurredAtUtc: this.timestamp(context.occurredAtUtc),
          payload: { gate: approval.gate, cause: "safety.input.changed" },
        });
      }
      stored.approvals = stored.approvals.filter((approval) => approval.missionRevisionId !== revision.id);
      await this.commitMission(stored, audits);
      throw new MissionServiceError(409, "SAFETY_EVALUATION_STALE", "gate decisions are blocked until safety is recomputed");
    }
    return this.evaluationView(record);
  }

  private evaluationView(result: StoredSafetyEvaluation): SafetyEvaluationView {
    return Object.freeze({ ...result.envelope, stale: result.stale });
  }

  private rejectCallerSafetyResult(envelope: Record<string, unknown>): void {
    if (containsForbiddenSafetyResult(envelope)) {
      throw new MissionServiceError(400, "CALLER_SAFETY_RESULT_FORBIDDEN", "safetyResult is computed by the server and cannot be supplied by clients");
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
    try {
      const parsed = loadMissionSnapshots(this.database.sql()) as unknown as StoredMission[];
      for (const raw of parsed) {
        const revisions = raw.revisions.map((revision) => this.parseMission(revision));
        const safetyResults = raw.safetyResults.flatMap((result) => {
          if (!isObject(result) || !isObject(result.envelope) || typeof result.stale !== "boolean") return [];
          try {
            const envelope = validateSafetyEvaluationEnvelope(result.envelope as unknown as SafetyEvaluationEnvelope, String(result.envelope.revisionId));
            return [{ envelope, stale: result.stale }];
          } catch {
            this.safetyIntegrityFailure = true;
            void this.audit.simulateWriteFailure();
            return [];
          }
        });
        const approvals = raw.approvals.map((approval) => {
          const { checklistResponseIds, ...baseApproval } = approval;
          return Object.freeze({ ...parseGateApproval(baseApproval), checklistResponseIds: Object.freeze([...checklistResponseIds]) });
        });
        this.missions.set(raw.missionId, { ...raw, revisions, safetyResults, approvals });
      }
    } catch {
      this.missions.clear();
      this.safetyIntegrityFailure = true;
      void this.audit.simulateWriteFailure();
    }
  }

  private async commitMission(stored: StoredMission, auditInputs: readonly AuditEventInput[]): Promise<void> {
    return this.commitMissions([stored], auditInputs);
  }

  private async commitMissions(storedMissions: readonly StoredMission[], auditInputs: readonly AuditEventInput[]): Promise<void> {
    if (this.database === undefined) {
      for (const input of auditInputs) await this.appendAudit(input);
      for (const stored of storedMissions) this.missions.set(stored.missionId, stored);
      return;
    }
    try {
      await this.audit.commitAtomic(auditInputs, () => {
        try {
          for (const stored of storedMissions) writeMissionSnapshot(this.database!.sql(), stored as unknown as Parameters<typeof writeMissionSnapshot>[1]);
        } catch (error) {
          if (error instanceof MissionSnapshotConflictError) throw new AtomicConflictError(error.message, { cause: error });
          throw new AtomicDomainWriteError("normalized mission persistence failed", { cause: error });
        }
      });
    } catch (error) {
      if (error instanceof AtomicConflictError) throw new MissionServiceError(409, "CONCURRENT_MISSION_WRITE", error.message);
      if (error instanceof AtomicDomainWriteError) {
        throw new MissionServiceError(503, "MISSION_STORE_UNAVAILABLE", errorMessage(error.cause ?? error));
      }
      throw new MissionServiceError(503, "AUDIT_LEDGER_UNAVAILABLE", errorMessage(error));
    }
    for (const stored of storedMissions) {
      stored.persistenceVersion += 1;
      this.missions.set(stored.missionId, stored);
    }
  }

  private enqueueMutation<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.mutationTail.then(operation);
    this.mutationTail = result.then(() => undefined, () => undefined);
    return result;
  }
}

function cloneStoredMission(stored: StoredMission): StoredMission {
  return {
    missionId: stored.missionId,
    persistenceVersion: stored.persistenceVersion,
    revisions: [...stored.revisions],
    safetyResults: stored.safetyResults.map((result) => ({ envelope: result.envelope, stale: result.stale })),
    checklistResponses: [...stored.checklistResponses],
    approvals: [...stored.approvals],
    ...(stored.postflight === undefined ? {} : { postflight: stored.postflight }),
    occurrences: [...stored.occurrences],
  };
}

function objectInput(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new MissionServiceError(400, "INVALID_REQUEST", "request payload must be an object");
  return value as Record<string, unknown>;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function containsForbiddenSafetyResult(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(containsForbiddenSafetyResult);
  if (!isObject(value)) return false;
  if (Object.prototype.hasOwnProperty.call(value, "safetyResult")) return true;
  return Object.values(value).some(containsForbiddenSafetyResult);
}

function objectRequired(value: unknown, field: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new MissionServiceError(400, "INVALID_REQUEST", `${field} must be an object`);
  return value as Record<string, unknown>;
}

function required(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "" || value !== value.trim() || value.includes("\0")) throw new MissionServiceError(400, "INVALID_REQUEST", `${field} is required`);
  return value;
}

function arrayOfText(value: unknown, field: string): string[] {
  if (!Array.isArray(value)) throw new MissionServiceError(400, "INVALID_REQUEST", `${field} must be an array`);
  return value.map((item) => required(item, field));
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
