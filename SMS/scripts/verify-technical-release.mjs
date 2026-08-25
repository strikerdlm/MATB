#!/usr/bin/env node

import { createHash, createPublicKey, verify as verifySignature } from "node:crypto";
import { createReadStream } from "node:fs";
import { chmod, cp, lstat, mkdir, mkdtemp, readFile, readdir, realpath, rename, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { spawn } from "node:child_process";
import { pathToFileURL } from "node:url";
import { verifyPlatformInventory } from "./verify-platform-inventory.mjs";

const SHA256 = /^[a-f0-9]{64}$/u;
const SOURCE_COMMIT = /^[a-f0-9]{40}$/u;
const RELEASE = "0.2.0-rc.1";
const TARGETS = Object.freeze([
  { target: "linux-x64", kind: "native", suffix: "linux-x64.tar.gz" },
  { target: "win32-x64", kind: "native", suffix: "win32-x64.zip" },
  { target: "linux-amd64-oci", kind: "oci", suffix: "linux-amd64.oci.tar" },
]);
const REQUIRED_EVIDENCE = Object.freeze([
  "sbom",
  "dependency-scan",
  "oci-vulnerability-scan",
  "malware-scan",
  "native-linux-smoke",
  "native-windows-smoke",
  "oci-linux-smoke",
  "ubuntu-ci",
  "windows-ci",
]);

async function sha256File(path) {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(path)) digest.update(chunk);
  return digest.digest("hex");
}

function run(command, args, options = {}) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: { ...process.env, TZ: "UTC" },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    const stdout = [];
    const stderr = [];
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.once("error", reject);
    child.once("close", (code, signal) => {
      const result = {
        code: code ?? 1,
        signal,
        stdout: Buffer.concat(stdout).toString("utf8"),
        stderr: Buffer.concat(stderr).toString("utf8"),
      };
      if (result.code === 0) resolvePromise(result);
      else reject(new Error(`${command} failed (${signal ?? result.code}): ${result.stderr.trim()}`));
    });
  });
}

function exactUtc(value) {
  if (typeof value !== "string") return false;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) && new Date(parsed).toISOString() === value;
}

function contained(root, value, field) {
  if (typeof value !== "string" || value === "" || value.includes("\0")) throw new Error(`${field} is required`);
  const target = resolve(root, value);
  const fromRoot = relative(root, target);
  if (fromRoot === "" || fromRoot === ".." || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot)) {
    throw new Error(`${field} escapes the candidate directory`);
  }
  return target;
}

async function regularFile(path, field) {
  const info = await lstat(path);
  if (!info.isFile() || info.isSymbolicLink()) throw new Error(`${field} must be a regular non-symlink file`);
  return info;
}

function safeArchiveListing(output, expectedRoot) {
  const seen = new Set();
  for (const raw of output.split(/\r?\n/u).filter(Boolean)) {
    const path = raw.replaceAll("\\", "/").replace(/\/$/u, "");
    if (path.startsWith("/") || /^[A-Za-z]:\//u.test(path) || path.split("/").includes("..")) {
      throw new Error(`unsafe archive path: ${raw}`);
    }
    if (expectedRoot !== undefined && path !== expectedRoot && !path.startsWith(`${expectedRoot}/`)) throw new Error(`unexpected archive root: ${raw}`);
    if (seen.has(path)) throw new Error(`duplicate archive path: ${raw}`);
    seen.add(path);
  }
  return seen;
}

function rejectSpecialTarEntries(output) {
  for (const line of output.split(/\r?\n/u).filter(Boolean)) {
    const type = line[0];
    if (type !== "-" && type !== "d") throw new Error(`special archive entry is forbidden: ${line}`);
  }
}

function rejectSpecialZipEntries(output, expectedCount) {
  const entries = output.split(/\r?\n/u).filter((line) => /^[bcdlps-][rwx-]{9}\s/u.test(line));
  if (entries.length !== expectedCount) throw new Error("ZIP metadata does not cover every archive entry");
  for (const line of entries) if (line[0] !== "-" && line[0] !== "d") throw new Error(`special archive entry is forbidden: ${line}`);
}

function expectedIdentity(testOnlyFixture) {
  const prefix = testOnlyFixture ? "TEST-ONLY-" : "";
  return {
    releaseId: `${prefix}fac-isr-sms@${RELEASE}`,
    artifactName: (suffix) => `${prefix}fac-isr-sms-${RELEASE}-${suffix}`,
  };
}

async function verifyNativeArtifact(path, record, target, testOnlyFixture) {
  const stage = await mkdtemp(join(tmpdir(), "sms-release-native-"));
  try {
    if (target === "linux-x64") {
      const listing = await run("tar", ["-tzf", path]);
      safeArchiveListing(listing.stdout, "fac-isr-sms");
      rejectSpecialTarEntries((await run("tar", ["-tvzf", path])).stdout);
      await run("tar", ["-xzf", path, "-C", stage, "--no-same-owner"]);
    } else {
      const listing = await run("unzip", ["-Z1", path]);
      const paths = safeArchiveListing(listing.stdout, "fac-isr-sms");
      rejectSpecialZipEntries((await run("zipinfo", ["-l", path])).stdout, paths.size);
      await run("unzip", ["-q", path, "-d", stage]);
    }
    const roots = await readdir(stage, { withFileTypes: true });
    if (roots.length !== 1 || roots[0].name !== "fac-isr-sms" || !roots[0].isDirectory() || roots[0].isSymbolicLink()) {
      throw new Error("native artifact must contain exactly the fac-isr-sms directory");
    }
    const bundle = join(stage, "fac-isr-sms");
    const inventory = await verifyPlatformInventory(bundle);
    if (!inventory.valid) throw new Error(`native inventory mismatch: ${JSON.stringify(inventory)}`);
    const release = JSON.parse(await readFile(join(bundle, "release.json"), "utf8"));
    const identity = expectedIdentity(testOnlyFixture);
    const expectedProduction = !testOnlyFixture;
    const expectedProvenance = testOnlyFixture ? "controlled-test-fixture" : "official-node-signed-checksums";
    if (release.release !== identity.releaseId || release.target !== target || release.nodeVersion !== "22.23.2"
      || release.internet !== "disabled" || release.production !== expectedProduction
      || release.runtimeProvenance !== expectedProvenance || release.operationalReady !== false) {
      throw new Error(`native ${target} release metadata does not match the candidate`);
    }
    const inventorySha256 = await sha256File(join(bundle, "inventory.tsv"));
    if (record?.contentInventorySha256 !== undefined && record.contentInventorySha256 !== inventorySha256) throw new Error(`native ${target} inventory digest differs from release evidence`);
    return inventorySha256;
  } finally {
    await rm(stage, { recursive: true, force: true });
  }
}

function validDescriptor(descriptor, mediaTypes) {
  return descriptor !== null && typeof descriptor === "object" && mediaTypes.includes(descriptor.mediaType)
    && /^sha256:[a-f0-9]{64}$/u.test(descriptor.digest) && Number.isSafeInteger(descriptor.size) && descriptor.size > 0;
}

async function verifyDescriptorBlob(stage, descriptor, label) {
  const blobPath = join(stage, "blobs/sha256", descriptor.digest.slice("sha256:".length));
  const info = await regularFile(blobPath, label);
  if (info.size !== descriptor.size || await sha256File(blobPath) !== descriptor.digest.slice("sha256:".length)) {
    throw new Error(`${label} descriptor does not match its blob`);
  }
  return blobPath;
}

async function verifyOciArtifact(path, record, testOnlyFixture, expectedSourceCommit) {
  const stage = await mkdtemp(join(tmpdir(), "sms-release-oci-"));
  try {
    const listing = await run("tar", ["-tf", path]);
    safeArchiveListing(listing.stdout);
    const originalPaths = new Set(listing.stdout.split(/\r?\n/u).filter(Boolean).map((item) => item.replace(/\/$/u, "")));
    if (!originalPaths.has("index.json") || !originalPaths.has("oci-layout")) throw new Error("OCI archive is missing index.json or oci-layout");
    for (const item of originalPaths) {
      if (item !== "index.json" && item !== "oci-layout" && item !== "blobs" && item !== "blobs/sha256" && !/^blobs\/sha256\/[a-f0-9]{64}$/u.test(item)) {
        throw new Error(`unexpected OCI archive path: ${item}`);
      }
    }
    rejectSpecialTarEntries((await run("tar", ["-tvf", path])).stdout);
    await run("tar", ["-xf", path, "-C", stage, "--no-same-owner"]);
    const layout = JSON.parse(await readFile(join(stage, "oci-layout"), "utf8"));
    const indexPath = join(stage, "index.json");
    const index = JSON.parse(await readFile(indexPath, "utf8"));
    if (layout.imageLayoutVersion !== "1.0.0" || index.schemaVersion !== 2 || index.mediaType !== "application/vnd.oci.image.index.v1+json"
      || !Array.isArray(index.manifests) || index.manifests.length !== 1) {
      throw new Error("OCI layout/index contract is invalid");
    }
    const descriptor = index.manifests[0];
    const expectedReference = `${testOnlyFixture ? "TEST-ONLY-" : ""}fac-isr-sms:${RELEASE}`;
    if (descriptor.platform?.os !== "linux" || descriptor.platform?.architecture !== "amd64"
      || descriptor.annotations?.["org.opencontainers.image.ref.name"] !== expectedReference
      || !validDescriptor(descriptor, ["application/vnd.oci.image.manifest.v1+json"])) throw new Error("OCI platform or release reference is invalid");
    const manifestPath = await verifyDescriptorBlob(stage, descriptor, "OCI manifest blob");
    const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
    if (manifest.schemaVersion !== 2 || manifest.mediaType !== "application/vnd.oci.image.manifest.v1+json"
      || !validDescriptor(manifest.config, ["application/vnd.oci.image.config.v1+json"]) || !Array.isArray(manifest.layers)) {
      throw new Error("OCI manifest contract is invalid");
    }
    const descriptors = [manifest.config, ...manifest.layers];
    const layerTypes = ["application/vnd.oci.image.layer.v1.tar", "application/vnd.oci.image.layer.v1.tar+gzip", "application/vnd.oci.image.layer.v1.tar+zstd"];
    if (manifest.layers.some((layer) => !validDescriptor(layer, layerTypes))) throw new Error("OCI layer descriptor is invalid");
    const digests = new Set([descriptor.digest]);
    for (const [indexNumber, item] of descriptors.entries()) {
      if (digests.has(item.digest)) throw new Error("OCI descriptors contain a duplicate digest");
      digests.add(item.digest);
      await verifyDescriptorBlob(stage, item, indexNumber === 0 ? "OCI config blob" : `OCI layer ${indexNumber}`);
    }
    const actualBlobs = (await readdir(join(stage, "blobs/sha256"), { withFileTypes: true })).map((entry) => {
      if (!entry.isFile() || entry.isSymbolicLink() || !/^[a-f0-9]{64}$/u.test(entry.name)) throw new Error(`unsupported OCI blob entry: ${entry.name}`);
      return `sha256:${entry.name}`;
    }).sort();
    if (JSON.stringify(actualBlobs) !== JSON.stringify([...digests].sort())) throw new Error("OCI layout has missing or unexpected blobs");
    const config = JSON.parse(await readFile(join(stage, "blobs/sha256", manifest.config.digest.slice(7)), "utf8"));
    const labels = config.config?.Labels;
    const expectedProvenance = testOnlyFixture ? "controlled-test-fixture" : "official-node-pinned-image";
    if (config.os !== "linux" || config.architecture !== "amd64" || config.config?.User !== "10001:10001"
      || labels?.["org.opencontainers.image.version"] !== RELEASE || labels?.["org.fac-isr.sms.runtime-provenance"] !== expectedProvenance
      || (expectedSourceCommit !== undefined && labels?.["org.opencontainers.image.revision"] !== expectedSourceCommit)) {
      throw new Error("OCI config platform, non-root user, release, source, or provenance is invalid");
    }
    const inventorySha256 = await sha256File(indexPath);
    if (record?.contentInventorySha256 !== undefined && record.contentInventorySha256 !== inventorySha256) throw new Error("OCI inventory digest differs from release evidence");
    return inventorySha256;
  } finally {
    await rm(stage, { recursive: true, force: true });
  }
}

export async function inspectCandidateArtifact(artifactPathInput, target, options = {}) {
  const expected = TARGETS.find((candidate) => candidate.target === target);
  if (expected === undefined) throw new Error(`unsupported candidate target: ${String(target)}`);
  const artifactPath = resolve(artifactPathInput);
  await regularFile(artifactPath, "candidate artifact");
  const identity = expectedIdentity(options.testOnlyFixture === true);
  const artifactName = identity.artifactName(expected.suffix);
  if (basename(artifactPath) !== artifactName) throw new Error(`candidate artifact must be named ${artifactName}`);
  const contentInventorySha256 = expected.kind === "native"
    ? await verifyNativeArtifact(artifactPath, undefined, target, options.testOnlyFixture === true)
    : await verifyOciArtifact(artifactPath, undefined, options.testOnlyFixture === true, options.expectedSourceCommit);
  const info = await stat(artifactPath);
  return {
    target,
    kind: expected.kind,
    artifactName,
    artifactSha256: await sha256File(artifactPath),
    artifactSizeBytes: info.size,
    contentInventorySha256,
  };
}

async function assertArtifacts(root, manifest, expectedSourceCommit, testOnlyFixture) {
  if (!Array.isArray(manifest.artifacts) || manifest.artifacts.length !== TARGETS.length) throw new Error("exactly three platform artifacts are required");
  const identity = expectedIdentity(testOnlyFixture);
  const seen = new Set();
  for (let index = 0; index < TARGETS.length; index += 1) {
    const expected = TARGETS[index];
    const record = manifest.artifacts[index];
    const name = identity.artifactName(expected.suffix);
    if (record?.target !== expected.target || record?.kind !== expected.kind || basename(record?.path ?? "") !== name || seen.has(record?.target)) {
      throw new Error(`artifact ${index + 1} is not the exact ${expected.target} candidate`);
    }
    seen.add(record.target);
    if (!SHA256.test(record.sha256) || !Number.isSafeInteger(record.sizeBytes) || record.sizeBytes < 1 || !SHA256.test(record.inventorySha256)) {
      throw new Error(`artifact ${name} has invalid hash/size inventory metadata`);
    }
    const artifactPath = contained(root, record.path, "artifact path");
    const artifactInfo = await regularFile(artifactPath, "artifact");
    if (artifactInfo.size !== record.sizeBytes || await sha256File(artifactPath) !== record.sha256) throw new Error(`artifact bytes differ: ${name}`);
    const inventoryPath = contained(root, record.inventoryPath, "platform inventory path");
    await regularFile(inventoryPath, "platform inventory");
    if (await sha256File(inventoryPath) !== record.inventorySha256) throw new Error(`platform inventory bytes differ: ${expected.target}`);
    const inventory = JSON.parse(await readFile(inventoryPath, "utf8"));
    if (inventory.schemaVersion !== "1.0" || inventory.sourceCommit !== expectedSourceCommit || inventory.target !== expected.target
      || inventory.artifactName !== name || inventory.artifactSha256 !== record.sha256 || inventory.artifactSizeBytes !== record.sizeBytes
      || inventory.contentInventorySha256 === undefined || !SHA256.test(inventory.contentInventorySha256)) {
      throw new Error(`platform inventory provenance differs: ${expected.target}`);
    }
    const inspected = await inspectCandidateArtifact(artifactPath, expected.target, { testOnlyFixture, expectedSourceCommit });
    if (inspected.contentInventorySha256 !== inventory.contentInventorySha256) throw new Error(`content inventory differs: ${expected.target}`);
  }
}

async function assertFreshEvidence(root, manifest, expectedSourceCommit, now, maxEvidenceAgeMs) {
  if (!Array.isArray(manifest.evidence) || manifest.evidence.length !== REQUIRED_EVIDENCE.length) throw new Error("the exact release evidence set is required");
  const byType = new Map();
  for (const item of manifest.evidence) {
    if (typeof item?.type !== "string" || byType.has(item.type) || !REQUIRED_EVIDENCE.includes(item.type) || !SHA256.test(item.sha256)) {
      throw new Error("release evidence types must be exact, unique, and hash locked");
    }
    const path = contained(root, item.path, "release evidence path");
    await regularFile(path, "release evidence");
    if (await sha256File(path) !== item.sha256) throw new Error(`release evidence bytes differ: ${item.type}`);
    const record = JSON.parse(await readFile(path, "utf8"));
    const generatedAt = Date.parse(record.generatedAtUtc);
    const age = now.getTime() - generatedAt;
    if (record.schemaVersion !== "1.0" || record.type !== item.type || record.sourceCommit !== expectedSourceCommit
      || record.status !== "pass" || !exactUtc(record.generatedAtUtc) || age < 0 || age > maxEvidenceAgeMs) {
      throw new Error(`release evidence is stale, failing, or for another commit: ${item.type}`);
    }
    byType.set(item.type, record);
  }
  const artifactHashes = Object.fromEntries(manifest.artifacts.map((artifact) => [artifact.target, artifact.sha256]));
  const exactArtifactHashes = (record, targets, label) => {
    const expected = Object.fromEntries(targets.map((target) => [target, artifactHashes[target]]));
    if (record?.artifactSha256s === null || typeof record?.artifactSha256s !== "object"
      || JSON.stringify(Object.keys(record.artifactSha256s).sort()) !== JSON.stringify(Object.keys(expected).sort())
      || Object.entries(expected).some(([target, digest]) => record.artifactSha256s[target] !== digest)) {
      throw new Error(`${label} does not bind the exact required artifact hashes`);
    }
  };
  const sbom = byType.get("sbom");
  if (sbom.bomFormat !== "CycloneDX" || !Array.isArray(sbom.components) || sbom.components.length === 0) throw new Error("fresh CycloneDX SBOM is incomplete");
  exactArtifactHashes(sbom, TARGETS.map(({ target }) => target), "SBOM");
  const evidenceItems = new Map(manifest.evidence.map((item) => [item.type, item]));
  for (const [type, targets, threshold] of [
    ["dependency-scan", TARGETS.map(({ target }) => target), "low"],
    ["oci-vulnerability-scan", ["linux-amd64-oci"], "high"],
    ["malware-scan", TARGETS.map(({ target }) => target), "zero-malware"],
  ]) {
    const record = byType.get(type);
    const item = evidenceItems.get(type);
    if (typeof record.scanner !== "string" || record.scanner.trim() === "" || record.threshold !== threshold
      || record.findingsAtOrAboveThreshold !== 0 || !SHA256.test(record.scannerOutputSha256 ?? "")
      || item?.scannerOutputPath !== record.scannerOutputPath || item?.scannerOutputSha256 !== record.scannerOutputSha256) {
      throw new Error(`${type} scanner result metadata is absent, failing, or not signed`);
    }
    exactArtifactHashes(record, targets, type);
    const rawPath = contained(root, record.scannerOutputPath, `${type} scanner output path`);
    await regularFile(rawPath, `${type} scanner output`);
    if (await sha256File(rawPath) !== record.scannerOutputSha256) throw new Error(`${type} scanner output bytes differ`);
    const raw = JSON.parse(await readFile(rawPath, "utf8"));
    if (type === "dependency-scan") {
      if (!Number.isSafeInteger(raw.auditReportVersion) || raw.metadata?.vulnerabilities?.total !== 0) throw new Error("dependency scan raw output reports vulnerabilities or is invalid");
    } else if (type === "oci-vulnerability-scan") {
      if (!Array.isArray(raw.matches)) throw new Error("OCI vulnerability scan raw output is invalid");
      const blocked = raw.matches.filter((match) => ["high", "critical"].includes(String(match?.vulnerability?.severity ?? "").toLowerCase()));
      if (blocked.length !== 0) throw new Error("OCI vulnerability scan raw output reaches the high threshold");
    } else {
      exactArtifactHashes(raw, targets, "malware scan raw output");
      if (raw.malwareFound !== 0 || raw.errors !== 0) throw new Error("malware scan raw output is invalid or reports findings");
    }
  }
  for (const [type, target, platform] of [
    ["native-linux-smoke", "linux-x64", "ubuntu-24.04"],
    ["native-windows-smoke", "win32-x64", "windows-2022"],
    ["oci-linux-smoke", "linux-amd64-oci", "ubuntu-24.04"],
  ]) {
    const record = byType.get(type);
    if (record.clean !== true || record.platform !== platform || record.artifactSha256 !== artifactHashes[target]) throw new Error(`${type} does not attest the exact clean candidate`);
  }
  if (byType.get("ubuntu-ci").clean !== true || byType.get("ubuntu-ci").platform !== "ubuntu-24.04"
    || byType.get("windows-ci").clean !== true || byType.get("windows-ci").platform !== "windows-2022") {
    throw new Error("clean Ubuntu 24.04 and Windows Server 2022 CI evidence is required");
  }
  exactArtifactHashes(byType.get("ubuntu-ci"), ["linux-x64", "linux-amd64-oci"], "Ubuntu CI");
  exactArtifactHashes(byType.get("windows-ci"), ["win32-x64"], "Windows CI");
}

export async function publishCandidateAtomic(root, manifest, manifestPath, signaturePath, destination) {
  try {
    await lstat(destination);
    throw new Error("publish directory must not already exist");
  } catch (error) {
    if (!(error instanceof Error) || error.code !== "ENOENT") throw error;
  }
  const parent = dirname(destination);
  await mkdir(parent, { recursive: true, mode: 0o755 });
  const staging = await mkdtemp(join(parent, `.${basename(destination)}.staging-`));
  await chmod(staging, 0o700);
  let published = false;
  const paths = [
    ...manifest.artifacts.flatMap((record) => [record.path, record.inventoryPath]),
    ...manifest.evidence.flatMap((record) => [record.path, ...(record.scannerOutputPath ? [record.scannerOutputPath] : [])]),
  ];
  try {
    for (const path of [...new Set(paths)]) {
      const source = contained(root, path, "publish input");
      const target = resolve(staging, path);
      await mkdir(dirname(target), { recursive: true });
      await cp(source, target, { errorOnExist: true, force: false });
    }
    await cp(manifestPath, resolve(staging, basename(manifestPath)), { errorOnExist: true, force: false });
    await cp(signaturePath, resolve(staging, basename(signaturePath)), { errorOnExist: true, force: false });
    await rename(staging, destination);
    published = true;
  } finally {
    if (!published) await rm(staging, { recursive: true, force: true });
  }
}

export async function verifyTechnicalRelease(candidateRoot, options = {}) {
  const root = resolve(candidateRoot);
  const checks = [];
  const add = (id, status, detail) => checks.push({ id, status, detail });
  const expectedSourceCommit = options.expectedSourceCommit;
  const testOnlyFixture = options.testOnlyFixture === true;
  const now = options.now instanceof Date ? options.now : new Date();
  const maxEvidenceAgeMs = options.maxEvidenceAgeMs ?? 24 * 60 * 60 * 1000;
  const manifestPath = resolve(options.manifestPath ?? join(root, testOnlyFixture ? "TEST-ONLY-release-evidence.json" : "release-evidence.json"));
  const signaturePath = resolve(options.signaturePath ?? join(root, testOnlyFixture ? "TEST-ONLY-release-evidence.sig" : "release-evidence.sig"));
  let manifest;
  let manifestBytes;

  try {
    if (!SOURCE_COMMIT.test(expectedSourceCommit ?? "")) throw new Error("an exact 40-character --source-commit is required");
    manifestBytes = await readFile(await regularFile(manifestPath, "release evidence manifest").then(() => manifestPath));
    manifest = JSON.parse(manifestBytes.toString("utf8"));
    add("manifest", "pass", "release evidence manifest is readable");
  } catch (error) {
    add("manifest", "fail", error instanceof Error ? error.message : String(error));
  }

  if (manifest !== undefined) {
    try {
      const identity = expectedIdentity(testOnlyFixture);
      if (manifest.schemaVersion !== "1.0" || manifest.releaseId !== identity.releaseId || manifest.version !== RELEASE
        || manifest.sourceCommit !== expectedSourceCommit || !exactUtc(manifest.generatedAtUtc)) throw new Error("release identity or exact source commit is invalid");
      if (testOnlyFixture && manifest.fixtureClassification !== "TEST-ONLY-NON-PRODUCTION") throw new Error("controlled fixture is not visibly TEST-ONLY");
      if (!testOnlyFixture && (manifest.releaseId.includes("TEST") || manifest.releaseId.includes("development") || "fixtureClassification" in manifest)) {
        throw new Error("development/test evidence is forbidden on the production release path");
      }
      add("release-identity", "pass", `exact release identity and source commit ${expectedSourceCommit.slice(0, 12)} verified`);
    } catch (error) {
      add("release-identity", "fail", error instanceof Error ? error.message : String(error));
    }

    try {
      if (manifest.technicalReady !== true || manifest.operationalReady !== false) {
        throw new Error("technicalReady must be true and operationalReady must remain false for this RC");
      }
      add("readiness-separation", "pass", "technicalReady=true; operationalReady=false");
    } catch (error) {
      add("readiness-separation", "fail", error instanceof Error ? error.message : String(error));
    }

    try {
      const publicKeyPath = resolve(options.publicKeyPath ?? process.env.SMS_RELEASE_PUBLIC_KEY_PATH ?? "");
      if (!options.publicKeyPath && !process.env.SMS_RELEASE_PUBLIC_KEY_PATH) throw new Error("externally supplied release public key is required");
      await regularFile(publicKeyPath, "release public key");
      if (!testOnlyFixture) {
        const fromRoot = relative(root, await realpath(publicKeyPath));
        if (fromRoot === "" || (!fromRoot.startsWith(`..${sep}`) && fromRoot !== ".." && !isAbsolute(fromRoot))) {
          throw new Error("release public key must be supplied from outside the candidate directory");
        }
      }
      const key = createPublicKey(await readFile(publicKeyPath));
      if (key.asymmetricKeyType !== "ed25519") throw new Error("release public key must be Ed25519");
      const signatureText = (await readFile(await regularFile(signaturePath, "detached release signature").then(() => signaturePath), "utf8")).trim();
      if (!/^[A-Za-z0-9+/]+={0,2}$/u.test(signatureText)
        || !verifySignature(null, manifestBytes, key, Buffer.from(signatureText, "base64"))) throw new Error("detached release signature is invalid");
      add("signature", "pass", "detached release signature verified using externally supplied public material");
    } catch (error) {
      add("signature", "fail", error instanceof Error ? error.message : String(error));
    }

    try {
      if (!Array.isArray(manifest.artifacts) || manifest.artifacts.length !== TARGETS.length
        || manifest.artifacts.some((record, index) => record?.target !== TARGETS[index].target || record?.kind !== TARGETS[index].kind)) {
        throw new Error("artifact target order/set differs from linux-x64, win32-x64, linux-amd64-oci");
      }
      add("artifact-set", "pass", "exact three platform artifact targets are declared");
    } catch (error) {
      add("artifact-set", "fail", error instanceof Error ? error.message : String(error));
    }

    try {
      await assertArtifacts(root, manifest, expectedSourceCommit, testOnlyFixture);
      add("artifact-inventories", "pass", "exact native and OCI artifact bytes, manifests, and inventories verified");
    } catch (error) {
      add("artifact-inventories", "fail", error instanceof Error ? error.message : String(error));
    }

    try {
      if (!Number.isSafeInteger(maxEvidenceAgeMs) || maxEvidenceAgeMs < 1) throw new Error("maximum evidence age must be a positive integer");
      await assertFreshEvidence(root, manifest, expectedSourceCommit, now, maxEvidenceAgeMs);
      add("fresh-evidence", "pass", "SBOM, scans, clean native/OCI smoke, and both CI attest the exact fresh commit/artifacts");
    } catch (error) {
      add("fresh-evidence", "fail", error instanceof Error ? error.message : String(error));
    }
  }

  const ok = checks.length > 0 && !checks.some((check) => check.status === "fail");
  if (ok && options.publishDirectory) await publishCandidateAtomic(root, manifest, manifestPath, signaturePath, resolve(options.publishDirectory));
  return {
    schemaVersion: "1.0",
    ok,
    technicalReady: ok && manifest?.technicalReady === true,
    operationalReady: false,
    releaseId: typeof manifest?.releaseId === "string" ? manifest.releaseId : "unknown",
    sourceCommit: typeof manifest?.sourceCommit === "string" ? manifest.sourceCommit : "unknown",
    checks,
  };
}

function parse(argv) {
  const options = { json: false, testOnlyFixture: false };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--json") options.json = true;
    else if (argument === "--test-only-fixture") options.testOnlyFixture = true;
    else if (["--candidate", "--source-commit", "--public-key", "--manifest", "--signature", "--publish-dir", "--max-age-hours"].includes(argument)) {
      const value = argv[++index];
      if (!value || value.startsWith("--")) throw new Error(`${argument} requires a value`);
      options[argument.slice(2).replaceAll(/-([a-z])/gu, (_, letter) => letter.toUpperCase())] = value;
    } else throw new Error(`unknown argument: ${argument}`);
  }
  if (!options.candidate || !options.sourceCommit || !options.publicKey) throw new Error("--candidate, --source-commit, and --public-key are required");
  const hours = Number(options.maxAgeHours ?? "24");
  if (!Number.isFinite(hours) || hours <= 0 || hours > 168) throw new Error("--max-age-hours must be in (0, 168]");
  return { ...options, maxEvidenceAgeMs: Math.floor(hours * 60 * 60 * 1000) };
}

async function main() {
  const options = parse(process.argv.slice(2));
  const report = await verifyTechnicalRelease(options.candidate, {
    expectedSourceCommit: options.sourceCommit,
    publicKeyPath: options.publicKey,
    manifestPath: options.manifest,
    signaturePath: options.signature,
    publishDirectory: options.publishDir,
    testOnlyFixture: options.testOnlyFixture,
    maxEvidenceAgeMs: options.maxEvidenceAgeMs,
  });
  if (options.json) process.stdout.write(`${JSON.stringify(report)}\n`);
  else {
    process.stdout.write(`${report.ok ? "PASS" : "FAIL"} technical release: ${report.releaseId}\n`);
    process.stdout.write(`technicalReady=${String(report.technicalReady)} operationalReady=false\n`);
    for (const check of report.checks) process.stdout.write(`${check.status.toUpperCase()} ${check.id}: ${check.detail}\n`);
  }
  if (!report.ok) process.exitCode = 1;
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
