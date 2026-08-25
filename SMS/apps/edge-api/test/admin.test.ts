import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { generateKeyPairSync } from "node:crypto";
import { afterEach, describe, expect, it } from "vitest";
import { createDatabaseBackup, restoreDatabaseBackup, verifyDatabaseBackup } from "../src/admin/backup.js";
import { runAdminCli } from "../src/admin/cli.js";
import { RuntimeLease, RuntimeLeaseError } from "../src/admin/runtime-lease.js";
import { openDatabase } from "../src/db/migrate.js";

const temporaryDirectories: string[] = [];

function paths(): { directory: string; database: string; backup: string } {
  const directory = mkdtempSync(join(tmpdir(), "sms-admin-"));
  temporaryDirectories.push(directory);
  return { directory, database: join(directory, "edge.sqlite"), backup: join(directory, "backup.sqlite") };
}

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) rmSync(directory, { recursive: true, force: true });
});

describe("offline runtime lease and recovery", () => {
  it("allows one unexpired runtime lease and permits takeover only after expiry", () => {
    const database = openDatabase(":memory:");
    const first = new RuntimeLease(database, { holderId: "service-1", now: () => "2026-08-25T10:00:00.000Z", durationMs: 60_000 });
    first.acquire();

    expect(() => new RuntimeLease(database, { holderId: "admin-1", now: () => "2026-08-25T10:00:30.000Z", durationMs: 60_000 }).acquire()).toThrow(RuntimeLeaseError);
    expect(() => new RuntimeLease(database, { holderId: "admin-1", now: () => "2026-08-25T10:01:00.000Z", durationMs: 60_000 }).acquire()).not.toThrow();
    expect(database.sql().prepare("SELECT holder_id FROM runtime_lease").get()).toEqual({ holder_id: "admin-1" });
    database.close();
  });

  it("creates a verified backup and restores its exact operational state", () => {
    const { database: databasePath, backup } = paths();
    const database = openDatabase(databasePath);
    database.sql().prepare("INSERT INTO identities (user_id, display_name) VALUES (?, ?)").run("admin-1", "Administrator");
    database.close();

    const created = createDatabaseBackup(databasePath, backup);
    expect(created.sha256).toMatch(/^[a-f0-9]{64}$/);
    expect(verifyDatabaseBackup(backup)).toMatchObject({ ok: true, schemaVersion: 2, sha256: created.sha256 });
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

  it("requires a protected password file and never echoes its contents", async () => {
    const { directory, database } = paths();
    const passwordFile = join(directory, "password.txt");
    writeFileSync(passwordFile, "protected-password\n");
    chmodSync(passwordFile, 0o644);
    const io = { stdin: async () => "", stdout: () => undefined, stderr: () => undefined };

    await expect(runAdminCli(["init", "--database", database, "--user-id", "admin-1", "--display-name", "Administrator", "--password-file", passwordFile], io)).rejects.toThrow(/permission|protected|mode/i);

    chmodSync(passwordFile, 0o600);
    await expect(runAdminCli(["init", "--database", database, "--user-id", "admin-1", "--display-name", "Administrator", "--password-file", passwordFile], io)).resolves.toBe(0);
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
