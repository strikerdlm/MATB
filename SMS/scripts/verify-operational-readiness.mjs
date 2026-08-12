#!/usr/bin/env node

import { lstat, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import {
  KNOWN_LIMITATION_CATEGORIES,
  REQUIRED_REVIEW_SCOPES,
  REVIEW_STATUSES,
  exactUtc,
  nonEmptyString,
  readJsonLines,
  resolveContainedExistingFile,
  sha256File,
  signatureRecordFailure,
  deriveReviewDecisionState,
  isControlledAcceptanceArtifactPath,
} from "./acceptance-contracts.mjs";

export { signatureRecordFailure, deriveReviewDecisionState } from "./acceptance-contracts.mjs";

const RECORD_PATH = "docs/release/operational-readiness-record.json";
const READINESS_DOCUMENT_FIELDS = Object.freeze([
  ["acceptanceChecklistPath", "acceptance checklist"],
  ["knownLimitationsPath", "known-limitations register"],
  ["verificationMatrixPath", "verification matrix"],
]);

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

function knownLimitationFailure(limitation) {
  if (!nonEmptyString(limitation?.id)) return "id is required";
  if (!KNOWN_LIMITATION_CATEGORIES.includes(limitation?.category)) return "category is invalid";
  if (!["open", "closed"].includes(limitation?.status)) return "status must be open or closed";
  if (typeof limitation?.releaseBlocking !== "boolean") return "releaseBlocking must be boolean";
  if (!nonEmptyString(limitation?.summary)) return "summary is required";
  if (!nonEmptyString(limitation?.degradedDataProcedure)) return "degradedDataProcedure is required";
  if (!nonEmptyString(limitation?.requiredHumanAction)) return "requiredHumanAction is required";
  return undefined;
}

async function signatureEvidenceFailure(root, signature) {
  try {
    const artifactPath = await resolveContainedExistingFile(root, signature.institutionalArtifact.path, "institutional artifact");
    if (!isControlledAcceptanceArtifactPath(signature.institutionalArtifact.path)) {
      return "institutional artifact must be below docs/release/acceptance-artifacts/";
    }
    const artifact = JSON.parse(await readFile(artifactPath, "utf8"));
    if (artifact?.schemaVersion !== "1.0"
      || artifact?.recordType !== "institutional-acceptance-artifact"
      || artifact?.classification !== "unclassified-controlled"
      || artifact?.contentType !== "controlled-safety-metadata") {
      return "institutional artifact must contain unclassified controlled safety metadata";
    }
  } catch (error) {
    return error instanceof Error ? error.message : String(error);
  }
  const evidenceRecords = [
    ...signature.evidenceHashes,
    { path: signature.sourcePacketPath, sha256: signature.sourcePacketSha256 },
    signature.institutionalArtifact,
  ];
  for (const evidence of evidenceRecords) {
    try {
      const evidencePath = await resolveContainedExistingFile(root, evidence.path, "evidence");
      const actual = await sha256File(evidencePath);
      if (actual !== evidence.sha256) return `${evidence.path} SHA-256 does not match`;
    } catch (error) {
      return error instanceof Error ? error.message : String(error);
    }
  }
  return undefined;
}

/** Verify that the release record describes institutional readiness truthfully. */
export async function verifyOperationalReadiness(root = process.cwd(), options = {}) {
  const repositoryRoot = resolve(root);
  const violations = [];
  const asOfUtc = options.asOfUtc ?? new Date().toISOString();
  let record;
  let signatures = [];

  try {
    record = await readJson(await resolveContainedExistingFile(
      repositoryRoot,
      options.recordRelativePath ?? RECORD_PATH,
      "readiness record",
    ));
  } catch (error) {
    return {
      ok: false,
      operationalReady: false,
      qualification: "blocked",
      verifiedAtUtc: asOfUtc,
      signatureCount: 0,
      pendingReviewScopes: [],
      blockers: [{ code: "READINESS_RECORD_INVALID", detail: error instanceof Error ? error.message : String(error) }],
      violations: [{ code: "READINESS_RECORD_INVALID", detail: error instanceof Error ? error.message : String(error) }],
    };
  }

  if (options.allowTransactionJournal !== true) {
    try {
      await lstat(resolve(repositoryRoot, "docs/release/.acceptance-transaction.json"));
      violations.push({
        code: "ACCEPTANCE_TRANSACTION_ACTIVE",
        detail: "an active acceptance transaction journal must be resolved before readiness verification",
      });
    } catch (error) {
      if (error?.code !== "ENOENT") {
        violations.push({
          code: "ACCEPTANCE_TRANSACTION_ACTIVE",
          detail: `cannot verify acceptance transaction journal: ${error instanceof Error ? error.message : String(error)}`,
        });
      }
    }
  }

  if (record.schemaVersion !== "1.0") violations.push({ code: "READINESS_SCHEMA_INVALID", detail: "schemaVersion must be 1.0" });
  if (!exactUtc(asOfUtc)) violations.push({ code: "VERIFICATION_TIME_INVALID", detail: "asOfUtc must be an exact UTC timestamp" });
  if (typeof record.operationalReady !== "boolean") violations.push({ code: "READINESS_STATE_INVALID", detail: "operationalReady must be boolean" });
  if (!Array.isArray(record.requiredReviews)) violations.push({ code: "REQUIRED_REVIEWS_INVALID", detail: "requiredReviews must be an array" });
  if (!Array.isArray(record.knownLimitations)) violations.push({ code: "KNOWN_LIMITATIONS_INVALID", detail: "knownLimitations must be an array" });
  const knownLimitations = Array.isArray(record.knownLimitations) ? record.knownLimitations : [];
  const limitationIdCounts = new Map();
  for (const limitation of knownLimitations) {
    if (typeof limitation?.id === "string") {
      limitationIdCounts.set(limitation.id, (limitationIdCounts.get(limitation.id) ?? 0) + 1);
    }
    const failure = knownLimitationFailure(limitation);
    if (failure !== undefined) {
      violations.push({
        code: "KNOWN_LIMITATION_INVALID",
        limitationId: typeof limitation?.id === "string" ? limitation.id : undefined,
        detail: `${String(limitation?.id ?? "unknown")}: ${failure}`,
      });
    }
  }
  for (const [limitationId, count] of limitationIdCounts) {
    if (count > 1) {
      violations.push({
        code: "KNOWN_LIMITATION_ID_DUPLICATE",
        limitationId,
        detail: `known limitation identifier ${limitationId} occurs ${count} times`,
      });
    }
  }
  for (const [field, label] of READINESS_DOCUMENT_FIELDS) {
    try {
      const contents = await readFile(await resolveContainedExistingFile(repositoryRoot, record[field], "evidence"), "utf8");
      if (contents.trim() === "") throw new Error(`${label} is empty`);
    } catch (error) {
      violations.push({
        code: "READINESS_DOCUMENT_INVALID",
        detail: `${field}: ${error instanceof Error ? error.message : String(error)}`,
      });
    }
  }

  try {
    signatures = await readJsonLines(await resolveContainedExistingFile(
      repositoryRoot,
      options.signatureLogRelativePath ?? record.signatureLogPath,
      "evidence",
    ));
  } catch (error) {
    violations.push({ code: "SIGNATURE_LOG_INVALID", detail: error instanceof Error ? error.message : String(error) });
  }

  for (const signature of signatures) {
    if (signature?.reviewer?.identityType === "automation") {
      violations.push({
        code: "AUTOMATED_ACCEPTANCE_FORBIDDEN",
        detail: `institutional acceptance signature ${String(signature?.signatureId ?? "unknown")} must identify a human reviewer`,
      });
      continue;
    }
    const failure = signatureRecordFailure(signature);
    if (failure !== undefined) {
      violations.push({
        code: "SIGNATURE_RECORD_INVALID",
        scope: typeof signature?.scope === "string" ? signature.scope : undefined,
        detail: `${String(signature?.signatureId ?? "unknown")}: ${failure}`,
      });
      continue;
    }
    const evidenceFailure = await signatureEvidenceFailure(repositoryRoot, signature);
    if (evidenceFailure !== undefined) {
      violations.push({
        code: "SIGNATURE_EVIDENCE_INVALID",
        scope: signature.scope,
        detail: `${signature.signatureId}: ${evidenceFailure}`,
      });
    }
    if (exactUtc(asOfUtc) && Date.parse(signature.signedAtUtc) > Date.parse(asOfUtc)) {
      violations.push({
        code: "SIGNATURE_TIME_INVALID",
        scope: signature.scope,
        detail: `${signature.signatureId}: signing time ${signature.signedAtUtc} is after ${asOfUtc}`,
      });
    }
    if (exactUtc(asOfUtc) && Date.parse(signature.reviewDueAtUtc) <= Date.parse(asOfUtc)) {
      violations.push({
        code: "SIGNATURE_REVIEW_EXPIRED",
        scope: signature.scope,
        detail: `${signature.signatureId}: review date ${signature.reviewDueAtUtc} is not after ${asOfUtc}`,
      });
    }
  }

  const reviews = Array.isArray(record.requiredReviews) ? record.requiredReviews : [];
  const reviewScopes = new Set(reviews.map((review) => review?.scope).filter((scope) => typeof scope === "string"));
  const reviewScopeCounts = new Map();
  for (const review of reviews) {
    if (typeof review?.scope !== "string") continue;
    reviewScopeCounts.set(review.scope, (reviewScopeCounts.get(review.scope) ?? 0) + 1);
    if (!REVIEW_STATUSES.includes(review.status)) {
      violations.push({
        code: "REVIEW_STATUS_INVALID",
        scope: review.scope,
        detail: `institutional review ${review.scope} has invalid status ${String(review.status)}`,
      });
    }
  }
  for (const [scope, count] of reviewScopeCounts) {
    if (count > 1) {
      violations.push({
        code: "REQUIRED_REVIEW_SCOPE_DUPLICATE",
        scope,
        detail: `institutional review scope ${scope} occurs ${count} times`,
      });
    }
  }
  for (const scope of REQUIRED_REVIEW_SCOPES) {
    if (!reviewScopes.has(scope)) {
      violations.push({
        code: "REQUIRED_REVIEW_SCOPE_MISSING",
        scope,
        detail: `required institutional review scope ${scope} is absent`,
      });
    }
  }
  const signatureIdCounts = new Map();
  for (const signature of signatures) {
    if (typeof signature?.signatureId !== "string") continue;
    signatureIdCounts.set(signature.signatureId, (signatureIdCounts.get(signature.signatureId) ?? 0) + 1);
  }
  for (const [signatureId, count] of signatureIdCounts) {
    if (count > 1) {
      violations.push({
        code: "SIGNATURE_ID_DUPLICATE",
        detail: `institutional signature identifier ${signatureId} occurs ${count} times`,
      });
    }
  }
  const reviewSignatureReferenceCounts = new Map();
  const matchingReviewSignatureReferenceCounts = new Map();
  for (const review of reviews) {
    for (const signatureId of Array.isArray(review?.signatureIds) ? review.signatureIds : []) {
      reviewSignatureReferenceCounts.set(signatureId, (reviewSignatureReferenceCounts.get(signatureId) ?? 0) + 1);
      const signature = signatures.find((candidate) => candidate?.signatureId === signatureId);
      if (signature?.scope === review?.scope) {
        matchingReviewSignatureReferenceCounts.set(signatureId, (matchingReviewSignatureReferenceCounts.get(signatureId) ?? 0) + 1);
      }
    }
  }
  for (const signature of signatures) {
    if (typeof signature?.signatureId !== "string") continue;
    const references = reviewSignatureReferenceCounts.get(signature.signatureId) ?? 0;
    const matchingReferences = matchingReviewSignatureReferenceCounts.get(signature.signatureId) ?? 0;
    if (references !== 1 || matchingReferences !== 1) {
      violations.push({
        code: "SIGNATURE_UNLINKED",
        scope: typeof signature?.scope === "string" ? signature.scope : undefined,
        detail: `institutional decision ${signature.signatureId} must appear exactly once in its matching review`,
      });
    }
  }
  const reviewStates = new Map();
  const roleMissingFindings = [];
  for (const review of reviews) {
    if ((review?.status === "accepted" || review?.status === "accepted-with-conditions")
      && (!Array.isArray(review.signatureIds) || review.signatureIds.length === 0)) {
      violations.push({
        code: "MISSING_REVIEW_SIGNATURE",
        scope: typeof review?.scope === "string" ? review.scope : undefined,
        detail: `accepted institutional review ${String(review?.scope ?? "unknown")} has no linked signature`,
      });
    }
    const state = deriveReviewDecisionState(review, signatures);
    if (typeof review?.scope === "string") reviewStates.set(review.scope, state);
    violations.push(...state.violations);
    for (const role of state.missingRoles) {
      roleMissingFindings.push({
        code: "REVIEW_ROLE_MISSING",
        scope: typeof review?.scope === "string" ? review.scope : undefined,
        detail: `institutional review ${String(review?.scope ?? "unknown")} lacks a current decision from ${role}`,
      });
    }
  }
  const pendingReviewScopes = reviews
    .filter((review) => reviewStates.get(review?.scope)?.status === "pending")
    .map((review) => review.scope)
    .filter((scope) => typeof scope === "string")
    .sort();
  const blockers = [
    ...roleMissingFindings,
    ...pendingReviewScopes.map((scope) => ({
    code: "INSTITUTIONAL_REVIEW_PENDING",
    scope,
    detail: `qualified human acceptance is not recorded for ${scope}`,
    })),
  ];
  const rejectedReviewScopes = reviews
    .filter((review) => reviewStates.get(review?.scope)?.status === "rejected")
    .map((review) => review.scope)
    .filter((scope) => typeof scope === "string")
    .sort();
  blockers.push(...rejectedReviewScopes.map((scope) => ({
    code: "INSTITUTIONAL_REVIEW_REJECTED",
    scope,
    detail: `qualified human review rejected ${scope}`,
  })));
  const conditionalReviewScopes = reviews
    .filter((review) => reviewStates.get(review?.scope)?.status === "accepted-with-conditions")
    .map((review) => review.scope)
    .filter((scope) => typeof scope === "string")
    .sort();
  blockers.push(...conditionalReviewScopes.map((scope) => ({
    code: "ACCEPTANCE_CONDITION_OPEN",
    scope,
    detail: `acceptance conditions remain open for ${scope}`,
  })));
  const openReleaseLimitations = knownLimitations
    .filter((limitation) => limitation?.status === "open" && limitation?.releaseBlocking === true);
  blockers.push(...openReleaseLimitations.map((limitation) => ({
    code: "KNOWN_LIMITATION_OPEN",
    limitationId: limitation.id,
    detail: `release-blocking limitation ${String(limitation.id ?? "unknown")} remains open`,
  })));

  if (record.operationalReady === true
    && (pendingReviewScopes.length > 0 || rejectedReviewScopes.length > 0
      || conditionalReviewScopes.length > 0 || openReleaseLimitations.length > 0)) {
    violations.push({
      code: "READINESS_OVERCLAIMED",
      detail: "operationalReady cannot be true while an institutional review or release-blocking limitation remains unresolved",
    });
  }

  const operationalReady = violations.length === 0
    && record.operationalReady === true
    && pendingReviewScopes.length === 0
    && rejectedReviewScopes.length === 0
    && conditionalReviewScopes.length === 0
    && openReleaseLimitations.length === 0;

  return {
    ok: violations.length === 0,
    operationalReady,
    qualification: operationalReady ? "accepted" : "blocked",
    verifiedAtUtc: asOfUtc,
    signatureCount: signatures.length,
    pendingReviewScopes,
    blockers: [...blockers, ...violations],
    violations,
  };
}

async function main() {
  const asOfIndex = process.argv.indexOf("--as-of");
  const report = await verifyOperationalReadiness(process.cwd(), {
    asOfUtc: asOfIndex === -1 ? undefined : process.argv[asOfIndex + 1],
  });
  const json = process.argv.includes("--json");
  const requireReady = process.argv.includes("--require-ready");
  if (json) process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  else process.stdout.write(`${report.ok ? "PASS" : "FAIL"} acceptance evidence (${report.pendingReviewScopes.length} pending reviews; operationalReady=${String(report.operationalReady)})\n`);
  if (!report.ok || (requireReady && !report.operationalReady)) process.exitCode = 1;
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
