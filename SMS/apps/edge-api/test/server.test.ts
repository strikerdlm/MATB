import { createHash, generateKeyPairSync } from "node:crypto";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { FastifyInstance } from "fastify";
import { buildServer } from "../src/server.js";
import { openDatabase } from "../src/db/migrate.js";
import { AuditLedger } from "../src/audit/ledger.js";
import { LocalIdentityStore } from "../src/auth/identity.js";
import { DEFAULT_SESSION_POLICY } from "../src/auth/http.js";
import { SessionManager } from "../src/auth/session.js";
import { SqliteTrustedKeyStore } from "../src/services/safe-mode.js";
import { manifestContentDigest, signManifest } from "@fac-isr/evidence";

const readinessNow = "2026-08-25T00:00:00.000Z";

function authorityFixture(root: string, kind: "policy" | "terminology", keyId: string, packageId: string, keys: ReturnType<typeof generateKeyPairSync>) {
  const directory = `${kind}-fixture`;
  const full = join(root, directory);
  mkdirSync(full);
  const content = Buffer.from(JSON.stringify({ kind, entries: [] }));
  const path = `${kind}.json`;
  writeFileSync(join(full, path), content);
  const files = [{ path, sha256: createHash("sha256").update(content).digest("hex"), sizeBytes: content.byteLength }];
  const manifest = signManifest({
    schemaVersion: "1.0", packageId, kind, issuer: "fac-isr", version: "1.0.0",
    issuedAtUtc: "2026-08-24T00:00:00.000Z", effectiveFromUtc: "2026-08-24T00:00:00.000Z",
    expiresAtUtc: "2027-08-24T00:00:00.000Z", geographicScope: "Colombia",
    contentSha256: manifestContentDigest(files), keyId, dependencies: [], files,
    qualification: "approved", caveats: [], signature: "",
  }, keys.privateKey.export({ type: "pkcs1", format: "pem" }).toString());
  return { directory, manifest };
}

describe("offline edge server", () => {
  let app: FastifyInstance | undefined;
  const temporaryDirectories: string[] = [];

  afterEach(async () => {
    await app?.close();
    app = undefined;
    for (const directory of temporaryDirectories.splice(0)) rmSync(directory, { recursive: true, force: true });
  });

  it("boots with internet disabled and exposes a local health check", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });

    const response = await app.inject({ method: "GET", url: "/healthz" });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({
      status: "ok",
      internet: "disabled",
    });
  });

  it("does not claim readiness before policy dependencies are validated", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });

    const response = await app.inject({ method: "GET", url: "/readyz" });

    expect(response.statusCode).toBe(503);
    expect(response.json()).toMatchObject({
      status: "not_ready",
      technicalReady: false,
      operationalReady: false,
      checks: {
        database: { status: "ok" },
        migrations: { status: "ok" },
        audit: { status: "ok" },
        tls: { status: "pending" },
        exportKey: { status: "pending" },
        trustAnchors: { status: "pending" },
        activeTerminology: { status: "pending" },
        activePolicy: { status: "pending" },
        bootstrapAdministrator: { status: "pending" },
      },
    });
  });

  it("does not report ready from malformed administrator, trust, or package rows", async () => {
    app = await buildServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      { readiness: { tlsConfigured: true, exportKeyConfigured: true } },
    );
    const server = app as Awaited<ReturnType<typeof buildServer>>;
    const sql = server.edgeDatabase.sql();
    sql.prepare("INSERT INTO identities (user_id, display_name) VALUES ('admin-1', 'Administrator')").run();
    sql.prepare("INSERT INTO identity_roles (user_id, role) VALUES ('admin-1', 'administrator')").run();
    sql.prepare("INSERT INTO trusted_keys (key_id, scope, algorithm, public_key_pem, added_at_utc, added_by_user_id) VALUES ('key-1', 'policy', 'ed25519', 'external', '2026-08-25T00:00:00.000Z', 'admin-1')").run();
    for (const [role, packageId] of [["policy", "policy-1"], ["terminology", "terminology-1"]]) {
      sql.prepare("INSERT INTO packages (package_id, version, kind, state, imported_at_utc, record_json) VALUES (?, '1.0.0', ?, 'active', '2026-08-25T00:00:00.000Z', '{}')").run(packageId, role);
      sql.prepare("INSERT INTO active_package_roles (role, package_id, version) VALUES (?, ?, '1.0.0')").run(role, packageId);
    }

    const response = await app.inject({ method: "GET", url: "/readyz" });

    expect(response.statusCode).toBe(503);
    expect(response.json()).toMatchObject({ status: "not_ready", technicalReady: false, operationalReady: false, checks: {
      bootstrapAdministrator: { status: "pending" }, trustAnchors: { status: "pending" },
      activePolicy: { status: "pending" }, activeTerminology: { status: "pending" },
    } });
  });

  it("returns HTTP 200 only for reverified packages, usable trust, and an enabled credentialed administrator", async () => {
    const directory = mkdtempSync(join(tmpdir(), "sms-ready-valid-"));
    temporaryDirectories.push(directory);
    app = await buildServer(
      { databaseUrl: join(directory, "edge.sqlite"), internet: "disabled", packageDirectory: directory },
      { readiness: { tlsConfigured: true, exportKeyConfigured: true }, now: () => readinessNow },
    );
    const server = app as Awaited<ReturnType<typeof buildServer>>;
    new LocalIdentityStore({ database: server.edgeDatabase, now: () => readinessNow }).register({ userId: "admin-1", displayName: "Administrator", roles: ["administrator"], missionIds: ["*"], password: "readiness-admin-password" });
    const trust = new SqliteTrustedKeyStore(server.edgeDatabase);
    for (const kind of ["policy", "terminology"] as const) {
      const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
      const keyId = `${kind}-key`;
      trust.add({ keyId, scope: kind, algorithm: "rsa-sha256", publicKeyPem: keys.publicKey.export({ type: "spki", format: "pem" }).toString(), addedAtUtc: readinessNow, addedByUserId: "admin-1" });
      const fixture = authorityFixture(directory, kind, keyId, `${kind}-package`, keys);
      const imported = await server.safeModeService.importPackage({ ...fixture, keyId }, { actorUserId: "admin-1", clientSessionId: "bootstrap", occurredAtUtc: readinessNow });
      await server.safeModeService.activatePackage({ packageId: imported.packageId, version: imported.version, keyId }, { actorUserId: "admin-1", clientSessionId: "bootstrap", occurredAtUtc: readinessNow });
    }

    const response = await app.inject({ method: "GET", url: "/readyz" });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({ status: "ready", technicalReady: true, operationalReady: false });
  });

  it("serves liveness in degraded mode when the database file is physically corrupt", async () => {
    const directory = mkdtempSync(join(tmpdir(), "sms-physical-corrupt-"));
    temporaryDirectories.push(directory);
    const databaseUrl = join(directory, "edge.sqlite");
    writeFileSync(databaseUrl, "not a sqlite database");

    app = await buildServer({ databaseUrl, internet: "disabled" });

    expect((await app.inject({ method: "GET", url: "/healthz" })).statusCode).toBe(200);
    const readiness = await app.inject({ method: "GET", url: "/readyz" });
    expect(readiness.statusCode).toBe(503);
    expect(readiness.json()).toMatchObject({ technicalReady: false, operationalReady: false, checks: { database: { status: "pending" } } });
    expect((await app.inject({ method: "POST", url: "/api/auth/login", payload: { userId: "x", password: "x" } })).statusCode).toBe(503);
  });

  for (const domain of ["identity", "session", "package"] as const) {
    it(`serves liveness but not readiness when persisted ${domain} state is malformed`, async () => {
      const directory = mkdtempSync(join(tmpdir(), `sms-${domain}-corrupt-`));
      temporaryDirectories.push(directory);
      const databaseUrl = join(directory, "edge.sqlite");
      const database = openDatabase(databaseUrl);
      const identities = new LocalIdentityStore({ database, now: () => readinessNow });
      const identity = identities.register({ userId: "user-1", displayName: "User", roles: ["administrator"], missionIds: ["*"], password: "corruption-test-password" });
      if (domain === "identity") database.sql().prepare("UPDATE identities SET qualification_refs_json = '{bad-json' WHERE user_id = 'user-1'").run();
      if (domain === "session") {
        new SessionManager({ ...DEFAULT_SESSION_POLICY, database, now: () => readinessNow }).issueSession(identity);
        database.sql().prepare("UPDATE sessions SET session_json = '{bad-json'").run();
      }
      if (domain === "package") database.sql().prepare("INSERT INTO packages (package_id, version, kind, state, imported_at_utc, record_json) VALUES ('bad-package', '1.0.0', 'policy', 'active', ?, '{}')").run(readinessNow);
      database.close();

      app = await buildServer({ databaseUrl, internet: "disabled", packageDirectory: directory });

      const health = await app.inject({ method: "GET", url: "/healthz" });
      expect(health.statusCode).toBe(200);
      expect(health.json()).toMatchObject({ status: "ok", degraded: true });
      expect((await app.inject({ method: "GET", url: "/readyz" })).statusCode).toBe(503);
      expect((await app.inject({ method: "POST", url: "/api/auth/login", payload: { userId: "user-1", password: "corruption-test-password" } })).statusCode).toBe(503);
    });
  }

  it("boots read-only with liveness intact when the persisted audit chain is corrupt", async () => {
    const directory = mkdtempSync(join(tmpdir(), "sms-audit-startup-"));
    temporaryDirectories.push(directory);
    const databaseUrl = join(directory, "edge.sqlite");
    const database = openDatabase(databaseUrl);
    const ledger = new AuditLedger({ database, now: () => "2026-08-25T00:00:00.000Z" });
    await ledger.append({ type: "fixture.created", actorUserId: "fixture", action: "create", reason: "fixture" });
    database.sql().prepare("UPDATE audit_events SET hash = ? WHERE sequence = 0").run("f".repeat(64));
    database.close();

    app = await buildServer({ databaseUrl, internet: "disabled" });
    const server = app as Awaited<ReturnType<typeof buildServer>>;

    expect(server.auditLedger.isReadOnlySafeMode()).toBe(true);
    expect((await app.inject({ method: "GET", url: "/healthz" })).statusCode).toBe(200);
    const readiness = await app.inject({ method: "GET", url: "/readyz" });
    expect(readiness.statusCode).toBe(503);
    expect(readiness.json()).toMatchObject({ technicalReady: false, checks: { audit: { status: "pending" } } });
  });

  it("boots read-only when normalized mission state is corrupt", async () => {
    const directory = mkdtempSync(join(tmpdir(), "sms-domain-startup-"));
    temporaryDirectories.push(directory);
    const databaseUrl = join(directory, "edge.sqlite");
    const database = openDatabase(databaseUrl);
    database.sql().prepare("INSERT INTO missions (mission_id, current_revision) VALUES ('mission-bad', 0)").run();
    database.sql().prepare("INSERT INTO mission_revisions (revision_id, mission_id, revision, revision_json) VALUES ('mission-bad:r0', 'mission-bad', 0, '{bad-json')").run();
    database.close();

    app = await buildServer({ databaseUrl, internet: "disabled" });
    const server = app as Awaited<ReturnType<typeof buildServer>>;
    expect(server.auditLedger.isReadOnlySafeMode()).toBe(true);
    expect((await app.inject({ method: "GET", url: "/healthz" })).statusCode).toBe(200);
  });

  it("fails closed when configured TLS material cannot be loaded", async () => {
    await expect(buildServer({
      databaseUrl: ":memory:",
      tls: {
        certPath: "/missing/server.crt",
        keyPath: "/missing/server.key",
      },
    })).rejects.toThrow(/TLS material/i);
  });
});
