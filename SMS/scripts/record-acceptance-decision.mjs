#!/usr/bin/env node

import { constants } from "node:fs";
import { lstat, mkdir, open, readdir, rename, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
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
import { buildAcceptanceReviewPacketManifest } from "./generate-acceptance-review-packets.mjs";
import { verifyOperationalReadiness } from "./verify-operational-readiness.mjs";

const RECORD_PATH = "docs/release/operational-readiness-record.json";
const LEDGER_PATH = "docs/release/verification-signatures.jsonl";
const RELEASE_DIRECTORY = "docs/release";
const JOURNAL_PATH = `${RELEASE_DIRECTORY}/.acceptance-transaction.json`;
const LOCK_PATH = `${RELEASE_DIRECTORY}/.acceptance-update.lock`;
const TRANSACTION_DIRECTORY = `${RELEASE_DIRECTORY}/.acceptance-transactions`;
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

function requirePacketAgreement(packet, canonicalPacket, record, review, decision, options) {
  if (!sameCanonical(packet, canonicalPacket)) {
    fail("source packet does not match the generator-owned canonical manifest for the current repository state");
  }
  if (packet.releaseId !== record.releaseId || decision.releaseId !== packet.releaseId) fail("decision release does not match the current packet");
  if (packet.readinessRecordId !== record.recordId) fail("packet readiness record does not match the current repository state");
  if (packet.scope !== review.scope || decision.scope !== packet.scope) fail("decision scope does not match the current packet");
  if (packet.asOfUtc !== options.asOfUtc) fail("packet as-of time does not match validation time");
  if (!sameCanonical(packet.requiredReviewerRoles, review.requiredReviewerRoles)) fail("packet reviewer roles do not match the current review");
  if (!sameCanonical(decision.evidenceHashes, packet.evidence)) {
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
  const canonicalPacket = await buildAcceptanceReviewPacketManifest(repositoryRoot, decision.scope, {
    asOfUtc: options.asOfUtc,
  });
  requirePacketAgreement(packet, canonicalPacket, record, review, decision, options);
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

class AcceptanceFailpointError extends Error {
  constructor(name) {
    super(`acceptance transaction failpoint: ${name}`);
    this.name = "AcceptanceFailpointError";
  }
}

async function pathExists(path) {
  try {
    await lstat(path);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

async function fsyncDirectory(path) {
  const handle = await open(path, constants.O_RDONLY);
  try {
    await handle.sync();
  } finally {
    await handle.close();
  }
}

async function writeExclusiveSynced(path, bytes, mode = 0o600) {
  const handle = await open(path, "wx", mode);
  try {
    await handle.writeFile(bytes);
    await handle.sync();
  } finally {
    await handle.close();
  }
}

async function readRegularBytesSnapshot(path, label) {
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
    return { bytes, sha256: sha256Bytes(bytes) };
  } finally {
    await handle.close();
  }
}

async function snapshotApplySources(root, packetPath, decisionPath) {
  const decisionInput = await readRegularJsonSnapshot(decisionPath, "decision input");
  const packetInput = await readRegularJsonSnapshot(packetPath, "packet input");
  const recordPath = await resolveContainedExistingFile(root, RECORD_PATH, "readiness record");
  const recordInput = await readRegularJsonSnapshot(recordPath, "readiness record");
  const ledgerRelativePath = recordInput.value?.signatureLogPath;
  if (ledgerRelativePath !== LEDGER_PATH) fail(`readiness record signatureLogPath must be ${LEDGER_PATH}`);
  const ledgerPath = await resolveContainedExistingFile(root, ledgerRelativePath, "signature log");
  const ledgerInput = await readRegularBytesSnapshot(ledgerPath, "signature log");
  const containedPaths = new Set([
    ...ACCEPTANCE_STATE_PATHS,
    ...(Array.isArray(packetInput.value?.evidence) ? packetInput.value.evidence.map((item) => item?.path) : []),
    decisionInput.value?.institutionalArtifact?.path,
  ]);
  const snapshots = [
    { path: resolve(decisionPath), sha256: decisionInput.sha256 },
    { path: resolve(packetPath), sha256: packetInput.sha256 },
  ];
  for (const candidate of containedPaths) {
    const path = await resolveContainedExistingFile(root, candidate, "acceptance source");
    snapshots.push({ path, sha256: await sha256File(path) });
  }
  const uniqueSnapshots = [...new Map(snapshots.map((item) => [item.path, item])).values()]
    .sort((left, right) => left.path.localeCompare(right.path));
  return { decisionInput, packetInput, recordInput, ledgerInput, recordPath, ledgerPath, sourceSnapshots: uniqueSnapshots };
}

async function assertSourcesUnchanged(snapshots) {
  for (const snapshot of snapshots) {
    if (await sha256File(snapshot.path) !== snapshot.sha256) {
      fail(`acceptance source changed after validation: ${snapshot.path}`);
    }
  }
}

function appendCanonicalLine(bytes, value) {
  const separator = bytes.length === 0 || bytes[bytes.length - 1] === 0x0a ? "" : "\n";
  return Buffer.concat([bytes, Buffer.from(`${separator}${canonicalJson(value)}\n`, "utf8")]);
}

function candidateRecordBytes(record, decision, projectedStatus) {
  const candidate = structuredClone(record);
  const review = candidate.requiredReviews.find((item) => item?.scope === decision.scope);
  if (review === undefined) fail("candidate readiness record does not contain the decision scope");
  review.signatureIds = [...review.signatureIds, decision.signatureId];
  review.status = projectedStatus;
  return Buffer.from(`${JSON.stringify(candidate, null, 2)}\n`, "utf8");
}

function relativeTransactionPath(transactionId, name) {
  return `${TRANSACTION_DIRECTORY}/${transactionId}/${name}`;
}

function transactionJournal(transactionId, originalLedgerHash, candidateLedgerHash, originalRecordHash, candidateRecordHash) {
  return {
    schemaVersion: "1.0",
    transactionId,
    ledger: {
      path: LEDGER_PATH,
      originalPath: relativeTransactionPath(transactionId, "ledger.original"),
      candidatePath: relativeTransactionPath(transactionId, "ledger.candidate"),
      originalSha256: originalLedgerHash,
      candidateSha256: candidateLedgerHash,
    },
    record: {
      path: RECORD_PATH,
      originalPath: relativeTransactionPath(transactionId, "record.original"),
      candidatePath: relativeTransactionPath(transactionId, "record.candidate"),
      originalSha256: originalRecordHash,
      candidateSha256: candidateRecordHash,
    },
  };
}

async function acquireApplyLock(root, transactionId) {
  const lockPath = resolve(root, LOCK_PATH);
  try {
    await writeExclusiveSynced(lockPath, `${transactionId}\n`);
    await fsyncDirectory(resolve(root, RELEASE_DIRECTORY));
  } catch (error) {
    if (error?.code === "EEXIST") fail("an acceptance update lock is already active");
    throw error;
  }
  return lockPath;
}

async function ensurePacketArchive(root, packet, packetBytes) {
  const archivePath = resolve(root, packet.sourcePacketPath ?? `docs/release/acceptance-packets/${packet.packetId}.json`);
  try {
    await writeExclusiveSynced(archivePath, packetBytes);
    await fsyncDirectory(dirname(archivePath));
  } catch (error) {
    if (error?.code !== "EEXIST") throw error;
    const archived = await readRegularBytesSnapshot(archivePath, "archived source packet");
    if (!archived.bytes.equals(packetBytes)) fail("existing source packet archive differs from the canonical packet");
  }
}

async function installStagedFile(root, stagedRelativePath, authoritativeRelativePath) {
  await rename(resolve(root, stagedRelativePath), resolve(root, authoritativeRelativePath));
  await fsyncDirectory(resolve(root, RELEASE_DIRECTORY));
}

async function stageReplacement(root, sourceRelativePath, destinationRelativePath, expectedHash) {
  const source = await readRegularBytesSnapshot(resolve(root, sourceRelativePath), "transaction snapshot");
  if (source.sha256 !== expectedHash) {
    fail(`transaction snapshot hash does not match the journal; manual investigation is required: ${sourceRelativePath}`);
  }
  const destinationPath = resolve(root, destinationRelativePath);
  try {
    await writeExclusiveSynced(destinationPath, source.bytes);
  } catch (error) {
    if (error?.code !== "EEXIST") throw error;
    const existing = await readRegularBytesSnapshot(destinationPath, "transaction replacement stage");
    if (existing.sha256 !== expectedHash) {
      fail(`transaction replacement stage hash is unrecognized; manual investigation is required: ${destinationRelativePath}`);
    }
  }
  return destinationRelativePath;
}

async function restoreOriginals(root, journal) {
  const ledgerTemporary = `${RELEASE_DIRECTORY}/.acceptance-${journal.transactionId}-ledger-rollback`;
  const recordTemporary = `${RELEASE_DIRECTORY}/.acceptance-${journal.transactionId}-record-rollback`;
  try {
    await stageReplacement(root, journal.ledger.originalPath, ledgerTemporary, journal.ledger.originalSha256);
    await stageReplacement(root, journal.record.originalPath, recordTemporary, journal.record.originalSha256);
    await installStagedFile(root, ledgerTemporary, journal.ledger.path);
    await installStagedFile(root, recordTemporary, journal.record.path);
    const [ledger, record] = await Promise.all([
      readRegularBytesSnapshot(resolve(root, journal.ledger.path), "restored signature log"),
      readRegularBytesSnapshot(resolve(root, journal.record.path), "restored readiness record"),
    ]);
    if (ledger.sha256 !== journal.ledger.originalSha256 || record.sha256 !== journal.record.originalSha256) {
      fail("restored acceptance state does not match the journaled original hashes; manual investigation is required");
    }
  } finally {
    await rm(resolve(root, ledgerTemporary), { force: true });
    await rm(resolve(root, recordTemporary), { force: true });
  }
}

async function validateRecoveryState(root, asOfUtc) {
  const report = await verifyOperationalReadiness(root, { asOfUtc, allowTransactionJournal: true });
  if (!report.ok) fail(`recovered acceptance state is invalid: ${JSON.stringify(report.violations)}`);
}

async function cleanupTransaction(root, journal, failpoint) {
  await rm(resolve(root, LOCK_PATH), { force: true });
  await fsyncDirectory(resolve(root, RELEASE_DIRECTORY));
  if (failpoint === "after-lock-remove") throw new AcceptanceFailpointError(failpoint);
  await rm(resolve(root, JOURNAL_PATH));
  await fsyncDirectory(resolve(root, RELEASE_DIRECTORY));
  if (failpoint === "after-journal-remove") throw new AcceptanceFailpointError(failpoint);
  for (const suffix of ["ledger-install", "record-install", "ledger-rollback", "record-rollback"]) {
    await rm(resolve(root, `${RELEASE_DIRECTORY}/.acceptance-${journal.transactionId}-${suffix}`), { force: true });
  }
  await rm(resolve(root, TRANSACTION_DIRECTORY, journal.transactionId), { recursive: true, force: true });
  await fsyncDirectory(resolve(root, TRANSACTION_DIRECTORY));
}

function validateJournal(journal) {
  if (journal?.schemaVersion !== "1.0" || !/^[a-f0-9]{64}$/u.test(journal?.transactionId ?? "")) {
    fail("acceptance transaction journal is invalid; manual investigation is required");
  }
  const expected = {
    ledger: { path: LEDGER_PATH, originalPath: relativeTransactionPath(journal.transactionId, "ledger.original"), candidatePath: relativeTransactionPath(journal.transactionId, "ledger.candidate") },
    record: { path: RECORD_PATH, originalPath: relativeTransactionPath(journal.transactionId, "record.original"), candidatePath: relativeTransactionPath(journal.transactionId, "record.candidate") },
  };
  for (const kind of ["ledger", "record"]) {
    const entry = journal[kind];
    if (entry?.path !== expected[kind].path || entry?.originalPath !== expected[kind].originalPath
      || entry?.candidatePath !== expected[kind].candidatePath
      || !/^[a-f0-9]{64}$/u.test(entry?.originalSha256 ?? "") || !/^[a-f0-9]{64}$/u.test(entry?.candidateSha256 ?? "")) {
      fail("acceptance transaction journal is invalid; manual investigation is required");
    }
  }
  return journal;
}

async function prepareTransactionSnapshots(root, transactionPath, snapshots) {
  try {
    await mkdir(transactionPath, { mode: 0o700 });
  } catch (error) {
    if (error?.code !== "EEXIST") throw error;
    const transactionEntry = await lstat(transactionPath);
    if (!transactionEntry.isDirectory() || transactionEntry.isSymbolicLink()) {
      fail("stale acceptance transaction evidence is not an owned directory; manual investigation is required");
    }
    const expectedNames = Object.keys(snapshots).sort();
    const actualNames = (await readdir(transactionPath)).sort();
    if (!sameCanonical(actualNames, expectedNames)) {
      fail("stale acceptance transaction evidence has an unrecognized inventory; manual investigation is required");
    }
    for (const name of expectedNames) {
      const snapshot = await readRegularBytesSnapshot(resolve(transactionPath, name), "stale acceptance transaction snapshot");
      if (snapshot.sha256 !== snapshots[name].sha256) {
        fail("stale acceptance transaction snapshot hash is unrecognized; manual investigation is required");
      }
    }
    return;
  }

  try {
    for (const [name, snapshot] of Object.entries(snapshots)) {
      await writeExclusiveSynced(resolve(transactionPath, name), snapshot.bytes);
    }
    await fsyncDirectory(transactionPath);
    await fsyncDirectory(resolve(root, TRANSACTION_DIRECTORY));
  } catch (error) {
    await rm(transactionPath, { recursive: true, force: true });
    await fsyncDirectory(resolve(root, TRANSACTION_DIRECTORY));
    throw error;
  }
}

/** Apply one validated institutional decision through a crash-consistent journal. */
export async function recordAcceptanceDecision(root, packetPath, decisionPath, options) {
  if (options?.apply !== true) fail("authoritative mutation requires apply: true");
  if (!exactUtc(options.asOfUtc)) fail("asOfUtc must be an exact UTC timestamp");
  const repositoryRoot = resolve(root);
  if (await pathExists(resolve(repositoryRoot, JOURNAL_PATH))) {
    fail("an incomplete acceptance transaction requires explicit recovery");
  }
  const validation = await validateAcceptanceDecision(repositoryRoot, packetPath, decisionPath, options);
  const baseline = await snapshotApplySources(repositoryRoot, packetPath, decisionPath);
  const candidateLedger = appendCanonicalLine(baseline.ledgerInput.bytes, baseline.decisionInput.value);
  const candidateRecord = candidateRecordBytes(baseline.recordInput.value, baseline.decisionInput.value, validation.projectedStatus);
  const candidateLedgerHash = sha256Bytes(candidateLedger);
  const candidateRecordHash = sha256Bytes(candidateRecord);
  const transactionId = sha256Bytes(canonicalJson({
    candidateSignatureId: baseline.decisionInput.value.signatureId,
    candidateRecordSha256: candidateRecordHash,
    candidateLedgerSha256: candidateLedgerHash,
  }));
  const journal = transactionJournal(
    transactionId,
    baseline.ledgerInput.sha256,
    candidateLedgerHash,
    baseline.recordInput.sha256,
    candidateRecordHash,
  );
  const transactionPath = resolve(repositoryRoot, TRANSACTION_DIRECTORY, transactionId);
  let lockPath;
  let journalCreated = false;
  let transactionCreated = false;
  try {
    lockPath = await acquireApplyLock(repositoryRoot, transactionId);
    await assertSourcesUnchanged(baseline.sourceSnapshots);
    await validateAcceptanceDecision(repositoryRoot, packetPath, decisionPath, options);
    await assertSourcesUnchanged(baseline.sourceSnapshots);

    await mkdir(resolve(repositoryRoot, TRANSACTION_DIRECTORY), { recursive: true, mode: 0o700 });
    await prepareTransactionSnapshots(repositoryRoot, transactionPath, {
      "ledger.original": { bytes: baseline.ledgerInput.bytes, sha256: journal.ledger.originalSha256 },
      "ledger.candidate": { bytes: candidateLedger, sha256: journal.ledger.candidateSha256 },
      "record.original": { bytes: baseline.recordInput.bytes, sha256: journal.record.originalSha256 },
      "record.candidate": { bytes: candidateRecord, sha256: journal.record.candidateSha256 },
    });
    transactionCreated = true;

    const candidateRecordRelative = journal.record.candidatePath;
    const candidateLedgerRelative = journal.ledger.candidatePath;
    const candidateReport = await verifyOperationalReadiness(repositoryRoot, {
      asOfUtc: options.asOfUtc,
      recordRelativePath: candidateRecordRelative,
      signatureLogRelativePath: candidateLedgerRelative,
      allowTransactionJournal: true,
    });
    if (!candidateReport.ok) fail(`candidate acceptance state is invalid: ${JSON.stringify(candidateReport.violations)}`);

    await writeExclusiveSynced(resolve(repositoryRoot, JOURNAL_PATH), `${JSON.stringify(journal, null, 2)}\n`);
    journalCreated = true;
    await fsyncDirectory(resolve(repositoryRoot, RELEASE_DIRECTORY));
    await ensurePacketArchive(repositoryRoot, baseline.decisionInput.value, baseline.packetInput.bytes);
    if (options.failpoint === "after-packet-install") throw new AcceptanceFailpointError(options.failpoint);

    const ledgerInstall = `${RELEASE_DIRECTORY}/.acceptance-${transactionId}-ledger-install`;
    const recordInstall = `${RELEASE_DIRECTORY}/.acceptance-${transactionId}-record-install`;
    await stageReplacement(repositoryRoot, journal.ledger.candidatePath, ledgerInstall, journal.ledger.candidateSha256);
    await installStagedFile(repositoryRoot, ledgerInstall, journal.ledger.path);
    if (options.failpoint === "after-ledger-replace") throw new AcceptanceFailpointError(options.failpoint);
    await stageReplacement(repositoryRoot, journal.record.candidatePath, recordInstall, journal.record.candidateSha256);
    await installStagedFile(repositoryRoot, recordInstall, journal.record.path);
    if (options.failpoint === "after-record-replace") throw new AcceptanceFailpointError(options.failpoint);

    await validateRecoveryState(repositoryRoot, options.asOfUtc);
    await cleanupTransaction(repositoryRoot, journal);
    return { ...validation, mode: "applied", transactionId };
  } catch (error) {
    if (error instanceof AcceptanceFailpointError) throw error;
    const journalExists = await pathExists(resolve(repositoryRoot, JOURNAL_PATH));
    if (journalCreated && journalExists) {
      try {
        await restoreOriginals(repositoryRoot, journal);
        await validateRecoveryState(repositoryRoot, options.asOfUtc);
        await cleanupTransaction(repositoryRoot, journal);
      } catch (rollbackError) {
        const applyDetail = error instanceof Error ? error.message : String(error);
        const rollbackDetail = rollbackError instanceof Error ? rollbackError.message : String(rollbackError);
        throw new Error(`acceptance apply failed (${applyDetail}) and rollback could not complete: ${rollbackDetail}`, { cause: rollbackError });
      }
    } else if (!journalCreated && !journalExists) {
      if (transactionCreated) await rm(transactionPath, { recursive: true, force: true });
      if (lockPath !== undefined) {
        await rm(lockPath, { force: true });
        await fsyncDirectory(resolve(repositoryRoot, RELEASE_DIRECTORY));
      }
    }
    throw error;
  }
}

/** Resolve one interrupted acceptance transaction from authoritative hashes only. */
export async function recoverAcceptanceTransaction(root, options) {
  if (!exactUtc(options?.asOfUtc)) fail("asOfUtc must be an exact UTC timestamp");
  const repositoryRoot = resolve(root);
  const journalPath = resolve(repositoryRoot, JOURNAL_PATH);
  const journal = validateJournal((await readRegularJsonSnapshot(journalPath, "acceptance transaction journal")).value);
  const lockPath = resolve(repositoryRoot, LOCK_PATH);
  if (await pathExists(lockPath)) {
    const owner = (await readRegularBytesSnapshot(lockPath, "acceptance update lock")).bytes.toString("utf8").trim();
    if (owner !== journal.transactionId) fail("acceptance update lock belongs to a different transaction");
  } else {
    await writeExclusiveSynced(lockPath, `${journal.transactionId}\n`);
    await fsyncDirectory(resolve(repositoryRoot, RELEASE_DIRECTORY));
  }

  const [ledgerHash, recordHash] = await Promise.all([
    sha256File(resolve(repositoryRoot, journal.ledger.path)),
    sha256File(resolve(repositoryRoot, journal.record.path)),
  ]);
  const ledgerState = ledgerHash === journal.ledger.originalSha256 ? "original"
    : ledgerHash === journal.ledger.candidateSha256 ? "candidate" : "unknown";
  const recordState = recordHash === journal.record.originalSha256 ? "original"
    : recordHash === journal.record.candidateSha256 ? "candidate" : "unknown";
  if (ledgerState === "unknown" || recordState === "unknown") {
    fail("authoritative acceptance hashes are unrecognized; manual investigation is required");
  }

  let action;
  if (ledgerState === "candidate" && recordState === "candidate") {
    action = "finalized";
  } else if (ledgerState === "original" && recordState === "original") {
    action = "cleaned-original";
  } else {
    await restoreOriginals(repositoryRoot, journal);
    action = "rolled-back";
  }
  await validateRecoveryState(repositoryRoot, options.asOfUtc);
  await cleanupTransaction(repositoryRoot, journal, options.failpoint);
  return { ok: true, action, transactionId: journal.transactionId };
}

function parseCliArguments(arguments_) {
  const options = { apply: false, recover: false, json: false };
  const valueArguments = new Map([
    ["--packet", "packetPath"],
    ["--decision", "decisionPath"],
    ["--as-of", "asOfUtc"],
  ]);
  for (let index = 0; index < arguments_.length; index += 1) {
    const argument = arguments_[index];
    if (argument === "--apply" || argument === "--recover" || argument === "--json") {
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
  if (options.asOfUtc === undefined) fail("--as-of is required");
  if (options.recover) {
    if (options.apply) fail("--apply and --recover are mutually exclusive");
    if (options.packetPath !== undefined || options.decisionPath !== undefined) fail("--recover does not accept --packet or --decision");
  } else {
    if (options.packetPath === undefined) fail("--packet is required");
    if (options.decisionPath === undefined) fail("--decision is required");
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
    const report = options.recover
      ? await recoverAcceptanceTransaction(process.cwd(), options)
      : options.apply
        ? await recordAcceptanceDecision(process.cwd(), options.packetPath, options.decisionPath, options)
        : await validateAcceptanceDecision(process.cwd(), options.packetPath, options.decisionPath, options);
    const message = options.recover
      ? `PASS acceptance transaction ${report.action}\n`
      : options.apply
        ? `PASS institutional decision applied (${report.projectedStatus})\n`
        : "PASS institutional decision validated (dry-run)\n";
    process.stdout.write(options.json ? `${JSON.stringify(report, null, 2)}\n` : message);
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
    process.exitCode = 1;
  }
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
