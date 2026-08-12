import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { afterEach, describe, expect, it } from "vitest";
import { copyAcceptanceEvidence } from "../../scripts/build-offline-bundle.mjs";
import { verifyBundle } from "../../scripts/verify-offline.mjs";

const smsRoot = process.cwd();
const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

async function fixture(
  files: Readonly<Record<string, string>> = {},
  manifestOverrides: Readonly<Record<string, unknown>> = {},
): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "fac-isr-offline-fixture-"));
  temporaryDirectories.push(root);
  for (const [path, contents] of Object.entries(files)) {
    const target = join(root, path);
    await mkdir(resolve(target, ".."), { recursive: true });
    await writeFile(target, contents, "utf8");
  }
  await writeFile(join(root, "bundle-manifest.json"), JSON.stringify({
    schemaVersion: "1.0",
    releaseId: "offline-fixture",
    commit: "0".repeat(40),
    builtAtUtc: "2026-08-10T00:00:00Z",
    files: [],
    image: {
      path: "images/fac-isr-sms-edge.oci.tar",
      archiveSha256: "0".repeat(64),
      manifestDigest: `sha256:${"0".repeat(64)}`,
      platform: "linux/amd64",
    },
    ...manifestOverrides,
  }), "utf8");
  return root;
}

async function verifyOffline(bundle: string) {
  const report = await verifyBundle(bundle, { noNetwork: true });
  return { status: report.ok ? 0 : 1, report };
}

async function acceptanceEvidenceFiles(record?: unknown, signatures?: string): Promise<Record<string, string>> {
  const source = join(smsRoot, "docs/release");
  const currentRecord = record ?? JSON.parse(await readFile(join(source, "operational-readiness-record.json"), "utf8"));
  return {
    "reports/acceptance/operational-readiness-record.json": `${JSON.stringify(currentRecord, null, 2)}\n`,
    "reports/acceptance/state-aviation-acceptance-checklist.md": await readFile(join(source, "state-aviation-acceptance-checklist.md"), "utf8"),
    "reports/acceptance/known-limitations.md": await readFile(join(source, "known-limitations.md"), "utf8"),
    "reports/acceptance/verification-signatures.jsonl": signatures ?? await readFile(join(source, "verification-signatures.jsonl"), "utf8"),
  };
}

describe("disconnected edge installation", () => {
  it("copies the exact institutional acceptance package into the transfer bundle", async () => {
    const stage = await mkdtemp(join(tmpdir(), "fac-isr-acceptance-stage-"));
    temporaryDirectories.push(stage);

    const evidence = await copyAcceptanceEvidence(stage);

    expect(evidence).toMatchObject({
      recordPath: "reports/acceptance/operational-readiness-record.json",
      qualification: "blocked",
      operationalReady: false,
      signatureCount: 0,
    });

    for (const name of [
      "operational-readiness-record.json",
      "state-aviation-acceptance-checklist.md",
      "known-limitations.md",
      "verification-signatures.jsonl",
    ]) {
      const source = await readFile(join(smsRoot, "docs/release", name), "utf8");
      const bundled = await readFile(join(stage, "reports/acceptance", name), "utf8");
      expect(bundled).toBe(source);
    }
  });

  it("exposes hardened image and bundle commands", async () => {
    const packageJson = JSON.parse(await readFile(join(smsRoot, "package.json"), "utf8")) as {
      scripts?: Record<string, string>;
    };
    const dockerfile = await readFile(join(smsRoot, "Dockerfile"), "utf8");
    const compose = await readFile(join(smsRoot, "docker/compose.edge.yml"), "utf8");

    expect(packageJson.scripts).toMatchObject({
      "build:offline": "node scripts/build-offline-bundle.mjs",
      "verify:offline": "node scripts/verify-offline.mjs",
    });
    expect(dockerfile).toMatch(/node:22\.23\.2-bookworm-slim@sha256:[a-f0-9]{64}/);
    expect(dockerfile).toContain("USER 10001:10001");
    expect(compose).toContain("internal: true");
    expect(compose).toContain("read_only: true");
    expect(compose).toContain("no-new-privileges:true");
    expect(compose).toContain("/opt/sms/packages:ro");
  });

  it("fails with a named terrain check when the local package register is absent", async () => {
    const bundle = await fixture();

    const result = await verifyOffline(bundle);

    expect(result.status).toBe(1);
    expect(result.report.ok).toBe(false);
    expect(result.report.checks).toContainEqual(expect.objectContaining({
      id: "terrain-package",
      status: "fail",
    }));
  });

  it("fails with a named institutional-acceptance check when its evidence is absent", async () => {
    const bundle = await fixture();

    const result = await verifyOffline(bundle);

    expect(result.status).toBe(1);
    expect(result.report.checks).toContainEqual(expect.objectContaining({
      id: "institutional-acceptance",
      status: "fail",
    }));
  });

  it("reports present pending institutional evidence as a release-blocking warning", async () => {
    const bundle = await fixture(await acceptanceEvidenceFiles());

    const result = await verifyOffline(bundle);

    expect(result.report.operationalReady).toBe(false);
    expect(result.report.checks).toContainEqual(expect.objectContaining({
      id: "institutional-acceptance",
      status: "warn",
      detail: expect.stringContaining("blocked"),
    }));
  });

  it("rejects an automated identity that forges bundled institutional acceptance", async () => {
    const sourceRecord = JSON.parse(await readFile(join(smsRoot, "docs/release/operational-readiness-record.json"), "utf8")) as {
      requiredReviews: Array<Record<string, unknown>>;
      [key: string]: unknown;
    };
    const automatedSignature = {
      schemaVersion: "1.0",
      signatureId: "forged-automation",
      reviewer: { identity: "ci", identityType: "automation", organizationUnit: "software", role: "test runner" },
      scope: "risk-authority",
      decision: "accept",
      signedAtUtc: "2026-08-09T00:00:00.000Z",
      evidenceHashes: [{ path: "reports/image-smoke.json", sha256: "a".repeat(64) }],
      conflicts: [],
      conditions: [],
      reviewDueAtUtc: "2026-09-12T00:00:00.000Z",
    };
    const record = {
      ...sourceRecord,
      qualification: "accepted",
      operationalReady: true,
      readinessDecision: "accept",
      knownLimitations: [],
      requiredReviews: sourceRecord.requiredReviews.map((review) => ({
        ...review,
        status: "accepted",
        signatureIds: ["forged-automation"],
      })),
    };
    const bundle = await fixture(await acceptanceEvidenceFiles(record, `${JSON.stringify(automatedSignature)}\n`));

    const result = await verifyOffline(bundle);

    expect(result.report.operationalReady).toBe(false);
    expect(result.report.checks).toContainEqual(expect.objectContaining({
      id: "institutional-acceptance",
      status: "fail",
      detail: expect.stringMatching(/automation|human/u),
    }));
  });

  it("rejects a bundled readiness claim while institutional reviews and limitations remain open", async () => {
    const sourceRecord = JSON.parse(await readFile(join(smsRoot, "docs/release/operational-readiness-record.json"), "utf8")) as Record<string, unknown>;
    const record = {
      ...sourceRecord,
      qualification: "accepted",
      operationalReady: true,
      readinessDecision: "accept",
    };
    const bundle = await fixture(await acceptanceEvidenceFiles(record, ""));

    const result = await verifyOffline(bundle);

    expect(result.report.operationalReady).toBe(false);
    expect(result.report.checks).toContainEqual(expect.objectContaining({
      id: "institutional-acceptance",
      status: "fail",
      detail: expect.stringMatching(/pending|limitation|blocked/u),
    }));
  });

  it("rejects an operational acceptance claim without linked human signatures", async () => {
    const sourceRecord = JSON.parse(await readFile(join(smsRoot, "docs/release/operational-readiness-record.json"), "utf8")) as {
      requiredReviews: Array<Record<string, unknown>>;
      [key: string]: unknown;
    };
    const record = {
      ...sourceRecord,
      qualification: "accepted",
      operationalReady: true,
      readinessDecision: "accept",
      knownLimitations: [],
      requiredReviews: sourceRecord.requiredReviews.map((review) => ({
        ...review,
        status: "accepted",
        signatureIds: [],
      })),
    };
    const bundle = await fixture(await acceptanceEvidenceFiles(record, ""));

    const result = await verifyOffline(bundle);

    expect(result.report.operationalReady).toBe(false);
    expect(result.report.checks).toContainEqual(expect.objectContaining({
      id: "institutional-acceptance",
      status: "fail",
      detail: expect.stringMatching(/human signature|linked signature/u),
    }));
  });

  it("rejects human acceptance signatures whose cited evidence is absent", async () => {
    const sourceRecord = JSON.parse(await readFile(join(smsRoot, "docs/release/operational-readiness-record.json"), "utf8")) as {
      requiredReviews: Array<Record<string, unknown>>;
      [key: string]: unknown;
    };
    const signatures = sourceRecord.requiredReviews.map((review) => ({
      schemaVersion: "1.0",
      signatureId: `human-${String(review.scope)}`,
      reviewer: {
        identity: `reviewer-${String(review.scope)}`,
        identityType: "human",
        organizationUnit: "Colombian Aerospace Force",
        role: `qualified reviewer for ${String(review.scope)}`,
      },
      scope: review.scope,
      decision: "accept",
      signedAtUtc: "2026-08-09T00:00:00.000Z",
      evidenceHashes: [{ path: "reports/absent-acceptance-evidence.json", sha256: "a".repeat(64) }],
      conflicts: [],
      conditions: [],
      reviewDueAtUtc: "2027-08-12T00:00:00.000Z",
    }));
    const record = {
      ...sourceRecord,
      qualification: "accepted",
      operationalReady: true,
      readinessDecision: "accept",
      knownLimitations: [],
      requiredReviews: sourceRecord.requiredReviews.map((review) => ({
        ...review,
        status: "accepted",
        signatureIds: [`human-${String(review.scope)}`],
      })),
    };
    const ledger = `${signatures.map((signature) => JSON.stringify(signature)).join("\n")}\n`;
    const bundle = await fixture(await acceptanceEvidenceFiles(record, ledger));

    const result = await verifyOffline(bundle);

    expect(result.report.operationalReady).toBe(false);
    expect(result.report.checks).toContainEqual(expect.objectContaining({
      id: "institutional-acceptance",
      status: "fail",
      detail: expect.stringMatching(/evidence|ENOENT|hash/u),
    }));
  });

  it("rejects acceptance metadata that contradicts the bundled readiness record", async () => {
    const files = await acceptanceEvidenceFiles();
    const bundle = await fixture(files, {
      acceptanceEvidence: {
        recordPath: "reports/acceptance/operational-readiness-record.json",
        checklistPath: "reports/acceptance/state-aviation-acceptance-checklist.md",
        knownLimitationsPath: "reports/acceptance/known-limitations.md",
        signatureLogPath: "reports/acceptance/verification-signatures.jsonl",
        qualification: "accepted",
        operationalReady: true,
        signatureCount: 99,
      },
    });

    const result = await verifyOffline(bundle);

    expect(result.report.checks).toContainEqual(expect.objectContaining({
      id: "institutional-acceptance",
      status: "fail",
      detail: expect.stringMatching(/metadata|contradict/u),
    }));
  });

  it("rejects private signing material anywhere in the transfer bundle", async () => {
    const bundle = await fixture({
      "secrets/release-private.key": "-----BEGIN PRIVATE KEY-----\nfixture-only\n-----END PRIVATE KEY-----\n",
    });

    const result = await verifyOffline(bundle);

    expect(result.status).toBe(1);
    expect(result.report.checks).toContainEqual(expect.objectContaining({
      id: "private-key-material",
      status: "fail",
    }));
  });

  const image = process.env.SMS_OCI_IMAGE;
  it.skipIf(image === undefined)("starts the edge image with network access blocked", () => {
    const result = spawnSync("docker", [
      "run",
      "--rm",
      "--network",
      "none",
      "--read-only",
      "--tmpfs",
      "/tmp:rw,noexec,nosuid,size=16m",
      image!,
      "/opt/sms/bin/healthcheck",
    ], { cwd: smsRoot, encoding: "utf8" });

    expect(result.status, result.stderr).toBe(0);
    expect(result.stdout).toContain("PASS edge self-test");
  });
});
