import { constants, copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { assertMaintenanceLockOwnership, MaintenanceLock } from "../admin/maintenance-lock.js";
import { parseGateApproval, parseMissionRevision, type MissionRevision } from "@fac-isr/safety-kernel";
import { GENESIS_HASH, hashAuditEvent } from "../audit/ledger.js";
import { validateSafetyEvaluationEnvelope, type SafetyEvaluationEnvelope } from "../services/safety-evaluation.js";
import { parsePackageRecord } from "../services/safe-mode.js";
import { validateGateAuthorityScope } from "../services/gate-authority.js";
import { configureDatabase, MIGRATIONS, SCHEMA_VERSION } from "./schema.js";
import type { SqlDatabase } from "./schema.js";

type SqlRow = Record<string, unknown>;

export interface DatabaseOpenOptions {
  readonly now?: () => string;
  readonly maintenanceLock?: MaintenanceLock;
}

export class EdgeDatabase {
  private fence?: { readonly holderId: string; readonly token: number; readonly now: () => string };
  public constructor(private readonly database: SqlDatabase) {}

  /** Exposes the configured local connection to services that own their tables. */
  public sql(): SqlDatabase {
    return this.database;
  }

  public migrate(): void {
    const highestVersion = this.schemaVersion();
    if (highestVersion > SCHEMA_VERSION) {
      throw new Error(`database schema ${highestVersion} is newer than supported ${SCHEMA_VERSION}`);
    }

    this.database.exec("BEGIN IMMEDIATE");
    try {
      for (const migration of MIGRATIONS) {
        if (migration.version <= highestVersion) continue;
        for (const statement of migration.statements) this.database.exec(statement);
        if (migration.version === 2) migrateLegacyState(this.database);
        this.database
          .prepare("INSERT INTO schema_migrations (version, applied_at_utc) VALUES (?, ?)")
          .run(migration.version, new Date().toISOString());
      }
      this.database.exec("COMMIT");
    } catch (error) {
      this.database.exec("ROLLBACK");
      throw error;
    }
  }

  public schemaVersion(): number {
    const tableExists = this.database
      .prepare("SELECT 1 AS present FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'")
      .get() as SqlRow | undefined;
    if (tableExists === undefined) return 0;
    const row = this.database
      .prepare("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations")
      .get() as SqlRow;
    return Number(row.version);
  }

  public pragma(name: "foreign_keys" | "journal_mode" | "busy_timeout"): number | string {
    const row = this.database.prepare(`PRAGMA ${name}`).get() as SqlRow;
    const value = Object.values(row)[0];
    if (typeof value !== "number" && typeof value !== "string") {
      throw new Error(`PRAGMA ${name} returned no scalar value`);
    }
    return value;
  }

  public tableNames(): string[] {
    const rows = this.database
      .prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
      .all() as SqlRow[];
    return rows.map((row) => String(row.name));
  }

  public integrityCheck(): { readonly ok: boolean; readonly detail: string } {
    try {
      const row = this.database.prepare("PRAGMA integrity_check").get() as SqlRow;
      const detail = String(Object.values(row)[0] ?? "no integrity result");
      return { ok: detail === "ok", detail };
    } catch (error) {
      return { ok: false, detail: error instanceof Error ? error.message : String(error) };
    }
  }

  public setFencingToken(holderId: string, token: number, now: () => string): void {
    this.fence = { holderId, token, now };
  }

  public clearFencingToken(holderId: string): void {
    if (this.fence?.holderId === holderId) this.fence = undefined;
  }

  public assertFencingToken(): void {
    if (this.fence === undefined) return;
    const row = this.database.prepare("SELECT holder_id, fencing_token, expires_at_utc FROM runtime_lease WHERE singleton = 1").get() as { holder_id: string; fencing_token: number; expires_at_utc: string } | undefined;
    const now = Date.parse(this.fence.now());
    if (row === undefined || row.holder_id !== this.fence.holderId || row.fencing_token !== this.fence.token || !Number.isFinite(now) || Date.parse(row.expires_at_utc) <= now) {
      throw new Error("runtime lease fencing token is stale or expired");
    }
  }

  public close(): void {
    this.database.close();
  }
}

function requireObject(value: unknown, field: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error(`${field} must be an object`);
  return value as Record<string, unknown>;
}

function requireArray(value: unknown, field: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`${field} must be an array`);
  return value;
}

function requiredText(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "" || value !== value.trim()) throw new Error(`${field} must be canonical non-empty text`);
  return value;
}

function requiredUtc(value: unknown, field: string): string {
  const text = requiredText(value, field);
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(text) || !Number.isFinite(Date.parse(text))) {
    throw new Error(`${field} must be a valid UTC timestamp`);
  }
  return text;
}

function optionalText(value: unknown, field: string): string | undefined {
  return value === undefined ? undefined : requiredText(value, field);
}

function parseLegacyJson(database: SqlDatabase, key: string, fallback: unknown): unknown {
  const row = database.prepare("SELECT value FROM service_state WHERE key = ?").get(key) as SqlRow | undefined;
  if (row === undefined) return fallback;
  try {
    return JSON.parse(String(row.value)) as unknown;
  } catch (error) {
    throw new Error(`${key} is not valid JSON`, { cause: error });
  }
}

function migrateLegacyState(database: SqlDatabase): void {
  const missions = requireArray(parseLegacyJson(database, "mission_store", []), "mission_store");
  for (const missionValue of missions) {
    const mission = requireObject(missionValue, "mission_store mission");
    const missionId = requiredText(mission.missionId, "mission_store missionId");
    const revisions = requireArray(mission.revisions, "mission_store revisions").map((value) => requireObject(value, "mission revision"));
    if (revisions.length === 0) throw new Error(`mission_store mission ${missionId} has no revisions`);
    const currentRevision = revisions.reduce((highest, revision) => Math.max(highest, Number(revision.revision)), -1);
    if (!Number.isInteger(currentRevision) || currentRevision < 0) throw new Error(`mission_store mission ${missionId} has an invalid revision`);
    database.prepare("INSERT INTO missions (mission_id, current_revision) VALUES (?, ?)").run(missionId, currentRevision);
    const revisionsById = new Map<string, MissionRevision>();
    for (const revision of revisions) {
      const revisionId = requiredText(revision.id, "mission revision id");
      const revisionNumber = Number(revision.revision);
      if (!Number.isInteger(revisionNumber) || revisionNumber < 0) throw new Error(`mission revision ${revisionId} is invalid`);
      const validatedRevision = parseMissionRevision(revision);
      if (validatedRevision.missionId !== missionId || validatedRevision.id !== revisionId || validatedRevision.revision !== revisionNumber) {
        throw new Error(`mission revision ${revisionId} does not belong to its legacy mission envelope`);
      }
      if (revisionsById.has(revisionId)) throw new Error(`duplicate mission revision ${revisionId}`);
      revisionsById.set(revisionId, validatedRevision);
      database.prepare("INSERT INTO mission_revisions (revision_id, mission_id, revision, revision_json) VALUES (?, ?, ?, ?)")
        .run(revisionId, missionId, revisionNumber, JSON.stringify(validatedRevision));
    }
    for (const value of requireArray(mission.safetyResults ?? [], "mission safetyResults")) {
      const result = requireObject(value, "mission safety result");
      const envelope = requireObject(result.envelope, "mission safety envelope");
      const revisionId = requiredText(envelope.revisionId, "evaluation revisionId");
      if (!revisionsById.has(revisionId)) throw new Error(`evaluation ${revisionId} does not belong to mission ${missionId}`);
      const validatedEnvelope = validateSafetyEvaluationEnvelope(envelope as unknown as SafetyEvaluationEnvelope, revisionId);
      database.prepare("INSERT INTO evaluation_envelopes (revision_id, envelope_json, stale) VALUES (?, ?, ?)")
        .run(revisionId, JSON.stringify(validatedEnvelope), result.stale === true ? 1 : 0);
    }
    const checklistById = new Map<string, string>();
    for (const value of requireArray(mission.checklistResponses ?? [], "mission checklistResponses")) {
      const response = requireObject(value, "checklist response");
      const responseId = requiredText(response.responseId, "checklist responseId");
      const revisionId = requiredText(response.revisionId, "checklist revisionId");
      const revision = revisionsById.get(revisionId);
      if (revision === undefined) throw new Error(`checklist response ${responseId} does not belong to mission ${missionId}`);
      const actorUserId = requiredText(response.actorUserId, "checklist actorUserId");
      if (!revision.crew.some(({ userId }) => userId === actorUserId)) throw new Error(`checklist actor ${actorUserId} is not assigned to revision ${revisionId}`);
      const normalized = {
        responseId,
        revisionId,
        itemId: requiredText(response.itemId, "checklist itemId"),
        response: requiredText(response.response, "checklist response"),
        actorUserId,
        occurredAtUtc: requiredUtc(response.occurredAtUtc, "checklist occurredAtUtc"),
        ...(optionalText(response.evidenceRef, "checklist evidenceRef") === undefined ? {} : { evidenceRef: optionalText(response.evidenceRef, "checklist evidenceRef") }),
        ...(optionalText(response.reason, "checklist reason") === undefined ? {} : { reason: optionalText(response.reason, "checklist reason") }),
      };
      database.prepare("INSERT INTO checklist_responses (response_id, revision_id, item_id, response_json) VALUES (?, ?, ?, ?)")
        .run(responseId, revisionId, normalized.itemId, JSON.stringify(normalized));
      checklistById.set(responseId, revisionId);
    }
    for (const value of requireArray(mission.approvals ?? [], "mission approvals")) {
      const decision = requireObject(value, "gate decision");
      const revisionId = requiredText(decision.missionRevisionId, "gate revisionId");
      const revision = revisionsById.get(revisionId);
      if (revision === undefined) throw new Error(`gate decision does not belong to mission ${missionId}`);
      const { checklistResponseIds: rawChecklistIds, ...approvalValue } = decision;
      const approval = parseGateApproval(approvalValue);
      const checklistResponseIds = requireArray(rawChecklistIds, "gate checklistResponseIds").map((id) => requiredText(id, "gate checklistResponseId"));
      if (checklistResponseIds.length === 0 || checklistResponseIds.some((id) => checklistById.get(id) !== revisionId)) throw new Error(`gate decision for ${revisionId} references invalid checklist responses`);
      validateGateAuthorityScope(revision, approval);
      const gate = approval.gate;
      const aircraftScope = approval.aircraftId ?? "";
      const normalized = { ...approval, checklistResponseIds };
      database.prepare("INSERT INTO gate_decisions (decision_id, revision_id, gate, aircraft_scope, decision_json) VALUES (?, ?, ?, ?, ?)")
        .run(`${revisionId}:${gate}:${aircraftScope}`, revisionId, gate, aircraftScope, JSON.stringify(normalized));
    }
    if (mission.postflight !== undefined) {
      const record = requireObject(mission.postflight, "postflight record");
      const revisionId = requiredText(record.revisionId, "postflight revisionId");
      if (!revisionsById.has(revisionId)) throw new Error(`postflight record does not belong to mission ${missionId}`);
      const telemetry = requireObject(record.telemetry, "postflight telemetry");
      if (telemetry.preserved !== true || !/^[a-f0-9]{64}$/.test(requiredText(telemetry.checksum, "postflight telemetry checksum"))) throw new Error("postflight telemetry preservation is invalid");
      const normalized = { revisionId, recordedAtUtc: requiredUtc(record.recordedAtUtc, "postflight recordedAtUtc"), recovery: requireObject(record.recovery, "postflight recovery"), battery: requireObject(record.battery, "postflight battery"), telemetry, debrief: requireObject(record.debrief, "postflight debrief") };
      database.prepare("INSERT INTO postflight_records (revision_id, record_json) VALUES (?, ?)")
        .run(revisionId, JSON.stringify(normalized));
    }
    for (const value of requireArray(mission.occurrences ?? [], "mission occurrences")) {
      const record = requireObject(value, "occurrence record");
      const occurrenceId = requiredText(record.occurrenceId, "occurrenceId");
      const revisionId = requiredText(record.revisionId, "occurrence revisionId");
      if (!revisionsById.has(revisionId)) throw new Error(`occurrence ${occurrenceId} does not belong to mission ${missionId}`);
      if (typeof record.reportable !== "boolean") throw new Error(`occurrence ${occurrenceId} reportability is invalid`);
      const normalized = { occurrenceId, revisionId, screenedAtUtc: requiredUtc(record.screenedAtUtc, "occurrence screenedAtUtc"), reportable: record.reportable, disposition: requiredText(record.disposition, "occurrence disposition"), ...(optionalText(record.details, "occurrence details") === undefined ? {} : { details: optionalText(record.details, "occurrence details") }) };
      database.prepare("INSERT INTO occurrences (occurrence_id, revision_id, record_json) VALUES (?, ?, ?)")
        .run(occurrenceId, revisionId, JSON.stringify(normalized));
    }
  }

  const packages = requireArray(parseLegacyJson(database, "package_store", []), "package_store");
  for (const value of packages) {
    const record = parsePackageRecord(value) as unknown as Record<string, unknown>;
    const packageId = requiredText(record.packageId, "packageId");
    const version = requiredText(record.version, "package version");
    const manifest = record.manifest === undefined ? undefined : requireObject(record.manifest, "package manifest");
    const kind = typeof manifest?.kind === "string" ? manifest.kind : null;
    const state = requiredText(record.state, "package state");
    database.prepare("INSERT INTO packages (package_id, version, kind, state, imported_at_utc, record_json) VALUES (?, ?, ?, ?, ?, ?)")
      .run(packageId, version, kind, state, requiredText(record.importedAtUtc, "package importedAtUtc"), JSON.stringify(record));
    if (state === "active" && kind !== null) {
      database.prepare("INSERT INTO active_package_roles (role, package_id, version) VALUES (?, ?, ?)").run(kind, packageId, version);
    }
  }
  const legacyAudit = database.prepare("SELECT 1 AS present FROM sqlite_master WHERE type = 'table' AND name = 'operational_audit_events'").get() as SqlRow | undefined;
  if (legacyAudit !== undefined) {
    database.exec(`INSERT INTO audit_events
      (sequence, event_id, type, actor_user_id, mission_revision_id, occurred_at_utc,
       action, reason, evidence_snapshot_id, client_session_id, schema_version,
       payload_json, previous_hash, hash)
      SELECT sequence, event_id, type, actor_user_id, mission_revision_id, occurred_at_utc,
       action, reason, evidence_snapshot_id, client_session_id, schema_version,
       payload_json, previous_hash, hash
      FROM operational_audit_events ORDER BY sequence`);
    database.exec("DROP TABLE operational_audit_events");
  }
  validateMigratedAuditChain(database);
  database.prepare("DELETE FROM service_state WHERE key IN ('mission_store', 'package_store')").run();
}

function validateMigratedAuditChain(database: SqlDatabase): void {
  const rows = database.prepare("SELECT * FROM audit_events ORDER BY sequence").all() as SqlRow[];
  let previousHash = GENESIS_HASH;
  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index]!;
    let payload: unknown;
    try {
      payload = JSON.parse(String(row.payload_json));
    } catch (error) {
      throw new Error(`audit payload ${index} is invalid JSON`, { cause: error });
    }
    if (payload === null || typeof payload !== "object" || Array.isArray(payload)) throw new Error(`audit payload ${index} must be an object`);
    const event = {
      sequence: Number(row.sequence),
      eventId: requiredText(row.event_id, "audit eventId"),
      type: requiredText(row.type, "audit type"),
      actorUserId: requiredText(row.actor_user_id, "audit actor"),
      ...(row.mission_revision_id === null ? {} : { missionRevisionId: requiredText(row.mission_revision_id, "audit mission revision") }),
      occurredAtUtc: requiredUtc(row.occurred_at_utc, "audit occurredAtUtc"),
      action: requiredText(row.action, "audit action"),
      reason: requiredText(row.reason, "audit reason"),
      ...(row.evidence_snapshot_id === null ? {} : { evidenceSnapshotId: requiredText(row.evidence_snapshot_id, "audit evidence snapshot") }),
      ...(row.client_session_id === null ? {} : { clientSessionId: requiredText(row.client_session_id, "audit client session") }),
      schemaVersion: Number(row.schema_version),
      payload: payload as Record<string, unknown>,
      previousHash: String(row.previous_hash),
    };
    const valid = event.sequence === index
      && Number.isInteger(event.schemaVersion) && event.schemaVersion > 0
      && /^[a-f0-9]{64}$/.test(event.previousHash)
      && event.previousHash === previousHash
      && /^[a-f0-9]{64}$/.test(String(row.hash))
      && hashAuditEvent(event) === row.hash;
    if (!valid) throw new Error(`migrated audit chain is invalid at sequence ${index}`);
    previousHash = String(row.hash);
  }
}

function sqliteConstructor(): new (path: string, options?: { enableForeignKeyConstraints?: boolean; timeout?: number; readOnly?: boolean }) => SqlDatabase {
  const sqlite = process.getBuiltinModule("node:sqlite") as
    | { DatabaseSync: new (path: string, options?: { enableForeignKeyConstraints?: boolean; timeout?: number; readOnly?: boolean }) => SqlDatabase }
    | undefined;
  if (sqlite === undefined) throw new Error("the Node.js built-in SQLite module is unavailable");
  return sqlite.DatabaseSync;
}

function backupTimestamp(value: string): string {
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) throw new Error("migration clock returned an invalid UTC timestamp");
  return parsed.toISOString().replace(/[-:.]/g, "");
}

function coherentBackup(database: SqlDatabase, databasePath: string, timestamp: string): string {
  const integrity = database.prepare("PRAGMA integrity_check").all() as SqlRow[];
  if (integrity.length !== 1 || String(Object.values(integrity[0] ?? {})[0]) !== "ok") {
    throw new Error("database integrity check failed before schema v2 migration");
  }
  const checkpoint = database.prepare("PRAGMA wal_checkpoint(FULL)").get() as SqlRow;
  if (Number(checkpoint.busy ?? 0) !== 0) throw new Error("database WAL could not be checkpointed for schema v2 migration");
  const stem = `${databasePath}.pre-v2-${timestamp}`;
  for (let collision = 0; collision < 10_000; collision += 1) {
    const candidate = `${stem}${collision === 0 ? "" : `-${collision}`}.sqlite`;
    try {
      copyFileSync(databasePath, candidate, constants.COPYFILE_EXCL);
      return candidate;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
    }
  }
  throw new Error("could not allocate a collision-safe schema v2 backup path");
}

function acquireLegacyDatabaseExclusion(database: SqlDatabase): void {
  database.prepare("PRAGMA locking_mode = EXCLUSIVE").get();
  try {
    database.exec("BEGIN EXCLUSIVE");
    database.exec("COMMIT");
  } catch (error) {
    try { database.exec("ROLLBACK"); } catch { /* The exclusive transaction did not begin. */ }
    throw new Error("schema-v1 migration requires the legacy service and every legacy database connection to be stopped", { cause: error });
  }
}

export function openDatabase(databaseUrl: string, lockTimeoutMs = 5_000, options: DatabaseOpenOptions = {}): EdgeDatabase {
  if (databaseUrl !== ":memory:") {
    mkdirSync(dirname(databaseUrl), { recursive: true });
  }
  const ownedMaintenanceLock = databaseUrl === ":memory:" || options.maintenanceLock !== undefined ? undefined : new MaintenanceLock(databaseUrl, lockTimeoutMs);
  ownedMaintenanceLock?.acquire();
  const maintenanceLock = options.maintenanceLock ?? ownedMaintenanceLock;
  const DatabaseSync = sqliteConstructor();
  let database: SqlDatabase | undefined;
  let backupPath: string | undefined;
  try {
    if (databaseUrl !== ":memory:") {
      assertMaintenanceLockOwnership(maintenanceLock, databaseUrl);
    }
    database = new DatabaseSync(databaseUrl, { enableForeignKeyConstraints: true, timeout: lockTimeoutMs });
    let edgeDatabase = new EdgeDatabase(database);
    const migratingLegacy = databaseUrl !== ":memory:" && existsSync(databaseUrl) && edgeDatabase.schemaVersion() === 1;
    if (migratingLegacy) {
      acquireLegacyDatabaseExclusion(database);
      backupPath = coherentBackup(database, databaseUrl, backupTimestamp((options.now ?? (() => new Date().toISOString()))()));
    }
    configureDatabase(database, lockTimeoutMs);
    edgeDatabase.migrate();
    if (migratingLegacy) {
      database.prepare("PRAGMA locking_mode = NORMAL").get();
      database.close();
      database = undefined;
      database = new DatabaseSync(databaseUrl, { enableForeignKeyConstraints: true, timeout: lockTimeoutMs });
      configureDatabase(database, lockTimeoutMs);
      edgeDatabase = new EdgeDatabase(database);
    }
    return edgeDatabase;
  } catch (error) {
    database?.close();
    if (backupPath !== undefined) {
      copyFileSync(backupPath, databaseUrl);
    }
    throw error;
  } finally {
    ownedMaintenanceLock?.release();
  }
}
