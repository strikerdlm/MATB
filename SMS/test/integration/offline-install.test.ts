import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { afterEach, describe, expect, it } from "vitest";
import { copyAcceptanceEvidence } from "../../scripts/build-offline-bundle.mjs";
import { verifyBundle } from "../../scripts/verify-offline.mjs";

const smsRoot = process.cwd();
const temporaryDirectories: string[] = [];
const acceptanceEvidenceSourcePaths = [
  "docs/release/known-limitations.md",
  "docs/release/release-manifest.json",
  "docs/release/release-manifest.sig",
  "docs/release/release-public-key.pem",
  "docs/release/sbom.cdx.json",
  "docs/release/security-scan.json",
  "docs/release/state-aviation-acceptance-checklist.md",
  "docs/release/test-report.json",
  "docs/release/verification-matrix.md",
] as const;
const acceptanceStateSourcePaths = [
  "docs/release/operational-readiness-record.json",
  "docs/release/verification-signatures.jsonl",
  "docs/release/state-aviation-acceptance-checklist.md",
  "docs/release/known-limitations.md",
  "docs/release/verification-matrix.md",
  "docs/release/release-manifest.json",
] as const;

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson((value as Record<string, unknown>)[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function sha256(value: string | Buffer): string {
  return createHash("sha256").update(value).digest("hex");
}

function jsonWithNewline(value: unknown): string {
  return `${JSON.stringify(value, null, 2)}\n`;
}

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

async function fixture(
  files: Readonly<Record<string, string | Buffer>> = {},
  manifestOverrides: Readonly<Record<string, unknown>> = {},
): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "fac-isr-offline-fixture-"));
  temporaryDirectories.push(root);
  for (const [path, contents] of Object.entries(files)) {
    const target = join(root, path);
    await mkdir(resolve(target, ".."), { recursive: true });
    await writeFile(target, contents);
  }
  const inventory = Object.entries(files).map(([path, contents]) => ({
    path,
    sha256: sha256(contents),
    sizeBytes: Buffer.byteLength(contents),
  })).sort((left, right) => left.path.localeCompare(right.path));
  await writeFile(join(root, "bundle-manifest.json"), JSON.stringify({
    schemaVersion: "1.0",
    releaseId: "offline-fixture",
    commit: "0".repeat(40),
    builtAtUtc: "2026-08-10T00:00:00Z",
    files: inventory,
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

function tarEntry(path: string, contents: Buffer): Buffer {
  const header = Buffer.alloc(512);
  header.write(path, 0, 100, "utf8");
  header.write(`${contents.length.toString(8).padStart(11, "0")}\0`, 124, 12, "ascii");
  const padding = Buffer.alloc(Math.ceil(contents.length / 512) * 512 - contents.length);
  return Buffer.concat([header, contents, padding]);
}

function minimalOciArchive(): { archive: Buffer; manifestDigest: string } {
  const imageManifest = Buffer.from('{"schemaVersion":2}\n', "utf8");
  const manifestHash = sha256(imageManifest);
  const manifestDigest = `sha256:${manifestHash}`;
  const layout = Buffer.from('{"imageLayoutVersion":"1.0.0"}\n', "utf8");
  const index = Buffer.from(`${JSON.stringify({ schemaVersion: 2, manifests: [{ digest: manifestDigest }] })}\n`, "utf8");
  return {
    archive: Buffer.concat([
      tarEntry("oci-layout", layout),
      tarEntry("index.json", index),
      tarEntry(`blobs/sha256/${manifestHash}`, imageManifest),
      Buffer.alloc(1024),
    ]),
    manifestDigest,
  };
}

async function addDirectoryFiles(
  files: Record<string, string | Buffer>,
  sourceDirectory: string,
  bundleDirectory: string,
): Promise<void> {
  for (const entry of await readdir(sourceDirectory, { withFileTypes: true })) {
    const source = join(sourceDirectory, entry.name);
    const bundled = `${bundleDirectory}/${entry.name}`;
    if (entry.isDirectory()) await addDirectoryFiles(files, source, bundled);
    else if (entry.isFile()) files[bundled] = await readFile(source);
    else throw new Error(`unsupported fixture source: ${source}`);
  }
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

async function acceptanceWorkflowFixture(): Promise<{
  files: Record<string, string>;
  acceptanceEvidence: Record<string, unknown>;
}> {
  const sourceRecord = JSON.parse(await readFile(join(smsRoot, "docs/release/operational-readiness-record.json"), "utf8")) as {
    recordId: string;
    releaseId: string;
    requiredReviews: Array<{ scope: string; requiredReviewerRoles: string[]; [key: string]: unknown }>;
    [key: string]: unknown;
  };
  const signatureId = "institutional-risk-authority-001";
  const record = {
    ...sourceRecord,
    requiredReviews: sourceRecord.requiredReviews.map((review) => review.scope === "risk-authority"
      ? { ...review, signatureIds: [signatureId] }
      : review),
  };
  const files = await acceptanceEvidenceFiles(record, "");
  const evidenceMappings: Array<{ sourcePath: string; bundlePath: string; sha256: string }> = [];
  for (const sourcePath of acceptanceEvidenceSourcePaths) {
    const contents = await readFile(join(smsRoot, sourcePath.replace(/^docs\//u, "docs/")), "utf8");
    const digest = sha256(contents);
    const bundlePath = `reports/acceptance/review-evidence/${digest}-${sourcePath.split("/").at(-1)}`;
    files[bundlePath] = contents;
    evidenceMappings.push({ sourcePath, bundlePath, sha256: digest });
  }
  const packetEvidence = evidenceMappings.map(({ sourcePath, sha256: digest }) => ({ path: sourcePath, sha256: digest }));
  const currentPackets = [];
  let historicalPacket: Record<string, unknown> | undefined;
  let historicalPacketBytes = "";
  for (const review of record.requiredReviews) {
    const roleCoverage = review.requiredReviewerRoles.map((role) => ({
      role,
      signatureId: review.scope === "risk-authority" && role === "designated risk authority" ? signatureId : null,
      decision: review.scope === "risk-authority" && role === "designated risk authority" ? "accept" : null,
    }));
    const unsignedPacket = {
      schemaVersion: "1.0",
      recordType: "review-packet",
      releaseId: record.releaseId,
      readinessRecordId: record.recordId,
      asOfUtc: "2026-08-10T00:00:00Z",
      scope: review.scope,
      requiredReviewerRoles: review.requiredReviewerRoles,
      currentStatus: "pending",
      roleCoverage,
      acceptanceStateFingerprint: sha256("fixture acceptance state"),
      evidence: packetEvidence,
    };
    const packet = { ...unsignedPacket, packetId: sha256(canonicalJson(unsignedPacket)) };
    const packetBytes = jsonWithNewline(packet);
    const path = `reports/acceptance/reviewer-packets/${review.scope}/packet-manifest.json`;
    files[path] = packetBytes;
    currentPackets.push({ scope: review.scope, packetId: packet.packetId, path, sha256: sha256(packetBytes) });
    if (review.scope === "risk-authority") {
      historicalPacket = packet;
      historicalPacketBytes = packetBytes;
    }
  }
  if (historicalPacket === undefined) throw new Error("risk-authority fixture packet is missing");
  const packetDigest = sha256(historicalPacketBytes);
  const sourcePacketPath = `docs/release/acceptance-packets/${String(historicalPacket.packetId)}.json`;
  const packetBundlePath = `reports/acceptance/recorded-decisions/${packetDigest}-${String(historicalPacket.packetId)}.json`;
  files[packetBundlePath] = historicalPacketBytes;

  const artifact = jsonWithNewline({
    schemaVersion: "1.0",
    recordType: "institutional-acceptance-artifact",
    classification: "unclassified-controlled",
    contentType: "controlled-safety-metadata",
    reference: "fixture-risk-authority-001",
  });
  const artifactSha256 = sha256(artifact);
  const artifactSourcePath = "docs/release/acceptance-artifacts/risk-authority-001.json";
  const artifactBundlePath = `reports/acceptance/recorded-decisions/${artifactSha256}-risk-authority-001.json`;
  files[artifactBundlePath] = artifact;
  const decision = {
    schemaVersion: "1.0",
    recordType: "institutional-decision",
    signatureId,
    sourcePacketId: historicalPacket.packetId,
    sourcePacketPath,
    sourcePacketSha256: packetDigest,
    supersedesSignatureId: null,
    releaseId: record.releaseId,
    scope: "risk-authority",
    reviewer: {
      identity: "Fixture Risk Authority",
      identityType: "human",
      organizationUnit: "FAC Safety Directorate",
      role: "designated risk authority",
    },
    decision: "accept",
    signedAtUtc: "2026-08-09T00:00:00.000Z",
    evidenceHashes: packetEvidence,
    conflicts: [],
    conditions: [],
    reviewDueAtUtc: "2027-08-10T00:00:00.000Z",
    systemOfRecordRef: "fixture://acceptance/risk-authority-001",
    institutionalArtifact: { path: artifactSourcePath, sha256: artifactSha256 },
  };
  files["reports/acceptance/verification-signatures.jsonl"] = `${JSON.stringify(decision)}\n`;
  const coreStatePaths = new Map([
    ["docs/release/operational-readiness-record.json", "reports/acceptance/operational-readiness-record.json"],
    ["docs/release/verification-signatures.jsonl", "reports/acceptance/verification-signatures.jsonl"],
    ["docs/release/state-aviation-acceptance-checklist.md", "reports/acceptance/state-aviation-acceptance-checklist.md"],
    ["docs/release/known-limitations.md", "reports/acceptance/known-limitations.md"],
  ]);
  const acceptanceState = acceptanceStateSourcePaths.map((sourcePath) => {
    const bundlePath = coreStatePaths.get(sourcePath)
      ?? evidenceMappings.find((mapping) => mapping.sourcePath === sourcePath)?.bundlePath;
    if (bundlePath === undefined) throw new Error(`fixture acceptance-state mapping is missing: ${sourcePath}`);
    return { path: sourcePath, sha256: sha256(files[bundlePath]!) };
  }).sort((left, right) => left.path.localeCompare(right.path));
  const currentFingerprint = sha256(canonicalJson(acceptanceState));
  for (const metadata of currentPackets) {
    const packet = JSON.parse(files[metadata.path]!) as Record<string, unknown>;
    packet.acceptanceStateFingerprint = currentFingerprint;
    delete packet.packetId;
    const packetId = sha256(canonicalJson(packet));
    const packetBytes = jsonWithNewline({ ...packet, packetId });
    metadata.packetId = packetId;
    metadata.sha256 = sha256(packetBytes);
    files[metadata.path] = packetBytes;
  }
  files["bin/verify-offline.mjs"] = await readFile(join(smsRoot, "scripts/verify-offline.mjs"), "utf8");
  files["bin/acceptance-contracts.mjs"] = await readFile(join(smsRoot, "scripts/acceptance-contracts.mjs"), "utf8");

  return {
    files,
    acceptanceEvidence: {
      recordPath: "reports/acceptance/operational-readiness-record.json",
      checklistPath: "reports/acceptance/state-aviation-acceptance-checklist.md",
      knownLimitationsPath: "reports/acceptance/known-limitations.md",
      signatureLogPath: "reports/acceptance/verification-signatures.jsonl",
      qualification: "blocked",
      operationalReady: false,
      signatureCount: 1,
      workflow: {
        currentPackets: currentPackets.sort((left, right) => left.scope.localeCompare(right.scope)),
        evidenceMappings,
        recordedDecisions: [{
          signatureId,
          scope: "risk-authority",
          role: "designated risk authority",
          sourcePacketPath,
          packetBundlePath,
          sourcePacketSha256: packetDigest,
          artifactSourcePath,
          artifactBundlePath,
          artifactSha256,
        }],
        roleHeads: [{ scope: "risk-authority", role: "designated risk authority", signatureId, decision: "accept" }],
      },
    },
  };
}

type AcceptanceWorkflowFixture = Awaited<ReturnType<typeof acceptanceWorkflowFixture>>;

async function completeAcceptanceWorkflowBundle(workflow: AcceptanceWorkflowFixture): Promise<string> {
  const files: Record<string, string | Buffer> = { ...workflow.files };
  const provenance = join(smsRoot, "docs/provenance");
  await addDirectoryFiles(files, join(provenance, "package-content"), "packages/regulatory/package-content");
  for (const name of [
    "evidence-package-manifest.json",
    "evidence-package-manifest.sig",
    "evidence-package-public-key.pem",
  ]) {
    files[`packages/regulatory/${name}`] = await readFile(join(provenance, name));
  }
  const regulatoryManifest = JSON.parse(String(files["packages/regulatory/evidence-package-manifest.json"]));
  files["packages/package-index.json"] = jsonWithNewline({
    schemaVersion: "1.0",
    packages: [{ version: regulatoryManifest.version }],
  });
  files["runtime/schema.json"] = jsonWithNewline({ schemaVersion: 1, journalMode: "WAL", foreignKeys: true });
  files["provenance/map-package-register.jsonl"] = await readFile(join(provenance, "map-package-register.jsonl"));
  files["provenance/kernel-golden-case-report.md"] = await readFile(join(provenance, "kernel-golden-case-report.md"));
  files["install/compose.edge.yml"] = await readFile(join(smsRoot, "docker/compose.edge.yml"));
  files["install/README.md"] = "Install on an approved encrypted volume and provision TLS before use.\n";
  files["reports/image-smoke.json"] = jsonWithNewline({ status: "pass", networkMode: "none", readOnlyRoot: true });
  files["sbom/npm.cdx.json"] = jsonWithNewline({ bomFormat: "CycloneDX", components: [] });
  files["licenses/THIRD_PARTY_NOTICES.md"] = "# Fixture notices\n";
  const image = minimalOciArchive();
  files["images/fac-isr-sms-edge.oci.tar"] = image.archive;
  return fixture(files, {
    acceptanceEvidence: workflow.acceptanceEvidence,
    releaseAttestation: null,
    image: {
      path: "images/fac-isr-sms-edge.oci.tar",
      archiveSha256: sha256(image.archive),
      manifestDigest: image.manifestDigest,
      platform: "linux/amd64",
    },
  });
}

function refreshCurrentPacketFingerprints(workflow: AcceptanceWorkflowFixture): void {
  const metadata = workflow.acceptanceEvidence.workflow as {
    evidenceMappings: Array<{ sourcePath: string; bundlePath: string; sha256: string }>;
    currentPackets: Array<{ path: string; packetId: string; sha256: string }>;
  };
  const coreStatePaths = new Map([
    ["docs/release/operational-readiness-record.json", "reports/acceptance/operational-readiness-record.json"],
    ["docs/release/verification-signatures.jsonl", "reports/acceptance/verification-signatures.jsonl"],
    ["docs/release/state-aviation-acceptance-checklist.md", "reports/acceptance/state-aviation-acceptance-checklist.md"],
    ["docs/release/known-limitations.md", "reports/acceptance/known-limitations.md"],
  ]);
  const acceptanceState = acceptanceStateSourcePaths.map((sourcePath) => {
    const bundlePath = coreStatePaths.get(sourcePath)
      ?? metadata.evidenceMappings.find((mapping) => mapping.sourcePath === sourcePath)?.bundlePath;
    if (bundlePath === undefined) throw new Error(`fixture acceptance-state mapping is missing: ${sourcePath}`);
    return { path: sourcePath, sha256: sha256(workflow.files[bundlePath]!) };
  }).sort((left, right) => left.path.localeCompare(right.path));
  const fingerprint = sha256(canonicalJson(acceptanceState));
  for (const current of metadata.currentPackets) {
    const packet = JSON.parse(workflow.files[current.path]!) as Record<string, unknown>;
    packet.acceptanceStateFingerprint = fingerprint;
    delete packet.packetId;
    const packetId = sha256(canonicalJson(packet));
    const bytes = jsonWithNewline({ ...packet, packetId });
    current.packetId = packetId;
    current.sha256 = sha256(bytes);
    workflow.files[current.path] = bytes;
  }
}

describe("disconnected edge installation", () => {
  it("copies the exact institutional acceptance package into the transfer bundle", async () => {
    const stage = await mkdtemp(join(tmpdir(), "fac-isr-acceptance-stage-"));
    temporaryDirectories.push(stage);

    const evidence = await copyAcceptanceEvidence(stage, { asOfUtc: "2026-08-12T16:00:00.000Z" });

    expect(evidence).toMatchObject({
      recordPath: "reports/acceptance/operational-readiness-record.json",
      qualification: "blocked",
      operationalReady: false,
      signatureCount: 0,
    });
    expect(evidence.workflow.currentPackets).toHaveLength(9);
    expect(evidence.workflow.recordedDecisions).toEqual([]);
    for (const packet of evidence.workflow.currentPackets) {
      expect(await readFile(join(stage, packet.path), "utf8")).toContain(`"packetId": "${packet.packetId}"`);
    }

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

  it("verifies a disconnected archived human decision while readiness remains blocked", async () => {
    const workflow = await acceptanceWorkflowFixture();
    const bundle = await completeAcceptanceWorkflowBundle(workflow);

    const result = spawnSync(process.execPath, [join(bundle, "bin/verify-offline.mjs"), "--bundle", bundle, "--no-network", "--json"], {
      cwd: bundle,
      encoding: "utf8",
    });
    const report = JSON.parse(result.stdout) as Awaited<ReturnType<typeof verifyBundle>>;

    expect(result.status, result.stderr).toBe(0);
    expect(report.ok).toBe(true);
    expect(report.operationalReady).toBe(false);
    expect(report.checks).toContainEqual(expect.objectContaining({
      id: "institutional-acceptance",
      status: "warn",
      detail: expect.stringContaining("blocked"),
    }));
  });

  it("keeps current packet identity pinned to build time during a later verification", async () => {
    const workflow = await acceptanceWorkflowFixture();
    const bundle = await fixture(workflow.files, { acceptanceEvidence: workflow.acceptanceEvidence });

    const result = await verifyBundle(bundle, { noNetwork: true, asOfUtc: "2026-08-12T16:00:00.000Z" });

    expect(result.checks).toContainEqual(expect.objectContaining({
      id: "institutional-acceptance",
      status: "warn",
    }));
  });

  const acceptanceWorkflowTamperCases = [
    {
      name: "current packet",
      detail: /current packet|packet.*hash/iu,
      mutate: (workflow: Awaited<ReturnType<typeof acceptanceWorkflowFixture>>) => {
        const packet = workflow.acceptanceEvidence.workflow as { currentPackets: Array<{ path: string }> };
        workflow.files[packet.currentPackets[0]!.path] += " ";
      },
    },
    {
      name: "historical packet",
      detail: /historical packet|source packet/iu,
      mutate: (workflow: Awaited<ReturnType<typeof acceptanceWorkflowFixture>>) => {
        const metadata = workflow.acceptanceEvidence.workflow as { recordedDecisions: Array<{ packetBundlePath: string }> };
        workflow.files[metadata.recordedDecisions[0]!.packetBundlePath] += " ";
      },
    },
    {
      name: "institutional artifact",
      detail: /institutional artifact/iu,
      mutate: (workflow: Awaited<ReturnType<typeof acceptanceWorkflowFixture>>) => {
        const metadata = workflow.acceptanceEvidence.workflow as { recordedDecisions: Array<{ artifactBundlePath: string }> };
        workflow.files[metadata.recordedDecisions[0]!.artifactBundlePath] += " ";
      },
    },
    {
      name: "role-head metadata",
      detail: /role head/iu,
      mutate: (workflow: Awaited<ReturnType<typeof acceptanceWorkflowFixture>>) => {
        const metadata = workflow.acceptanceEvidence.workflow as { roleHeads: Array<{ signatureId: string }> };
        metadata.roleHeads[0]!.signatureId = "tampered-role-head";
      },
    },
    {
      name: "source-to-bundle mapping",
      detail: /mapping|evidence/iu,
      mutate: (workflow: Awaited<ReturnType<typeof acceptanceWorkflowFixture>>) => {
        const metadata = workflow.acceptanceEvidence.workflow as { evidenceMappings: Array<{ sourcePath: string }> };
        metadata.evidenceMappings[0]!.sourcePath = "docs/release/tampered-evidence.json";
      },
    },
    {
      name: "acceptance-state fingerprint",
      detail: /acceptance-state fingerprint/iu,
      mutate: (workflow: Awaited<ReturnType<typeof acceptanceWorkflowFixture>>) => {
        const path = "reports/acceptance/operational-readiness-record.json";
        const record = JSON.parse(workflow.files[path]!) as Record<string, unknown>;
        record.recordStatus = "tampered-but-still-blocked";
        workflow.files[path] = jsonWithNewline(record);
      },
    },
    {
      name: "mapped evidence path traversal",
      detail: /mapping|directory|traversal/iu,
      mutate: (workflow: AcceptanceWorkflowFixture) => {
        const metadata = workflow.acceptanceEvidence.workflow as { evidenceMappings: Array<{ sourcePath: string; bundlePath: string }> };
        const mapping = metadata.evidenceMappings.find((candidate) => candidate.sourcePath === "docs/release/known-limitations.md");
        if (mapping === undefined) throw new Error("known-limitations mapping is missing");
        mapping.bundlePath = "reports/acceptance/review-evidence/../known-limitations.md";
      },
    },
    {
      name: "historical packet path traversal",
      detail: /historical packet|directory|traversal/iu,
      mutate: (workflow: AcceptanceWorkflowFixture) => {
        const metadata = workflow.acceptanceEvidence.workflow as { recordedDecisions: Array<{ packetBundlePath: string }> };
        const decision = metadata.recordedDecisions[0]!;
        workflow.files["reports/acceptance/historical-packet-escape.json"] = workflow.files[decision.packetBundlePath]!;
        decision.packetBundlePath = "reports/acceptance/recorded-decisions/../historical-packet-escape.json";
      },
    },
    {
      name: "institutional artifact path traversal",
      detail: /institutional artifact|directory|traversal/iu,
      mutate: (workflow: AcceptanceWorkflowFixture) => {
        const metadata = workflow.acceptanceEvidence.workflow as { recordedDecisions: Array<{ artifactBundlePath: string }> };
        const decision = metadata.recordedDecisions[0]!;
        workflow.files["reports/acceptance/artifact-escape.json"] = workflow.files[decision.artifactBundlePath]!;
        decision.artifactBundlePath = "reports/acceptance/recorded-decisions/../artifact-escape.json";
      },
    },
    {
      name: "current packet release and readiness identifiers",
      detail: /current packet.*release|readiness/iu,
      mutate: (workflow: AcceptanceWorkflowFixture) => {
        const metadata = workflow.acceptanceEvidence.workflow as { currentPackets: Array<{ path: string; packetId: string; sha256: string }> };
        const current = metadata.currentPackets[0]!;
        const packet = JSON.parse(workflow.files[current.path]!) as Record<string, unknown>;
        packet.releaseId = "foreign-release@9.9.9";
        packet.readinessRecordId = "foreign-readiness-record";
        delete packet.packetId;
        const packetId = sha256(canonicalJson(packet));
        const bytes = jsonWithNewline({ ...packet, packetId });
        current.packetId = packetId;
        current.sha256 = sha256(bytes);
        workflow.files[current.path] = bytes;
      },
    },
    {
      name: "historical decision release and readiness identifiers",
      detail: /historical packet.*release|readiness|decision.*release/iu,
      mutate: (workflow: AcceptanceWorkflowFixture) => {
        const metadata = workflow.acceptanceEvidence.workflow as {
          recordedDecisions: Array<{
            packetBundlePath: string;
            sourcePacketPath: string;
            sourcePacketSha256: string;
          }>;
        };
        const recorded = metadata.recordedDecisions[0]!;
        const packet = JSON.parse(workflow.files[recorded.packetBundlePath]!) as Record<string, unknown>;
        packet.releaseId = "foreign-release@9.9.9";
        packet.readinessRecordId = "foreign-readiness-record";
        delete packet.packetId;
        const packetId = sha256(canonicalJson(packet));
        const packetBytes = jsonWithNewline({ ...packet, packetId });
        const packetHash = sha256(packetBytes);
        workflow.files[recorded.packetBundlePath] = packetBytes;
        recorded.sourcePacketPath = `docs/release/acceptance-packets/${packetId}.json`;
        recorded.sourcePacketSha256 = packetHash;

        const ledgerPath = "reports/acceptance/verification-signatures.jsonl";
        const decision = JSON.parse(workflow.files[ledgerPath]!) as Record<string, unknown>;
        decision.releaseId = "foreign-release@9.9.9";
        decision.sourcePacketId = packetId;
        decision.sourcePacketPath = recorded.sourcePacketPath;
        decision.sourcePacketSha256 = packetHash;
        workflow.files[ledgerPath] = `${JSON.stringify(decision)}\n`;
        refreshCurrentPacketFingerprints(workflow);
      },
    },
  ];

  for (const tamperCase of acceptanceWorkflowTamperCases) {
    it(`rejects tampered acceptance workflow ${tamperCase.name}`, async () => {
      const workflow = await acceptanceWorkflowFixture();
      tamperCase.mutate(workflow);
      const bundle = await fixture(workflow.files, { acceptanceEvidence: workflow.acceptanceEvidence });

      const result = await verifyOffline(bundle);

      expect(result.report.checks).toContainEqual(expect.objectContaining({
        id: "institutional-acceptance",
        status: "fail",
        detail: expect.stringMatching(tamperCase.detail),
      }));
    });
  }

  it("rejects an incomplete acceptance transaction journal in the bundle", async () => {
    const files = await acceptanceEvidenceFiles();
    files["reports/acceptance/.acceptance-transaction.json"] = "{}\n";
    const bundle = await fixture(files);

    const result = await verifyOffline(bundle);

    expect(result.report.checks).toContainEqual(expect.objectContaining({
      id: "institutional-acceptance",
      status: "fail",
      detail: expect.stringMatching(/transaction|journal|incomplete/iu),
    }));
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
