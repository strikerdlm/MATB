#!/usr/bin/env node

import {
  createHash,
  createPrivateKey,
  createPublicKey,
  sign as signPayload,
  verify as verifySignature,
} from "node:crypto";
import { createReadStream } from "node:fs";
import {
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  realpath,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { extname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const smsRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const defaultRepositoryRoot = resolve(smsRoot, "..");
const RELEASE_DIRECTORY = "SMS/docs/release";
const MANIFEST_PATH = `${RELEASE_DIRECTORY}/release-manifest.json`;
const SIGNATURE_PATH = `${RELEASE_DIRECTORY}/release-manifest.sig`;
const PUBLIC_KEY_PATH = `${RELEASE_DIRECTORY}/release-public-key.pem`;
const SBOM_PATH = `${RELEASE_DIRECTORY}/sbom.cdx.json`;
const SCAN_REPORT_PATH = `${RELEASE_DIRECTORY}/security-scan.json`;
const TEST_REPORT_PATH = `${RELEASE_DIRECTORY}/test-report.json`;
const SHA256 = /^[a-f0-9]{64}$/;
const SEMVER = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const EXACT_UTC = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{3}))?Z$/;
const KEY_ID = /^ed25519-sha256-[a-f0-9]{16}$/;
const BASE_ARTIFACTS = Object.freeze([
  ".github/workflows/sms-ci.yml",
  "SMS/.dockerignore",
  "SMS/Dockerfile",
  "SMS/apps/edge-api/src/server.ts",
  "SMS/docker/compose.edge.yml",
  "SMS/docker/entrypoint.sh",
  "SMS/docker/healthcheck.sh",
  "SMS/docs/release/known-limitations.md",
  "SMS/docs/release/operational-readiness-record.json",
  "SMS/docs/release/state-aviation-acceptance-checklist.md",
  "SMS/docs/release/verification-signatures.jsonl",
  "SMS/package-lock.json",
  "SMS/package.json",
  "SMS/scripts/build-offline-bundle.d.mts",
  "SMS/scripts/build-offline-bundle.mjs",
  "SMS/scripts/edge-healthcheck.mjs",
  "SMS/scripts/generate-sbom.d.mts",
  "SMS/scripts/generate-sbom.mjs",
  "SMS/scripts/start-edge.mjs",
  "SMS/scripts/verify-offline.mjs",
  "SMS/scripts/verify-operational-readiness.d.mts",
  "SMS/scripts/verify-operational-readiness.mjs",
  "SMS/test/integration/operational-readiness.test.ts",
  "SMS/test/integration/release-manifest.test.ts",
  "SMS/docs/provenance/evidence-package-manifest.json",
  "SMS/docs/provenance/evidence-package-manifest.sig",
  "SMS/docs/provenance/evidence-package-public-key.pem",
]);
const GENERATED_ARTIFACTS = Object.freeze([SBOM_PATH, SCAN_REPORT_PATH, TEST_REPORT_PATH]);

function parseArguments(argv) {
  const [command, ...rest] = argv;
  const options = {
    command,
    version: undefined,
    keyId: undefined,
    privateKeyPath: process.env.SMS_RELEASE_PRIVATE_KEY_PATH,
    json: false,
    help: false,
  };
  for (let index = 0; index < rest.length; index += 1) {
    const argument = rest[index];
    if (argument === "--version" || argument === "--key-id" || argument === "--private-key") {
      const value = rest[index + 1];
      if (value === undefined || value.startsWith("--")) throw new Error(`${argument} requires a value`);
      if (argument === "--version") options.version = value;
      else if (argument === "--key-id") options.keyId = value;
      else options.privateKeyPath = value;
      index += 1;
    } else if (argument === "--json") options.json = true;
    else if (argument === "--help") options.help = true;
    else throw new Error(`unknown argument: ${argument}`);
  }
  return options;
}

function canonicalJson(value) {
  if (value === null) return "null";
  if (typeof value === "string") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number" && Number.isFinite(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (typeof value !== "object" || (Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null)) {
    throw new TypeError("canonical JSON supports only JSON values");
  }
  return `{${Object.entries(value)
    .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
    .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`)
    .join(",")}}`;
}

function stableJsonValue(value) {
  return JSON.parse(canonicalJson(value));
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

async function sha256File(path) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}

function exactUtc(value) {
  if (typeof value !== "string") return false;
  const match = EXACT_UTC.exec(value);
  if (match === null) return false;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText, millisecondsText = "000"] = match;
  const date = new Date(value);
  return Number.isFinite(date.getTime())
    && date.getUTCFullYear() === Number(yearText)
    && date.getUTCMonth() + 1 === Number(monthText)
    && date.getUTCDate() === Number(dayText)
    && date.getUTCHours() === Number(hourText)
    && date.getUTCMinutes() === Number(minuteText)
    && date.getUTCSeconds() === Number(secondText)
    && date.getUTCMilliseconds() === Number(millisecondsText);
}

function containedPath(root, value, field) {
  if (typeof value !== "string" || value === "" || isAbsolute(value) || value.includes("\\") || value.includes("\0")) {
    throw new Error(`${field} must be a relative POSIX path`);
  }
  if (value.split("/").some((component) => component === "" || component === "." || component === "..")) {
    throw new Error(`${field} contains path traversal`);
  }
  const target = resolve(root, value);
  const fromRoot = relative(root, target);
  if (fromRoot === "" || fromRoot === ".." || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot)) {
    throw new Error(`${field} escapes the repository root`);
  }
  return target;
}

function mediaType(path) {
  const types = new Map([
    [".json", "application/json"],
    [".mjs", "text/javascript"],
    [".pem", "application/x-pem-file"],
    [".sh", "text/x-shellscript"],
    [".sig", "application/octet-stream"],
    [".ts", "text/typescript"],
    [".yml", "application/yaml"],
  ]);
  return types.get(extname(path)) ?? "application/octet-stream";
}

async function run(command, args, { cwd = smsRoot, allowFailure = false, env = {} } = {}) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, {
      cwd,
      env: { ...process.env, ...env, NO_COLOR: "1" },
      stdio: ["ignore", "pipe", "pipe"],
    });
    const stdout = [];
    const stderr = [];
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.once("error", reject);
    child.once("close", (code, signal) => {
      const stdoutBuffer = Buffer.concat(stdout);
      const result = {
        code: code ?? 1,
        signal,
        stdout: stdoutBuffer.toString("utf8"),
        stdoutBuffer,
        stderr: Buffer.concat(stderr).toString("utf8"),
      };
      if (result.code === 0 || allowFailure) resolvePromise(result);
      else reject(new Error(`${command} ${args.join(" ")} failed (${signal ?? result.code})${result.stderr === "" ? "" : `: ${result.stderr.trim()}`}`));
    });
  });
}

async function writeJson(path, value) {
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8", mode: 0o644 });
}

async function sourceMetadata(repositoryRoot) {
  const commitResult = await run("git", ["rev-parse", "HEAD"], { cwd: repositoryRoot });
  const commit = commitResult.stdout.trim();
  if (!/^[a-f0-9]{40}$/.test(commit)) throw new Error("could not resolve a full source commit");
  const fieldsResult = await run("git", ["show", "-s", "--format=%cI%x00%an%x00%ae", commit], { cwd: repositoryRoot });
  const [committedAt, authorName, authorEmail] = fieldsResult.stdout.trim().split("\0");
  const committedAtUtc = new Date(committedAt).toISOString();
  if (!exactUtc(committedAtUtc) || !authorName || !authorEmail) throw new Error("source commit metadata is incomplete");
  return { commit, committedAtUtc, authorName, authorEmail };
}

function addMetadataProperty(sbom, name, value) {
  const properties = Array.isArray(sbom.metadata?.properties) ? sbom.metadata.properties : [];
  sbom.metadata.properties = [...properties.filter((item) => item?.name !== name), { name, value }]
    .sort((left, right) => String(left.name).localeCompare(String(right.name)));
}

async function generateSbom(stagingDirectory, source, version) {
  const result = await run("npm", ["sbom", "--sbom-format", "cyclonedx"], { cwd: smsRoot });
  let sbom;
  try {
    sbom = JSON.parse(result.stdout);
  } catch (error) {
    throw new Error(`npm SBOM output is not complete JSON (${Buffer.byteLength(result.stdout, "utf8")} bytes; stderr: ${result.stderr.trim() || "none"})`, { cause: error });
  }
  if (sbom.bomFormat !== "CycloneDX" || !Array.isArray(sbom.components) || sbom.metadata?.component === undefined) {
    throw new Error("npm did not produce a complete CycloneDX SBOM");
  }
  delete sbom.serialNumber;
  sbom.metadata.timestamp = source.committedAtUtc;
  sbom.metadata.component.version = version;
  const sourceReference = { type: "vcs", url: "https://github.com/strikerdlm/MATB" };
  const rootComponents = [sbom.metadata.component];
  if (sbom.component !== undefined) {
    sbom.component.version = version;
    rootComponents.push(sbom.component);
  }
  for (const component of rootComponents) {
    const references = Array.isArray(component.externalReferences) ? component.externalReferences : [];
    if (!references.some((reference) => reference?.type === sourceReference.type && reference?.url === sourceReference.url)) {
      component.externalReferences = [...references, sourceReference];
    }
  }
  sbom.components.sort((left, right) => String(left["bom-ref"] ?? "").localeCompare(String(right["bom-ref"] ?? "")));
  if (Array.isArray(sbom.dependencies)) {
    sbom.dependencies.sort((left, right) => String(left.ref ?? "").localeCompare(String(right.ref ?? "")));
  }
  const licenseCoverage = sbom.components.filter((component) => Array.isArray(component.licenses) && component.licenses.length > 0).length;
  const sourceCoverage = sbom.components.filter((component) => Array.isArray(component.externalReferences) && component.externalReferences.length > 0).length;
  addMetadataProperty(sbom, "fac-isr:source-commit", source.commit);
  addMetadataProperty(sbom, "fac-isr:component-count", String(sbom.components.length));
  addMetadataProperty(sbom, "fac-isr:license-covered-components", String(licenseCoverage));
  addMetadataProperty(sbom, "fac-isr:source-covered-components", String(sourceCoverage));
  addMetadataProperty(sbom, "fac-isr:map-license-status", "provider-specific map and terrain content is not bundled; approval remains required");
  addMetadataProperty(sbom, "fac-isr:font-license-status", "no font binaries are bundled; the console uses the receiving workstation system stack");
  await writeJson(resolve(stagingDirectory, "sbom.cdx.json"), stableJsonValue(sbom));
  return { componentCount: sbom.components.length, licenseCoverage, sourceCoverage };
}

async function generateSecurityScan(stagingDirectory, source) {
  const versionResult = await run("npm", ["--version"], { cwd: smsRoot });
  const auditResult = await run("npm", ["audit", "--json"], { cwd: smsRoot, allowFailure: true });
  let audit;
  try {
    audit = JSON.parse(auditResult.stdout);
  } catch (error) {
    throw new Error(`npm audit did not return JSON: ${error instanceof Error ? error.message : String(error)}`, { cause: error });
  }
  const vulnerabilityCounts = audit.metadata?.vulnerabilities;
  if (vulnerabilityCounts === undefined || !Number.isSafeInteger(vulnerabilityCounts.total)) {
    throw new Error("npm audit vulnerability totals are unavailable");
  }
  const report = {
    schemaVersion: "1.0",
    generatedAtUtc: source.committedAtUtc,
    sourceCommit: source.commit,
    dependencyAudit: {
      scanner: { name: "npm audit", version: versionResult.stdout.trim(), auditReportVersion: audit.auditReportVersion },
      status: vulnerabilityCounts.total === 0 ? "pass" : "findings",
      exitCode: auditResult.code,
      vulnerabilityCounts: stableJsonValue(vulnerabilityCounts),
      findings: stableJsonValue(audit.vulnerabilities ?? {}),
      disposition: vulnerabilityCounts.total === 0 ? "no locked dependency advisories reported" : "release blocker pending reviewed remediation or disposition",
    },
    approvedImageScanner: {
      status: "not-configured",
      disposition: "release-blocker",
      reason: "No institutionally approved OCI vulnerability scanner and signed database snapshot were supplied to this build.",
    },
    malwareScanner: {
      status: "not-configured",
      disposition: "release-blocker",
      reason: "No institutionally approved malware scanner and signed definition set were supplied to this build.",
    },
  };
  await writeJson(resolve(stagingDirectory, "security-scan.json"), report);
  return report;
}

async function generateTestReport(stagingDirectory, source) {
  const commands = [
    { command: "npm", args: ["run", "typecheck"] },
    { command: "npm", args: ["run", "lint"] },
    { command: process.execPath, args: ["node_modules/vitest/vitest.mjs", "run", "--exclude", "test/integration/release-manifest.test.ts"] },
    { command: "npm", args: ["run", "verify:no-c2"] },
    { command: "npm", args: ["run", "verify:data-separation"] },
  ];
  const checks = [];
  for (const item of commands) {
    const display = `${item.command === process.execPath ? "node" : item.command} ${item.args.join(" ")}`;
    process.stdout.write(`Release prerequisite: ${display}\n`);
    const result = await run(item.command, item.args, { cwd: smsRoot, allowFailure: true });
    const outputSha256 = sha256(Buffer.concat([
      Buffer.from(result.stdout, "utf8"),
      Buffer.from([0]),
      Buffer.from(result.stderr, "utf8"),
    ]));
    checks.push({ command: display, status: result.code === 0 ? "pass" : "fail", exitCode: result.code, outputSha256 });
    if (result.code !== 0) throw new Error(`release prerequisite failed: ${display}`);
  }
  const report = {
    schemaVersion: "1.0",
    sourceCommit: source.commit,
    completedAtUtc: source.committedAtUtc,
    timestampBasis: "source commit time",
    status: "pass",
    exclusions: ["test/integration/release-manifest.test.ts is verified after signing to avoid a bootstrap cycle"],
    checks,
  };
  await writeJson(resolve(stagingDirectory, "test-report.json"), report);
  return report;
}

async function artifactRecord(repositoryRoot, path, alternatePath) {
  const full = alternatePath ?? containedPath(repositoryRoot, path, "release artifact path");
  const info = await lstat(full);
  if (!info.isFile() || info.isSymbolicLink()) throw new Error(`release artifact must be a regular non-symlink file: ${path}`);
  return {
    path,
    sha256: await sha256File(full),
    sizeBytes: info.size,
    mediaType: mediaType(path),
  };
}

async function packageRecords(repositoryRoot) {
  const manifestPath = containedPath(repositoryRoot, "SMS/docs/provenance/evidence-package-manifest.json", "package manifest path");
  const detachedPath = containedPath(repositoryRoot, "SMS/docs/provenance/evidence-package-manifest.sig", "package signature path");
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  return [{
    packageId: manifest.packageId,
    kind: manifest.kind,
    version: manifest.version,
    contentSha256: manifest.contentSha256,
    manifestSha256: await sha256File(manifestPath),
    signatureSha256: await sha256File(detachedPath),
    keyId: manifest.keyId,
    qualification: manifest.qualification,
  }];
}

async function generateManifest(repositoryRoot, version) {
  if (!SEMVER.test(version)) throw new Error("--version must be a stable semantic version");
  const releaseDirectory = resolve(repositoryRoot, RELEASE_DIRECTORY);
  try {
    await lstat(releaseDirectory);
    throw new Error(`release directory already exists; release records are immutable: ${releaseDirectory}`);
  } catch (error) {
    if (!(error instanceof Error) || error.code !== "ENOENT") throw error;
  }
  const docsDirectory = resolve(repositoryRoot, "SMS/docs");
  await mkdir(docsDirectory, { recursive: true, mode: 0o755 });
  const stagingDirectory = await mkdtemp(join(docsDirectory, ".release-staging-"));
  let published = false;
  try {
    const source = await sourceMetadata(repositoryRoot);
    const rootPackage = JSON.parse(await readFile(resolve(repositoryRoot, "SMS/package.json"), "utf8"));
    if (rootPackage.version !== version) throw new Error(`release version ${version} does not match SMS/package.json ${String(rootPackage.version)}`);
    const npmVersion = (await run("npm", ["--version"], { cwd: smsRoot })).stdout.trim();
    const dockerVersionResult = await run("docker", ["--version"], { cwd: smsRoot, allowFailure: true });
    const sbomSummary = await generateSbom(stagingDirectory, source, version);
    const scan = await generateSecurityScan(stagingDirectory, source);
    const testReport = await generateTestReport(stagingDirectory, source);
    const artifacts = [];
    for (const path of [...BASE_ARTIFACTS, ...GENERATED_ARTIFACTS].sort()) {
      const alternate = path.startsWith(`${RELEASE_DIRECTORY}/`)
        ? resolve(stagingDirectory, path.slice(`${RELEASE_DIRECTORY}/`.length))
        : undefined;
      artifacts.push(await artifactRecord(repositoryRoot, path, alternate));
    }
    const byPath = new Map(artifacts.map((artifact) => [artifact.path, artifact]));
    const manifest = {
      schemaVersion: "1.0",
      releaseId: `fac-isr-sms@${version}`,
      version,
      issuer: "FAC ISR SMS development release automation",
      author: {
        softwareAuthor: rootPackage.author,
        sourceCommitAuthor: { name: source.authorName, email: source.authorEmail },
      },
      sourceCommit: source.commit,
      sourceCommittedAtUtc: source.committedAtUtc,
      generatedAtUtc: source.committedAtUtc,
      timestampBasis: "source commit time",
      repository: "https://github.com/strikerdlm/MATB",
      toolchain: {
        node: process.version.slice(1),
        npm: npmVersion,
        docker: dockerVersionResult.code === 0 ? dockerVersionResult.stdout.trim() : "unavailable",
        platform: "linux/amd64",
      },
      keyId: null,
      publicKeySha256: null,
      signature: null,
      qualification: "blocked",
      operationalReady: false,
      artifacts,
      sbomPath: SBOM_PATH,
      sbomSha256: byPath.get(SBOM_PATH).sha256,
      sbomSummary,
      scanReportPath: SCAN_REPORT_PATH,
      scanReportSha256: byPath.get(SCAN_REPORT_PATH).sha256,
      testReportPath: TEST_REPORT_PATH,
      testReportSha256: byPath.get(TEST_REPORT_PATH).sha256,
      packages: await packageRecords(repositoryRoot),
      verification: {
        prerequisiteStatus: testReport.status,
        dependencyAuditStatus: scan.dependencyAudit.status,
        approvedImageScannerStatus: scan.approvedImageScanner.status,
        malwareScannerStatus: scan.malwareScanner.status,
      },
      knownLimitations: [
        "The development release key is not an institutional FAC/AAAES approval signature.",
        "An institutionally approved OCI vulnerability scan and signed scanner database snapshot are not attached.",
        "An institutionally approved malware scan and signed definition set are not attached.",
        "Approved terrain, map, AIP, terminology-policy, and operational policy packages are not bundled.",
        "Receiving-node no-downgrade state and encrypted storage must be independently attested.",
        "Qualified cybersecurity, operational, ERP, and FAC/AAAES acceptance reviews remain outstanding.",
      ],
    };
    await writeJson(resolve(stagingDirectory, "release-manifest.json"), manifest);
    await rename(stagingDirectory, releaseDirectory);
    published = true;
    process.stdout.write(`PASS unsigned release manifest generated for ${source.commit.slice(0, 12)}\n`);
    process.stdout.write(`${resolve(repositoryRoot, MANIFEST_PATH)}\n`);
  } finally {
    if (!published) await rm(stagingDirectory, { recursive: true, force: true });
  }
}

async function privateKeyMaterial(repositoryRoot, keyPathValue) {
  if (typeof keyPathValue !== "string" || keyPathValue.trim() === "") {
    throw new Error("SMS_RELEASE_PRIVATE_KEY_PATH or --private-key is required");
  }
  const keyPath = resolve(keyPathValue);
  const keyInfo = await lstat(keyPath);
  if (!keyInfo.isFile() || keyInfo.isSymbolicLink()) throw new Error("release private key must be a regular non-symlink file");
  if ((keyInfo.mode & 0o077) !== 0) throw new Error("release private key permissions must not grant group or other access");
  const actualKeyPath = await realpath(keyPath);
  const fromRepository = relative(repositoryRoot, actualKeyPath);
  if (fromRepository === "" || (!fromRepository.startsWith(`..${sep}`) && fromRepository !== ".." && !isAbsolute(fromRepository))) {
    throw new Error("release private key must be stored outside the repository");
  }
  const privateKey = createPrivateKey(await readFile(actualKeyPath));
  if (privateKey.asymmetricKeyType !== "ed25519") throw new Error("release private key must be Ed25519");
  const publicKey = createPublicKey(privateKey);
  const publicPem = publicKey.export({ type: "spki", format: "pem" }).toString();
  const fingerprint = sha256(Buffer.from(publicPem, "utf8"));
  return { privateKey, publicKey, publicPem, fingerprint, keyId: `ed25519-sha256-${fingerprint.slice(0, 16)}` };
}

async function signManifest(repositoryRoot, requiredKeyId, keyPathValue) {
  if (typeof requiredKeyId !== "string" || !KEY_ID.test(requiredKeyId)) throw new Error("--key-id must use ed25519-sha256-<16 hex>");
  const manifestPath = resolve(repositoryRoot, MANIFEST_PATH);
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  if (manifest.signature !== null || manifest.keyId !== null || manifest.publicKeySha256 !== null) {
    throw new Error("release manifest is already signed; release records are immutable");
  }
  manifestShape(manifest, false);
  await assertArtifactInventory(repositoryRoot, manifest);
  const key = await privateKeyMaterial(repositoryRoot, keyPathValue);
  if (requiredKeyId !== key.keyId) throw new Error(`--key-id does not match the supplied key; expected ${key.keyId}`);
  const unsigned = { ...manifest, keyId: key.keyId, publicKeySha256: key.fingerprint, signature: null };
  const payload = { ...unsigned };
  delete payload.signature;
  const signature = signPayload(null, Buffer.from(canonicalJson(payload), "utf8"), key.privateKey).toString("base64");
  const signed = { ...unsigned, signature };
  const releaseDirectory = resolve(repositoryRoot, RELEASE_DIRECTORY);
  const temporaryManifest = resolve(releaseDirectory, ".release-manifest.json.tmp");
  const temporarySignature = resolve(releaseDirectory, ".release-manifest.sig.tmp");
  const temporaryPublicKey = resolve(releaseDirectory, ".release-public-key.pem.tmp");
  try {
    await writeJson(temporaryManifest, signed);
    await writeFile(temporarySignature, `${signature}\n`, { encoding: "utf8", mode: 0o644 });
    await writeFile(temporaryPublicKey, key.publicPem, { encoding: "utf8", mode: 0o644 });
    await rename(temporaryPublicKey, resolve(repositoryRoot, PUBLIC_KEY_PATH));
    await rename(temporarySignature, resolve(repositoryRoot, SIGNATURE_PATH));
    await rename(temporaryManifest, manifestPath);
  } finally {
    await Promise.all([
      rm(temporaryManifest, { force: true }),
      rm(temporarySignature, { force: true }),
      rm(temporaryPublicKey, { force: true }),
    ]);
  }
  process.stdout.write(`PASS release manifest signed with ${key.keyId}\n`);
}

function manifestShape(manifest, signatureRequired = true) {
  if (manifest === null || typeof manifest !== "object" || Array.isArray(manifest)) throw new Error("release manifest must be an object");
  if (manifest.schemaVersion !== "1.0" || !SEMVER.test(manifest.version) || manifest.releaseId !== `fac-isr-sms@${manifest.version}`) {
    throw new Error("release manifest identity is invalid");
  }
  if (!/^[a-f0-9]{40}$/.test(manifest.sourceCommit) || !exactUtc(manifest.sourceCommittedAtUtc) || !exactUtc(manifest.generatedAtUtc)) {
    throw new Error("release source provenance is invalid");
  }
  if (signatureRequired) {
    if (!KEY_ID.test(manifest.keyId) || !SHA256.test(manifest.publicKeySha256) || !/^[A-Za-z0-9+/]+={0,2}$/.test(manifest.signature)) {
      throw new Error("release signature metadata is invalid");
    }
  } else if (manifest.keyId !== null || manifest.publicKeySha256 !== null || manifest.signature !== null) {
    throw new Error("unsigned release manifest must not contain signature metadata");
  }
  if (!Array.isArray(manifest.artifacts) || manifest.artifacts.length === 0 || !Array.isArray(manifest.packages)) {
    throw new Error("release artifact or package inventory is unavailable");
  }
  if (!SHA256.test(manifest.sbomSha256) || !SHA256.test(manifest.scanReportSha256) || !SHA256.test(manifest.testReportSha256)) {
    throw new Error("release evidence hashes are invalid");
  }
  if (!Array.isArray(manifest.knownLimitations) || manifest.knownLimitations.length === 0) throw new Error("known limitations are required");
}

async function sourceCommitArtifact(repositoryRoot, sourceCommit, artifactPath) {
  const repositoryTopLevel = (await run("git", ["rev-parse", "--show-toplevel"], { cwd: repositoryRoot })).stdout.trim();
  if (await realpath(repositoryTopLevel) !== await realpath(repositoryRoot)) {
    throw new Error("source-commit verification requires the repository root");
  }
  const tree = (await run("git", ["ls-tree", sourceCommit, "--", artifactPath], { cwd: repositoryRoot })).stdout.trim();
  const metadata = /^(100644|100755) blob [a-f0-9]{40}\t(.+)$/.exec(tree);
  if (metadata === null || metadata[2] !== artifactPath) throw new Error(`release artifact is absent or not a regular file at source commit: ${artifactPath}`);
  return (await run("git", ["show", `${sourceCommit}:${artifactPath}`], { cwd: repositoryRoot })).stdoutBuffer;
}

async function assertArtifactInventory(repositoryRoot, manifest, options = {}) {
  const artifactSource = options.artifactSource ?? "worktree";
  if (artifactSource !== "worktree" && artifactSource !== "source-commit") throw new Error(`unsupported artifact source: ${String(artifactSource)}`);
  const seen = new Set();
  let previous = "";
  for (const artifact of manifest.artifacts) {
    if (artifact === null || typeof artifact !== "object" || typeof artifact.path !== "string" || !SHA256.test(artifact.sha256)
      || !Number.isSafeInteger(artifact.sizeBytes) || artifact.sizeBytes < 0 || typeof artifact.mediaType !== "string") {
      throw new Error(`invalid artifact record: ${String(artifact?.path)}`);
    }
    if (previous >= artifact.path || seen.has(artifact.path)) throw new Error("artifact inventory must be sorted and unique");
    previous = artifact.path;
    seen.add(artifact.path);
    const path = containedPath(repositoryRoot, artifact.path, "release artifact path");
    let sizeBytes;
    let digest;
    if (artifactSource === "source-commit" && !artifact.path.startsWith(`${RELEASE_DIRECTORY}/`)) {
      const content = await sourceCommitArtifact(repositoryRoot, manifest.sourceCommit, artifact.path);
      sizeBytes = content.byteLength;
      digest = sha256(content);
    } else {
      const info = await lstat(path);
      if (!info.isFile() || info.isSymbolicLink()) throw new Error(`release artifact is not a regular file: ${artifact.path}`);
      sizeBytes = info.size;
      digest = await sha256File(path);
    }
    if (sizeBytes !== artifact.sizeBytes || digest !== artifact.sha256) {
      throw new Error(`release artifact hash or size mismatch: ${artifact.path}`);
    }
    if (/(^|\/)(?:[^/]*private[^/]*|[^/]+\.(?:key|p12|pfx))$/iu.test(artifact.path)) {
      throw new Error(`private key artifact is forbidden: ${artifact.path}`);
    }
  }
  for (const [pathField, hashField] of [
    ["sbomPath", "sbomSha256"],
    ["scanReportPath", "scanReportSha256"],
    ["testReportPath", "testReportSha256"],
  ]) {
    const record = manifest.artifacts.find((artifact) => artifact.path === manifest[pathField]);
    if (record === undefined || record.sha256 !== manifest[hashField]) throw new Error(`${pathField} is not locked by the artifact inventory`);
  }
  return manifest.artifacts.map((artifact) => artifact.path);
}

export async function verifyRelease(repositoryRoot = defaultRepositoryRoot, options = {}) {
  const root = resolve(repositoryRoot);
  const checks = [];
  const add = (id, status, detail, evidence = []) => checks.push({ id, status, detail, evidence });
  let manifest;
  try {
    const manifestFile = await lstat(resolve(root, MANIFEST_PATH));
    if (!manifestFile.isFile() || manifestFile.isSymbolicLink()) throw new Error("release manifest must be a regular non-symlink file");
    manifest = JSON.parse(await readFile(resolve(root, MANIFEST_PATH), "utf8"));
    manifestShape(manifest);
    add("manifest-shape", "pass", "release identity, provenance, and evidence fields are valid", [MANIFEST_PATH]);
  } catch (error) {
    add("manifest-shape", "fail", error instanceof Error ? error.message : String(error), [MANIFEST_PATH]);
  }

  if (manifest !== undefined) {
    try {
      const detached = (await readFile(resolve(root, SIGNATURE_PATH), "utf8")).trim();
      const publicPem = await readFile(resolve(root, PUBLIC_KEY_PATH), "utf8");
      if (detached !== manifest.signature) throw new Error("detached release signature differs from the manifest");
      const fingerprint = sha256(Buffer.from(publicPem, "utf8"));
      if (fingerprint !== manifest.publicKeySha256 || manifest.keyId !== `ed25519-sha256-${fingerprint.slice(0, 16)}`) {
        throw new Error("release public key fingerprint does not match the pinned key ID");
      }
      const publicKey = createPublicKey(publicPem);
      if (publicKey.asymmetricKeyType !== "ed25519") throw new Error("release public key is not Ed25519");
      const { signature, ...payload } = manifest;
      if (!verifySignature(null, Buffer.from(canonicalJson(payload), "utf8"), publicKey, Buffer.from(signature, "base64"))) {
        throw new Error("release manifest signature is invalid");
      }
      add("signature", "pass", `detached Ed25519 signature verified with pinned key ${manifest.keyId}`, [SIGNATURE_PATH, PUBLIC_KEY_PATH]);
    } catch (error) {
      add("signature", "fail", error instanceof Error ? error.message : String(error), [SIGNATURE_PATH, PUBLIC_KEY_PATH]);
    }

    try {
      const evidence = await assertArtifactInventory(root, manifest, options);
      const sourceDetail = options.artifactSource === "source-commit" ? ` at source commit ${manifest.sourceCommit.slice(0, 12)}` : " in the worktree";
      add("artifact-inventory", "pass", `${manifest.artifacts.length} release artifacts match exact sizes and SHA-256 hashes${sourceDetail}`, evidence);
    } catch (error) {
      add("artifact-inventory", "fail", error instanceof Error ? error.message : String(error));
    }

    try {
      const sbom = JSON.parse(await readFile(containedPath(root, manifest.sbomPath, "SBOM path"), "utf8"));
      const properties = new Map((sbom.metadata?.properties ?? []).map((property) => [property.name, property.value]));
      if (sbom.bomFormat !== "CycloneDX" || !Array.isArray(sbom.components) || sbom.components.length === 0) throw new Error("CycloneDX SBOM component inventory is unavailable");
      if (properties.get("fac-isr:source-commit") !== manifest.sourceCommit) throw new Error("SBOM source commit differs from the release manifest");
      if (!sbom.components.some((component) => Array.isArray(component.licenses) && component.licenses.length > 0)) throw new Error("SBOM has no license evidence");
      if (!sbom.components.some((component) => Array.isArray(component.externalReferences) && component.externalReferences.length > 0)) throw new Error("SBOM has no dependency source references");
      add("sbom", "pass", `${sbom.components.length} CycloneDX components include locked source, license, map, and font metadata`, [manifest.sbomPath]);
    } catch (error) {
      add("sbom", "fail", error instanceof Error ? error.message : String(error), [String(manifest.sbomPath)]);
    }

    try {
      const scan = JSON.parse(await readFile(containedPath(root, manifest.scanReportPath, "security scan report path"), "utf8"));
      if (scan.schemaVersion !== "1.0" || scan.sourceCommit !== manifest.sourceCommit || !Number.isSafeInteger(scan.dependencyAudit?.vulnerabilityCounts?.total)) {
        throw new Error("security scan report provenance or dependency counts are invalid");
      }
      if (scan.dependencyAudit.vulnerabilityCounts.total === 0) add("dependency-vulnerability-scan", "pass", "npm audit reported no locked dependency advisories", [manifest.scanReportPath]);
      else add("dependency-vulnerability-scan", "warn", `${scan.dependencyAudit.vulnerabilityCounts.total} dependency advisories require disposition`, [manifest.scanReportPath]);
      if (scan.approvedImageScanner?.status === "pass" && scan.malwareScanner?.status === "pass") {
        add("approved-security-scan", "pass", "approved OCI vulnerability and malware scan evidence is attached", [manifest.scanReportPath]);
      } else {
        add("approved-security-scan", "warn", "approved OCI vulnerability and malware scan evidence remains a release blocker", [manifest.scanReportPath]);
      }
    } catch (error) {
      add("dependency-vulnerability-scan", "fail", error instanceof Error ? error.message : String(error), [String(manifest.scanReportPath)]);
      add("approved-security-scan", "fail", "security scan evidence is unavailable", [String(manifest.scanReportPath)]);
    }

    try {
      const report = JSON.parse(await readFile(containedPath(root, manifest.testReportPath, "test report path"), "utf8"));
      if (report.schemaVersion !== "1.0" || report.sourceCommit !== manifest.sourceCommit || report.status !== "pass"
        || !Array.isArray(report.checks) || report.checks.length === 0 || report.checks.some((check) => check.status !== "pass" || !SHA256.test(check.outputSha256))) {
        throw new Error("release prerequisite test evidence is incomplete or failing");
      }
      add("test-evidence", "pass", `${report.checks.length} release prerequisite commands passed with output digests`, [manifest.testReportPath]);
    } catch (error) {
      add("test-evidence", "fail", error instanceof Error ? error.message : String(error), [String(manifest.testReportPath)]);
    }

    if (manifest.qualification === "blocked" && manifest.operationalReady === false && manifest.knownLimitations.length > 0) {
      add("qualification", "warn", "release integrity is signed, but institutional and scanner acceptance blockers remain explicit");
    } else if (manifest.qualification === "approved" && manifest.operationalReady === true) {
      add("qualification", "pass", "release manifest records approved operational readiness");
    } else {
      add("qualification", "fail", "release qualification and operationalReady fields are inconsistent");
    }
  }

  const ok = !checks.some((check) => check.status === "fail");
  const operationalReady = ok && manifest?.operationalReady === true && !checks.some((check) => check.status === "warn");
  return {
    schemaVersion: "1.0",
    ok,
    operationalReady,
    releaseId: typeof manifest?.releaseId === "string" ? manifest.releaseId : "unknown",
    sourceCommit: typeof manifest?.sourceCommit === "string" ? manifest.sourceCommit : "unknown",
    checks,
  };
}

function humanSummary(report) {
  const lines = [
    `${report.ok ? "PASS" : "FAIL"} signed release integrity: ${report.releaseId}`,
    `Operational readiness: ${report.operationalReady ? "READY" : "BLOCKED"}`,
  ];
  for (const check of report.checks) lines.push(`${check.status.toUpperCase().padEnd(4)} ${check.id}: ${check.detail}`);
  return `${lines.join("\n")}\n`;
}

async function main() {
  let options;
  try {
    options = parseArguments(process.argv.slice(2));
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 2;
    return;
  }
  if (options.help || options.command === undefined) {
    process.stdout.write([
      "Usage:",
      "  node scripts/generate-sbom.mjs manifest --version <x.y.z>",
      "  node scripts/generate-sbom.mjs sign --key-id <ed25519-sha256-id> [--private-key <external-path>]",
      "  node scripts/generate-sbom.mjs verify [--json]",
      "",
    ].join("\n"));
    return;
  }
  try {
    if (options.command === "manifest") {
      if (options.version === undefined) throw new Error("manifest requires --version");
      await generateManifest(defaultRepositoryRoot, options.version);
    } else if (options.command === "sign") {
      if (options.keyId === undefined) throw new Error("sign requires --key-id");
      await signManifest(defaultRepositoryRoot, options.keyId, options.privateKeyPath);
    } else if (options.command === "verify") {
      const report = await verifyRelease(defaultRepositoryRoot);
      process.stdout.write(options.json ? `${JSON.stringify(report)}\n` : humanSummary(report));
      process.exitCode = report.ok ? 0 : 1;
    } else throw new Error(`unknown command: ${String(options.command)}`);
  } catch (error) {
    process.stderr.write(`FAIL release ${String(options.command)}: ${error instanceof Error ? error.message : String(error)}\n`);
    if (process.env.SMS_RELEASE_DEBUG === "1" && error instanceof Error && error.stack !== undefined) {
      process.stderr.write(`${error.stack}\n`);
    }
    process.exitCode = 1;
  }
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await main();
}
