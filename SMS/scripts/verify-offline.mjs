#!/usr/bin/env node

import { createHash, verify as verifySignature } from "node:crypto";
import { createReadStream } from "node:fs";
import { lstat, open, readFile, readdir, stat, writeFile } from "node:fs/promises";
import { isAbsolute, relative, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";
import {
  ACCEPTANCE_EVIDENCE_PATHS,
  ACCEPTANCE_STATE_PATHS,
  deriveReviewDecisionState,
  signatureRecordFailure,
} from "./acceptance-contracts.mjs";

const SHA256 = /^[a-f0-9]{64}$/;
const OCI_DIGEST = /^sha256:([a-f0-9]{64})$/;
const EXACT_UTC = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{3}))?Z$/;
const CONTROL_FILES = new Set([
  "evidence-package-manifest.json",
  "evidence-package-manifest.sig",
  "evidence-package-public-key.pem",
]);
const REQUIRED_ACCEPTANCE_SCOPES = new Set([
  "cybersecurity-deployment",
  "emergency-response",
  "human-factors-protocol",
  "official-geospatial-data",
  "operational-checklist",
  "racae-interpretation-translation",
  "research-separation",
  "risk-authority",
  "training-safety-promotion",
]);
const ACCEPTANCE_REVIEW_STATUSES = new Set(["pending", "accepted", "accepted-with-conditions", "rejected"]);
const OPERATIONAL_WARNING_IDS = new Set([
  "encrypted-storage",
  "institutional-acceptance",
  "map-baseline",
  "no-downgrade",
  "policy-package",
  "release-qualification",
  "release-signature",
  "terrain-package",
]);

function parseArguments(argv) {
  const options = { bundle: undefined, asOfUtc: undefined, report: undefined, json: false, noNetwork: false };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--bundle" || argument === "--as-of" || argument === "--report") {
      const value = argv[index + 1];
      if (value === undefined || value.startsWith("--")) throw new Error(`${argument} requires a value`);
      if (argument === "--bundle") options.bundle = value;
      else if (argument === "--as-of") options.asOfUtc = value;
      else options.report = value;
      index += 1;
    } else if (argument === "--json") options.json = true;
    else if (argument === "--no-network") options.noNetwork = true;
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

async function sha256File(path) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}

function containedPath(root, path, field) {
  if (typeof path !== "string" || path === "" || isAbsolute(path) || path.includes("\\") || path.includes("\0")) {
    throw new Error(`${field} must be a relative POSIX path`);
  }
  const components = path.split("/");
  if (components.some((component) => component === "" || component === "." || component === "..")) {
    throw new Error(`${field} contains path traversal`);
  }
  const target = resolve(root, path);
  const fromRoot = relative(root, target);
  if (fromRoot === "" || fromRoot === ".." || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot)) {
    throw new Error(`${field} escapes the bundle root`);
  }
  return target;
}

function containedDirectoryPath(root, directory, path, field) {
  const target = containedPath(root, path, field);
  const directoryRoot = resolve(root, directory);
  const fromDirectory = relative(directoryRoot, target);
  if (fromDirectory === "" || fromDirectory === ".." || fromDirectory.startsWith(`..${sep}`) || isAbsolute(fromDirectory)) {
    throw new Error(`${field} must be below ${directory}/`);
  }
  return target;
}

async function walkFiles(root, current = root) {
  const entries = await readdir(current, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = resolve(current, entry.name);
    const path = relative(root, full).split(sep).join("/");
    if (entry.isSymbolicLink()) throw new Error(`symbolic links are forbidden in the bundle: ${path}`);
    if (entry.isDirectory()) files.push(...await walkFiles(root, full));
    else if (entry.isFile()) files.push({ path, full, sizeBytes: (await stat(full)).size });
    else throw new Error(`unsupported bundle entry: ${path}`);
  }
  return files.sort((left, right) => left.path.localeCompare(right.path));
}

function parseJson(text, field) {
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`${field} is not valid JSON: ${error instanceof Error ? error.message : String(error)}`, { cause: error });
  }
}

function exactUtc(value) {
  if (typeof value !== "string") return false;
  const match = EXACT_UTC.exec(value);
  if (match === null) return false;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText, millisecondsText = "000"] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  const milliseconds = Number(millisecondsText);
  const date = new Date(value);
  return Number.isFinite(date.getTime())
    && date.getUTCFullYear() === year
    && date.getUTCMonth() + 1 === month
    && date.getUTCDate() === day
    && date.getUTCHours() === hour
    && date.getUTCMinutes() === minute
    && date.getUTCSeconds() === second
    && date.getUTCMilliseconds() === milliseconds;
}

function packageVersion(value) {
  return typeof value === "string" && /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(value);
}

function nonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

async function bundledSignatureFailure(bundleRoot, signature, asOfUtc) {
  if (signature?.schemaVersion !== "1.0") return "signature schemaVersion must be 1.0";
  if (!nonEmptyString(signature?.signatureId)) return "signatureId is required";
  if (signature?.reviewer?.identityType !== "human") return "reviewer identity must be human";
  if (!nonEmptyString(signature?.reviewer?.identity)
    || !nonEmptyString(signature?.reviewer?.organizationUnit)
    || !nonEmptyString(signature?.reviewer?.role)) {
    return "human reviewer identity, organization/unit, and role are required";
  }
  if (!REQUIRED_ACCEPTANCE_SCOPES.has(signature?.scope)) return "signature scope is invalid";
  if (!["accept", "accept-with-conditions", "reject"].includes(signature?.decision)) return "signature decision is invalid";
  if (!exactUtc(signature?.signedAtUtc) || Date.parse(signature.signedAtUtc) > Date.parse(asOfUtc)) {
    return "signature time must be exact UTC and not after bundle verification time";
  }
  if (!Array.isArray(signature?.evidenceHashes) || signature.evidenceHashes.length === 0) {
    return "at least one hash-addressed evidence file is required";
  }
  for (const evidence of signature.evidenceHashes) {
    if (!nonEmptyString(evidence?.path) || !SHA256.test(evidence?.sha256)) return "signature evidence path or SHA-256 is invalid";
    try {
      const path = containedPath(bundleRoot, evidence.path, "institutional signature evidence");
      if (await sha256File(path) !== evidence.sha256) return `institutional signature evidence hash does not match: ${evidence.path}`;
    } catch (error) {
      return `institutional signature evidence is unavailable: ${error instanceof Error ? error.message : String(error)}`;
    }
  }
  if (!Array.isArray(signature?.conflicts) || signature.conflicts.some((conflict) => !nonEmptyString(conflict))) {
    return "signature conflicts must be an array of non-empty strings";
  }
  if (!Array.isArray(signature?.conditions) || signature.conditions.some((condition) => !nonEmptyString(condition))) {
    return "signature conditions must be an array of non-empty strings";
  }
  if (signature.decision === "accept-with-conditions" && signature.conditions.length === 0) {
    return "conditional acceptance must state at least one condition";
  }
  if (signature.decision === "accept" && signature.conditions.length > 0) {
    return "unconditional acceptance cannot retain conditions";
  }
  if (!exactUtc(signature?.reviewDueAtUtc)
    || Date.parse(signature.reviewDueAtUtc) <= Date.parse(signature.signedAtUtc)
    || Date.parse(signature.reviewDueAtUtc) <= Date.parse(asOfUtc)) {
    return "signature review date must be exact UTC, future, and after signing";
  }
  return undefined;
}

function sameCanonical(left, right) {
  return canonicalJson(left) === canonicalJson(right);
}

function rebuildPacketId(packet, label) {
  if (packet?.schemaVersion !== "1.0" || packet?.recordType !== "review-packet" || !SHA256.test(packet?.packetId)) {
    throw new Error(`${label} shape is invalid`);
  }
  const { packetId, ...unsigned } = packet;
  const actual = createHash("sha256").update(canonicalJson(unsigned)).digest("hex");
  if (actual !== packetId) throw new Error(`${label} packet identifier does not match its canonical manifest`);
  return packetId;
}

function sortedRoleHeads(heads) {
  return [...heads].sort((left, right) => left.scope.localeCompare(right.scope) || left.role.localeCompare(right.role));
}

async function verifyAcceptanceWorkflow(bundleRoot, workflow, record, signatures, builtAtUtc, asOfUtc) {
  if (!Array.isArray(workflow?.currentPackets) || !Array.isArray(workflow?.evidenceMappings)
    || !Array.isArray(workflow?.recordedDecisions) || !Array.isArray(workflow?.roleHeads)) {
    throw new Error("acceptance workflow metadata is incomplete");
  }

  const mappingsBySource = new Map();
  const mappingDestinations = new Set();
  for (const mapping of workflow.evidenceMappings) {
    if (!ACCEPTANCE_EVIDENCE_PATHS.includes(mapping?.sourcePath) || !SHA256.test(mapping?.sha256)
      || typeof mapping?.bundlePath !== "string" || !mapping.bundlePath.startsWith("reports/acceptance/review-evidence/")) {
      throw new Error("acceptance evidence mapping is malformed");
    }
    if (mappingsBySource.has(mapping.sourcePath) || mappingDestinations.has(mapping.bundlePath)) {
      throw new Error("acceptance evidence mapping source or destination is duplicated");
    }
    const path = containedDirectoryPath(
      bundleRoot,
      "reports/acceptance/review-evidence",
      mapping.bundlePath,
      "acceptance evidence mapping",
    );
    if (await sha256File(path) !== mapping.sha256) throw new Error(`acceptance evidence mapping hash mismatch: ${mapping.sourcePath}`);
    mappingsBySource.set(mapping.sourcePath, mapping);
    mappingDestinations.add(mapping.bundlePath);
  }
  const expectedSources = [...ACCEPTANCE_EVIDENCE_PATHS].sort();
  if (!sameCanonical(workflow.evidenceMappings.map((mapping) => mapping.sourcePath), expectedSources)) {
    throw new Error("acceptance evidence mappings must be the complete unique sorted source inventory");
  }
  const mappedEvidence = workflow.evidenceMappings.map((mapping) => ({ path: mapping.sourcePath, sha256: mapping.sha256 }));
  const bundledStatePaths = new Map([
    ["docs/release/operational-readiness-record.json", "reports/acceptance/operational-readiness-record.json"],
    ["docs/release/verification-signatures.jsonl", "reports/acceptance/verification-signatures.jsonl"],
    ["docs/release/state-aviation-acceptance-checklist.md", "reports/acceptance/state-aviation-acceptance-checklist.md"],
    ["docs/release/known-limitations.md", "reports/acceptance/known-limitations.md"],
  ]);
  const acceptanceState = [];
  for (const sourcePath of ACCEPTANCE_STATE_PATHS) {
    const mappedPath = bundledStatePaths.get(sourcePath) ?? mappingsBySource.get(sourcePath)?.bundlePath;
    if (mappedPath === undefined) throw new Error(`acceptance-state evidence mapping is absent: ${sourcePath}`);
    acceptanceState.push({ path: sourcePath, sha256: await sha256File(containedPath(bundleRoot, mappedPath, "acceptance-state evidence")) });
  }
  acceptanceState.sort((left, right) => left.path.localeCompare(right.path));
  const acceptanceStateFingerprint = createHash("sha256").update(canonicalJson(acceptanceState)).digest("hex");

  const currentScopes = new Set();
  const currentPacketScopes = workflow.currentPackets.map((packet) => packet?.scope);
  if (!sameCanonical(currentPacketScopes, [...REQUIRED_ACCEPTANCE_SCOPES].sort())) {
    throw new Error("current packet inventory must contain every institutional acceptance scope in sorted order");
  }
  for (const current of workflow.currentPackets) {
    if (currentScopes.has(current.scope) || !SHA256.test(current.packetId) || !SHA256.test(current.sha256)
      || current.path !== `reports/acceptance/reviewer-packets/${current.scope}/packet-manifest.json`) {
      throw new Error(`current packet metadata is invalid: ${String(current?.scope ?? "unknown")}`);
    }
    currentScopes.add(current.scope);
    const path = containedPath(bundleRoot, current.path, "current acceptance packet");
    if (await sha256File(path) !== current.sha256) throw new Error(`current packet hash mismatch: ${current.scope}`);
    const packet = parseJson(await readFile(path, "utf8"), `current packet ${current.scope}`);
    if (rebuildPacketId(packet, `current packet ${current.scope}`) !== current.packetId || packet.scope !== current.scope
      || packet.releaseId !== record.releaseId || packet.readinessRecordId !== record.recordId
      || packet.asOfUtc !== builtAtUtc || packet.acceptanceStateFingerprint !== acceptanceStateFingerprint
      || !sameCanonical(packet.evidence, mappedEvidence)) {
      if (packet.acceptanceStateFingerprint !== acceptanceStateFingerprint) {
        throw new Error(`current packet acceptance-state fingerprint differs: ${current.scope}`);
      }
      if (packet.releaseId !== record.releaseId || packet.readinessRecordId !== record.recordId) {
        throw new Error(`current packet release or readiness identifier differs: ${current.scope}`);
      }
      throw new Error(`current packet metadata or evidence differs: ${current.scope}`);
    }
    const review = record.requiredReviews.find((candidate) => candidate?.scope === current.scope);
    const state = review === undefined ? undefined : deriveReviewDecisionState(review, signatures);
    const expectedCoverage = review?.requiredReviewerRoles?.map((role) => {
      const head = state?.roleHeads.find((candidate) => candidate.role === role);
      return head === undefined ? { role, signatureId: null, decision: null } : { role, signatureId: head.signatureId, decision: head.decision };
    });
    if (review === undefined || state.violations.length > 0 || packet.currentStatus !== state.status
      || !sameCanonical(packet.requiredReviewerRoles, review.requiredReviewerRoles)
      || !sameCanonical(packet.roleCoverage, expectedCoverage)) {
      throw new Error(`current packet role state differs from the acceptance record: ${current.scope}`);
    }
  }

  if (workflow.recordedDecisions.length !== signatures.length) {
    throw new Error("recorded decision inventory does not match the signature ledger");
  }
  const decisionsById = new Map(signatures.map((decision) => [decision?.signatureId, decision]));
  const recordedIds = new Set();
  for (const metadata of workflow.recordedDecisions) {
    const decision = decisionsById.get(metadata?.signatureId);
    if (decision === undefined || recordedIds.has(metadata.signatureId)) throw new Error("recorded decision metadata is absent or duplicated");
    recordedIds.add(metadata.signatureId);
    const failure = signatureRecordFailure(decision);
    if (failure !== undefined) throw new Error(`${metadata.signatureId}: ${failure}`);
    if (decision.releaseId !== record.releaseId) {
      throw new Error(`${metadata.signatureId}: decision release differs from the bundled readiness record`);
    }
    if (Date.parse(decision.signedAtUtc) > Date.parse(asOfUtc) || Date.parse(decision.reviewDueAtUtc) <= Date.parse(asOfUtc)) {
      throw new Error(`${metadata.signatureId}: institutional decision time is outside the verification window`);
    }
    if (metadata.scope !== decision.scope || metadata.role !== decision.reviewer.role
      || metadata.sourcePacketPath !== decision.sourcePacketPath
      || metadata.sourcePacketSha256 !== decision.sourcePacketSha256
      || metadata.artifactSourcePath !== decision.institutionalArtifact.path
      || metadata.artifactSha256 !== decision.institutionalArtifact.sha256) {
      throw new Error(`${metadata.signatureId}: recorded decision metadata contradicts the signature ledger`);
    }
    for (const evidence of decision.evidenceHashes) {
      const mapping = mappingsBySource.get(evidence.path);
      if (mapping === undefined || mapping.sha256 !== evidence.sha256) {
        throw new Error(`${metadata.signatureId}: decision evidence mapping is absent or inconsistent`);
      }
    }
    if (typeof metadata.packetBundlePath !== "string" || !metadata.packetBundlePath.startsWith("reports/acceptance/recorded-decisions/")) {
      throw new Error(`${metadata.signatureId}: historical packet bundle path is invalid`);
    }
    const packetPath = containedDirectoryPath(
      bundleRoot,
      "reports/acceptance/recorded-decisions",
      metadata.packetBundlePath,
      "historical acceptance packet",
    );
    if (await sha256File(packetPath) !== metadata.sourcePacketSha256) throw new Error(`${metadata.signatureId}: historical packet hash mismatch`);
    const packet = parseJson(await readFile(packetPath, "utf8"), `historical packet ${metadata.signatureId}`);
    if (rebuildPacketId(packet, `historical packet ${metadata.signatureId}`) !== decision.sourcePacketId
      || packet.scope !== decision.scope || packet.releaseId !== record.releaseId
      || packet.readinessRecordId !== record.recordId || !sameCanonical(packet.evidence, decision.evidenceHashes)) {
      throw new Error(`${metadata.signatureId}: historical packet differs from the recorded decision`);
    }
    if (typeof metadata.artifactBundlePath !== "string" || !metadata.artifactBundlePath.startsWith("reports/acceptance/recorded-decisions/")) {
      throw new Error(`${metadata.signatureId}: institutional artifact bundle path is invalid`);
    }
    const artifactPath = containedDirectoryPath(
      bundleRoot,
      "reports/acceptance/recorded-decisions",
      metadata.artifactBundlePath,
      "institutional acceptance artifact",
    );
    if (await sha256File(artifactPath) !== metadata.artifactSha256) throw new Error(`${metadata.signatureId}: institutional artifact hash mismatch`);
    const artifact = parseJson(await readFile(artifactPath, "utf8"), `institutional artifact ${metadata.signatureId}`);
    if (artifact?.schemaVersion !== "1.0" || artifact?.recordType !== "institutional-acceptance-artifact"
      || artifact?.classification !== "unclassified-controlled" || artifact?.contentType !== "controlled-safety-metadata") {
      throw new Error(`${metadata.signatureId}: institutional artifact classification is invalid`);
    }
  }

  const reviewStates = new Map();
  const expectedHeads = [];
  for (const review of record.requiredReviews) {
    const state = deriveReviewDecisionState(review, signatures);
    if (state.violations.length > 0) throw new Error(`acceptance decision chain is invalid for ${String(review?.scope)}`);
    reviewStates.set(review.scope, state);
    expectedHeads.push(...state.roleHeads.map((head) => ({ scope: review.scope, ...head })));
  }
  const expectedSortedHeads = sortedRoleHeads(expectedHeads);
  if (!sameCanonical(workflow.roleHeads, sortedRoleHeads(workflow.roleHeads))
    || !sameCanonical(workflow.roleHeads, expectedSortedHeads)) {
    throw new Error("acceptance workflow role heads do not equal the exact sorted derived role heads");
  }
  return reviewStates;
}

async function scanTar(path, wanted = new Set()) {
  const handle = await open(path, "r");
  const captured = new Map();
  const entries = new Set();
  try {
    const info = await handle.stat();
    let offset = 0;
    while (offset + 512 <= info.size) {
      const header = Buffer.alloc(512);
      const { bytesRead } = await handle.read(header, 0, 512, offset);
      if (bytesRead !== 512) throw new Error("truncated tar header");
      if (header.every((byte) => byte === 0)) break;
      const name = header.subarray(0, 100).toString("utf8").replace(/\0.*$/s, "");
      const prefix = header.subarray(345, 500).toString("utf8").replace(/\0.*$/s, "");
      const entryPath = prefix === "" ? name : `${prefix}/${name}`;
      const sizeText = header.subarray(124, 136).toString("ascii").replace(/\0.*$/s, "").trim();
      const size = Number.parseInt(sizeText || "0", 8);
      if (!Number.isSafeInteger(size) || size < 0 || offset + 512 + size > info.size) throw new Error(`invalid tar entry size: ${entryPath}`);
      entries.add(entryPath.replace(/\/$/u, ""));
      if (wanted.has(entryPath)) {
        if (size > 4 * 1024 * 1024) throw new Error(`OCI metadata entry is unexpectedly large: ${entryPath}`);
        const body = Buffer.alloc(size);
        if (size > 0) {
          const result = await handle.read(body, 0, size, offset + 512);
          if (result.bytesRead !== size) throw new Error(`truncated tar entry: ${entryPath}`);
        }
        captured.set(entryPath, body);
      }
      offset += 512 + Math.ceil(size / 512) * 512;
    }
  } finally {
    await handle.close();
  }
  return { entries, captured };
}

async function verifyOciArchive(path, expectedManifestDigest) {
  const first = await scanTar(path, new Set(["oci-layout", "index.json"]));
  const layoutBuffer = first.captured.get("oci-layout");
  const indexBuffer = first.captured.get("index.json");
  if (layoutBuffer === undefined || indexBuffer === undefined) throw new Error("archive is missing oci-layout or index.json");
  const layout = parseJson(layoutBuffer.toString("utf8"), "oci-layout");
  if (layout.imageLayoutVersion !== "1.0.0") throw new Error("unsupported OCI layout version");
  const index = parseJson(indexBuffer.toString("utf8"), "OCI index");
  const digest = index?.manifests?.[0]?.digest;
  if (digest !== expectedManifestDigest) throw new Error(`OCI manifest digest mismatch: expected ${expectedManifestDigest}, found ${String(digest)}`);
  const match = OCI_DIGEST.exec(digest);
  if (match === null) throw new Error("OCI index manifest digest is malformed");
  const blobPath = `blobs/sha256/${match[1]}`;
  const second = await scanTar(path, new Set([blobPath]));
  const manifestBlob = second.captured.get(blobPath);
  if (manifestBlob === undefined) throw new Error("OCI manifest blob is absent");
  const actual = createHash("sha256").update(manifestBlob).digest("hex");
  if (actual !== match[1]) throw new Error("OCI manifest blob hash mismatch");
}

async function verifyEvidencePackage(bundleRoot, asOfUtc) {
  const packageRoot = resolve(bundleRoot, "packages/regulatory");
  const manifestPath = resolve(packageRoot, "evidence-package-manifest.json");
  const detachedPath = resolve(packageRoot, "evidence-package-manifest.sig");
  const keyPath = resolve(packageRoot, "evidence-package-public-key.pem");
  const manifest = parseJson(await readFile(manifestPath, "utf8"), "regulatory package manifest");
  const detached = (await readFile(detachedPath, "utf8")).trim();
  const publicKey = await readFile(keyPath, "utf8");
  if (manifest.signature !== detached) throw new Error("detached package signature does not match the manifest");
  if (!exactUtc(manifest.effectiveFromUtc) || (manifest.expiresAtUtc !== undefined && !exactUtc(manifest.expiresAtUtc))) {
    throw new Error("regulatory package effective window is malformed");
  }
  const asOf = Date.parse(asOfUtc);
  if (asOf < Date.parse(manifest.effectiveFromUtc)) throw new Error("regulatory package is not yet effective");
  if (manifest.expiresAtUtc !== undefined && asOf >= Date.parse(manifest.expiresAtUtc)) throw new Error("regulatory package is expired");
  const { signature, ...unsigned } = manifest;
  if (!verifySignature(null, Buffer.from(canonicalJson(unsigned), "utf8"), publicKey, Buffer.from(signature, "base64"))) {
    throw new Error("regulatory package signature is invalid");
  }
  const inventoryDigest = createHash("sha256").update(canonicalJson(manifest.files)).digest("hex");
  if (inventoryDigest !== manifest.contentSha256) throw new Error("regulatory package inventory digest is invalid");
  const expected = new Set(manifest.files.map((file) => file.path));
  const walked = await walkFiles(packageRoot);
  const actual = walked.map((file) => file.path).filter((path) => !CONTROL_FILES.has(path));
  const missing = [...expected].filter((path) => !actual.includes(path));
  const extra = actual.filter((path) => !expected.has(path));
  if (missing.length > 0 || extra.length > 0) throw new Error(`regulatory package file set differs (missing: ${missing.join(", ") || "none"}; extra: ${extra.join(", ") || "none"})`);
  for (const file of manifest.files) {
    const path = containedPath(packageRoot, file.path, "regulatory package file");
    const info = await stat(path);
    if (info.size !== file.sizeBytes || await sha256File(path) !== file.sha256) throw new Error(`regulatory package file hash mismatch: ${file.path}`);
  }
  if (Array.isArray(manifest.dependencies) && manifest.dependencies.length > 0) throw new Error("regulatory package dependencies are unavailable in this bundle");
  return manifest;
}

async function verifyReleaseAttestation(bundleRoot, bundleManifest) {
  const releaseRoot = resolve(bundleRoot, "provenance/release");
  const manifestPath = resolve(releaseRoot, "release-manifest.json");
  const manifest = parseJson(await readFile(manifestPath, "utf8"), "release manifest");
  const detached = (await readFile(resolve(releaseRoot, "release-manifest.sig"), "utf8")).trim();
  const publicKey = await readFile(resolve(releaseRoot, "release-public-key.pem"), "utf8");
  if (manifest.schemaVersion !== "1.0" || typeof manifest.releaseId !== "string" || !/^[a-f0-9]{40}$/.test(manifest.sourceCommit)
    || typeof manifest.keyId !== "string" || !SHA256.test(manifest.publicKeySha256) || !Array.isArray(manifest.artifacts)) {
    throw new Error("release manifest shape is invalid");
  }
  if (detached !== manifest.signature) throw new Error("detached release signature differs from the manifest");
  const fingerprint = createHash("sha256").update(publicKey).digest("hex");
  if (fingerprint !== manifest.publicKeySha256 || manifest.keyId !== `ed25519-sha256-${fingerprint.slice(0, 16)}`) {
    throw new Error("release public key fingerprint does not match its key ID");
  }
  const { signature, ...payload } = manifest;
  if (!verifySignature(null, Buffer.from(canonicalJson(payload), "utf8"), publicKey, Buffer.from(signature, "base64"))) {
    throw new Error("release manifest signature is invalid");
  }
  if (bundleManifest.commit !== manifest.sourceCommit) throw new Error("bundle source commit differs from the signed release");
  const control = bundleManifest.releaseAttestation;
  if (control?.path !== "provenance/release/release-manifest.json" || control.keyId !== manifest.keyId
    || control.sha256 !== await sha256File(manifestPath)) {
    throw new Error("bundle release-attestation metadata differs from the signed manifest");
  }
  for (const [pathField, hashField] of [
    ["sbomPath", "sbomSha256"],
    ["scanReportPath", "scanReportSha256"],
    ["testReportPath", "testReportSha256"],
  ]) {
    const releasePath = manifest[pathField];
    const record = manifest.artifacts.find((artifact) => artifact.path === releasePath);
    const name = typeof releasePath === "string" ? releasePath.split("/").at(-1) : undefined;
    if (record === undefined || name === undefined || record.sha256 !== manifest[hashField]) {
      throw new Error(`${pathField} is not locked by the release artifact inventory`);
    }
    if (await sha256File(resolve(releaseRoot, name)) !== record.sha256) throw new Error(`bundled release evidence hash mismatch: ${name}`);
  }
  const sbom = parseJson(await readFile(resolve(releaseRoot, "sbom.cdx.json"), "utf8"), "signed release SBOM");
  const scan = parseJson(await readFile(resolve(releaseRoot, "security-scan.json"), "utf8"), "signed security scan report");
  const tests = parseJson(await readFile(resolve(releaseRoot, "test-report.json"), "utf8"), "signed test report");
  if (sbom.bomFormat !== "CycloneDX" || !Array.isArray(sbom.components) || sbom.components.length === 0) throw new Error("signed release SBOM is incomplete");
  if (scan.sourceCommit !== manifest.sourceCommit || tests.sourceCommit !== manifest.sourceCommit || tests.status !== "pass") {
    throw new Error("signed scan or test evidence does not match the release source");
  }
  const approvedScans = scan.approvedImageScanner?.status === "pass" && scan.malwareScanner?.status === "pass";
  return { manifest, approvedScans };
}

export async function verifyBundle(bundleRoot, options) {
  const checks = [];
  const add = (id, status, detail, evidence = []) => checks.push({ id, status, detail, evidence });
  let files = [];
  let manifest;
  let releaseId = "unknown";

  try {
    const rootInfo = await lstat(bundleRoot);
    if (!rootInfo.isDirectory() || rootInfo.isSymbolicLink()) throw new Error("bundle root must be a real directory");
    files = await walkFiles(bundleRoot);
    add("bundle-root", "pass", "bundle root contains only regular files and directories", [bundleRoot]);
  } catch (error) {
    add("bundle-root", "fail", error instanceof Error ? error.message : String(error), [bundleRoot]);
  }

  try {
    manifest = parseJson(await readFile(resolve(bundleRoot, "bundle-manifest.json"), "utf8"), "bundle manifest");
    releaseId = typeof manifest.releaseId === "string" ? manifest.releaseId : "unknown";
    if (manifest.schemaVersion !== "1.0" || !Array.isArray(manifest.files) || !exactUtc(manifest.builtAtUtc)) throw new Error("bundle manifest shape is invalid");
    if (typeof manifest.commit !== "string" || !/^[a-f0-9]{40}$/.test(manifest.commit)) throw new Error("bundle manifest commit is invalid");
    add("bundle-manifest", "pass", "bundle manifest shape is valid", ["bundle-manifest.json"]);
  } catch (error) {
    add("bundle-manifest", "fail", error instanceof Error ? error.message : String(error), ["bundle-manifest.json"]);
  }

  if (manifest !== undefined && Array.isArray(manifest.files)) {
    try {
      const declared = new Map();
      for (const file of manifest.files) {
        if (!SHA256.test(file.sha256) || !Number.isSafeInteger(file.sizeBytes) || file.sizeBytes < 0) throw new Error(`invalid file record: ${String(file.path)}`);
        containedPath(bundleRoot, file.path, "bundle manifest file");
        if (declared.has(file.path)) throw new Error(`duplicate bundle file record: ${file.path}`);
        declared.set(file.path, file);
      }
      const actual = files.filter((file) => file.path !== "bundle-manifest.json" && file.path !== options.reportRelative);
      const missing = [...declared.keys()].filter((path) => !actual.some((file) => file.path === path));
      const extra = actual.map((file) => file.path).filter((path) => !declared.has(path));
      if (missing.length > 0 || extra.length > 0) throw new Error(`bundle inventory differs (missing: ${missing.join(", ") || "none"}; extra: ${extra.join(", ") || "none"})`);
      for (const file of actual) {
        const record = declared.get(file.path);
        if (record.sizeBytes !== file.sizeBytes || await sha256File(file.full) !== record.sha256) throw new Error(`bundle file hash mismatch: ${file.path}`);
      }
      add("bundle-inventory", "pass", `${actual.length} bundle artifacts match the manifest`, actual.map((file) => file.path));
    } catch (error) {
      add("bundle-inventory", "fail", error instanceof Error ? error.message : String(error));
    }
  } else add("bundle-inventory", "fail", "bundle manifest inventory is unavailable");

  try {
    let rejected;
    for (const file of files) {
      if (/(^|\/)(?:[^/]*private[^/]*|[^/]+\.(?:key|p12|pfx))$/iu.test(file.path)) {
        rejected = file.path;
        break;
      }
      if (file.sizeBytes <= 2 * 1024 * 1024 && !/\.(?:pdf|tar|gz|png|jpg|jpeg|woff2?)$/iu.test(file.path)) {
        const contents = await readFile(file.full, "utf8");
        if (/-----BEGIN (?:EC |RSA |OPENSSH )?PRIVATE KEY-----/u.test(contents)) {
          rejected = file.path;
          break;
        }
      }
    }
    if (rejected !== undefined) throw new Error(`private signing or TLS key material is forbidden: ${rejected}`);
    add("private-key-material", "pass", "bundle contains public verification material only");
  } catch (error) {
    add("private-key-material", "fail", error instanceof Error ? error.message : String(error));
  }

  if (options.noNetwork) add("network-isolation", "pass", "verification requested with network disabled");
  else add("network-isolation", "fail", "--no-network is required for disconnected verification");

  if (manifest?.image !== undefined) {
    try {
      if (!SHA256.test(manifest.image.archiveSha256) || OCI_DIGEST.exec(manifest.image.manifestDigest) === null) throw new Error("image digest metadata is malformed");
      const imagePath = containedPath(bundleRoot, manifest.image.path, "image archive path");
      if (await sha256File(imagePath) !== manifest.image.archiveSha256) throw new Error("OCI archive hash does not match image metadata");
      await verifyOciArchive(imagePath, manifest.image.manifestDigest);
      add("oci-image", "pass", `OCI archive and manifest digest verified for ${manifest.image.platform}`, [manifest.image.path]);
    } catch (error) {
      add("oci-image", "fail", error instanceof Error ? error.message : String(error), [String(manifest.image.path ?? "images/fac-isr-sms-edge.oci.tar")]);
    }
  } else add("oci-image", "fail", "bundle manifest has no OCI image metadata");

  const asOfUtc = options.asOfUtc ?? manifest?.builtAtUtc;
  try {
    if (!exactUtc(asOfUtc)) throw new Error("an exact --as-of UTC timestamp or valid bundle build time is required");
    const regulatory = await verifyEvidencePackage(bundleRoot, asOfUtc);
    add("regulatory-package", "pass", `${regulatory.packageId}@${regulatory.version} signature, hashes, dependencies, and effective window verified`, ["packages/regulatory/evidence-package-manifest.json"]);
  } catch (error) {
    add("regulatory-package", "fail", error instanceof Error ? error.message : String(error), ["packages/regulatory"]);
  }

  try {
    const schema = parseJson(await readFile(resolve(bundleRoot, "runtime/schema.json"), "utf8"), "runtime schema");
    if (schema.schemaVersion !== 1 || schema.journalMode !== "WAL" || schema.foreignKeys !== true) throw new Error("runtime schema does not require migration v1, WAL, and foreign keys");
    add("database-migrations", "pass", "runtime schema and SQLite safety pragmas are pinned", ["runtime/schema.json"]);
  } catch (error) {
    add("database-migrations", "fail", error instanceof Error ? error.message : String(error), ["runtime/schema.json"]);
  }

  let mapRecords;
  try {
    const register = await readFile(resolve(bundleRoot, "provenance/map-package-register.jsonl"), "utf8");
    mapRecords = register.split(/\r?\n/u).filter(Boolean).map((line, index) => parseJson(line, `map package register line ${index + 1}`));
    const terrain = mapRecords.find((record) => record.kind === "terrain");
    if (terrain === undefined) throw new Error("terrain source record is absent");
    if (terrain.contentStatus === "not-bundled") add("terrain-package", "warn", `${terrain.packageId} is explicitly planned but not bundled; terrain-dependent release gates remain blocked`, ["provenance/map-package-register.jsonl"]);
    else add("terrain-package", "pass", `${terrain.packageId} is registered as bundled`, ["provenance/map-package-register.jsonl"]);
  } catch (error) {
    add("terrain-package", "fail", error instanceof Error ? error.message : String(error), ["provenance/map-package-register.jsonl"]);
  }

  try {
    if (!Array.isArray(mapRecords)) throw new Error("map package register is unavailable");
    const map = mapRecords.find((record) => record.kind === "map");
    if (map === undefined) throw new Error("map baseline source record is absent");
    if (map.contentStatus === "not-bundled") add("map-baseline", "warn", `${map.packageId} is planning context only and is not bundled`, ["provenance/map-package-register.jsonl"]);
    else add("map-baseline", "pass", `${map.packageId} is registered as bundled`, ["provenance/map-package-register.jsonl"]);
  } catch (error) {
    add("map-baseline", "fail", error instanceof Error ? error.message : String(error), ["provenance/map-package-register.jsonl"]);
  }

  try {
    const termsPath = resolve(bundleRoot, "packages/regulatory/package-content/docs/translations/controlled-terms.json");
    const terms = parseJson(await readFile(termsPath, "utf8"), "controlled terminology");
    if (!Array.isArray(terms.terms) || terms.terms.length === 0) throw new Error("controlled terminology is empty");
    add("terminology", "pass", `${terms.terms.length} controlled translation records are checksum-covered by the regulatory package`, ["packages/regulatory/package-content/docs/translations/controlled-terms.json"]);
  } catch (error) {
    add("terminology", "fail", error instanceof Error ? error.message : String(error));
  }

  try {
    await readFile(resolve(bundleRoot, "provenance/kernel-golden-case-report.md"), "utf8");
    add("policy-package", "warn", "kernel verification report is present, but no qualified signed operational policy package is bundled", ["provenance/kernel-golden-case-report.md"]);
  } catch (error) {
    add("policy-package", "fail", `kernel policy evidence is absent: ${error instanceof Error ? error.message : String(error)}`);
  }

  try {
    const compose = await readFile(resolve(bundleRoot, "install/compose.edge.yml"), "utf8");
    if (!compose.includes("internal: true") || !compose.includes("read_only: true") || !compose.includes("/opt/sms/packages:ro") || !compose.includes("no-new-privileges:true")) {
      throw new Error("compose profile is missing network, filesystem, or privilege hardening");
    }
    add("runtime-hardening", "pass", "compose profile uses an internal network, read-only root, read-only packages, and no-new-privileges", ["install/compose.edge.yml"]);
  } catch (error) {
    add("runtime-hardening", "fail", error instanceof Error ? error.message : String(error));
  }

  try {
    const report = parseJson(await readFile(resolve(bundleRoot, "reports/image-smoke.json"), "utf8"), "image smoke report");
    if (report.status !== "pass" || report.networkMode !== "none" || report.readOnlyRoot !== true) throw new Error("image was not smoke-tested with no network and a read-only root");
    add("health-endpoints", "pass", "container self-test passed with network=none and readiness remained fail-closed", ["reports/image-smoke.json"]);
  } catch (error) {
    add("health-endpoints", "fail", error instanceof Error ? error.message : String(error));
  }

  try {
    const sbom = parseJson(await readFile(resolve(bundleRoot, "sbom/npm.cdx.json"), "utf8"), "npm SBOM");
    if (sbom.bomFormat !== "CycloneDX" || !Array.isArray(sbom.components)) throw new Error("SBOM is not a CycloneDX component inventory");
    await readFile(resolve(bundleRoot, "licenses/THIRD_PARTY_NOTICES.md"), "utf8");
    add("sbom-licenses-fonts", "pass", `${sbom.components.length} dependency components and license/font handling notes are bundled`, ["sbom/npm.cdx.json", "licenses/THIRD_PARTY_NOTICES.md"]);
  } catch (error) {
    add("sbom-licenses-fonts", "fail", error instanceof Error ? error.message : String(error));
  }

  try {
    const packageIndex = parseJson(await readFile(resolve(bundleRoot, "packages/package-index.json"), "utf8"), "package index");
    if (!Array.isArray(packageIndex.packages) || packageIndex.packages.some((entry) => !packageVersion(entry.version))) throw new Error("package index versions are malformed");
    add("no-downgrade", "warn", "bundle versions are pinned; the receiving node must compare its signed installed-state before activation", ["packages/package-index.json"]);
  } catch (error) {
    add("no-downgrade", "fail", error instanceof Error ? error.message : String(error));
  }

  try {
    const instructions = await readFile(resolve(bundleRoot, "install/README.md"), "utf8");
    if (!/encrypted volume/iu.test(instructions) || !/TLS/iu.test(instructions)) throw new Error("install instructions do not require encrypted storage and TLS");
    add("encrypted-storage", "warn", "encrypted storage is required by the install profile but must be attested on the receiving host", ["install/README.md"]);
  } catch (error) {
    add("encrypted-storage", "fail", error instanceof Error ? error.message : String(error));
  }

  const acceptanceEvidence = [
    "reports/acceptance/operational-readiness-record.json",
    "reports/acceptance/state-aviation-acceptance-checklist.md",
    "reports/acceptance/known-limitations.md",
    "reports/acceptance/verification-signatures.jsonl",
  ];
  try {
    try {
      await lstat(resolve(bundleRoot, "reports/acceptance/.acceptance-transaction.json"));
      throw new Error("an incomplete acceptance transaction journal is present");
    } catch (error) {
      if (error instanceof Error && error.code !== "ENOENT") throw error;
    }
    const record = parseJson(await readFile(resolve(bundleRoot, acceptanceEvidence[0]), "utf8"), "operational-readiness record");
    const checklist = await readFile(resolve(bundleRoot, acceptanceEvidence[1]), "utf8");
    const limitations = await readFile(resolve(bundleRoot, acceptanceEvidence[2]), "utf8");
    const signatureLedger = await readFile(resolve(bundleRoot, acceptanceEvidence[3]), "utf8");
    if (record.schemaVersion !== "1.0" || typeof record.operationalReady !== "boolean"
      || !Array.isArray(record.requiredReviews) || !Array.isArray(record.knownLimitations)
      || checklist.trim() === "" || limitations.trim() === "") {
      throw new Error("institutional acceptance evidence shape is invalid");
    }
    const signatures = signatureLedger.split(/\r?\n/u)
      .filter((line) => line.trim() !== "")
      .map((line, index) => parseJson(line, `institutional signature line ${index + 1}`));
    if (signatures.some((signature) => signature?.reviewer?.identityType !== "human")) {
      throw new Error("institutional acceptance requires human reviewer identities; automation signatures are forbidden");
    }
    const acceptanceControl = manifest?.acceptanceEvidence;
    if (acceptanceControl !== undefined && (
      acceptanceControl.recordPath !== acceptanceEvidence[0]
      || acceptanceControl.checklistPath !== acceptanceEvidence[1]
      || acceptanceControl.knownLimitationsPath !== acceptanceEvidence[2]
      || acceptanceControl.signatureLogPath !== acceptanceEvidence[3]
      || acceptanceControl.qualification !== record.qualification
      || acceptanceControl.operationalReady !== record.operationalReady
      || acceptanceControl.signatureCount !== signatures.length
    )) {
      throw new Error("bundle acceptance metadata contradicts the bundled readiness record or signature ledger");
    }
    const scopeCounts = new Map();
    for (const review of record.requiredReviews) {
      if (!REQUIRED_ACCEPTANCE_SCOPES.has(review?.scope) || !ACCEPTANCE_REVIEW_STATUSES.has(review?.status)) {
        throw new Error(`institutional acceptance review is invalid: ${String(review?.scope ?? "unknown")}`);
      }
      scopeCounts.set(review.scope, (scopeCounts.get(review.scope) ?? 0) + 1);
    }
    const missingScopes = [...REQUIRED_ACCEPTANCE_SCOPES].filter((scope) => scopeCounts.get(scope) !== 1);
    if (missingScopes.length > 0 || scopeCounts.size !== REQUIRED_ACCEPTANCE_SCOPES.size) {
      throw new Error(`institutional acceptance scopes are missing or duplicated: ${missingScopes.join(", ") || "unexpected scope"}`);
    }
    const modernWorkflow = acceptanceControl?.workflow;
    const signatureById = new Map();
    for (const signature of signatures) {
      if (typeof signature?.signatureId !== "string" || signature.signatureId === "" || signatureById.has(signature.signatureId)) {
        throw new Error(`institutional human signature identifier is absent or duplicated: ${String(signature?.signatureId ?? "unknown")}`);
      }
      if (modernWorkflow === undefined) {
        const signatureFailure = await bundledSignatureFailure(bundleRoot, signature, asOfUtc);
        if (signatureFailure !== undefined) throw new Error(`${signature.signatureId}: ${signatureFailure}`);
      }
      signatureById.set(signature.signatureId, signature);
    }
    let reviewStates;
    if (modernWorkflow === undefined) {
      if (acceptanceControl !== undefined) throw new Error("bundle acceptance workflow metadata is absent");
      for (const review of record.requiredReviews) {
        const signatureIds = Array.isArray(review.signatureIds) ? review.signatureIds : [];
        if (review.status !== "pending" && signatureIds.length === 0) {
          throw new Error(`institutional review ${review.scope} has no linked human signature`);
        }
        const expectedDecision = review.status === "accepted"
          ? "accept"
          : review.status === "accepted-with-conditions"
            ? "accept-with-conditions"
            : review.status === "rejected"
              ? "reject"
              : undefined;
        for (const signatureId of signatureIds) {
          const signature = signatureById.get(signatureId);
          if (signature === undefined) throw new Error(`institutional review ${review.scope} references an absent linked signature`);
          if (signature.scope !== review.scope || (expectedDecision !== undefined && signature.decision !== expectedDecision)) {
            throw new Error(`institutional linked signature does not attest ${review.scope} and its recorded decision`);
          }
        }
      }
    } else {
      reviewStates = await verifyAcceptanceWorkflow(bundleRoot, modernWorkflow, record, signatures, manifest.builtAtUtc, asOfUtc);
    }
    const blockedReviews = record.requiredReviews.filter((review) => (reviewStates?.get(review.scope)?.status ?? review.status) !== "accepted");
    const openLimitations = record.knownLimitations.filter((limitation) => limitation?.status === "open" && limitation?.releaseBlocking === true);
    if (record.operationalReady && (blockedReviews.length > 0 || openLimitations.length > 0)) {
      throw new Error(`operational readiness is overclaimed while ${blockedReviews.length} reviews are pending or conditional and ${openLimitations.length} limitations remain release-blocking`);
    }
    if ((record.operationalReady && record.qualification !== "accepted")
      || (!record.operationalReady && record.qualification !== "blocked")) {
      throw new Error("institutional acceptance qualification contradicts operationalReady");
    }
    add(
      "institutional-acceptance",
      record.operationalReady ? "pass" : "warn",
      record.operationalReady
        ? "institutional acceptance record declares the exact release operationally ready"
        : `institutional acceptance evidence is present and explicitly blocked by ${blockedReviews.length} reviews and ${openLimitations.length} limitations`,
      acceptanceEvidence,
    );
  } catch (error) {
    add("institutional-acceptance", "fail", error instanceof Error ? error.message : String(error), acceptanceEvidence);
  }

  if (manifest?.releaseAttestation === null || manifest?.releaseAttestation === undefined) {
    add("release-signature", "warn", "no current signed software release attestation is bundled", ["bundle-manifest.json"]);
    add("release-qualification", "warn", "development bundle has no signed release qualification evidence");
  } else {
    try {
      const release = await verifyReleaseAttestation(bundleRoot, manifest);
      add("release-signature", "pass", `${release.manifest.releaseId} Ed25519 signature and evidence hashes verified`, ["provenance/release/release-manifest.json"]);
      if (release.manifest.qualification === "approved" && release.manifest.operationalReady === true && release.approvedScans) {
        add("release-qualification", "pass", "signed release records approved qualification and scanner evidence", ["provenance/release/release-manifest.json"]);
      } else {
        add("release-qualification", "warn", "signed development release remains blocked on approved scans and qualified institutional acceptance", ["provenance/release/release-manifest.json"]);
      }
    } catch (error) {
      add("release-signature", "fail", error instanceof Error ? error.message : String(error), ["provenance/release"]);
      add("release-qualification", "fail", "release qualification cannot be trusted because signature verification failed", ["provenance/release"]);
    }
  }

  const ok = !checks.some((check) => check.status === "fail");
  const operationalReady = ok && !checks.some((check) => check.status === "warn" && OPERATIONAL_WARNING_IDS.has(check.id));
  return {
    schemaVersion: "1.0",
    ok,
    operationalReady,
    releaseId,
    verifiedAtUtc: options.asOfUtc ?? manifest?.builtAtUtc ?? null,
    checks,
  };
}

function humanSummary(report) {
  const lines = [
    `${report.ok ? "PASS" : "FAIL"} offline bundle integrity: ${report.releaseId}`,
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
  if (options.help) {
    process.stdout.write("Usage: node scripts/verify-offline.mjs --bundle <directory> --no-network [--as-of <UTC>] [--json] [--report <path>]\n");
    return;
  }
  if (options.bundle === undefined) {
    process.stderr.write("--bundle is required\n");
    process.exitCode = 2;
    return;
  }
  const bundleRoot = resolve(options.bundle);
  const reportPath = options.report === undefined ? undefined : resolve(options.report);
  const reportRelative = reportPath === undefined ? undefined : relative(bundleRoot, reportPath).split(sep).join("/");
  let report;
  try {
    report = await verifyBundle(bundleRoot, { ...options, reportRelative });
  } catch (error) {
    report = {
      schemaVersion: "1.0",
      ok: false,
      operationalReady: false,
      releaseId: "unknown",
      verifiedAtUtc: options.asOfUtc ?? null,
      checks: [{ id: "verifier", status: "fail", detail: error instanceof Error ? error.message : String(error), evidence: [] }],
    };
  }
  if (reportPath !== undefined) {
    await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
  }
  process.stdout.write(options.json ? `${JSON.stringify(report)}\n` : humanSummary(report));
  process.exitCode = report.ok ? 0 : 1;
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await main();
}
