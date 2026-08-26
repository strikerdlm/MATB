import { createHash, generateKeyPairSync } from "node:crypto";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { manifestContentDigest, signManifest } from "../../packages/evidence/src/index.js";
import { AuditLedger } from "../../apps/edge-api/src/audit/ledger.js";
import { authorize } from "../../apps/edge-api/src/auth/roles.js";
import { authorizeTransport, validateTlsConfig } from "../../apps/edge-api/src/auth/tls.js";
import { SessionManager } from "../../apps/edge-api/src/auth/session.js";
import type { EdgeServer } from "../../apps/edge-api/src/server.js";
import { authenticatedTestServer } from "../../apps/edge-api/test/http-test-auth.js";
import type { TrustedKeyRecord } from "../../apps/edge-api/src/services/safe-mode.js";

const temporaryDirectories: string[] = [];
let app: EdgeServer | undefined;
const packageContext = { actorUserId: "administrator-1", clientSessionId: "offline-cli", occurredAtUtc: "2026-08-10T12:00:00.000Z" };

function trustedKey(keyId: string, publicKeyPem: string): TrustedKeyRecord {
  return { keyId, scope: "policy", algorithm: "ed25519", publicKeyPem, addedAtUtc: "2026-08-10T00:00:00.000Z", addedByUserId: "administrator-1" };
}

afterEach(async () => {
  await app?.close();
  app = undefined;
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

describe("tamper, rollback, transport, and least-privilege controls", () => {
  it("quarantines a signed package whose content changed after signing", async () => {
    const packageRoot = await mkdtemp(join(tmpdir(), "fac-isr-package-tamper-"));
    temporaryDirectories.push(packageRoot);
    const directory = join(packageRoot, "policy-v1");
    await mkdir(directory);
    const original = Buffer.from("approved policy\n", "utf8");
    const path = join(directory, "policy.json");
    await writeFile(path, original);
    const files = [{ path: "policy.json", sha256: createHash("sha256").update(original).digest("hex"), sizeBytes: original.byteLength }];
    const keys = generateKeyPairSync("ed25519");
    const manifest = signManifest({
      schemaVersion: "1.0",
      packageId: "fac-policy-security-test",
      kind: "policy",
      issuer: "security fixture",
      version: "1.0.0",
      issuedAtUtc: "2026-08-10T00:00:00.000Z",
      effectiveFromUtc: "2026-08-10T00:00:00.000Z",
      expiresAtUtc: "2027-08-10T00:00:00.000Z",
      geographicScope: "Colombia",
      contentSha256: manifestContentDigest(files),
      keyId: "fixture-ed25519",
      dependencies: [],
      files,
      qualification: "approved",
      caveats: ["test fixture"],
    }, keys.privateKey.export({ type: "pkcs8", format: "pem" }).toString());
    await writeFile(path, "tampered policy\n", "utf8");
    const record = trustedKey("fixture-ed25519", keys.publicKey.export({ type: "spki", format: "pem" }).toString());
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: packageRoot },
      undefined,
      { trustedKeyStore: { get: (keyId: string) => keyId === record.keyId ? record : undefined } },
    );
    app = server.app;

    const response = await app.safeModeService.importPackage({
      directory: basename(directory),
      manifest,
      keyId: record.keyId,
      asOfUtc: "2026-08-10T12:00:00.000Z",
    }, packageContext);

    expect(response).toMatchObject({ state: "quarantined", packageId: "fac-policy-security-test" });
  });

  it("enters read-only safe mode after an audit-chain alteration", async () => {
    const ledger = new AuditLedger({ now: () => "2026-08-10T12:00:00.000Z" });
    await ledger.append({
      eventId: "security-audit-1",
      type: "gate.accepted",
      actorUserId: "safety-1",
      occurredAtUtc: "2026-08-10T12:00:00.000Z",
      action: "accept",
      reason: "fixture accepted",
      payload: { gate: "safety" },
    });
    await ledger.tamperForFixture(0, { reason: "altered history" });

    await expect(ledger.verifyAuditChain()).resolves.toMatchObject({ ok: false, firstBrokenSequence: 0 });
    expect(ledger.isReadOnlySafeMode()).toBe(true);
    await expect(ledger.canApprove()).resolves.toBe(false);
  });

  it("quarantines an otherwise valid signed package rollback", async () => {
    const packageRoot = await mkdtemp(join(tmpdir(), "fac-isr-package-rollback-"));
    temporaryDirectories.push(packageRoot);
    const keys = generateKeyPairSync("ed25519");

    async function signedPackage(version: string) {
      const directory = join(packageRoot, `policy-${version}`);
      await mkdir(directory);
      const content = Buffer.from(`approved policy ${version}\n`, "utf8");
      await writeFile(join(directory, "policy.json"), content);
      const files = [{ path: "policy.json", sha256: createHash("sha256").update(content).digest("hex"), sizeBytes: content.byteLength }];
      return {
        directory: basename(directory),
        manifest: signManifest({
          schemaVersion: "1.0",
          packageId: "fac-policy-rollback-test",
          kind: "policy",
          issuer: "security fixture",
          version,
          issuedAtUtc: "2026-08-10T00:00:00.000Z",
          effectiveFromUtc: "2026-08-10T00:00:00.000Z",
          expiresAtUtc: "2027-08-10T00:00:00.000Z",
          geographicScope: "Colombia",
          contentSha256: manifestContentDigest(files),
          keyId: "fixture-ed25519",
          dependencies: [],
          files,
          qualification: "approved",
          caveats: ["test fixture"],
        }, keys.privateKey.export({ type: "pkcs8", format: "pem" }).toString()),
        keyId: "fixture-ed25519",
        asOfUtc: "2026-08-10T12:00:00.000Z",
      };
    }

    const record = trustedKey("fixture-ed25519", keys.publicKey.export({ type: "spki", format: "pem" }).toString());
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: packageRoot },
      undefined,
      { trustedKeyStore: { get: (keyId: string) => keyId === record.keyId ? record : undefined } },
    );
    app = server.app;
    const current = await app.safeModeService.importPackage(await signedPackage("2.0.0"), packageContext);
    await app.safeModeService.activatePackage({ packageId: current.packageId, version: current.version, keyId: record.keyId, asOfUtc: "2026-08-10T12:00:00.000Z" }, packageContext);
    const rollback = await app.safeModeService.importPackage(await signedPackage("1.9.0"), packageContext);

    expect(current).toMatchObject({ state: "verified" });
    expect(rollback).toMatchObject({ state: "quarantined", reason: expect.stringMatching(/downgrade/i) });
  });

  it("locks an idle session and denies subsequent gate authorization", () => {
    const sessions = new SessionManager({
      idleTimeoutMs: 60_000,
      maxLifetimeMs: 3_600_000,
      reauthenticationIntervalMs: 300_000,
      sessionIdFactory: () => "security-session",
    });
    const session = sessions.createSession({
      userId: "operator-1",
      displayName: "Operator One",
      roles: ["operator"],
      missionIds: ["mission-1"],
      qualificationRefs: [],
    }, "2026-08-10T12:00:00.000Z");

    const locked = sessions.touchSession(session.sessionId, "2026-08-10T12:01:00.000Z");

    expect(locked).toMatchObject({ state: "locked", lockReason: "idle timeout" });
    expect(authorize(locked, { action: "gate:operator:accept", missionId: "mission-1" })).toMatchObject({ allowed: false, reason: "session is locked" });
  });

  it("denies plaintext tactical transport and cross-role gate approval", () => {
    expect(() => validateTlsConfig({ tacticalMode: true, bindAddress: "192.168.10.20" })).toThrow(/certificate and key/i);
    expect(authorizeTransport({ bindAddress: "192.168.10.20", encrypted: false, loopbackBootstrap: false })).toMatchObject({ allowed: false });
    expect(authorize({
      userId: "commander-1",
      roles: ["commander"],
      missionIds: ["mission-1"],
      state: "active",
    }, {
      action: "gate:maintenance:accept",
      missionId: "mission-1",
    })).toMatchObject({ allowed: false, requiredRole: "maintainer" });
  });
});
