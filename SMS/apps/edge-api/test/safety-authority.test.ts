import { createHash, generateKeyPairSync } from "node:crypto";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";
import { tmpdir } from "node:os";
import { afterEach, describe, expect, it } from "vitest";
import { manifestContentDigest, signManifest, type SignedPackageManifest } from "@fac-isr/evidence";
import type { EdgeServer } from "../src/server.js";
import { ActivePackageSafetyResolver, DeterministicSafetyEvaluationProvider, UnavailableSafetyEvaluationProvider, validateSafetyEvaluationEnvelope } from "../src/services/safety-evaluation.js";
import { missionFixture, nowUtc, safetyResult, testSafetyEvaluationProvider } from "./mission-fixture.js";
import { authenticatedTestServer, type AuthenticatedTestServer } from "./http-test-auth.js";

const actorContext = Object.freeze({
  actorUserId: "administrator-1",
  clientSessionId: "offline-cli-session",
  occurredAtUtc: nowUtc,
});

interface PackageFixture {
  readonly directory: string;
  readonly manifest: SignedPackageManifest;
  readonly publicKeyPem: string;
}

function signedPackage(root: string, packageId: string, version: string, keyId: string): PackageFixture {
  const directoryPath = join(root, `${packageId}-${version.replaceAll(".", "-")}`);
  mkdirSync(directoryPath);
  const content = Buffer.from(`approved package ${packageId} ${version}\n`, "utf8");
  writeFileSync(join(directoryPath, "package.json"), content);
  const files = [{
    path: "package.json",
    sha256: createHash("sha256").update(content).digest("hex"),
    sizeBytes: content.byteLength,
  }];
  const keys = generateKeyPairSync("ed25519");
  const manifest = signManifest({
    schemaVersion: "1.0",
    packageId,
    kind: "policy",
    issuer: "Task 2 security fixture",
    version,
    issuedAtUtc: "2026-08-09T17:00:00.000Z",
    effectiveFromUtc: "2026-08-09T17:30:00.000Z",
    expiresAtUtc: "2027-08-09T17:30:00.000Z",
    geographicScope: "Colombia",
    contentSha256: manifestContentDigest(files),
    keyId,
    dependencies: [],
    files,
    qualification: "approved",
    caveats: ["test fixture"],
  }, keys.privateKey.export({ type: "pkcs8", format: "pem" }).toString());
  return {
    directory: basename(directoryPath),
    manifest,
    publicKeyPem: keys.publicKey.export({ type: "spki", format: "pem" }).toString(),
  };
}

function trustedKey(fixture: PackageFixture) {
  return Object.freeze({
    keyId: fixture.manifest.keyId,
    scope: "policy",
    algorithm: "ed25519",
    publicKeyPem: fixture.publicKeyPem,
    addedAtUtc: "2026-08-09T16:00:00.000Z",
    addedByUserId: "administrator-1",
  });
}

function trustedKeyStore(records: readonly ReturnType<typeof trustedKey>[]) {
  return { get: (keyId: string) => records.find((record) => record.keyId === keyId) };
}

function fixtureEvaluationProvider() {
  return testSafetyEvaluationProvider();
}

function activePackageResolver(evidenceSnapshot: unknown, requirements: unknown): ActivePackageSafetyResolver {
  return new ActivePackageSafetyResolver({
    async getReverifiedActivePackage(kind) {
      if (kind === "policy") return {
        packageId: "policy-authority",
        version: "1.0.0",
        documents: {
          "policy.json": JSON.stringify({
            packageId: "policy-authority",
            version: "1.0.0",
            status: "approved",
            delegatedAuthorities: [],
            freshness: {},
            signature: "trusted",
          }),
        } as Record<string, string>,
      };
      if (kind === "terminology") return { packageId: "terminology-authority", version: "1.0.0", documents: { "terminology.json": "{}" } as Record<string, string> };
      return {
        packageId: "regulatory-authority",
        version: "1.0.0",
        documents: {
          "evidence-snapshot.json": JSON.stringify(evidenceSnapshot),
          "requirements.json": JSON.stringify(requirements),
        } as Record<string, string>,
      };
    },
  });
}

function normalizedRequirement(requirementId: string, evidenceId: string) {
  return {
    requirementId,
    sourceRefs: [{ evidenceId, sourceId: "source-1", edition: "1", locator: { section: "1" }, quoteLanguage: "es", extractionSha256: "a".repeat(64), reviewState: "accepted" }],
    Spanish: `Requisito ${requirementId}`,
    EnglishControlled: `Requirement ${requirementId}`,
    applicabilityExpression: "state_aviation",
    severity: "hard",
    evidenceRequired: true,
    effectiveFromUtc: "2026-01-01T00:00:00.000Z",
    interpretationStatus: "approved",
    reviewerIds: ["reviewer-1"],
  };
}

describe("server-owned safety authority", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("rejects a caller-supplied forged ready safety result", async () => {
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      undefined,
      { safetyEvaluationProvider: fixtureEvaluationProvider() },
    );
    app = server.app;

    const response = await server.request({
      method: "POST",
      url: "/api/missions",
      payload: { revision: missionFixture(), safetyResult: safetyResult() },
    });

    expect(response.statusCode).toBe(400);
    expect(response.json()).toMatchObject({ error: "CALLER_SAFETY_RESULT_FORBIDDEN" });
  });

  it("stores only the injected provider's immutable evaluation envelope", async () => {
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      undefined,
      { safetyEvaluationProvider: fixtureEvaluationProvider() },
    );
    app = server.app;

    const created = await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });
    const result = await server.request({ method: "GET", url: "/api/revisions/mission-1:r0/safety-result" });

    expect(created.statusCode).toBe(201);
    expect(result.statusCode).toBe(200);
    expect(result.json()).toMatchObject({
      revisionId: "mission-1:r0",
      status: "ready",
      stale: false,
      policyPackage: { packageId: "policy-fixture", version: "1.0.0" },
      canonicalInputSha256: expect.stringMatching(/^[a-f0-9]{64}$/),
      evidenceSnapshotSha256: expect.stringMatching(/^[a-f0-9]{64}$/),
      resultSha256: expect.stringMatching(/^[a-f0-9]{64}$/),
    });
  });

  it("rejects caller safetyResult on material revisions", async () => {
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled" });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });

    const response = await server.request({
      method: "POST",
      url: "/api/missions/mission-1/revisions",
      payload: {
        expectedRevisionId: "mission-1:r0",
        change: { field: "route", previous: missionFixture().route, next: { ...missionFixture().route, routeHash: "route-hash-forged" } },
        safetyResult: safetyResult("mission-1:r1"),
      },
    });

    expect(response.statusCode).toBe(400);
    expect(response.json()).toMatchObject({ error: "CALLER_SAFETY_RESULT_FORBIDDEN" });
  });

  it("recomputes a revision-bound envelope for every material revision", async () => {
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled" });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });

    const revised = await server.request({
      method: "POST",
      url: "/api/missions/mission-1/revisions",
      payload: {
        expectedRevisionId: "mission-1:r0",
        change: { field: "route", previous: missionFixture().route, next: { ...missionFixture().route, routeHash: "route-hash-recomputed" } },
      },
    });
    const result = await server.request({ method: "GET", url: "/api/revisions/mission-1:r1/safety-result" });
    const prior = await server.request({ method: "GET", url: "/api/revisions/mission-1:r0/safety-result" });

    expect(revised.statusCode).toBe(201);
    expect(result.statusCode).toBe(200);
    expect(result.json()).toMatchObject({ revisionId: "mission-1:r1", stale: false });
    expect(prior.statusCode).toBe(200);
    expect(prior.json()).toMatchObject({ revisionId: "mission-1:r0", stale: true });
  });

  it("produces deterministic hashes from valid resolved policy and evidence fixtures", async () => {
    const modulePath = `../src/services/${"safety-evaluation"}.js`;
    const loaded = await import(modulePath).catch(() => undefined) as undefined | Record<string, unknown>;
    expect(loaded).toBeDefined();
    if (loaded === undefined) return;
    const Provider = loaded.DeterministicSafetyEvaluationProvider as new (options: Record<string, unknown>) => {
      evaluate(revision: ReturnType<typeof missionFixture>): Promise<Record<string, unknown>>;
    };
    const provider = new Provider({
      now: () => nowUtc,
      resolve: async () => ({
        requirements: [],
        policy: {
          packageId: "policy-fixture",
          version: "1.0.0",
          status: "approved",
          delegatedAuthorities: [],
          freshness: { weather: { maxAgeMinutes: 120, critical: true } },
          signature: "fixture-signature",
        },
        evidenceSnapshot: { snapshotId: "evidence-1", acceptedEvidenceIds: ["evidence-a"] },
        policyPackage: { packageId: "policy-fixture", version: "1.0.0" },
        terminologyPackage: { packageId: "terminology-fixture", version: "1.0.0" },
        evidencePackage: { packageId: "evidence-fixture", version: "1.0.0" },
      }),
    });

    const first = await provider.evaluate(missionFixture());
    const second = await provider.evaluate(missionFixture());

    expect(first).toEqual(second);
    expect(first).toMatchObject({
      revisionId: "mission-1:r0",
      status: "ready",
      canonicalInputSha256: expect.stringMatching(/^[a-f0-9]{64}$/),
      evidenceSnapshotSha256: expect.stringMatching(/^[a-f0-9]{64}$/),
      resultSha256: expect.stringMatching(/^[a-f0-9]{64}$/),
    });
    expect(Object.isFrozen(first)).toBe(true);
    expect(Object.isFrozen(first.evaluations)).toBe(true);
    expect(Object.isFrozen(first.blockers)).toBe(true);
  });

  it("rejects a readiness mutation that retains a blocked result hash", async () => {
    const blocked = await new UnavailableSafetyEvaluationProvider(() => nowUtc).evaluate(missionFixture() as never);
    const forged = JSON.parse(JSON.stringify({ ...blocked, status: "ready", blockers: [] })) as typeof blocked;

    expect(() => validateSafetyEvaluationEnvelope(forged, "mission-1:r0")).toThrow(/resultSha256/i);
  });

  it("enters fail-closed safe mode when a provider supplies a forged result envelope", async () => {
    const unavailable = new UnavailableSafetyEvaluationProvider(() => nowUtc);
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: mkdtempSync(join(tmpdir(), "fac-isr-forged-envelope-")) },
      undefined,
      {
        safetyEvaluationProvider: {
          async evaluate(revision: Parameters<typeof unavailable.evaluate>[0]) {
            const blocked = await unavailable.evaluate(revision);
            return JSON.parse(JSON.stringify({ ...blocked, status: "ready", blockers: [], invalidatedGates: [] }));
          },
          async isCurrent() { return true; },
        },
      },
    );
    app = server.app;

    const response = await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });

    expect(response.statusCode).toBe(503);
    expect(response.json()).toMatchObject({ error: "SAFETY_EVALUATION_INTEGRITY_FAILURE" });
    expect(app.auditLedger.isReadOnlySafeMode()).toBe(true);
  });

  it("rejects normalized impossible UTC dates in evaluation envelopes", async () => {
    const valid = await testSafetyEvaluationProvider().evaluate(missionFixture() as never);
    const impossible = JSON.parse(JSON.stringify({ ...valid, evaluatedAtUtc: "2026-02-31T18:00:00.000Z" })) as typeof valid;

    expect(() => validateSafetyEvaluationEnvelope(impossible, "mission-1:r0")).toThrow(/evaluatedAtUtc/i);
  });

  it("reevaluates time-dependent freshness at the trusted gate time", async () => {
    const provider = new DeterministicSafetyEvaluationProvider({
      now: () => nowUtc,
      resolve: async () => ({
        requirements: [{
          requirementId: "weather-current",
          sourceRefs: [{ evidenceId: "evidence-1", sourceId: "source-1", edition: "1", locator: { section: "1" }, quoteLanguage: "es", extractionSha256: "a".repeat(64), reviewState: "accepted" }],
          Spanish: "Tiempo vigente",
          EnglishControlled: "Current weather",
          applicabilityExpression: "state_aviation",
          severity: "hard",
          evidenceRequired: true,
          effectiveFromUtc: "2026-01-01T00:00:00.000Z",
          interpretationStatus: "approved",
          reviewerIds: ["reviewer-1"],
        }] as never,
        policy: {
          packageId: "policy-time",
          version: "1.0.0",
          status: "approved",
          delegatedAuthorities: [],
          freshness: { aip: { maxAgeMinutes: 60, critical: true }, notam: { maxAgeMinutes: 60, critical: true }, weather: { maxAgeMinutes: 60, critical: true }, terrain: { maxAgeMinutes: 60, critical: true }, airspace: { maxAgeMinutes: 60, critical: true }, policy: { maxAgeMinutes: 60, critical: true }, regulation: { maxAgeMinutes: 60, critical: true } },
          signature: "trusted",
        },
        evidenceSnapshot: { id: "evidence-1" },
        policyPackage: { packageId: "policy-time", version: "1.0.0" },
        terminologyPackage: { packageId: "terms-time", version: "1.0.0" },
        evidencePackage: { packageId: "evidence-time", version: "1.0.0" },
      }),
    });
    const revision = missionFixture({ dataSnapshots: [{ snapshotId: "weather-1", kind: "weather", packageId: "weather-pack", status: "current", capturedAtUtc: nowUtc }] });
    const envelope = await provider.evaluate(revision as never);

    await expect(provider.isCurrent(revision as never, envelope, "2026-08-09T19:00:00.001Z")).resolves.toBe(false);
  });

  it("rejects an active evidence snapshot that does not match the mission revision", async () => {
    const resolver = activePackageResolver({ snapshotId: "different-snapshot", requirementIds: [], acceptedEvidenceIds: [] }, []);

    await expect(resolver.resolve(missionFixture({ evidenceSnapshotId: "mission-snapshot" }) as never, nowUtc)).rejects.toThrow(/snapshot.*mission|mission.*snapshot|identity/i);
  });

  it("rejects an evidence snapshot whose requirement evidence references are not bound", async () => {
    const requirements = [{
      requirementId: "requirement-1",
      sourceRefs: [{ evidenceId: "evidence-1", sourceId: "source-1", edition: "1", locator: { section: "1" }, quoteLanguage: "es", extractionSha256: "a".repeat(64), reviewState: "accepted" }],
      Spanish: "Requisito",
      EnglishControlled: "Requirement",
      applicabilityExpression: "state_aviation",
      severity: "hard",
      evidenceRequired: true,
      effectiveFromUtc: "2026-01-01T00:00:00.000Z",
      interpretationStatus: "approved",
      reviewerIds: ["reviewer-1"],
    }];
    const resolver = activePackageResolver({ snapshotId: "evidence-1", requirementIds: ["requirement-1"], acceptedEvidenceIds: [] }, requirements);

    await expect(resolver.resolve(missionFixture() as never, nowUtc)).rejects.toThrow(/evidence/i);
  });

  it("accepts one immutable evidence identity cited by multiple distinct requirements", async () => {
    const requirements = [normalizedRequirement("requirement-1", "evidence-1"), normalizedRequirement("requirement-2", "evidence-1")];
    const resolver = activePackageResolver({ snapshotId: "evidence-1", requirementIds: ["requirement-1", "requirement-2"], acceptedEvidenceIds: ["evidence-1"] }, requirements);

    await expect(resolver.resolve(missionFixture() as never, nowUtc)).resolves.toMatchObject({ requirements: [{ requirementId: "requirement-1" }, { requirementId: "requirement-2" }] });
  });

  it("rejects duplicate evidence reference records within one requirement", async () => {
    const requirement = normalizedRequirement("requirement-1", "evidence-1");
    const requirements = [{ ...requirement, sourceRefs: [requirement.sourceRefs[0], requirement.sourceRefs[0]] }];
    const resolver = activePackageResolver({ snapshotId: "evidence-1", requirementIds: ["requirement-1"], acceptedEvidenceIds: ["evidence-1"] }, requirements);

    await expect(resolver.resolve(missionFixture() as never, nowUtc)).rejects.toThrow(/duplicate.*reference/i);
  });

  it("rejects nested safetyResult inside a revision change", async () => {
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled" });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });

    const response = await server.request({
      method: "POST",
      url: "/api/missions/mission-1/revisions",
      payload: {
        expectedRevisionId: "mission-1:r0",
        change: { field: "route", previous: missionFixture().route, next: { ...missionFixture().route, routeHash: "nested-forgery" }, safetyResult: safetyResult("mission-1:r1") },
      },
    });

    expect(response.statusCode).toBe(400);
    expect(response.json()).toMatchObject({ error: "CALLER_SAFETY_RESULT_FORBIDDEN" });
  });

  it("invalidates approvals before publishing a recomputed envelope", async () => {
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      [
        { userId: "commander-1", roles: ["commander"], missionIds: ["mission-1"] },
        { userId: "operator-1", roles: ["operator"], missionIds: ["mission-1"] },
      ],
    );
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } }, "commander-1");
    await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/checklist-responses", payload: { responseId: "check-op", itemId: "operator", response: "pass" } }, "operator-1");
    await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/gates/operator", payload: { decision: "accept", aircraftId: "aircraft-1", reason: "accepted", evidenceSnapshotId: "evidence-1", checklistResponseIds: ["check-op"] } }, "operator-1");

    await app.missionService.recomputeSafetyEvaluation("mission-1:r0", actorContext);

    expect((app.missionService.getMission("mission-1") as { gateApprovals: unknown[] }).gateApprovals).toEqual([]);
    await expect(app.auditLedger.queryAudit({ type: "gate.invalidated" })).resolves.toHaveLength(1);
  });
});

describe("trusted package state boundary", () => {
  let app: EdgeServer | undefined;
  let server: AuthenticatedTestServer;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("quarantines an attacker-signed package instead of trusting its request key", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-attacker-package-"));
    const attacker = signedPackage(root, "attacker-policy", "1.0.0", "attacker-key");
    server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: root },
      undefined,
      { trustedKeyStore: trustedKeyStore([]) },
    );
    app = server.app;

    const record = await app.safeModeService.importPackage({
      directory: attacker.directory,
      manifest: attacker.manifest,
      keyId: attacker.manifest.keyId,
      publicKeyPem: attacker.publicKeyPem,
      asOfUtc: nowUtc,
    }, actorContext);

    expect(record).toMatchObject({ state: "quarantined", reason: expect.stringMatching(/unknown trusted key/i) });
  });

  it("rejects activation when the package key is no longer trusted", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-unknown-key-"));
    const fixture = signedPackage(root, "policy-unknown-key", "1.0.0", "removed-key");
    server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: root },
      undefined,
      { trustedKeyStore: trustedKeyStore([]) },
    );
    app = server.app;

    await expect(async () => app!.safeModeService.activatePackage({
      packageId: fixture.manifest.packageId,
      version: fixture.manifest.version,
      keyId: fixture.manifest.keyId,
    }, actorContext)).rejects.toMatchObject({ code: "TRUSTED_KEY_UNKNOWN" });
  });

  it("marks existing evaluation stale and invalidates approvals when a package activates", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-package-activation-"));
    const fixture = signedPackage(root, "policy-next", "2.0.0", "trusted-policy-key");
    server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: root },
      [
        { userId: "commander-1", roles: ["commander"], missionIds: ["mission-1"] },
        { userId: "operator-1", roles: ["operator"], missionIds: ["mission-1"] },
        { userId: "administrator-1", roles: ["administrator"], missionIds: ["mission-1"] },
      ],
      { safetyEvaluationProvider: fixtureEvaluationProvider(), trustedKeyStore: trustedKeyStore([trustedKey(fixture)]) },
    );
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } }, "commander-1");
    await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/checklist-responses", payload: { responseId: "check-op", itemId: "operator", response: "pass" } }, "operator-1");
    const firstGate = await server.request({
      method: "POST",
      url: "/api/revisions/mission-1:r0/gates/operator",
      payload: { decision: "accept", aircraftId: "aircraft-1", reason: "accepted", evidenceSnapshotId: "evidence-1", checklistResponseIds: ["check-op"] },
    }, "operator-1");
    expect(firstGate.statusCode).toBe(201);

    const imported = await app.safeModeService.importPackage({
      directory: fixture.directory,
      manifest: fixture.manifest,
      keyId: fixture.manifest.keyId,
      asOfUtc: nowUtc,
    }, actorContext);
    expect(imported.state).toBe("verified");
    await app.safeModeService.activatePackage({
      packageId: fixture.manifest.packageId,
      version: fixture.manifest.version,
      keyId: fixture.manifest.keyId,
    }, actorContext);

    const evaluation = await server.request({ method: "GET", url: "/api/revisions/mission-1:r0/safety-result" }, "operator-1");
    const mission = await server.request({ method: "GET", url: "/api/missions/mission-1" }, "operator-1");
    expect(evaluation.json()).toMatchObject({ revisionId: "mission-1:r0", stale: true });
    expect(mission.json().gateApprovals).toEqual([]);
  });

  it("blocks a gate attempt while the evaluation is stale", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-stale-gate-"));
    const fixture = signedPackage(root, "policy-stale-gate", "2.0.0", "trusted-stale-key");
    server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled", packageDirectory: root },
      [
        { userId: "commander-1", roles: ["commander"], missionIds: ["mission-1"] },
        { userId: "operator-1", roles: ["operator"], missionIds: ["mission-1"] },
      ],
      { safetyEvaluationProvider: fixtureEvaluationProvider(), trustedKeyStore: trustedKeyStore([trustedKey(fixture)]) },
    );
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } }, "commander-1");
    await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/checklist-responses", payload: { responseId: "check-op", itemId: "operator", response: "pass" } }, "operator-1");
    await app.safeModeService.importPackage({ directory: fixture.directory, manifest: fixture.manifest, keyId: fixture.manifest.keyId, asOfUtc: nowUtc }, actorContext);
    await app.safeModeService.activatePackage({ packageId: fixture.manifest.packageId, version: fixture.manifest.version, keyId: fixture.manifest.keyId }, actorContext);

    const gate = await server.request({
      method: "POST",
      url: "/api/revisions/mission-1:r0/gates/operator",
      payload: { decision: "accept", aircraftId: "aircraft-1", reason: "attempted stale acceptance", evidenceSnapshotId: "evidence-1", checklistResponseIds: ["check-op"] },
    }, "operator-1");

    expect(gate.statusCode).toBe(409);
    expect(gate.json()).toMatchObject({ error: "SAFETY_EVALUATION_STALE" });
  });

  it("detects trusted package input changes after evaluation before accepting a gate", async () => {
    const modulePath = `../src/services/${"safety-evaluation"}.js`;
    const loaded = await import(modulePath) as Record<string, unknown>;
    const Provider = loaded.DeterministicSafetyEvaluationProvider as new (options: Record<string, unknown>) => {
      evaluate(revision: ReturnType<typeof missionFixture>): Promise<Record<string, unknown>>;
      isCurrent(revision: ReturnType<typeof missionFixture>, envelope: Record<string, unknown>): Promise<boolean>;
    };
    let policyVersion = "1.0.0";
    const provider = new Provider({
      now: () => nowUtc,
      resolve: async () => ({
        requirements: [],
        policy: {
          packageId: "policy-mutable",
          version: policyVersion,
          status: "approved",
          delegatedAuthorities: [],
          freshness: {},
          signature: `signature-${policyVersion}`,
        },
        evidenceSnapshot: { snapshotId: "evidence-1", acceptedEvidenceIds: [] },
        policyPackage: { packageId: "policy-mutable", version: policyVersion },
        terminologyPackage: { packageId: "terminology-fixture", version: "1.0.0" },
        evidencePackage: { packageId: "evidence-fixture", version: "1.0.0" },
      }),
    });
    server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      [
        { userId: "commander-1", roles: ["commander"], missionIds: ["mission-1"] },
        { userId: "operator-1", roles: ["operator"], missionIds: ["mission-1"] },
      ],
      { safetyEvaluationProvider: provider },
    );
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } }, "commander-1");
    await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/checklist-responses", payload: { responseId: "check-op", itemId: "operator", response: "pass" } }, "operator-1");
    policyVersion = "1.0.1";

    const gate = await server.request({
      method: "POST",
      url: "/api/revisions/mission-1:r0/gates/operator",
      payload: { decision: "accept", aircraftId: "aircraft-1", reason: "attempted changed-package acceptance", evidenceSnapshotId: "evidence-1", checklistResponseIds: ["check-op"] },
    }, "operator-1");

    expect(gate.statusCode).toBe(409);
    expect(gate.json()).toMatchObject({ error: "SAFETY_EVALUATION_STALE" });
  });

  it("keeps package import and activation unavailable to network clients", async () => {
    server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled" });
    app = server.app;

    const imported = await server.request({ method: "POST", url: "/api/packages/import", payload: {} });
    const activated = await server.request({ method: "POST", url: "/api/packages/activate", payload: {} });
    const listed = await server.request({ method: "GET", url: "/api/packages" });

    expect(imported.statusCode).toBe(404);
    expect(activated.statusCode).toBe(404);
    expect(listed.statusCode).toBe(200);
    expect(listed.json()).toMatchObject({ active: [], quarantined: [] });
  });
});
