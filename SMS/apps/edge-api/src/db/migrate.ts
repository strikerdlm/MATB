import { copyFileSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname } from "node:path";
import { configureDatabase, MIGRATIONS, SCHEMA_VERSION } from "./schema.js";
import type { SqlDatabase } from "./schema.js";

type SqlRow = Record<string, unknown>;

export interface DatabaseOpenOptions {
  readonly now?: () => string;
}

export class EdgeDatabase {
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
  if (typeof value !== "string" || value.trim() === "") throw new Error(`${field} must be non-empty text`);
  return value;
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
    for (const revision of revisions) {
      const revisionId = requiredText(revision.id, "mission revision id");
      const revisionNumber = Number(revision.revision);
      if (!Number.isInteger(revisionNumber) || revisionNumber < 0) throw new Error(`mission revision ${revisionId} is invalid`);
      database.prepare("INSERT INTO mission_revisions (revision_id, mission_id, revision, revision_json) VALUES (?, ?, ?, ?)")
        .run(revisionId, missionId, revisionNumber, JSON.stringify(revision));
    }
    for (const value of requireArray(mission.safetyResults ?? [], "mission safetyResults")) {
      const result = requireObject(value, "mission safety result");
      const envelope = requireObject(result.envelope, "mission safety envelope");
      database.prepare("INSERT INTO evaluation_envelopes (revision_id, envelope_json, stale) VALUES (?, ?, ?)")
        .run(requiredText(envelope.revisionId, "evaluation revisionId"), JSON.stringify(envelope), result.stale === true ? 1 : 0);
    }
    for (const value of requireArray(mission.checklistResponses ?? [], "mission checklistResponses")) {
      const response = requireObject(value, "checklist response");
      database.prepare("INSERT INTO checklist_responses (response_id, revision_id, item_id, response_json) VALUES (?, ?, ?, ?)")
        .run(requiredText(response.responseId, "checklist responseId"), requiredText(response.revisionId, "checklist revisionId"), requiredText(response.itemId, "checklist itemId"), JSON.stringify(response));
    }
    for (const value of requireArray(mission.approvals ?? [], "mission approvals")) {
      const decision = requireObject(value, "gate decision");
      const revisionId = requiredText(decision.missionRevisionId, "gate revisionId");
      const gate = requiredText(decision.gate, "gate");
      const aircraftScope = typeof decision.aircraftId === "string" ? decision.aircraftId : "";
      database.prepare("INSERT INTO gate_decisions (decision_id, revision_id, gate, aircraft_scope, decision_json) VALUES (?, ?, ?, ?, ?)")
        .run(`${revisionId}:${gate}:${aircraftScope}`, revisionId, gate, aircraftScope, JSON.stringify(decision));
    }
    if (mission.postflight !== undefined) {
      const record = requireObject(mission.postflight, "postflight record");
      database.prepare("INSERT INTO postflight_records (revision_id, record_json) VALUES (?, ?)")
        .run(requiredText(record.revisionId, "postflight revisionId"), JSON.stringify(record));
    }
    for (const value of requireArray(mission.occurrences ?? [], "mission occurrences")) {
      const record = requireObject(value, "occurrence record");
      database.prepare("INSERT INTO occurrences (occurrence_id, revision_id, record_json) VALUES (?, ?, ?)")
        .run(requiredText(record.occurrenceId, "occurrenceId"), requiredText(record.revisionId, "occurrence revisionId"), JSON.stringify(record));
    }
  }

  const packages = requireArray(parseLegacyJson(database, "package_store", []), "package_store");
  for (const value of packages) {
    const record = requireObject(value, "package record");
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
  database.prepare("DELETE FROM service_state WHERE key IN ('mission_store', 'package_store')").run();
}

function sqliteConstructor(): new (path: string, options?: { enableForeignKeyConstraints?: boolean; timeout?: number; readOnly?: boolean }) => SqlDatabase {
  const sqlite = process.getBuiltinModule("node:sqlite") as
    | { DatabaseSync: new (path: string, options?: { enableForeignKeyConstraints?: boolean; timeout?: number; readOnly?: boolean }) => SqlDatabase }
    | undefined;
  if (sqlite === undefined) throw new Error("the Node.js built-in SQLite module is unavailable");
  return sqlite.DatabaseSync;
}

function integrityCheck(databasePath: string): void {
  const DatabaseSync = sqliteConstructor();
  const database = new DatabaseSync(databasePath, { readOnly: true });
  try {
    const rows = database.prepare("PRAGMA integrity_check").all() as SqlRow[];
    if (rows.length !== 1 || String(Object.values(rows[0] ?? {})[0]) !== "ok") {
      throw new Error("database integrity check failed");
    }
  } finally {
    database.close();
  }
}

function schemaVersionAtPath(databasePath: string): number {
  const DatabaseSync = sqliteConstructor();
  const database = new DatabaseSync(databasePath, { readOnly: true });
  try {
    const table = database.prepare("SELECT 1 AS present FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'").get() as SqlRow | undefined;
    if (table === undefined) return 0;
    const row = database.prepare("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations").get() as SqlRow;
    return Number(row.version);
  } finally {
    database.close();
  }
}

function backupTimestamp(value: string): string {
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) throw new Error("migration clock returned an invalid UTC timestamp");
  return parsed.toISOString().replace(/[-:.]/g, "");
}

export function openDatabase(databaseUrl: string, lockTimeoutMs = 5_000, options: DatabaseOpenOptions = {}): EdgeDatabase {
  if (databaseUrl !== ":memory:") {
    mkdirSync(dirname(databaseUrl), { recursive: true });
  }
  let backupPath: string | undefined;
  if (databaseUrl !== ":memory:" && existsSync(databaseUrl) && schemaVersionAtPath(databaseUrl) === 1) {
    backupPath = `${databaseUrl}.pre-v2-${backupTimestamp((options.now ?? (() => new Date().toISOString()))())}.sqlite`;
    copyFileSync(databaseUrl, backupPath);
    try {
      integrityCheck(databaseUrl);
    } catch (error) {
      throw new Error("database integrity check failed before schema v2 migration", { cause: error });
    }
  }
  const DatabaseSync = sqliteConstructor();
  const database = new DatabaseSync(databaseUrl, {
    enableForeignKeyConstraints: true,
    timeout: lockTimeoutMs,
  });
  try {
    configureDatabase(database, lockTimeoutMs);
    const edgeDatabase = new EdgeDatabase(database);
    edgeDatabase.migrate();
    return edgeDatabase;
  } catch (error) {
    database.close();
    if (backupPath !== undefined) {
      rmSync(`${databaseUrl}-wal`, { force: true });
      rmSync(`${databaseUrl}-shm`, { force: true });
      copyFileSync(backupPath, databaseUrl);
    }
    throw error;
  }
}
