import { createHash, generateKeyPairSync } from "node:crypto";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";
import { tmpdir } from "node:os";
import { afterEach, describe, expect, it } from "vitest";
import { manifestContentDigest, signManifest, type SignedPackageManifest } from "@fac-isr/evidence";
import type { EdgeServer } from "../src/server.js";
import { authenticatedTestServer } from "./http-test-auth.js";
import type { TrustedKeyRecord } from "../src/services/safe-mode.js";

const asOfUtc = "2026-08-09T18:00:00.000Z";

function signedPackage(root: string, version: string, keys: ReturnType<typeof generateKeyPairSync>): { directory: string; manifest: SignedPackageManifest } {
  const directoryPath = join(root, `map-${version.replaceAll(".", "-")}`);
  mkdirSync(directoryPath);
  const content = Buffer.from(`map package ${version}`, "utf8");
  writeFileSync(join(directoryPath, "map.txt"), content);
  const files = [{ path: "map.txt", sha256: createHash("sha256").update(content).digest("hex"), sizeBytes: content.byteLength }];
  const manifest = signManifest({
    schemaVersion: "1.0",
    packageId: "map-colombia",
    kind: "map",
    issuer: "fac-isr",
    version,
    issuedAtUtc: "2026-08-09T17:00:00.000Z",
    effectiveFromUtc: "2026-08-09T17:30:00.000Z",
    expiresAtUtc: "2027-08-09T17:30:00.000Z",
    geographicScope: "Colombia",
    contentSha256: manifestContentDigest(files),
    keyId: "local-key-1",
    dependencies: [],
    files,
    qualification: "approved",
    caveats: ["local fixture"],
    signature: "",
  }, keys.privateKey.export({ type: "pkcs1", format: "pem" }).toString());
  return { directory: basename(directoryPath), manifest };
}

const context = { actorUserId: "administrator-1", clientSessionId: "offline-cli", occurredAtUtc: asOfUtc };

function trustedKey(keys: ReturnType<typeof generateKeyPairSync>): TrustedKeyRecord {
  return {
    keyId: "local-key-1",
    scope: "map",
    algorithm: "rsa-sha256",
    publicKeyPem: keys.publicKey.export({ type: "spki", format: "pem" }).toString(),
    addedAtUtc: "2026-08-09T16:00:00.000Z",
    addedByUserId: "administrator-1",
  };
}

describe("signed package import and quarantine", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("quarantines an unsigned package before activation", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-packages-"));
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled", packageDirectory: root });
    app = server.app;
    const response = await app.safeModeService.importPackage({ directory: ".", manifest: { schemaVersion: "1.0", packageId: "map-colombia", kind: "map", version: "1.0.0" }, asOfUtc }, context);

    expect(response).toMatchObject({ state: "quarantined", packageId: "map-colombia" });
  });

  it("refuses a signed downgrade while preserving the quarantine record", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-packages-"));
    const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const record = trustedKey(keys);
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: root },
      undefined,
      { trustedKeyStore: { get: (keyId: string) => keyId === record.keyId ? record : undefined } },
    );
    app = server.app;
    const current = signedPackage(root, "1.2.0", keys);
    const first = await app.safeModeService.importPackage({ ...current, keyId: record.keyId, asOfUtc }, context);
    expect(first).toMatchObject({ state: "verified", packageId: "map-colombia", version: "1.2.0" });
    await app.safeModeService.activatePackage({ packageId: first.packageId, version: first.version, keyId: record.keyId, asOfUtc }, context);

    const older = signedPackage(root, "1.1.0", keys);
    const downgrade = await app.safeModeService.importPackage({ ...older, keyId: record.keyId, asOfUtc }, context);
    expect(downgrade).toMatchObject({ state: "quarantined", reason: expect.stringMatching(/downgrade/i) });

    const quarantine = await server.request({ method: "GET", url: "/api/packages/quarantine" });
    expect(quarantine.statusCode).toBe(200);
    expect(quarantine.json().packages).toEqual(expect.arrayContaining([expect.objectContaining({ version: "1.1.0", state: "quarantined" })]));
  });

  it("quarantines a package when a configured key has the wrong package scope", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-package-scope-"));
    const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const fixture = signedPackage(root, "1.0.0", keys);
    const wrongScope = { ...trustedKey(keys), scope: "policy" as const };
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: root },
      undefined,
      { trustedKeyStore: { get: () => wrongScope } },
    );
    app = server.app;

    const record = await app.safeModeService.importPackage({ ...fixture, keyId: wrongScope.keyId, asOfUtc }, context);

    expect(record).toMatchObject({ state: "quarantined", reason: expect.stringMatching(/wrong scope/i) });
  });

  it("never accepts a request-provided public key even when keyId is configured", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-package-request-key-"));
    const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const fixture = signedPackage(root, "1.0.0", keys);
    const record = trustedKey(keys);
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: root },
      undefined,
      { trustedKeyStore: { get: () => record } },
    );
    app = server.app;

    const result = await app.safeModeService.importPackage({ ...fixture, keyId: record.keyId, publicKeyPem: record.publicKeyPem, asOfUtc }, context);

    expect(result).toMatchObject({ state: "quarantined", reason: expect.stringMatching(/request-provided publicKeyPem is not accepted/i) });
  });
});
