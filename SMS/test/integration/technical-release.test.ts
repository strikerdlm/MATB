import { createHash, generateKeyPairSync, sign } from "node:crypto";
import { execFile } from "node:child_process";
import { chmod, mkdir, mkdtemp, readFile, readdir, rm, stat, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { promisify } from "node:util";
import { afterEach, describe, expect, it } from "vitest";
import { inspectCandidateArtifact, verifyTechnicalRelease } from "../../scripts/verify-technical-release.mjs";
import * as releaseVerifier from "../../scripts/verify-technical-release.mjs";

const execute = promisify(execFile);
const SOURCE_COMMIT = "a".repeat(40);
const NOW = new Date("2026-08-25T12:00:00.000Z");
const temporaryDirectories: string[] = [];

interface Fixture {
  readonly root: string;
  readonly publicKeyPath: string;
  readonly privateKey: ReturnType<typeof generateKeyPairSync>["privateKey"];
  readonly manifestPath: string;
  readonly signaturePath: string;
  readonly publishPath: string;
}

interface MutableArtifactRecord {
  target: string;
  inventorySha256: string;
  readonly [key: string]: unknown;
}

interface MutableEvidenceItem {
  readonly type: string;
  readonly path: string;
  sha256: string;
}

interface MutableManifest {
  technicalReady: boolean;
  operationalReady: boolean;
  readonly artifacts: MutableArtifactRecord[];
  readonly evidence: MutableEvidenceItem[];
  readonly [key: string]: unknown;
}

interface MutableEvidenceRecord {
  generatedAtUtc: string;
  sourceCommit: string;
  [key: string]: unknown;
}

function sha256(value: string | Buffer): string {
  return createHash("sha256").update(value).digest("hex");
}

async function sha256File(path: string): Promise<string> {
  return sha256(await readFile(path));
}

async function writeJson(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`);
}

async function nativeArchive(root: string, target: "linux-x64" | "win32-x64"): Promise<{ path: string; inventorySha256: string }> {
  const stage = join(root, `stage-${target}`);
  const bundle = join(stage, "fac-isr-sms");
  await mkdir(bundle, { recursive: true });
  const release = {
    release: "TEST-ONLY-fac-isr-sms@0.2.0-rc.1",
    target,
    nodeVersion: "22.23.2",
    internet: "disabled",
    operationalReady: false,
    production: false,
    runtimeProvenance: "controlled-test-fixture",
  };
  await writeJson(join(bundle, "release.json"), release);
  await writeFile(join(bundle, "TEST-ONLY.txt"), "TEST-ONLY controlled release verifier fixture\n");
  const files = [];
  for (const name of ["TEST-ONLY.txt", "release.json"]) {
    const path = join(bundle, name);
    await chmod(path, 0o444);
    files.push({ path: name, sha256: await sha256File(path), sizeBytes: (await stat(path)).size, mode: 0o444 });
  }
  await writeJson(join(bundle, "inventory.json"), {
    schemaVersion: "1.0",
    release: "TEST-ONLY-fac-isr-sms@0.2.0-rc.1",
    target,
    inventoryPath: "inventory.json",
    files,
  });
  await chmod(join(bundle, "inventory.json"), 0o444);
  const inventoryInfo = await stat(join(bundle, "inventory.json"));
  const trusted = [...files, {
    path: "inventory.json",
    sha256: await sha256File(join(bundle, "inventory.json")),
    sizeBytes: inventoryInfo.size,
    mode: 0o444,
  }];
  const inventoryText = `${trusted.map((item) => `${item.path}\t${item.sha256}\t${item.sizeBytes}\t444`).join("\n")}\n`;
  await writeFile(join(bundle, "inventory.tsv"), inventoryText, { mode: 0o444 });
  const artifacts = join(root, "artifacts");
  await mkdir(artifacts, { recursive: true });
  const name = target === "linux-x64"
    ? "TEST-ONLY-fac-isr-sms-0.2.0-rc.1-linux-x64.tar.gz"
    : "TEST-ONLY-fac-isr-sms-0.2.0-rc.1-win32-x64.zip";
  const path = join(artifacts, name);
  if (target === "linux-x64") await execute("tar", ["-czf", path, "fac-isr-sms"], { cwd: stage });
  else await execute("zip", ["-X", "-q", "-r", path, "fac-isr-sms"], { cwd: stage });
  return { path, inventorySha256: sha256(inventoryText) };
}

interface OciOptions { readonly configUser?: string; readonly extraBlob?: boolean; readonly missingLayer?: boolean; readonly symlinkBlob?: boolean }

async function ociArchive(root: string, options: OciOptions = {}): Promise<{ path: string; inventorySha256: string }> {
  const stage = join(root, "stage-oci");
  await rm(stage, { recursive: true, force: true });
  await mkdir(join(stage, "blobs/sha256"), { recursive: true });
  const config = Buffer.from(`${JSON.stringify({
    architecture: "amd64",
    os: "linux",
    config: {
      User: options.configUser ?? "10001:10001",
      Labels: {
        "org.opencontainers.image.version": "0.2.0-rc.1",
        "org.opencontainers.image.revision": SOURCE_COMMIT,
        "org.fac-isr.sms.runtime-provenance": "controlled-test-fixture",
      },
    },
    rootfs: { type: "layers", diff_ids: [] },
  })}\n`);
  const configDigest = sha256(config);
  await writeFile(join(stage, "blobs/sha256", configDigest), config);
  const manifest = Buffer.from(`${JSON.stringify({
    schemaVersion: 2,
    mediaType: "application/vnd.oci.image.manifest.v1+json",
    config: { mediaType: "application/vnd.oci.image.config.v1+json", digest: `sha256:${configDigest}`, size: config.length },
    layers: options.missingLayer ? [{ mediaType: "application/vnd.oci.image.layer.v1.tar", digest: `sha256:${"d".repeat(64)}`, size: 12 }] : [],
  })}\n`);
  const manifestDigest = sha256(manifest);
  await writeFile(join(stage, "blobs/sha256", manifestDigest), manifest);
  const index = {
    schemaVersion: 2,
    mediaType: "application/vnd.oci.image.index.v1+json",
    manifests: [{
      mediaType: "application/vnd.oci.image.manifest.v1+json",
      digest: `sha256:${manifestDigest}`,
      size: manifest.length,
      platform: { architecture: "amd64", os: "linux" },
      annotations: { "org.opencontainers.image.ref.name": "TEST-ONLY-fac-isr-sms:0.2.0-rc.1" },
    }],
  };
  await writeJson(join(stage, "index.json"), index);
  await writeFile(join(stage, "oci-layout"), '{"imageLayoutVersion":"1.0.0"}\n');
  if (options.extraBlob) await writeFile(join(stage, "blobs/sha256", "e".repeat(64)), "unexpected\n");
  if (options.symlinkBlob) await symlink("../../index.json", join(stage, "blobs/sha256", "f".repeat(64)));
  const artifacts = join(root, "artifacts");
  await mkdir(artifacts, { recursive: true });
  const path = join(artifacts, "TEST-ONLY-fac-isr-sms-0.2.0-rc.1-linux-amd64.oci.tar");
  await execute("tar", ["-cf", path, "blobs", "index.json", "oci-layout"], { cwd: stage });
  return { path, inventorySha256: await sha256File(join(stage, "index.json")) };
}

async function replaceOciArtifact(fixture: Fixture, options: OciOptions): Promise<void> {
  const rebuilt = await ociArchive(fixture.root, options);
  const manifest = JSON.parse(await readFile(fixture.manifestPath, "utf8")) as MutableManifest;
  const artifact = manifest.artifacts[2] as MutableArtifactRecord & { sha256: string; sizeBytes: number };
  artifact.sha256 = await sha256File(rebuilt.path);
  artifact.sizeBytes = (await stat(rebuilt.path)).size;
  const inventoryPath = join(fixture.root, "inventories/linux-amd64-oci.json");
  const inventory = JSON.parse(await readFile(inventoryPath, "utf8"));
  inventory.artifactSha256 = artifact.sha256;
  inventory.artifactSizeBytes = artifact.sizeBytes;
  inventory.contentInventorySha256 = rebuilt.inventorySha256;
  await writeJson(inventoryPath, inventory);
  artifact.inventorySha256 = await sha256File(inventoryPath);
  const smokeItem = manifest.evidence.find((item) => item.type === "oci-linux-smoke");
  if (smokeItem === undefined) throw new Error("missing OCI smoke fixture");
  const smokePath = resolve(fixture.root, smokeItem.path);
  const smoke = JSON.parse(await readFile(smokePath, "utf8"));
  smoke.artifactSha256 = artifact.sha256;
  await writeJson(smokePath, smoke);
  smokeItem.sha256 = await sha256File(smokePath);
  await writeJson(fixture.manifestPath, manifest);
  await resign(fixture);
}

async function resign(fixture: Fixture, mutate?: (manifest: MutableManifest) => void): Promise<void> {
  const manifest = JSON.parse(await readFile(fixture.manifestPath, "utf8")) as MutableManifest;
  mutate?.(manifest);
  const bytes = Buffer.from(`${JSON.stringify(manifest, null, 2)}\n`);
  await writeFile(fixture.manifestPath, bytes);
  await writeFile(fixture.signaturePath, sign(null, bytes, fixture.privateKey).toString("base64"));
}

async function createFixture(): Promise<Fixture> {
  const root = await mkdtemp(join(tmpdir(), "TEST-ONLY-sms-release-"));
  temporaryDirectories.push(root);
  const nativeLinux = await nativeArchive(root, "linux-x64");
  const nativeWindows = await nativeArchive(root, "win32-x64");
  const oci = await ociArchive(root);
  const generatedAtUtc = "2026-08-25T11:30:00.000Z";
  const artifactInputs = [
    { target: "linux-x64", kind: "native", ...nativeLinux },
    { target: "win32-x64", kind: "native", ...nativeWindows },
    { target: "linux-amd64-oci", kind: "oci", ...oci },
  ];
  const artifacts = [];
  for (const input of artifactInputs) {
    const name = input.path.split(/[\\/]/).at(-1)!;
    const record = {
      schemaVersion: "1.0",
      fixtureClassification: "TEST-ONLY-NON-PRODUCTION",
      sourceCommit: SOURCE_COMMIT,
      generatedAtUtc,
      target: input.target,
      artifactName: name,
      artifactSha256: await sha256File(input.path),
      artifactSizeBytes: (await stat(input.path)).size,
      contentInventorySha256: input.inventorySha256,
    };
    const inventoryPath = join(root, "inventories", `${input.target}.json`);
    await writeJson(inventoryPath, record);
    artifacts.push({
      target: input.target,
      kind: input.kind,
      path: `artifacts/${name}`,
      sha256: record.artifactSha256,
      sizeBytes: record.artifactSizeBytes,
      inventoryPath: `inventories/${input.target}.json`,
      inventorySha256: await sha256File(inventoryPath),
    });
  }
  const evidence = [];
  const allArtifactSha256s = Object.fromEntries(artifacts.map((artifact) => [artifact.target, artifact.sha256]));
  const scannerRaw = {
    "dependency-scan": { path: "scan-output/npm-audit.json", body: { auditReportVersion: 2, metadata: { vulnerabilities: { total: 0 } } } },
    "oci-vulnerability-scan": { path: "scan-output/oci-vulnerabilities.json", body: { matches: [] } },
    "malware-scan": { path: "scan-output/malware-scan.json", body: { malwareFound: 0, errors: 0, artifactSha256s: allArtifactSha256s } },
  } as const;
  for (const value of Object.values(scannerRaw)) await writeJson(join(root, value.path), value.body);
  const evidenceRecords = [
    ["sbom", "evidence/sbom.cdx.json", { bomFormat: "CycloneDX", specVersion: "1.6", components: [{ name: "TEST-ONLY-fac-isr-sms", version: "0.2.0-rc.1" }], artifactSha256s: allArtifactSha256s }],
    ["dependency-scan", "evidence/dependency-scan.json", { scanner: "TEST-ONLY npm-audit", threshold: "low", findingsAtOrAboveThreshold: 0, artifactSha256s: allArtifactSha256s, scannerOutputPath: scannerRaw["dependency-scan"].path, scannerOutputSha256: await sha256File(join(root, scannerRaw["dependency-scan"].path)) }],
    ["oci-vulnerability-scan", "evidence/oci-scan.json", { scanner: "TEST-ONLY grype", threshold: "high", findingsAtOrAboveThreshold: 0, artifactSha256s: { "linux-amd64-oci": artifacts[2].sha256 }, scannerOutputPath: scannerRaw["oci-vulnerability-scan"].path, scannerOutputSha256: await sha256File(join(root, scannerRaw["oci-vulnerability-scan"].path)) }],
    ["malware-scan", "evidence/malware-scan.json", { scanner: "TEST-ONLY malware", threshold: "zero-malware", findingsAtOrAboveThreshold: 0, artifactSha256s: allArtifactSha256s, scannerOutputPath: scannerRaw["malware-scan"].path, scannerOutputSha256: await sha256File(join(root, scannerRaw["malware-scan"].path)) }],
    ["native-linux-smoke", "evidence/linux-smoke.json", { platform: "ubuntu-24.04", artifactSha256: artifacts[0].sha256, clean: true }],
    ["native-windows-smoke", "evidence/windows-smoke.json", { platform: "windows-2022", artifactSha256: artifacts[1].sha256, clean: true }],
    ["oci-linux-smoke", "evidence/oci-smoke.json", { platform: "ubuntu-24.04", artifactSha256: artifacts[2].sha256, clean: true }],
    ["ubuntu-ci", "evidence/ubuntu-ci.json", { platform: "ubuntu-24.04", clean: true, artifactSha256s: { "linux-x64": artifacts[0].sha256, "linux-amd64-oci": artifacts[2].sha256 } }],
    ["windows-ci", "evidence/windows-ci.json", { platform: "windows-2022", clean: true, artifactSha256s: { "win32-x64": artifacts[1].sha256 } }],
  ] as const;
  for (const [type, relativePath, detail] of evidenceRecords) {
    await writeJson(join(root, relativePath), {
      schemaVersion: "1.0",
      fixtureClassification: "TEST-ONLY-NON-PRODUCTION",
      type,
      sourceCommit: SOURCE_COMMIT,
      generatedAtUtc,
      status: "pass",
      ...detail,
    });
    const raw = scannerRaw[type as keyof typeof scannerRaw];
    evidence.push({
      type,
      path: relativePath,
      sha256: await sha256File(join(root, relativePath)),
      ...(raw ? { scannerOutputPath: raw.path, scannerOutputSha256: await sha256File(join(root, raw.path)) } : {}),
    });
  }
  const manifestPath = join(root, "TEST-ONLY-release-evidence.json");
  const signaturePath = join(root, "TEST-ONLY-release-evidence.sig");
  await writeJson(manifestPath, {
    schemaVersion: "1.0",
    fixtureClassification: "TEST-ONLY-NON-PRODUCTION",
    releaseId: "TEST-ONLY-fac-isr-sms@0.2.0-rc.1",
    version: "0.2.0-rc.1",
    sourceCommit: SOURCE_COMMIT,
    generatedAtUtc,
    technicalReady: true,
    operationalReady: false,
    artifacts,
    evidence,
  });
  const { privateKey, publicKey } = generateKeyPairSync("ed25519");
  const publicKeyPath = join(root, "TEST-ONLY-public-key.pem");
  await writeFile(publicKeyPath, publicKey.export({ type: "spki", format: "pem" }));
  const fixture = { root, publicKeyPath, privateKey, manifestPath, signaturePath, publishPath: join(root, "published") };
  await resign(fixture);
  return fixture;
}

async function verify(fixture: Fixture) {
  return verifyTechnicalRelease(fixture.root, {
    expectedSourceCommit: SOURCE_COMMIT,
    publicKeyPath: fixture.publicKeyPath,
    manifestPath: fixture.manifestPath,
    signaturePath: fixture.signaturePath,
    now: NOW,
    maxEvidenceAgeMs: 24 * 60 * 60 * 1000,
    testOnlyFixture: true,
    publishDirectory: fixture.publishPath,
  });
}

async function mutateEvidence(fixture: Fixture, type: string, mutation: (record: MutableEvidenceRecord) => void): Promise<void> {
  const manifest = JSON.parse(await readFile(fixture.manifestPath, "utf8")) as MutableManifest;
  const item = manifest.evidence.find((candidate) => candidate.type === type);
  if (item === undefined) throw new Error(`missing fixture evidence: ${type}`);
  const path = resolve(fixture.root, item.path);
  const record = JSON.parse(await readFile(path, "utf8")) as MutableEvidenceRecord;
  mutation(record);
  await writeJson(path, record);
  item.sha256 = await sha256File(path);
  await writeJson(fixture.manifestPath, manifest);
  await resign(fixture);
}

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

describe("technical release evidence gate", () => {
  it("accepts a fresh, exact, controlled TEST-ONLY signed fixture", async () => {
    const report = await verify(await createFixture());
    expect(report.ok, JSON.stringify(report.checks, null, 2)).toBe(true);
    expect(report.technicalReady).toBe(true);
    expect(report.operationalReady).toBe(false);
  });

  it("rejects a stale source inventory and publishes no candidate", async () => {
    const fixture = await createFixture();
    const inventoryPath = join(fixture.root, "inventories/linux-x64.json");
    const inventory = JSON.parse(await readFile(inventoryPath, "utf8"));
    inventory.sourceCommit = "b".repeat(40);
    await writeJson(inventoryPath, inventory);
    await resign(fixture, (manifest) => {
      manifest.artifacts[0].inventorySha256 = sha256(JSON.stringify(inventory, null, 2) + "\n");
    });
    const report = await verify(fixture);
    expect(report.ok).toBe(false);
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "artifact-inventories", status: "fail" }));
    await expect(stat(fixture.publishPath)).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("rejects an absent or invalid detached signature", async () => {
    const absent = await createFixture();
    await rm(absent.signaturePath);
    expect((await verify(absent)).checks).toContainEqual(expect.objectContaining({ id: "signature", status: "fail" }));
    const invalid = await createFixture();
    await writeFile(invalid.signaturePath, Buffer.alloc(64).toString("base64"));
    expect((await verify(invalid)).checks).toContainEqual(expect.objectContaining({ id: "signature", status: "fail" }));
  });

  it("rejects development or test-only naming on the production path", async () => {
    const fixture = await createFixture();
    const report = await verifyTechnicalRelease(fixture.root, {
      expectedSourceCommit: SOURCE_COMMIT,
      publicKeyPath: fixture.publicKeyPath,
      manifestPath: fixture.manifestPath,
      signaturePath: fixture.signaturePath,
      now: NOW,
    });
    expect(report.ok).toBe(false);
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "release-identity", status: "fail" }));
  });

  it("rejects a cross-platform manifest mismatch", async () => {
    const fixture = await createFixture();
    await resign(fixture, (manifest) => { manifest.artifacts[1].target = "linux-x64"; });
    const report = await verify(fixture);
    expect(report.ok).toBe(false);
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "artifact-set", status: "fail" }));
  });

  it.each(["sbom", "dependency-scan", "native-linux-smoke", "windows-ci"])("rejects stale %s evidence", async (type) => {
    const fixture = await createFixture();
    await mutateEvidence(fixture, type, (record) => { record.generatedAtUtc = "2026-08-20T00:00:00.000Z"; });
    const report = await verify(fixture);
    expect(report.ok).toBe(false);
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "fresh-evidence", status: "fail" }));
  });

  it("rejects stale commit evidence", async () => {
    const fixture = await createFixture();
    await mutateEvidence(fixture, "oci-linux-smoke", (record) => { record.sourceCommit = "c".repeat(40); });
    const report = await verify(fixture);
    expect(report.ok).toBe(false);
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "fresh-evidence", status: "fail" }));
  });

  it("requires SBOM and both CI jobs to bind the exact relevant artifact hashes", async () => {
    for (const [type, mutation] of [
      ["sbom", { artifactSha256s: { "linux-x64": "0".repeat(64) } }],
      ["windows-ci", { artifactSha256s: { "win32-x64": "0".repeat(64) } }],
    ] as const) {
      const fixture = await createFixture();
      await mutateEvidence(fixture, type, (record) => Object.assign(record, mutation));
      const report = await verify(fixture);
      expect(report.ok).toBe(false);
      expect(report.checks).toContainEqual(expect.objectContaining({ id: "fresh-evidence", status: "fail" }));
    }
  });

  it("loads hash-locked scanner output and rejects findings at or above the declared threshold", async () => {
    const missingRaw = await createFixture();
    await mutateEvidence(missingRaw, "dependency-scan", (record) => {
      record.scannerOutputPath = "scan-output/missing.json";
      record.scannerOutputSha256 = "0".repeat(64);
    });
    expect((await verify(missingRaw)).ok).toBe(false);

    const findings = await createFixture();
    await mutateEvidence(findings, "oci-vulnerability-scan", (record) => { record.findingsAtOrAboveThreshold = 1; });
    expect((await verify(findings)).ok).toBe(false);
  });

  it("rejects native special entries before extraction", async () => {
    const root = await mkdtemp(join(tmpdir(), "TEST-ONLY-native-special-"));
    temporaryDirectories.push(root);
    await nativeArchive(root, "linux-x64");
    await execute("mkfifo", [join(root, "stage-linux-x64/fac-isr-sms/TEST-ONLY.fifo")]);
    const artifact = join(root, "artifacts/TEST-ONLY-fac-isr-sms-0.2.0-rc.1-linux-x64.tar.gz");
    await execute("tar", ["-czf", artifact, "fac-isr-sms"], { cwd: join(root, "stage-linux-x64") });
    await expect(inspectCandidateArtifact(artifact, "linux-x64", { testOnlyFixture: true })).rejects.toThrow(/special archive entry/u);
  });

  it.each([
    ["root container user", { configUser: "0:0" }],
    ["missing layer blob", { missingLayer: true }],
    ["unexpected blob", { extraBlob: true }],
    ["symbolic blob", { symlinkBlob: true }],
  ] as const)("rejects an OCI layout with %s", async (_label, options) => {
    const fixture = await createFixture();
    await replaceOciArtifact(fixture, options);
    const report = await verify(fixture);
    expect(report.ok).toBe(false);
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "artifact-inventories", status: "fail" }));
  });

  it("removes private staging and exposes no destination after a publication copy failure", async () => {
    const fixture = await createFixture();
    const destination = join(fixture.root, "atomic-published");
    const atomicPublish = (releaseVerifier as unknown as { publishCandidateAtomic: (...args: unknown[]) => Promise<void> }).publishCandidateAtomic;
    expect(typeof atomicPublish).toBe("function");
    await expect(async () => atomicPublish(fixture.root, {
      artifacts: [{ path: "artifacts/does-not-exist", inventoryPath: "inventories/linux-x64.json" }],
      evidence: [],
    }, fixture.manifestPath, fixture.signaturePath, destination)).rejects.toThrow();
    await expect(stat(destination)).rejects.toMatchObject({ code: "ENOENT" });
    expect((await readdir(fixture.root)).some((name) => name.startsWith(".atomic-published.staging-"))).toBe(false);
  });

  it("rejects technicalReady=false and every operationalReady=true claim", async () => {
    const notTechnical = await createFixture();
    await resign(notTechnical, (manifest) => { manifest.technicalReady = false; });
    expect((await verify(notTechnical)).checks).toContainEqual(expect.objectContaining({ id: "readiness-separation", status: "fail" }));
    const operationalOverclaim = await createFixture();
    await resign(operationalOverclaim, (manifest) => { manifest.operationalReady = true; });
    const report = await verify(operationalOverclaim);
    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "readiness-separation", status: "fail" }));
  });
});
