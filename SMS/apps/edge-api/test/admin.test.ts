import { chmodSync, lstatSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { generateKeyPairSync } from "node:crypto";
import { createRequire, syncBuiltinESMExports } from "node:module";
import { afterEach, describe, expect, it } from "vitest";
import { createDatabaseBackup, restoreDatabaseBackup, verifyDatabaseBackup } from "../src/admin/backup.js";
import { runAdminCli } from "../src/admin/cli.js";
import { RuntimeLease, RuntimeLeaseError } from "../src/admin/runtime-lease.js";
import { openDatabase } from "../src/db/migrate.js";
import { buildServer, type EdgeServer } from "../src/server.js";
import { AuditLedger } from "../src/audit/ledger.js";
import { LocalIdentityStore } from "../src/auth/identity.js";
import { MaintenanceLock } from "../src/admin/maintenance-lock.js";

const temporaryDirectories: string[] = [];
const runningServers: EdgeServer[] = [];
const isWindows = process.platform === "win32";

function paths(): { directory: string; database: string; backup: string } {
  const directory = mkdtempSync(join(tmpdir(), "sms-admin-"));
  temporaryDirectories.push(directory);
  return { directory, database: join(directory, "edge.sqlite"), backup: join(directory, "backup.sqlite") };
}

afterEach(async () => {
  for (const server of runningServers.splice(0)) await server.close();
  for (const directory of temporaryDirectories.splice(0)) rmSync(directory, { recursive: true, force: true });
});

describe("offline runtime lease and recovery", () => {
  it("allows one unexpired runtime lease and permits takeover only after expiry", () => {
    const database = openDatabase(":memory:");
    const first = new RuntimeLease(database, { holderId: "service-1", now: () => "2026-08-25T10:00:00.000Z", durationMs: 60_000 });
    first.acquire();

    expect(() => new RuntimeLease(database, { holderId: "admin-1", now: () => "2026-08-25T10:00:30.000Z", durationMs: 60_000 }).acquire()).toThrow(RuntimeLeaseError);
    expect(() => new RuntimeLease(database, { holderId: "admin-1", now: () => "2026-08-25T10:01:00.000Z", durationMs: 60_000 }).acquire()).not.toThrow();
    expect(database.sql().prepare("SELECT holder_id FROM runtime_lease").get()).toEqual({ holder_id: expect.stringMatching(/^admin-1:[a-f0-9]{32}$/) });
    database.close();
  });

  it("uses a unique operation nonce so equal holder labels are never reentrant", () => {
    const database = openDatabase(":memory:");
    const first = new RuntimeLease(database, { holderId: "edge-service:4242", now: () => "2026-08-25T10:00:00.000Z", durationMs: 60_000 });
    const duplicateLabel = new RuntimeLease(database, { holderId: "edge-service:4242", now: () => "2026-08-25T10:00:01.000Z", durationMs: 60_000 });
    first.acquire();

    expect(() => duplicateLabel.acquire()).toThrow(RuntimeLeaseError);
    first.release();
    database.close();
  });

  it("rejects renewal after expiry and advances a monotonic fencing token on takeover", () => {
    const database = openDatabase(":memory:");
    let now = "2026-08-25T10:00:00.000Z";
    const first = new RuntimeLease(database, { holderId: "service", now: () => now, durationMs: 60_000 });
    first.acquire();
    const firstRow = database.sql().prepare("SELECT fencing_token FROM runtime_lease WHERE singleton = 1").get();

    now = "2026-08-25T10:01:00.000Z";
    expect(() => first.renew()).toThrow(RuntimeLeaseError);
    const takeover = new RuntimeLease(database, { holderId: "admin", now: () => "2026-08-25T10:01:00.000Z", durationMs: 60_000 });
    takeover.acquire();
    const secondRow = database.sql().prepare("SELECT fencing_token FROM runtime_lease WHERE singleton = 1").get();

    expect(firstRow).toEqual({ fencing_token: 1 });
    expect(secondRow).toEqual({ fencing_token: 2 });
    takeover.release();
    database.close();
  });

  it("fences protected writes from a process whose lease was superseded", async () => {
    const { database: databasePath } = paths();
    const initialized = openDatabase(databasePath);
    initialized.close();
    const staleDatabase = openDatabase(databasePath);
    const takeoverDatabase = openDatabase(databasePath);
    const staleLease = new RuntimeLease(staleDatabase, { holderId: "service", now: () => "2026-08-25T10:00:00.000Z", durationMs: 60_000 });
    staleLease.acquire();
    new RuntimeLease(takeoverDatabase, { holderId: "admin", now: () => "2026-08-25T10:01:00.000Z", durationMs: 60_000 }).acquire();
    const staleAudit = new AuditLedger({ database: staleDatabase, now: () => "2026-08-25T10:01:01.000Z" });

    await expect(staleAudit.append({ type: "stale.write", actorUserId: "stale", action: "write", reason: "must be fenced" })).rejects.toThrow(/fenc|lease|safe|write/i);
    expect(takeoverDatabase.sql().prepare("SELECT COUNT(*) AS count FROM audit_events").get()).toEqual({ count: 0 });
    takeoverDatabase.close();
    staleDatabase.close();
  });

  it("fences identity writes from a process whose lease was superseded", () => {
    const { database: databasePath } = paths();
    const initialized = openDatabase(databasePath);
    initialized.close();
    const staleDatabase = openDatabase(databasePath);
    const takeoverDatabase = openDatabase(databasePath);
    const staleLease = new RuntimeLease(staleDatabase, { holderId: "service", now: () => "2026-08-25T10:00:00.000Z", durationMs: 60_000 });
    staleLease.acquire();
    new RuntimeLease(takeoverDatabase, { holderId: "admin", now: () => "2026-08-25T10:01:00.000Z", durationMs: 60_000 }).acquire();
    const identities = new LocalIdentityStore({ database: staleDatabase, now: () => "2026-08-25T10:01:01.000Z" });

    expect(() => identities.register({ userId: "stale", displayName: "Stale writer", roles: ["administrator"], password: "stale-password-value" })).toThrow(/fenc|lease|safe|write/i);
    expect(takeoverDatabase.sql().prepare("SELECT COUNT(*) AS count FROM identities").get()).toEqual({ count: 0 });
    takeoverDatabase.close();
    staleDatabase.close();
  });

  it("holds the write transaction before validating the fencing token", () => {
    const { database: databasePath } = paths();
    const initialized = openDatabase(databasePath);
    initialized.close();
    const staleDatabase = openDatabase(databasePath, 0);
    const takeoverDatabase = openDatabase(databasePath, 0);
    const staleLease = new RuntimeLease(staleDatabase, { holderId: "service", now: () => "2026-08-25T10:00:00.000Z", durationMs: 60_000 });
    staleLease.acquire();
    const identities = new LocalIdentityStore({ database: staleDatabase, now: () => "2026-08-25T10:00:00.000Z" });
    identities.register({ userId: "race-user", displayName: "Race User", roles: ["operator"], missionIds: ["mission-1"], password: "race-user-password" });
    const takeover = new RuntimeLease(takeoverDatabase, { holderId: "admin", now: () => "2026-08-25T10:01:00.000Z", durationMs: 60_000 });
    const originalFenceCheck = staleDatabase.assertFencingToken.bind(staleDatabase);
    staleDatabase.assertFencingToken = () => {
      originalFenceCheck();
      takeover.acquire();
    };

    expect(() => identities.assign("race-user", { roles: ["reviewer"], missionIds: ["mission-2"], qualificationRefs: [] })).toThrow(/lock|lease|fenc|transaction/i);
    expect(takeoverDatabase.sql().prepare("SELECT role FROM identity_roles WHERE user_id = 'race-user'").all()).toEqual([{ role: "operator" }]);
    takeoverDatabase.close();
    staleDatabase.close();
  });

  it("creates a verified backup and restores its exact operational state", () => {
    const { database: databasePath, backup } = paths();
    const database = openDatabase(databasePath);
    database.sql().prepare("INSERT INTO identities (user_id, display_name) VALUES (?, ?)").run("admin-1", "Administrator");
    database.close();

    const created = createDatabaseBackup(databasePath, backup);
    expect(created.sha256).toMatch(/^[a-f0-9]{64}$/);
    expect(verifyDatabaseBackup(backup)).toMatchObject({ ok: true, schemaVersion: 3, sha256: created.sha256 });
    const changed = openDatabase(databasePath);
    changed.sql().prepare("DELETE FROM identities").run();
    changed.close();

    restoreDatabaseBackup(backup, databasePath);

    const restored = openDatabase(databasePath);
    expect(restored.sql().prepare("SELECT user_id FROM identities").get()).toEqual({ user_id: "admin-1" });
    restored.close();
  });

  it("rejects corrupt backup bytes without replacing the target", () => {
    const { database: databasePath, backup } = paths();
    const database = openDatabase(databasePath);
    database.close();
    const original = readFileSync(databasePath);
    writeFileSync(backup, "not a sqlite database");

    expect(() => restoreDatabaseBackup(backup, databasePath)).toThrow(/backup|integrity/i);
    expect(readFileSync(databasePath)).toEqual(original);
  });

  it("rejects a symlink backup source instead of reopening a replaceable path", () => {
    const { directory, database: databasePath, backup } = paths();
    const database = openDatabase(databasePath);
    database.close();
    createDatabaseBackup(databasePath, backup);
    const link = join(directory, "replaceable-backup.sqlite");
    symlinkSync(backup, link);

    expect(() => restoreDatabaseBackup(link, databasePath)).toThrow(/symbolic|symlink|nofollow|regular|backup/i);
  });

  it("rejects a symlink database target without replacing the alias or missing the protected database", () => {
    const { directory, database: databasePath, backup } = paths();
    const initial = openDatabase(databasePath);
    initial.sql().prepare("INSERT INTO identities (user_id, display_name) VALUES ('restore-marker', 'Before')").run();
    initial.close();
    createDatabaseBackup(databasePath, backup);
    const changed = openDatabase(databasePath);
    changed.sql().prepare("UPDATE identities SET display_name = 'After' WHERE user_id = 'restore-marker'").run();
    changed.close();
    const alias = join(directory, "database-alias.sqlite");
    symlinkSync(databasePath, alias);

    expect(() => restoreDatabaseBackup(backup, alias)).toThrow(/symbolic|symlink|target|database/i);
    expect(lstatSync(alias).isSymbolicLink()).toBe(true);
    const protectedDatabase = openDatabase(databasePath);
    expect(protectedDatabase.sql().prepare("SELECT display_name FROM identities WHERE user_id = 'restore-marker'").get()).toEqual({ display_name: "After" });
    protectedDatabase.close();
  });

  it.skipIf(isWindows)("fsyncs POSIX rollback files and their directory before reporting restore failure", () => {
    const { database: databasePath, backup } = paths();
    const database = openDatabase(databasePath);
    database.sql().prepare("INSERT INTO identities (user_id, display_name) VALUES ('before-backup', 'Before Backup')").run();
    database.close();
    createDatabaseBackup(databasePath, backup);
    const changed = openDatabase(databasePath);
    changed.sql().prepare("INSERT INTO identities (user_id, display_name) VALUES ('must-survive', 'Must Survive')").run();
    changed.close();
    const original = readFileSync(databasePath);
    const mutableFs = createRequire(import.meta.url)("node:fs") as { fsyncSync(fd: number): void };
    const originalFsync = mutableFs.fsyncSync;
    let calls = 0;
    mutableFs.fsyncSync = (descriptor: number) => {
      calls += 1;
      if (calls === 2) throw new Error("injected post-replacement fsync failure");
      originalFsync(descriptor);
    };
    syncBuiltinESMExports();
    try {
      expect(() => restoreDatabaseBackup(backup, databasePath)).toThrow(/injected.*fsync|restore/i);
      expect(readFileSync(databasePath)).toEqual(original);
      expect(calls).toBeGreaterThanOrEqual(4);
    } finally {
      mutableFs.fsyncSync = originalFsync;
      syncBuiltinESMExports();
    }
  });

  it("never overwrites an existing backup output", () => {
    const { database: databasePath, backup } = paths();
    const database = openDatabase(databasePath);
    database.close();
    writeFileSync(backup, "reserved backup path");

    expect(() => createDatabaseBackup(databasePath, backup)).toThrow(/exist|overwrite|backup/i);
    expect(readFileSync(backup, "utf8")).toBe("reserved backup path");
  });

  it("rejects a backup from an unsupported future schema", () => {
    const { database: databasePath, backup } = paths();
    const database = openDatabase(databasePath);
    database.sql().prepare("INSERT INTO schema_migrations (version, applied_at_utc) VALUES (99, ?)").run("2026-08-25T00:00:00.000Z");
    database.close();
    writeFileSync(backup, readFileSync(databasePath));

    expect(() => verifyDatabaseBackup(backup)).toThrow(/unsupported|schema/i);
  });
});

describe("sms-admin secret boundary", () => {
  it("rejects password or secret values carried in argv", async () => {
    const io = { stdin: async () => "unused", stdout: () => undefined, stderr: () => undefined };

    await expect(runAdminCli(["init", "--database", ":memory:", "--password", "visible-secret"], io)).rejects.toThrow(/argv|secret/i);
    await expect(runAdminCli(["users", "create", "--database", ":memory:", "password=visible-secret"], io)).rejects.toThrow(/argv|secret/i);
  });

  it("bootstraps an administrator from stdin and applies durable user mutations", async () => {
    const { database } = paths();
    const output: string[] = [];
    const io = { stdin: async () => "correct horse battery staple\n", stdout: (message: string) => output.push(message), stderr: () => undefined };

    await expect(runAdminCli(["init", "--database", database, "--user-id", "admin-1", "--display-name", "Administrator", "--password-stdin"], io)).resolves.toBe(0);
    await expect(runAdminCli(["users", "create", "--database", database, "--user-id", "operator-1", "--display-name", "Operator", "--roles", "operator", "--mission-ids", "mission-1", "--password-stdin"], io)).resolves.toBe(0);
    await expect(runAdminCli(["users", "disable", "--database", database, "--user-id", "operator-1"], io)).resolves.toBe(0);

    const reopened = openDatabase(database);
    expect(reopened.sql().prepare("SELECT user_id FROM identity_roles WHERE role = 'administrator'").get()).toEqual({ user_id: "admin-1" });
    expect(reopened.sql().prepare("SELECT disabled_at_utc FROM identities WHERE user_id = 'operator-1'").get()).toEqual({ disabled_at_utc: expect.stringMatching(/Z$/) });
    expect(output.join("\n")).not.toContain("correct horse battery staple");
    reopened.close();
  });

  it.skipIf(isWindows)("enforces POSIX password-file modes and never echoes its contents", async () => {
    const { directory, database } = paths();
    const passwordFile = join(directory, "password.txt");
    writeFileSync(passwordFile, "protected-password\n");
    chmodSync(passwordFile, 0o644);
    const io = { stdin: async () => "", stdout: () => undefined, stderr: () => undefined };

    await expect(runAdminCli(["init", "--database", database, "--user-id", "admin-1", "--display-name", "Administrator", "--password-file", passwordFile], io)).rejects.toThrow(/permission|protected|mode/i);

    chmodSync(passwordFile, 0o600);
    await expect(runAdminCli(["init", "--database", database, "--user-id", "admin-1", "--display-name", "Administrator", "--password-file", passwordFile], io)).resolves.toBe(0);
  });

  it("rejects a password-file symlink even when its target is protected", async () => {
    const { directory, database } = paths();
    const target = join(directory, "password-target.txt");
    const link = join(directory, "password-link.txt");
    writeFileSync(target, "protected-password\n");
    chmodSync(target, 0o600);
    symlinkSync(target, link);
    const io = { stdin: async () => "", stdout: () => undefined, stderr: () => undefined };

    await expect(runAdminCli(["init", "--database", database, "--user-id", "admin-1", "--display-name", "Administrator", "--password-file", link], io)).rejects.toThrow(/symbolic|nofollow|regular|protected/i);
  });

  it("requires explicit piped stdin or a masked TTY prompt", async () => {
    const first = paths();
    const implicit = { stdin: async () => "implicit-password", stdinIsTty: () => false, stdout: () => undefined, stderr: () => undefined };
    await expect(runAdminCli(["init", "--database", first.database, "--user-id", "admin-1", "--display-name", "Administrator"], implicit)).rejects.toThrow(/password.stdin|prompt|source/i);

    const second = paths();
    const ttyViaStdin = { stdin: async () => "echoed-password", stdinIsTty: () => true, promptSecret: async () => "unused", stdout: () => undefined, stderr: () => undefined };
    await expect(runAdminCli(["init", "--database", second.database, "--user-id", "admin-1", "--display-name", "Administrator", "--password-stdin"], ttyViaStdin)).rejects.toThrow(/pipe|tty|prompt/i);

    const third = paths();
    const output: string[] = [];
    const prompted = { stdin: async () => "unused", stdinIsTty: () => true, promptSecret: async () => "masked-prompt-password", stdout: (message: string) => output.push(message), stderr: (message: string) => output.push(message) };
    await expect(runAdminCli(["init", "--database", third.database, "--user-id", "admin-1", "--display-name", "Administrator"], prompted)).resolves.toBe(0);
    expect(output.join("\n")).not.toContain("masked-prompt-password");
  });

  it("refuses offline mutations while the service runtime lease is live", async () => {
    const { database } = paths();
    const opened = openDatabase(database);
    const serviceLease = new RuntimeLease(opened, { holderId: "edge-service", durationMs: 60_000 });
    serviceLease.acquire();
    const io = { stdin: async () => "correct horse battery staple", stdout: () => undefined, stderr: () => undefined };

    await expect(runAdminCli(["init", "--database", database, "--user-id", "admin-1", "--display-name", "Administrator", "--password-stdin"], io)).rejects.toThrow(/lease|service|stopped/i);

    serviceLease.release();
    opened.close();
  });

  it("runs backup create, verify, restore, and diagnose offline", async () => {
    const { database, backup } = paths();
    const output: string[] = [];
    const io = { stdin: async () => "correct horse battery staple", stdout: (message: string) => output.push(message), stderr: () => undefined };
    await runAdminCli(["init", "--database", database, "--user-id", "admin-1", "--display-name", "Administrator", "--password-stdin"], io);

    await expect(runAdminCli(["backup", "create", "--database", database, "--output", backup], io)).resolves.toBe(0);
    await expect(runAdminCli(["backup", "verify", "--input", backup], io)).resolves.toBe(0);
    await expect(runAdminCli(["backup", "restore", "--database", database, "--input", backup], io)).resolves.toBe(0);
    await expect(runAdminCli(["diagnose", "--database", database], io)).resolves.toBe(0);
    expect(output.join("\n")).toMatch(/"ok":true/);
  });

  it("restores a valid backup over a physically corrupt target", async () => {
    const { database, backup } = paths();
    const opened = openDatabase(database);
    opened.sql().prepare("INSERT INTO identities (user_id, display_name) VALUES ('admin-1', 'Administrator')").run();
    opened.close();
    createDatabaseBackup(database, backup);
    writeFileSync(database, "physically corrupt database bytes");
    const io = { stdin: async () => "", stdout: () => undefined, stderr: () => undefined };

    await expect(runAdminCli(["backup", "restore", "--database", database, "--input", backup], io)).resolves.toBe(0);

    const restored = openDatabase(database);
    expect(restored.sql().prepare("SELECT display_name FROM identities WHERE user_id = 'admin-1'").get()).toEqual({ display_name: "Administrator" });
    restored.close();
  });

  it("blocks restore for a live service even if its target lease row is tampered away", async () => {
    const { database, backup } = paths();
    const initialized = openDatabase(database);
    initialized.close();
    createDatabaseBackup(database, backup);
    const server = await buildServer({ databaseUrl: database, packageDirectory: join(paths().directory, "packages") });
    runningServers.push(server);
    server.edgeDatabase.sql().prepare("DELETE FROM runtime_lease").run();
    const io = { stdin: async () => "", stdout: () => undefined, stderr: () => undefined };

    await expect(runAdminCli(["backup", "restore", "--database", database, "--input", backup], io)).rejects.toThrow(/service|maintenance|lock|stopped/i);
  });

  it("enforces the maintenance lock in the restore boundary itself", async () => {
    const { database, backup } = paths();
    const initialized = openDatabase(database);
    initialized.close();
    createDatabaseBackup(database, backup);
    const server = await buildServer({ databaseUrl: database, packageDirectory: join(paths().directory, "packages") });
    runningServers.push(server);

    expect(() => restoreDatabaseBackup(backup, database)).toThrow(/service|maintenance|lock|stopped/i);
  });

  it("rejects an unacquired or wrong-target maintenance-lock object", () => {
    const first = paths();
    const second = paths();
    const initialized = openDatabase(first.database);
    initialized.close();
    createDatabaseBackup(first.database, first.backup);
    const realOwner = new MaintenanceLock(first.database);
    realOwner.acquire();
    try {
      const unacquired = new MaintenanceLock(first.database);
      expect(() => restoreDatabaseBackup(first.backup, first.database, unacquired)).toThrow(/acquir|owner|maintenance|lock/i);
      expect(() => openDatabase(first.database, 5_000, { maintenanceLock: unacquired })).toThrow(/acquir|owner|maintenance|lock/i);
      Object.assign(unacquired, { assertAcquiredFor: () => undefined });
      expect(() => restoreDatabaseBackup(first.backup, first.database, unacquired)).toThrow(/acquir|owner|maintenance|lock/i);
      expect(() => openDatabase(first.database, 5_000, { maintenanceLock: unacquired })).toThrow(/acquir|owner|maintenance|lock/i);
      expect(() => restoreDatabaseBackup(first.backup, second.database, realOwner)).toThrow(/target|maintenance|lock/i);
    } finally {
      realOwner.release();
    }
  });

  it("adds and lists trust anchors and lists offline package state", async () => {
    const { directory, database } = paths();
    const publicKeyFile = join(directory, "trust.pem");
    const keys = generateKeyPairSync("ed25519");
    writeFileSync(publicKeyFile, keys.publicKey.export({ type: "spki", format: "pem" }));
    const output: string[] = [];
    const io = { stdin: async () => "correct horse battery staple", stdout: (message: string) => output.push(message), stderr: () => undefined };
    await runAdminCli(["init", "--database", database, "--user-id", "admin-1", "--display-name", "Administrator", "--password-stdin"], io);

    await expect(runAdminCli(["trust", "add", "--database", database, "--key-id", "policy-key-1", "--scope", "policy", "--algorithm", "ed25519", "--public-key-file", publicKeyFile, "--added-by", "admin-1"], io)).resolves.toBe(0);
    await expect(runAdminCli(["trust", "list", "--database", database], io)).resolves.toBe(0);
    await expect(runAdminCli(["packages", "list", "--database", database, "--package-directory", directory], io)).resolves.toBe(0);

    expect(output.join("\n")).toContain("policy-key-1");
  });
});
