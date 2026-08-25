import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { openDatabase } from "../src/db/migrate.js";
import { GENESIS_HASH, hashAuditEvent } from "../src/audit/ledger.js";
import { missionFixture } from "./mission-fixture.js";

const temporaryDirectories: string[] = [];

function temporaryDatabasePath(): string {
  const directory = mkdtempSync(join(tmpdir(), "sms-schema-v2-"));
  temporaryDirectories.push(directory);
  return join(directory, "edge.sqlite");
}

function createSchemaV1(databasePath: string, missionStore = "[]"): void {
  const sqlite = process.getBuiltinModule("node:sqlite") as {
    DatabaseSync: new (path: string) => {
      exec(sql: string): void;
      prepare(sql: string): { run(...bindings: readonly unknown[]): unknown };
      close(): void;
    };
  };
  const database = new sqlite.DatabaseSync(databasePath);
  database.exec(`
    CREATE TABLE schema_migrations (
      version INTEGER PRIMARY KEY CHECK (version > 0),
      applied_at_utc TEXT NOT NULL
    ) STRICT;
    CREATE TABLE service_state (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    ) STRICT;
  `);
  database.prepare("INSERT INTO schema_migrations (version, applied_at_utc) VALUES (1, ?)")
    .run("2026-08-24T00:00:00.000Z");
  database.prepare("INSERT INTO service_state (key, value) VALUES ('mission_store', ?)").run(missionStore);
  database.close();
}

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) rmSync(directory, { recursive: true, force: true });
});

describe("edge operational database", () => {
  it("enables foreign keys and records the current schema version", () => {
    const database = openDatabase(":memory:");

    expect(database.pragma("foreign_keys")).toBe(1);
    expect(database.schemaVersion()).toBe(2);
    expect(database.tableNames()).toEqual([
      "active_package_roles",
      "audit_events",
      "checklist_responses",
      "credential_versions",
      "evaluation_envelopes",
      "gate_decisions",
      "identities",
      "identity_roles",
      "login_lockout_state",
      "mission_assignments",
      "mission_revisions",
      "missions",
      "occurrences",
      "package_state_generation",
      "packages",
      "postflight_records",
      "runtime_lease",
      "schema_migrations",
      "service_state",
      "sessions",
      "trusted_keys",
    ]);

    database.close();
  });

  it("can rerun migrations without changing the schema", () => {
    const database = openDatabase(":memory:");
    const firstVersion = database.schemaVersion();

    database.migrate();

    expect(database.schemaVersion()).toBe(firstVersion);
    expect(database.tableNames()).toHaveLength(21);
    database.close();
  });

  it("backs up schema v1 bytes before a successful normalized migration", () => {
    const databasePath = temporaryDatabasePath();
    createSchemaV1(databasePath);
    const originalBytes = readFileSync(databasePath);

    const database = openDatabase(databasePath, 5_000, { now: () => "2026-08-25T01:02:03.004Z" });

    expect(database.schemaVersion()).toBe(2);
    database.close();
    const backupPath = `${databasePath}.pre-v2-20260825T010203004Z.sqlite`;
    expect(readFileSync(backupPath)).toEqual(originalBytes);
  });

  it("captures committed schema-v1 WAL state in the retained migration backup", () => {
    const databasePath = temporaryDatabasePath();
    createSchemaV1(databasePath);
    const sqlite = process.getBuiltinModule("node:sqlite") as {
      DatabaseSync: new (path: string) => {
        exec(sql: string): void;
        prepare(sql: string): { run(...bindings: readonly unknown[]): unknown; get(...bindings: readonly unknown[]): unknown };
        close(): void;
      };
    };
    const live = new sqlite.DatabaseSync(databasePath);
    live.exec("PRAGMA journal_mode=WAL; PRAGMA wal_autocheckpoint=0");
    const mission = missionFixture();
    const latest = JSON.stringify([{ missionId: mission.missionId, revisions: [mission], safetyResults: [], checklistResponses: [], approvals: [], occurrences: [] }]);
    live.prepare("UPDATE service_state SET value = ? WHERE key = 'mission_store'").run(latest);

    const migrated = openDatabase(databasePath, 5_000, { now: () => "2026-08-25T01:02:03.004Z" });
    migrated.close();
    const backupPath = `${databasePath}.pre-v2-20260825T010203004Z.sqlite`;
    const backup = new sqlite.DatabaseSync(backupPath);
    expect(backup.prepare("SELECT value FROM service_state WHERE key = 'mission_store'").get()).toEqual({ value: latest });
    backup.close();
    live.close();
  });

  it("publishes a collision-safe migration backup without overwriting an existing path", () => {
    const databasePath = temporaryDatabasePath();
    createSchemaV1(databasePath);
    const reserved = `${databasePath}.pre-v2-20260825T010203004Z.sqlite`;
    writeFileSync(reserved, "existing recovery artifact");

    const migrated = openDatabase(databasePath, 5_000, { now: () => "2026-08-25T01:02:03.004Z" });
    migrated.close();

    expect(readFileSync(reserved, "utf8")).toBe("existing recovery artifact");
    expect(readdirSync(join(databasePath, "..")).some((name) => name.startsWith("edge.sqlite.pre-v2-20260825T010203004Z-") && name.endsWith(".sqlite"))).toBe(true);
  });

  it("restores exact schema v1 bytes and retains the backup when normalization fails", () => {
    const databasePath = temporaryDatabasePath();
    createSchemaV1(databasePath, "{not-json");
    const originalBytes = readFileSync(databasePath);

    expect(() => openDatabase(databasePath, 5_000, { now: () => "2026-08-25T01:02:03.004Z" }))
      .toThrow(/mission_store/i);

    const backupPath = `${databasePath}.pre-v2-20260825T010203004Z.sqlite`;
    expect(readFileSync(databasePath)).toEqual(originalBytes);
    expect(readFileSync(backupPath)).toEqual(originalBytes);
    expect(readdirSync(join(databasePath, ".."))).toContain("edge.sqlite.pre-v2-20260825T010203004Z.sqlite");
  });

  it("normalizes schema v1 mission JSON and the legacy audit chain without loss", () => {
    const databasePath = temporaryDatabasePath();
    const mission = missionFixture();
    createSchemaV1(databasePath, JSON.stringify([{ missionId: mission.missionId, revisions: [mission], safetyResults: [], checklistResponses: [], approvals: [], occurrences: [] }]));
    const sqlite = process.getBuiltinModule("node:sqlite") as { DatabaseSync: new (path: string) => { exec(sql: string): void; prepare(sql: string): { run(...bindings: readonly unknown[]): unknown }; close(): void } };
    const legacy = new sqlite.DatabaseSync(databasePath);
    legacy.exec(`CREATE TABLE operational_audit_events (
      sequence INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, type TEXT NOT NULL,
      actor_user_id TEXT NOT NULL, mission_revision_id TEXT, occurred_at_utc TEXT NOT NULL,
      action TEXT NOT NULL, reason TEXT NOT NULL, evidence_snapshot_id TEXT, client_session_id TEXT,
      schema_version INTEGER NOT NULL, payload_json TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL
    ) STRICT`);
    const body = { sequence: 0, eventId: "mission.created:0", type: "mission.created", actorUserId: "commander-1", missionRevisionId: mission.id, occurredAtUtc: "2026-08-24T00:00:00.000Z", action: "create", reason: "legacy fixture", clientSessionId: "legacy-session", schemaVersion: 1, payload: { missionId: mission.missionId }, previousHash: GENESIS_HASH };
    legacy.prepare(`INSERT INTO operational_audit_events
      (sequence, event_id, type, actor_user_id, mission_revision_id, occurred_at_utc, action, reason,
       evidence_snapshot_id, client_session_id, schema_version, payload_json, previous_hash, hash)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .run(body.sequence, body.eventId, body.type, body.actorUserId, body.missionRevisionId, body.occurredAtUtc, body.action, body.reason, null, body.clientSessionId, body.schemaVersion, JSON.stringify(body.payload), body.previousHash, hashAuditEvent(body));
    legacy.close();

    const migrated = openDatabase(databasePath, 5_000, { now: () => "2026-08-25T01:02:03.004Z" });

    expect(JSON.parse(String((migrated.sql().prepare("SELECT revision_json FROM mission_revisions WHERE revision_id = ?").get(mission.id) as { revision_json: string }).revision_json))).toEqual(mission);
    expect(migrated.sql().prepare("SELECT event_id, hash FROM audit_events WHERE sequence = 0").get()).toEqual({ event_id: body.eventId, hash: hashAuditEvent(body) });
    expect(migrated.tableNames()).not.toContain("operational_audit_events");
    migrated.close();
  });

  it("restores v1 when a legacy mission revision violates full domain semantics", () => {
    const databasePath = temporaryDatabasePath();
    const malformed = { ...missionFixture(), evidenceSnapshotId: "" };
    createSchemaV1(databasePath, JSON.stringify([{ missionId: malformed.missionId, revisions: [malformed], safetyResults: [], checklistResponses: [], approvals: [], occurrences: [] }]));
    const original = readFileSync(databasePath);

    expect(() => openDatabase(databasePath, 5_000, { now: () => "2026-08-25T02:00:00.000Z" })).toThrow(/mission|revision|evidenceSnapshotId|too_small/i);
    expect(readFileSync(databasePath)).toEqual(original);
  });

  it("restores v1 when legacy checklist ownership violates mission invariants", () => {
    const databasePath = temporaryDatabasePath();
    const mission = missionFixture();
    const checklistResponses = [{
      responseId: "check-1", revisionId: mission.id, itemId: "weather-reviewed", response: "yes",
      actorUserId: "unassigned-user", occurredAtUtc: "2026-08-25T02:00:00.000Z",
    }];
    createSchemaV1(databasePath, JSON.stringify([{ missionId: mission.missionId, revisions: [mission], safetyResults: [], checklistResponses, approvals: [], occurrences: [] }]));
    const original = readFileSync(databasePath);

    expect(() => openDatabase(databasePath, 5_000, { now: () => "2026-08-25T02:00:00.000Z" })).toThrow(/checklist|actor|crew|mission/i);
    expect(readFileSync(databasePath)).toEqual(original);
  });

  it("restores v1 when a legacy package record is not a valid durable package", () => {
    const databasePath = temporaryDatabasePath();
    createSchemaV1(databasePath);
    const sqlite = process.getBuiltinModule("node:sqlite") as { DatabaseSync: new (path: string) => { prepare(sql: string): { run(...bindings: readonly unknown[]): unknown }; close(): void } };
    const legacy = new sqlite.DatabaseSync(databasePath);
    legacy.prepare("INSERT INTO service_state (key, value) VALUES ('package_store', ?)")
      .run(JSON.stringify([{ packageId: "policy-one", version: "1.0.0", state: "active", importedAtUtc: "2026-08-25T00:00:00.000Z", manifest: {} }]));
    legacy.close();
    const original = readFileSync(databasePath);

    expect(() => openDatabase(databasePath, 5_000, { now: () => "2026-08-25T02:00:00.000Z" })).toThrow(/package|manifest/i);
    expect(readFileSync(databasePath)).toEqual(original);
  });

  it("restores v1 when the migrated audit hash chain is semantically invalid", () => {
    const databasePath = temporaryDatabasePath();
    createSchemaV1(databasePath);
    const sqlite = process.getBuiltinModule("node:sqlite") as { DatabaseSync: new (path: string) => { exec(sql: string): void; prepare(sql: string): { run(...bindings: readonly unknown[]): unknown }; close(): void } };
    const legacy = new sqlite.DatabaseSync(databasePath);
    legacy.exec(`CREATE TABLE operational_audit_events (
      sequence INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, type TEXT NOT NULL,
      actor_user_id TEXT NOT NULL, mission_revision_id TEXT, occurred_at_utc TEXT NOT NULL,
      action TEXT NOT NULL, reason TEXT NOT NULL, evidence_snapshot_id TEXT, client_session_id TEXT,
      schema_version INTEGER NOT NULL, payload_json TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL
    ) STRICT`);
    legacy.prepare(`INSERT INTO operational_audit_events
      (sequence, event_id, type, actor_user_id, occurred_at_utc, action, reason, schema_version, payload_json, previous_hash, hash)
      VALUES (0, 'bad:0', 'bad', 'fixture', '2026-08-25T00:00:00.000Z', 'create', 'fixture', 1, '{}', ?, ?)`)
      .run(GENESIS_HASH, "f".repeat(64));
    legacy.close();
    const original = readFileSync(databasePath);

    expect(() => openDatabase(databasePath, 5_000, { now: () => "2026-08-25T02:00:00.000Z" })).toThrow(/audit|hash|chain/i);
    expect(readFileSync(databasePath)).toEqual(original);
  });
});
