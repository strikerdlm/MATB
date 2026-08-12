#!/usr/bin/env node

import { constants } from "node:fs";
import { open } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import {
  ACCEPTANCE_STATE_PATHS,
  canonicalJson,
  deriveReviewDecisionState,
  exactUtc,
  isControlledAcceptanceArtifactPath,
  readJsonLines,
  resolveContainedExistingFile,
  sha256Bytes,
  sha256File,
  signatureRecordFailure,
} from "./acceptance-contracts.mjs";

const RECORD_PATH = "docs/release/operational-readiness-record.json";
const CONTROLLED_ARTIFACT = {
  schemaVersion: "1.0",
  recordType: "institutional-acceptance-artifact",
  classification: "unclassified-controlled",
  contentType: "controlled-safety-metadata",
};

function fail(message) {
  throw new Error(message);
}

/** Read and parse one regular-file byte snapshot, never following a final symbolic link. */
export async function readRegularJsonSnapshot(path, label, afterBytesRead) {
  let handle;
  try {
    handle = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW);
  } catch (error) {
    if (error?.code === "ELOOP") fail(`${label} must not be a symbolic link`);
    throw error;
  }
  try {
    if (!(await handle.stat()).isFile()) fail(`${label} must be a regular file`);
    const bytes = await handle.readFile();
    await afterBytesRead?.();
    try {
      return { value: JSON.parse(bytes.toString("utf8")), bytes, sha256: sha256Bytes(bytes) };
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      fail(`${label} is not valid JSON: ${detail}`);
    }
  } finally {
    await handle.close();
  }
}

async function inventory(root, paths) {
  const records = await Promise.all(paths.map(async (path) => ({
    path,
    sha256: await sha256File(await resolveContainedExistingFile(root, path, "acceptance evidence")),
  })));
  return records.sort((left, right) => left.path.localeCompare(right.path));
}

function sameCanonical(left, right) {
  return canonicalJson(left) === canonicalJson(right);
}

function validSystemOfRecordRef(value) {
  return typeof value === "string"
    && value === value.trim()
    && value.length >= 1
    && value.length <= 512
    && !Array.from(value).some((character) => {
      const code = character.charCodeAt(0);
      return code <= 0x1f || code === 0x7f;
    });
}

async function validateInstitutionalArtifact(root, artifact) {
  if (!isControlledAcceptanceArtifactPath(artifact?.path)) {
    fail("institutional artifact must be below docs/release/acceptance-artifacts/");
  }
  const path = await resolveContainedExistingFile(root, artifact.path, "institutional artifact");
  const snapshot = await readRegularJsonSnapshot(path, "institutional artifact");
  if (snapshot.sha256 !== artifact.sha256) fail("institutional artifact SHA-256 does not match");
  for (const [field, expected] of Object.entries(CONTROLLED_ARTIFACT)) {
    if (snapshot.value?.[field] !== expected) fail("institutional artifact must contain unclassified controlled safety metadata");
  }
}

function rebuildPacketId(packet) {
  if (packet?.schemaVersion !== "1.0" || packet?.recordType !== "review-packet" || typeof packet?.packetId !== "string") {
    fail("source packet is not a review packet");
  }
  const { packetId, ...unsignedPacket } = packet;
  if (sha256Bytes(canonicalJson(unsignedPacket)) !== packetId) fail("source packet identifier does not match its canonical manifest");
  return packetId;
}

function requirePacketAgreement(packet, record, review, decision, options, acceptanceState, evidence) {
  if (packet.releaseId !== record.releaseId || decision.releaseId !== packet.releaseId) fail("decision release does not match the current packet");
  if (packet.readinessRecordId !== record.recordId) fail("packet readiness record does not match the current repository state");
  if (packet.scope !== review.scope || decision.scope !== packet.scope) fail("decision scope does not match the current packet");
  if (packet.asOfUtc !== options.asOfUtc) fail("packet as-of time does not match validation time");
  if (!sameCanonical(packet.requiredReviewerRoles, review.requiredReviewerRoles)) fail("packet reviewer roles do not match the current review");
  if (packet.acceptanceStateFingerprint !== sha256Bytes(canonicalJson(acceptanceState))) {
    fail("packet acceptance-state fingerprint does not match the current repository state");
  }
  if (!sameCanonical(packet.evidence, evidence) || !sameCanonical(decision.evidenceHashes, packet.evidence)) {
    fail("decision evidence does not exactly match the current packet evidence");
  }
}

async function verifyEvidence(root, evidence) {
  for (const item of evidence) {
    const path = await resolveContainedExistingFile(root, item.path, "evidence");
    if (await sha256File(path) !== item.sha256) fail(`evidence SHA-256 does not match: ${item.path}`);
  }
}

/** Validate an institutional human decision without changing any acceptance evidence. */
export async function validateAcceptanceDecision(root, packetPath, decisionPath, options) {
  const repositoryRoot = resolve(root);
  if (!exactUtc(options?.asOfUtc)) fail("asOfUtc must be an exact UTC timestamp");

  const decisionInput = await readRegularJsonSnapshot(decisionPath, "decision input");
  const decision = decisionInput.value;
  if (decision?.recordType !== "institutional-decision") fail("only institutional-decision records are recordable");
  const schemaFailure = signatureRecordFailure(decision);
  if (schemaFailure !== undefined) fail(schemaFailure);
  if (!validSystemOfRecordRef(decision.systemOfRecordRef)) fail("systemOfRecordRef must be trimmed, 1-512 characters, and contain no ASCII control characters");

  const expectedPacketPath = await resolveContainedExistingFile(repositoryRoot, decision.sourcePacketPath, "source packet");
  const packetInput = await readRegularJsonSnapshot(packetPath, "packet input");
  if (resolve(packetPath) !== expectedPacketPath) fail("packet input does not match decision sourcePacketPath");
  const packet = packetInput.value;
  const packetId = rebuildPacketId(packet);
  if (decision.sourcePacketId !== packetId) fail("decision source packet identifier does not match packet");
  if (decision.sourcePacketSha256 !== packetInput.sha256) fail("decision source packet SHA-256 does not match packet");

  const recordPath = await resolveContainedExistingFile(repositoryRoot, RECORD_PATH, "readiness record");
  const record = (await readRegularJsonSnapshot(recordPath, "readiness record")).value;
  const review = Array.isArray(record?.requiredReviews)
    ? record.requiredReviews.find((candidate) => candidate?.scope === decision.scope)
    : undefined;
  if (review === undefined) fail("current readiness record does not contain the decision scope");
  if (!Array.isArray(review.requiredReviewerRoles) || !review.requiredReviewerRoles.includes(decision.reviewer.role)) {
    fail("decision reviewer role is not required for the packet scope");
  }

  const signatureLogPath = await resolveContainedExistingFile(repositoryRoot, record.signatureLogPath, "signature log");
  const signatures = await readJsonLines(signatureLogPath);
  if (signatures.some((signature) => signature?.signatureId === decision.signatureId)) fail("decision signatureId already exists");
  const [acceptanceState, evidence] = await Promise.all([
    inventory(repositoryRoot, ACCEPTANCE_STATE_PATHS),
    inventory(repositoryRoot, packet.evidence?.map((item) => item?.path) ?? []),
  ]);
  requirePacketAgreement(packet, record, review, decision, options, acceptanceState, evidence);
  await verifyEvidence(repositoryRoot, decision.evidenceHashes);
  await validateInstitutionalArtifact(repositoryRoot, decision.institutionalArtifact);

  const signedAt = Date.parse(decision.signedAtUtc);
  const asOf = Date.parse(options.asOfUtc);
  const reviewDue = Date.parse(decision.reviewDueAtUtc);
  if (signedAt > asOf) fail("decision signing time must not be after asOfUtc");
  if (reviewDue <= asOf) fail("decision review due time must be after asOfUtc");

  const current = deriveReviewDecisionState(review, signatures);
  if (current.violations.length > 0) fail(`current decision chain is invalid: ${current.violations[0].detail}`);
  const head = current.roleHeads.find((candidate) => candidate.role === decision.reviewer.role);
  if (decision.supersedesSignatureId === null && head !== undefined) fail("decision must supersede the current role head");
  if (decision.supersedesSignatureId !== null && head?.signatureId !== decision.supersedesSignatureId) {
    fail("decision supersedesSignatureId must identify the exact current role head");
  }

  const reviewForProjection = Object.fromEntries(Object.entries(review).filter(([field]) => field !== "status"));
  const projected = deriveReviewDecisionState({
    ...reviewForProjection,
    signatureIds: [...review.signatureIds, decision.signatureId],
  }, [...signatures, decision]);
  if (projected.violations.length > 0) fail(`projected decision chain is invalid: ${projected.violations[0].detail}`);
  return {
    ok: true,
    mode: "dry-run",
    signatureId: decision.signatureId,
    scope: decision.scope,
    requiredRole: decision.reviewer.role,
    projectedStatus: projected.status,
    packetId,
    artifactSha256: decision.institutionalArtifact.sha256,
  };
}

function parseCliArguments(arguments_) {
  const options = { apply: false, json: false };
  const valueArguments = new Map([
    ["--packet", "packetPath"],
    ["--decision", "decisionPath"],
    ["--as-of", "asOfUtc"],
  ]);
  for (let index = 0; index < arguments_.length; index += 1) {
    const argument = arguments_[index];
    if (argument === "--apply" || argument === "--json") {
      const field = argument.slice(2);
      if (options[field] === true) fail(`${argument} may be specified only once`);
      options[field] = true;
      continue;
    }
    const field = valueArguments.get(argument);
    if (field === undefined) fail(`unknown argument: ${argument}`);
    const value = arguments_[index + 1];
    if (value === undefined || value.startsWith("--")) fail(`${argument} requires a value`);
    if (options[field] !== undefined) fail(`${argument} may be specified only once`);
    options[field] = value;
    index += 1;
  }
  for (const [argument, field] of valueArguments) {
    if (options[field] === undefined) fail(`${argument} is required`);
  }
  return options;
}

async function main() {
  let options;
  try {
    options = parseCliArguments(process.argv.slice(2));
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 2;
    return;
  }
  try {
    if (options.apply) fail("--apply is not available until transaction support is initialized");
    const report = await validateAcceptanceDecision(process.cwd(), options.packetPath, options.decisionPath, options);
    process.stdout.write(options.json ? `${JSON.stringify(report, null, 2)}\n` : "PASS institutional decision validated (dry-run)\n");
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
    process.exitCode = 1;
  }
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
