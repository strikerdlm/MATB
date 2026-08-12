#!/usr/bin/env node

import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { isAbsolute, relative, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";

const RECORD_PATH = "docs/release/operational-readiness-record.json";
const SHA256 = /^[a-f0-9]{64}$/u;
const EXACT_UTC = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{3}))?Z$/u;
const REQUIRED_REVIEW_SCOPES = Object.freeze([
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
const REVIEW_STATUSES = Object.freeze(["pending", "accepted", "accepted-with-conditions", "rejected"]);
const KNOWN_LIMITATION_CATEGORIES = Object.freeze([
  "aircraft-capability",
  "terrain-obstacle",
  "official-data-dependency",
  "telemetry-field",
  "profile-boundary",
  "translation-gap",
  "research-limitation",
  "human-factors",
  "cybersecurity-deployment",
  "performance-validation",
]);
const READINESS_DOCUMENT_FIELDS = Object.freeze([
  ["acceptanceChecklistPath", "acceptance checklist"],
  ["knownLimitationsPath", "known-limitations register"],
  ["verificationMatrixPath", "verification matrix"],
]);

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function readJsonLines(path) {
  const contents = await readFile(path, "utf8");
  return contents.split(/\r?\n/u).filter((line) => line.trim() !== "").map((line) => JSON.parse(line));
}

function nonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

function exactUtc(value) {
  if (typeof value !== "string") return false;
  const match = EXACT_UTC.exec(value);
  if (match === null) return false;
  const [, year, month, day, hour, minute, second, milliseconds = "000"] = match;
  const date = new Date(value);
  return Number.isFinite(date.getTime())
    && date.getUTCFullYear() === Number(year)
    && date.getUTCMonth() + 1 === Number(month)
    && date.getUTCDate() === Number(day)
    && date.getUTCHours() === Number(hour)
    && date.getUTCMinutes() === Number(minute)
    && date.getUTCSeconds() === Number(second)
    && date.getUTCMilliseconds() === Number(milliseconds);
}

function signatureRecordFailure(signature) {
  if (signature?.schemaVersion !== "1.0") return "schemaVersion must be 1.0";
  if (!nonEmptyString(signature?.signatureId)) return "signatureId is required";
  if (signature?.reviewer?.identityType !== "human") return "reviewer.identityType must be human";
  if (!nonEmptyString(signature?.reviewer?.identity)) return "reviewer identity is required";
  if (!nonEmptyString(signature?.reviewer?.organizationUnit)) return "reviewer organization/unit is required";
  if (!nonEmptyString(signature?.reviewer?.role)) return "reviewer role is required";
  if (!REQUIRED_REVIEW_SCOPES.includes(signature?.scope)) return "scope is not an approved institutional review scope";
  if (!["accept", "accept-with-conditions", "reject"].includes(signature?.decision)) return "decision is invalid";
  if (!exactUtc(signature?.signedAtUtc)) return "signedAtUtc must be an exact UTC timestamp";
  if (!Array.isArray(signature?.evidenceHashes) || signature.evidenceHashes.length === 0
    || signature.evidenceHashes.some((evidence) => !nonEmptyString(evidence?.path) || !SHA256.test(evidence?.sha256))) {
    return "at least one path and SHA-256 evidence record is required";
  }
  if (!Array.isArray(signature?.conflicts) || signature.conflicts.some((conflict) => !nonEmptyString(conflict))) {
    return "conflicts must be an array of non-empty strings";
  }
  if (!Array.isArray(signature?.conditions) || signature.conditions.some((condition) => !nonEmptyString(condition))) {
    return "conditions must be an array of non-empty strings";
  }
  if (signature.decision === "accept-with-conditions" && signature.conditions.length === 0) {
    return "accept-with-conditions requires at least one open condition";
  }
  if (signature.decision === "accept" && signature.conditions.length > 0) {
    return "unconditional acceptance cannot retain conditions";
  }
  if (!exactUtc(signature?.reviewDueAtUtc) || Date.parse(signature.reviewDueAtUtc) <= Date.parse(signature.signedAtUtc)) {
    return "reviewDueAtUtc must be an exact UTC timestamp after signedAtUtc";
  }
  return undefined;
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

function containedEvidencePath(root, value) {
  if (!nonEmptyString(value) || isAbsolute(value) || value.includes("\\") || value.includes("\0")) {
    throw new Error("evidence path must be a relative POSIX path");
  }
  if (value.split("/").some((component) => component === "" || component === "." || component === "..")) {
    throw new Error("evidence path contains traversal");
  }
  const target = resolve(root, value);
  const fromRoot = relative(root, target);
  if (fromRoot === "" || fromRoot === ".." || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot)) {
    throw new Error("evidence path escapes the repository root");
  }
  return target;
}

async function signatureEvidenceFailure(root, signature) {
  for (const evidence of signature.evidenceHashes) {
    try {
      const contents = await readFile(containedEvidencePath(root, evidence.path));
      const actual = createHash("sha256").update(contents).digest("hex");
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
    record = await readJson(resolve(repositoryRoot, RECORD_PATH));
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
      const contents = await readFile(containedEvidencePath(repositoryRoot, record[field]), "utf8");
      if (contents.trim() === "") throw new Error(`${label} is empty`);
    } catch (error) {
      violations.push({
        code: "READINESS_DOCUMENT_INVALID",
        detail: `${field}: ${error instanceof Error ? error.message : String(error)}`,
      });
    }
  }

  try {
    signatures = await readJsonLines(containedEvidencePath(repositoryRoot, record.signatureLogPath));
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
  const signatureById = new Map(signatures
    .filter((signature) => typeof signature?.signatureId === "string")
    .map((signature) => [signature.signatureId, signature]));
  for (const review of reviews) {
    if ((review?.status === "accepted" || review?.status === "accepted-with-conditions")
      && (!Array.isArray(review.signatureIds) || review.signatureIds.length === 0)) {
      violations.push({
        code: "MISSING_REVIEW_SIGNATURE",
        scope: typeof review?.scope === "string" ? review.scope : undefined,
        detail: `accepted institutional review ${String(review?.scope ?? "unknown")} has no linked signature`,
      });
    }
    for (const signatureId of Array.isArray(review?.signatureIds) ? review.signatureIds : []) {
      const signature = signatureById.get(signatureId);
      if (signature === undefined) {
        violations.push({
          code: "REVIEW_SIGNATURE_NOT_FOUND",
          scope: typeof review?.scope === "string" ? review.scope : undefined,
          detail: `institutional review ${String(review?.scope ?? "unknown")} references absent signature ${String(signatureId)}`,
        });
        continue;
      }
      const expectedDecision = review?.status === "accepted"
        ? "accept"
        : review?.status === "accepted-with-conditions"
          ? "accept-with-conditions"
          : review?.status === "rejected"
            ? "reject"
            : undefined;
      if (signature.scope !== review?.scope || (expectedDecision !== undefined && signature.decision !== expectedDecision)) {
        violations.push({
          code: "REVIEW_SIGNATURE_DECISION_INVALID",
          scope: typeof review?.scope === "string" ? review.scope : undefined,
          detail: `${String(signatureId)} does not attest the recorded scope and decision`,
        });
      }
    }
  }
  const pendingReviewScopes = reviews
    .filter((review) => review?.status === "pending")
    .map((review) => review.scope)
    .filter((scope) => typeof scope === "string")
    .sort();
  const blockers = pendingReviewScopes.map((scope) => ({
    code: "INSTITUTIONAL_REVIEW_PENDING",
    scope,
    detail: `qualified human acceptance is not recorded for ${scope}`,
  }));
  const rejectedReviewScopes = reviews
    .filter((review) => review?.status === "rejected")
    .map((review) => review.scope)
    .filter((scope) => typeof scope === "string")
    .sort();
  blockers.push(...rejectedReviewScopes.map((scope) => ({
    code: "INSTITUTIONAL_REVIEW_REJECTED",
    scope,
    detail: `qualified human review rejected ${scope}`,
  })));
  const conditionalReviewScopes = reviews
    .filter((review) => review?.status === "accepted-with-conditions")
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
