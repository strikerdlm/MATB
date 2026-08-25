import { createHash, generateKeyPairSync } from "node:crypto";
import { mkdirSync, mkdtempSync, symlinkSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";
import { tmpdir } from "node:os";
import { afterEach, describe, expect, it } from "vitest";
import { manifestContentDigest, signManifest, type SignedPackageManifest } from "@fac-isr/evidence";
import type { PolicyPackage } from "@fac-isr/safety-kernel";
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

function authorityPackage(
  root: string,
  kind: "policy" | "terminology" | "regulatory",
  packageId: string,
  keyId: string,
  keys: ReturnType<typeof generateKeyPairSync>,
  documents: Readonly<Record<string, unknown>>,
): { directory: string; manifest: SignedPackageManifest } {
  const directory = `${kind}-1-0-0`;
  const directoryPath = join(root, directory);
  mkdirSync(directoryPath);
  const files = Object.entries(documents).sort(([left], [right]) => left.localeCompare(right)).map(([path, value]) => {
    const content = Buffer.from(JSON.stringify(value), "utf8");
    writeFileSync(join(directoryPath, path), content);
    return { path, sha256: createHash("sha256").update(content).digest("hex"), sizeBytes: content.byteLength };
  });
  return {
    directory,
    manifest: signManifest({
      schemaVersion: "1.0",
      packageId,
      kind,
      issuer: "fac-isr",
      version: "1.0.0",
      issuedAtUtc: "2026-08-09T17:00:00.000Z",
      effectiveFromUtc: "2026-08-09T17:30:00.000Z",
      expiresAtUtc: "2027-08-09T17:30:00.000Z",
      geographicScope: "Colombia",
      contentSha256: manifestContentDigest(files),
      keyId,
      dependencies: [],
      files,
      qualification: "approved",
      caveats: ["authority fixture"],
      signature: "",
    }, keys.privateKey.export({ type: "pkcs1", format: "pem" }).toString()),
  };
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

  it("uses the service clock and re-quarantines active packages that expire at use time", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-package-clock-"));
    const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const base = signedPackage(root, "1.0.0", keys);
    const manifest = signManifest({ ...base.manifest, expiresAtUtc: "2026-08-20T00:00:00.000Z", signature: "" }, keys.privateKey.export({ type: "pkcs1", format: "pem" }).toString());
    const record = trustedKey(keys);
    const clock = { now: "2026-08-10T00:00:00.000Z" };
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: root },
      undefined,
      { trustedKeyStore: { get: () => record }, now: () => clock.now },
    );
    app = server.app;
    const imported = await app.safeModeService.importPackage({ directory: base.directory, manifest, keyId: record.keyId, asOfUtc: "2026-08-10T00:00:00.000Z" }, context);
    await app.safeModeService.activatePackage({ packageId: imported.packageId, version: imported.version, keyId: record.keyId, asOfUtc: "2026-08-10T00:00:00.000Z" }, context);
    clock.now = "2026-08-25T00:00:00.000Z";

    const state = await app.safeModeService.getPackageState();

    expect(state.active).toEqual([]);
    expect(state.quarantined).toEqual(expect.arrayContaining([expect.objectContaining({ packageId: "map-colombia", reason: expect.stringMatching(/expired/i) })]));
  });

  it("re-verifies persisted active package bytes before exposing them after restart", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-package-reload-"));
    const databaseUrl = join(root, "edge.sqlite");
    const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const fixture = signedPackage(root, "1.0.0", keys);
    const record = trustedKey(keys);
    const dependencies = { trustedKeyStore: { get: () => record }, now: () => asOfUtc };
    let server = await authenticatedTestServer({ databaseUrl, internet: "disabled", packageDirectory: root }, undefined, dependencies);
    app = server.app;
    const imported = await app.safeModeService.importPackage({ ...fixture, keyId: record.keyId }, context);
    await app.safeModeService.activatePackage({ packageId: imported.packageId, version: imported.version, keyId: record.keyId }, context);
    await app.close();
    app = undefined;
    writeFileSync(join(root, fixture.directory, "map.txt"), "tampered package bytes");

    server = await authenticatedTestServer({ databaseUrl, internet: "disabled", packageDirectory: root }, undefined, dependencies);
    app = server.app;
    const state = await app.safeModeService.getPackageState();

    expect(state.active).toEqual([]);
    expect(state.quarantined).toEqual(expect.arrayContaining([expect.objectContaining({ packageId: "map-colombia", reason: expect.stringMatching(/hash|size|verification/i) })]));
  });

  it("rolls back a verified import when its audit append fails", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-package-audit-rollback-"));
    const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const fixture = signedPackage(root, "1.0.0", keys);
    const record = trustedKey(keys);
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: root },
      undefined,
      { trustedKeyStore: { get: () => record }, now: () => asOfUtc },
    );
    app = server.app;
    await app.auditLedger.simulateWriteFailure();

    await expect(app.safeModeService.importPackage({ ...fixture, keyId: record.keyId }, context)).rejects.toBeDefined();
    app.auditLedger.clearReadOnlySafeMode();
    await expect(app.safeModeService.activatePackage({ packageId: "map-colombia", version: "1.0.0", keyId: record.keyId }, context)).rejects.toMatchObject({ code: "PACKAGE_NOT_VERIFIED" });
  });

  it("never exposes activation state when package persistence fails", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-package-persist-failure-"));
    const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const fixture = signedPackage(root, "1.0.0", keys);
    const record = trustedKey(keys);
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: root },
      undefined,
      { trustedKeyStore: { get: () => record }, now: () => asOfUtc },
    );
    app = server.app;
    const imported = await app.safeModeService.importPackage({ ...fixture, keyId: record.keyId }, context);
    app.edgeDatabase.sql().exec("CREATE TRIGGER fail_package_update BEFORE UPDATE ON service_state WHEN NEW.key = 'package_store' BEGIN SELECT RAISE(FAIL, 'package persistence failed'); END");

    await expect(app.safeModeService.activatePackage({ packageId: imported.packageId, version: imported.version, keyId: record.keyId }, context)).rejects.toMatchObject({ code: "SAFE_MODE_DATABASE_FAILURE" });
    const state = await app.safeModeService.getPackageState();
    expect(state.active).toEqual([]);
  });

  it("rejects a package root symlink that escapes the configured root", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-package-root-"));
    const external = mkdtempSync(join(tmpdir(), "fac-isr-package-external-"));
    const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const fixture = signedPackage(external, "1.0.0", keys);
    symlinkSync(join(external, fixture.directory), join(root, "escape"), "dir");
    const record = trustedKey(keys);
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: root },
      undefined,
      { trustedKeyStore: { get: () => record }, now: () => asOfUtc },
    );
    app = server.app;

    const imported = await app.safeModeService.importPackage({ directory: "escape", manifest: fixture.manifest, keyId: record.keyId }, context);

    expect(imported).toMatchObject({ state: "quarantined", reason: expect.stringMatching(/symbolic link|contain/i) });
  });

  it("detaches and deep-freezes stored manifests from caller mutation", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-package-immutable-"));
    const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const fixture = signedPackage(root, "1.0.0", keys);
    const record = trustedKey(keys);
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: root },
      undefined,
      { trustedKeyStore: { get: () => record }, now: () => asOfUtc },
    );
    app = server.app;
    const imported = await app.safeModeService.importPackage({ ...fixture, keyId: record.keyId }, context);
    (fixture.manifest.files[0] as { sha256: string }).sha256 = "0".repeat(64);

    await expect(app.safeModeService.activatePackage({ packageId: imported.packageId, version: imported.version, keyId: record.keyId }, context)).resolves.toMatchObject({ state: "active" });
  });

  it.each([
    ["lookup key mismatch", (record: TrustedKeyRecord) => ({ ...record, keyId: "different-key" })],
    ["wildcard scope", (record: TrustedKeyRecord) => ({ ...record, scope: "*" })],
    ["unsupported algorithm", (record: TrustedKeyRecord) => ({ ...record, algorithm: "none" })],
    ["invalid metadata", (record: TrustedKeyRecord) => ({ ...record, addedAtUtc: "not-utc", addedByUserId: "" })],
  ])("rejects configured trusted-key records with %s", async (_case, mutate) => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-invalid-trust-record-"));
    const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const fixture = signedPackage(root, "1.0.0", keys);
    const invalid = mutate(trustedKey(keys)) as TrustedKeyRecord;
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: root },
      undefined,
      { trustedKeyStore: { get: () => invalid }, now: () => asOfUtc },
    );
    app = server.app;

    const result = await app.safeModeService.importPackage({ ...fixture, keyId: "local-key-1" }, context);

    expect(result.state).toBe("quarantined");
    await app.close();
    app = undefined;
  });

  it("compares imports against the highest installed version and rejects duplicates", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-package-version-order-"));
    const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const record = trustedKey(keys);
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: root },
      undefined,
      { trustedKeyStore: { get: () => record }, now: () => asOfUtc },
    );
    app = server.app;
    const one = signedPackage(root, "1.0.0", keys);
    const three = signedPackage(root, "3.0.0", keys);
    const two = signedPackage(root, "2.0.0", keys);
    await app.safeModeService.importPackage({ ...one, keyId: record.keyId }, context);
    await app.safeModeService.importPackage({ ...three, keyId: record.keyId }, context);

    const rollback = await app.safeModeService.importPackage({ ...two, keyId: record.keyId }, context);
    const duplicate = await app.safeModeService.importPackage({ ...three, keyId: record.keyId }, context);

    expect(rollback).toMatchObject({ state: "quarantined", reason: expect.stringMatching(/downgrade/i) });
    expect(duplicate).toMatchObject({ state: "quarantined", reason: expect.stringMatching(/already imported|duplicate/i) });
  });

  it("preserves the verified version high-water mark after quarantine and restart", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-package-high-water-"));
    const databaseUrl = join(root, "edge.sqlite");
    const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const record = trustedKey(keys);
    const dependencies = { trustedKeyStore: { get: () => record }, now: () => asOfUtc };
    const three = signedPackage(root, "3.0.0", keys);
    const two = signedPackage(root, "2.0.0", keys);
    const four = signedPackage(root, "4.0.0", keys);
    const nine = signedPackage(root, "9.0.0", keys);
    let server = await authenticatedTestServer({ databaseUrl, internet: "disabled", packageDirectory: root }, undefined, dependencies);
    app = server.app;
    const imported = await app.safeModeService.importPackage({ ...three, keyId: record.keyId }, context);
    await app.safeModeService.activatePackage({ packageId: imported.packageId, version: imported.version, keyId: record.keyId }, context);
    writeFileSync(join(root, three.directory, "map.txt"), "tampered newest package");
    expect((await app.safeModeService.getPackageState()).quarantined).toEqual(expect.arrayContaining([expect.objectContaining({ version: "3.0.0" })]));
    await app.close();
    app = undefined;

    server = await authenticatedTestServer({ databaseUrl, internet: "disabled", packageDirectory: root }, undefined, dependencies);
    app = server.app;
    const invalidNine = await app.safeModeService.importPackage({ ...nine, manifest: { ...nine.manifest, signature: three.manifest.signature }, keyId: record.keyId }, context);
    const rollback = await app.safeModeService.importPackage({ ...two, keyId: record.keyId }, context);
    const forward = await app.safeModeService.importPackage({ ...four, keyId: record.keyId }, context);

    expect(invalidNine.state).toBe("quarantined");
    expect(rollback).toMatchObject({ state: "quarantined", reason: expect.stringMatching(/downgrade/i) });
    expect(forward.state).toBe("verified");
  });

  it("rejects a newer version whose effective period predates quarantined verified provenance after restart", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-package-effective-high-water-"));
    const databaseUrl = join(root, "edge.sqlite");
    const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const record = trustedKey(keys);
    const dependencies = { trustedKeyStore: { get: () => record }, now: () => asOfUtc };
    const three = signedPackage(root, "3.0.0", keys);
    const fourBase = signedPackage(root, "4.0.0", keys);
    const four = {
      ...fourBase,
      manifest: signManifest({ ...fourBase.manifest, issuedAtUtc: "2025-12-31T00:00:00.000Z", effectiveFromUtc: "2026-01-01T00:00:00.000Z", signature: "" }, keys.privateKey.export({ type: "pkcs1", format: "pem" }).toString()),
    };
    let server = await authenticatedTestServer({ databaseUrl, internet: "disabled", packageDirectory: root }, undefined, dependencies);
    app = server.app;
    const imported = await app.safeModeService.importPackage({ ...three, keyId: record.keyId }, context);
    await app.safeModeService.activatePackage({ packageId: imported.packageId, version: imported.version, keyId: record.keyId }, context);
    writeFileSync(join(root, three.directory, "map.txt"), "tampered effective high-water package");
    await app.safeModeService.getPackageState();
    await app.close();
    app = undefined;

    server = await authenticatedTestServer({ databaseUrl, internet: "disabled", packageDirectory: root }, undefined, dependencies);
    app = server.app;
    const rollback = await app.safeModeService.importPackage({ ...four, keyId: record.keyId }, context);

    expect(rollback).toMatchObject({ state: "quarantined", reason: expect.stringMatching(/effective|period|downgrade/i) });
  });

  it("fails closed when reloading pre-effective-date verified provenance", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-package-old-provenance-"));
    const databaseUrl = join(root, "edge.sqlite");
    const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const record = trustedKey(keys);
    const dependencies = { trustedKeyStore: { get: () => record }, now: () => asOfUtc };
    const one = signedPackage(root, "1.0.0", keys);
    const two = signedPackage(root, "2.0.0", keys);
    let server = await authenticatedTestServer({ databaseUrl, internet: "disabled", packageDirectory: root }, undefined, dependencies);
    app = server.app;
    const imported = await app.safeModeService.importPackage({ ...one, keyId: record.keyId }, context);
    await app.safeModeService.activatePackage({ packageId: imported.packageId, version: imported.version, keyId: record.keyId }, context);
    const row = app.edgeDatabase.sql().prepare("SELECT value FROM service_state WHERE key = ?").get("package_store") as { value: string };
    const oldSnapshot = JSON.parse(row.value) as Array<{ verifiedProvenance?: { effectiveFromUtc?: string } }>;
    delete oldSnapshot[0]?.verifiedProvenance?.effectiveFromUtc;
    app.edgeDatabase.sql().prepare("UPDATE service_state SET value = ? WHERE key = ?").run(JSON.stringify(oldSnapshot), "package_store");
    await app.close();
    app = undefined;

    server = await authenticatedTestServer({ databaseUrl, internet: "disabled", packageDirectory: root }, undefined, dependencies);
    app = server.app;

    expect((await app.safeModeService.getPackageState()).active).toEqual([]);
    await expect(app.safeModeService.importPackage({ ...two, keyId: record.keyId }, context)).rejects.toMatchObject({ code: "SAFE_MODE_DATABASE_FAILURE" });
  });

  it("reloads malformed quarantine evidence without disabling valid package writes", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-malformed-quarantine-reload-"));
    const databaseUrl = join(root, "edge.sqlite");
    let server = await authenticatedTestServer({ databaseUrl, internet: "disabled", packageDirectory: root });
    app = server.app;
    const malformed = await app.safeModeService.importPackage({ directory: ".", manifest: { schemaVersion: "1.0", packageId: "bad-package", kind: "map", version: "1.0.0" }, keyId: "missing-key" }, context);
    expect(malformed.state).toBe("quarantined");
    await app.close();
    app = undefined;

    const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const record = trustedKey(keys);
    const fixture = signedPackage(root, "1.0.0", keys);
    server = await authenticatedTestServer(
      { databaseUrl, internet: "disabled", packageDirectory: root },
      undefined,
      { trustedKeyStore: { get: () => record }, now: () => asOfUtc },
    );
    app = server.app;
    const state = await app.safeModeService.getPackageState();

    expect(state.quarantined).toEqual(expect.arrayContaining([expect.objectContaining({ packageId: "bad-package", state: "quarantined" })]));
    await expect(app.safeModeService.importPackage({ ...fixture, keyId: record.keyId }, context)).resolves.toMatchObject({ state: "verified" });
  });

  it("canonicalizes whitespace-malformed quarantine identity before restart", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-whitespace-quarantine-reload-"));
    const databaseUrl = join(root, "edge.sqlite");
    let server = await authenticatedTestServer({ databaseUrl, internet: "disabled", packageDirectory: root });
    app = server.app;
    const malformed = await app.safeModeService.importPackage({ directory: ".", manifest: { schemaVersion: "1.0", packageId: " bad-package ", kind: "map", version: " 9.0.0 " }, keyId: "missing-key" }, context);
    expect(malformed).toMatchObject({ state: "quarantined", packageId: "unknown", version: "unknown", untrustedManifestSha256: expect.stringMatching(/^[a-f0-9]{64}$/) });
    await app.close();
    app = undefined;

    const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const record = trustedKey(keys);
    const fixture = signedPackage(root, "1.0.0", keys);
    server = await authenticatedTestServer(
      { databaseUrl, internet: "disabled", packageDirectory: root },
      undefined,
      { trustedKeyStore: { get: () => record }, now: () => asOfUtc },
    );
    app = server.app;
    const state = await app.safeModeService.getPackageState();

    expect(state.quarantined).toEqual(expect.arrayContaining([expect.objectContaining({ packageId: "unknown", version: "unknown", untrustedManifestSha256: expect.stringMatching(/^[a-f0-9]{64}$/) })]));
    await expect(app.safeModeService.importPackage({ ...fixture, keyId: record.keyId }, context)).resolves.toMatchObject({ state: "verified" });
  });

  it("uses only reverified active packages as the default production safety authority", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-active-authority-"));
    const kinds = ["policy", "terminology", "regulatory"] as const;
    const keys = Object.fromEntries(kinds.map((kind) => [kind, generateKeyPairSync("rsa", { modulusLength: 2048 })])) as Record<typeof kinds[number], ReturnType<typeof generateKeyPairSync>>;
    const policy: PolicyPackage = {
      packageId: "policy-authority",
      version: "1.0.0",
      status: "approved",
      delegatedAuthorities: [],
      freshness: {
        aip: { maxAgeMinutes: 120, critical: true },
        notam: { maxAgeMinutes: 120, critical: true },
        weather: { maxAgeMinutes: 120, critical: true },
        terrain: { maxAgeMinutes: 120, critical: true },
        airspace: { maxAgeMinutes: 120, critical: true },
        policy: { maxAgeMinutes: 120, critical: true },
        regulation: { maxAgeMinutes: 120, critical: true },
      },
      signature: "package-authoritative",
    };
    const fixtures = [
      authorityPackage(root, "policy", "policy-authority", "policy-key", keys.policy, { "policy.json": policy }),
      authorityPackage(root, "terminology", "terminology-authority", "terminology-key", keys.terminology, { "terminology.json": { concepts: [] } }),
      authorityPackage(root, "regulatory", "regulatory-authority", "regulatory-key", keys.regulatory, {
        "evidence-snapshot.json": { snapshotId: "evidence-1", requirementIds: [], acceptedEvidenceIds: [] },
        "requirements.json": [],
      }),
    ];
    const trust = new Map(kinds.map((kind) => {
      const keyId = `${kind}-key`;
      return [keyId, {
        keyId,
        scope: kind,
        algorithm: "rsa-sha256" as const,
        publicKeyPem: keys[kind].publicKey.export({ type: "spki", format: "pem" }).toString(),
        addedAtUtc: "2026-08-09T16:00:00.000Z",
        addedByUserId: "administrator-1",
      }];
    }));
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: root },
      undefined,
      { safetyEvaluationProvider: undefined, trustedKeyStore: { get: (keyId: string) => trust.get(keyId) }, now: () => asOfUtc },
    );
    app = server.app;
    for (const fixture of fixtures) {
      const keyId = fixture.manifest.keyId;
      const imported = await app.safeModeService.importPackage({ ...fixture, keyId }, context);
      await app.safeModeService.activatePackage({ packageId: imported.packageId, version: imported.version, keyId }, context);
    }

    const created = await server.request({ method: "POST", url: "/api/missions", payload: { revision: (await import("./mission-fixture.js")).missionFixture() } });
    expect(created.statusCode).toBe(201);
    const evaluation = await server.request({ method: "GET", url: "/api/revisions/mission-1:r0/safety-result" });
    expect(evaluation.json()).toMatchObject({ status: "ready", policyPackage: { packageId: "policy-authority" }, terminologyPackage: { packageId: "terminology-authority" }, evidencePackage: { packageId: "regulatory-authority" } });
  });
});
