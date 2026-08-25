import { generateKeyPairSync, sign, verify } from "node:crypto";
import { afterEach, describe, expect, it } from "vitest";
import { canonicalJson } from "@fac-isr/evidence";
import type { EdgeServer } from "../src/server.js";
import { missionFixture } from "./mission-fixture.js";
import { authenticatedTestServer } from "./http-test-auth.js";

const keys = generateKeyPairSync("ed25519");
const exportSigner = Object.freeze({
  keyId: "runtime-export-key-2026",
  algorithm: "Ed25519" as const,
  sign(payload: Buffer): string {
    return sign(null, payload, keys.privateKey).toString("base64");
  },
});

describe("revision exports", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("creates a detached Ed25519 signature over release, revision, evaluation, package, and audit hashes", async () => {
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled" }, undefined, { exportSigner });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });

    const response = await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/export", payload: {} });
    expect(response.statusCode).toBe(200);
    const exported = response.json() as Record<string, unknown> & { hashes: Record<string, string>; detachedSignature: string };
    expect(exported).toMatchObject({
      exportSchemaVersion: "2.0",
      releaseId: "fac-isr-sms@0.2.0-rc.1",
      revisionId: "mission-1:r0",
      missionId: "mission-1",
      signatureKeyId: "runtime-export-key-2026",
      signatureAlgorithm: "Ed25519",
      hashes: {
        revisionSha256: expect.stringMatching(/^[a-f0-9]{64}$/),
        evaluationSha256: expect.stringMatching(/^[a-f0-9]{64}$/),
        packageSha256: expect.stringMatching(/^[a-f0-9]{64}$/),
        auditSha256: expect.stringMatching(/^[a-f0-9]{64}$/),
        payloadSha256: expect.stringMatching(/^[a-f0-9]{64}$/),
      },
      detachedSignature: expect.stringMatching(/^[A-Za-z0-9+/]+={0,2}$/),
    });
    const { detachedSignature, ...signed } = exported;
    expect(verify(null, Buffer.from(canonicalJson(signed)), keys.publicKey, Buffer.from(detachedSignature, "base64"))).toBe(true);
    await expect(app.auditLedger.queryAudit({ type: "export.created" })).resolves.toMatchObject([{
      actorUserId: "commander-1", clientSessionId: "test-session-1", missionRevisionId: "mission-1:r0",
    }]);
  });

  it("fails signature verification after any exported fact is tampered", async () => {
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled" }, undefined, { exportSigner });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });
    const response = await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/export", payload: {} });
    const exported = response.json() as Record<string, unknown> & { detachedSignature: string };
    const detachedSignature = exported.detachedSignature;
    const tampered = { ...exported, releaseId: "attacker-release" };
    delete (tampered as { detachedSignature?: string }).detachedSignature;
    expect(verify(null, Buffer.from(canonicalJson(tampered)), keys.publicKey, Buffer.from(detachedSignature, "base64"))).toBe(false);
  });

  it("requires a commander or reviewer with mission visibility and fresh reauthentication", async () => {
    const identities = [
      { userId: "commander-1", roles: ["commander"] as const, missionIds: ["mission-1"] },
      { userId: "reviewer-1", roles: ["reviewer"] as const, missionIds: [] },
      { userId: "operator-1", roles: ["operator"] as const, missionIds: ["mission-1"] },
      { userId: "admin-1", roles: ["administrator"] as const, missionIds: ["*"] },
    ];
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled" }, identities, { exportSigner });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } }, "commander-1");

    expect((await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/export", payload: {} }, "commander-1")).statusCode).toBe(200);
    expect((await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/export", payload: {} }, "reviewer-1")).statusCode).toBe(200);
    expect((await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/export", payload: {} }, "operator-1")).statusCode).toBe(403);
    expect((await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/export", payload: {} }, "admin-1")).statusCode).toBe(403);

  });

  it("resolves delimiter-bearing mission identities from authoritative revision state", async () => {
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      [{ userId: "commander-1", roles: ["commander"], missionIds: ["mission-1:secret"] }],
      { exportSigner },
    );
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture({ id: "mission-1:secret:r0", missionId: "mission-1:secret" }) } });
    const response = await server.request({ method: "POST", url: "/api/revisions/mission-1:secret:r0/export", payload: {} });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({ missionId: "mission-1:secret", revisionId: "mission-1:secret:r0" });
  });

  it("rejects an export when the session requires reauthentication", async () => {
    let current = "2026-08-09T18:00:00.000Z";
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      [{ userId: "commander-1", roles: ["commander"], missionIds: ["mission-1"] }],
      { exportSigner, now: () => current },
    );
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });
    current = "2026-08-09T18:05:00.000Z";

    const response = await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/export", payload: {} });
    expect(response.statusCode).toBe(403);
    expect(response.json()).toMatchObject({ error: "REAUTHENTICATION_REQUIRED" });
  });

  it("does not export without an externally provisioned Ed25519 signer", async () => {
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled" });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });
    const response = await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/export", payload: {} });
    expect(response.statusCode).toBe(503);
    expect(response.json()).toMatchObject({ error: "EXPORT_SIGNING_UNAVAILABLE" });
  });

  it("keeps a mission unchanged and sanitizes the response when export fails", async () => {
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled" }, undefined, { exportSigner });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });
    const before = await server.request({ method: "GET", url: "/api/missions/mission-1" });
    await app.safeModeService.simulateExportFailure();
    const failed = await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/export", payload: {} });
    const after = await server.request({ method: "GET", url: "/api/missions/mission-1" });
    expect(failed.statusCode).toBe(500);
    expect(failed.json()).toMatchObject({ error: "EXPORT_FAILED", message: "export could not be created" });
    expect(after.json()).toEqual(before.json());
  });
});
