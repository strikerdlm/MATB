import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { FastifyInstance } from "fastify";
import { buildServer } from "../src/server.js";
import { openDatabase } from "../src/db/migrate.js";
import { AuditLedger } from "../src/audit/ledger.js";

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

  it("returns HTTP 200 only when every technical readiness check passes", async () => {
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

    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({ status: "ready", technicalReady: true, operationalReady: false });
  });

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
