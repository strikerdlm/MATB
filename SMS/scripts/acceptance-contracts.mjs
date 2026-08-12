import { createHash } from "node:crypto";
import { lstat, open, readFile, realpath } from "node:fs/promises";
import { isAbsolute, relative, resolve, sep } from "node:path";

const EXACT_UTC = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{3}))?Z$/u;

export const REQUIRED_REVIEW_SCOPES = Object.freeze([
  "cybersecurity-deployment", "emergency-response", "human-factors-protocol",
  "official-geospatial-data", "operational-checklist", "racae-interpretation-translation",
  "research-separation", "risk-authority", "training-safety-promotion",
]);
export const REVIEW_STATUSES = Object.freeze(["pending", "accepted", "accepted-with-conditions", "rejected"]);
export const KNOWN_LIMITATION_CATEGORIES = Object.freeze([
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
export const ACCEPTANCE_EVIDENCE_PATHS = Object.freeze([
  "docs/release/known-limitations.md",
  "docs/release/release-manifest.json",
  "docs/release/release-manifest.sig",
  "docs/release/release-public-key.pem",
  "docs/release/sbom.cdx.json",
  "docs/release/security-scan.json",
  "docs/release/state-aviation-acceptance-checklist.md",
  "docs/release/test-report.json",
  "docs/release/verification-matrix.md",
]);
export const ACCEPTANCE_STATE_PATHS = Object.freeze([
  "docs/release/operational-readiness-record.json",
  "docs/release/verification-signatures.jsonl",
  "docs/release/state-aviation-acceptance-checklist.md",
  "docs/release/known-limitations.md",
  "docs/release/verification-matrix.md",
  "docs/release/release-manifest.json",
]);
const SHA256 = /^[a-f0-9]{64}$/u;
const ACCEPTANCE_DECISIONS = new Set(["accept", "accept-with-conditions", "reject"]);
const ACCEPTANCE_ARTIFACT_DIRECTORY = "docs/release/acceptance-artifacts/";

export function isControlledAcceptanceArtifactPath(candidate) {
  if (!nonEmptyString(candidate) || !candidate.startsWith(ACCEPTANCE_ARTIFACT_DIRECTORY)
    || candidate.includes("\\") || candidate.includes("\0")) return false;
  const descendants = candidate.slice(ACCEPTANCE_ARTIFACT_DIRECTORY.length).split("/");
  return descendants.length > 0 && descendants.every((component) => component !== "" && component !== "." && component !== "..");
}

/** Return the schema error for an institutional decision, if any. */
export function signatureRecordFailure(decision) {
  if (decision?.schemaVersion !== "1.0") return "schemaVersion must be 1.0";
  if (decision?.recordType !== "institutional-decision") return "recordType must be institutional-decision";
  if (!nonEmptyString(decision?.signatureId)) return "signatureId is required";
  if (!nonEmptyString(decision?.sourcePacketId) || !SHA256.test(decision.sourcePacketId)) return "sourcePacketId must be a SHA-256 identifier";
  if (decision?.sourcePacketPath !== `docs/release/acceptance-packets/${decision.sourcePacketId}.json`) return "sourcePacketPath must identify the source packet";
  if (!SHA256.test(decision?.sourcePacketSha256)) return "sourcePacketSha256 must be a SHA-256 hash";
  if (decision?.supersedesSignatureId !== null && !nonEmptyString(decision?.supersedesSignatureId)) return "supersedesSignatureId must be a signature identifier or null";
  if (!nonEmptyString(decision?.releaseId)) return "releaseId is required";
  if (decision?.reviewer?.identityType !== "human") return "reviewer.identityType must be human";
  if (!nonEmptyString(decision?.reviewer?.identity)) return "reviewer identity is required";
  if (!nonEmptyString(decision?.reviewer?.organizationUnit)) return "reviewer organization/unit is required";
  if (!nonEmptyString(decision?.reviewer?.role)) return "reviewer role is required";
  if (!REQUIRED_REVIEW_SCOPES.includes(decision?.scope)) return "scope is not an approved institutional review scope";
  if (!ACCEPTANCE_DECISIONS.has(decision?.decision)) return "decision is invalid";
  if (!exactUtc(decision?.signedAtUtc)) return "signedAtUtc must be an exact UTC timestamp";
  if (!Array.isArray(decision?.evidenceHashes) || decision.evidenceHashes.length === 0
    || decision.evidenceHashes.some((evidence) => !nonEmptyString(evidence?.path) || !SHA256.test(evidence?.sha256))) {
    return "at least one path and SHA-256 evidence record is required";
  }
  if (!Array.isArray(decision?.conflicts) || decision.conflicts.some((conflict) => !nonEmptyString(conflict))) return "conflicts must be an array of non-empty strings";
  if (!Array.isArray(decision?.conditions) || decision.conditions.some((condition) => !nonEmptyString(condition))) return "conditions must be an array of non-empty strings";
  if (decision.decision === "accept-with-conditions" && decision.conditions.length === 0) return "accept-with-conditions requires at least one open condition";
  if (decision.decision === "accept" && decision.conditions.length > 0) return "unconditional acceptance cannot retain conditions";
  if (!exactUtc(decision?.reviewDueAtUtc) || Date.parse(decision.reviewDueAtUtc) <= Date.parse(decision.signedAtUtc)) return "reviewDueAtUtc must be an exact UTC timestamp after signedAtUtc";
  if (!nonEmptyString(decision?.systemOfRecordRef)) return "systemOfRecordRef is required";
  if (!isControlledAcceptanceArtifactPath(decision?.institutionalArtifact?.path)
    || !SHA256.test(decision?.institutionalArtifact?.sha256)) {
    return "institutionalArtifact must be a hash-locked acceptance artifact";
  }
  return undefined;
}

/** Derive a review's current state from its append-only, role-specific decision chains. */
export function deriveReviewDecisionState(review, decisions) {
  const scope = typeof review?.scope === "string" ? review.scope : "unknown";
  const violations = [];
  const requiredRoles = Array.isArray(review?.requiredReviewerRoles) ? review.requiredReviewerRoles : [];
  const signatureIds = Array.isArray(review?.signatureIds) ? review.signatureIds : [];
  if (!requiredRoles.every(nonEmptyString) || new Set(requiredRoles).size !== requiredRoles.length) {
    violations.push({ code: "REVIEW_ROLE_INVALID", scope, detail: "requiredReviewerRoles must contain unique non-empty roles" });
  }
  if (!signatureIds.every(nonEmptyString) || new Set(signatureIds).size !== signatureIds.length) {
    violations.push({ code: "REVIEW_SIGNATURE_IDS_INVALID", scope, detail: "signatureIds must contain unique non-empty identifiers" });
  }
  const decisionList = Array.isArray(decisions) ? decisions : [];
  const byId = new Map();
  for (const decision of decisionList) {
    if (typeof decision?.signatureId === "string" && !byId.has(decision.signatureId)) byId.set(decision.signatureId, decision);
  }
  const linked = [];
  for (const signatureId of signatureIds) {
    const decision = byId.get(signatureId);
    if (decision === undefined) {
      violations.push({ code: "REVIEW_SIGNATURE_NOT_FOUND", scope, detail: `institutional review ${scope} references absent signature ${signatureId}` });
    } else {
      linked.push(decision);
    }
  }
  for (const decision of decisionList) {
    if (decision?.scope === scope && !signatureIds.includes(decision?.signatureId)) {
      violations.push({ code: "SIGNATURE_UNLINKED", scope, detail: `institutional decision ${String(decision?.signatureId ?? "unknown")} is not linked from ${scope}` });
    }
  }
  for (const decision of linked) {
    const failure = signatureRecordFailure(decision);
    if (failure !== undefined) violations.push({ code: "SIGNATURE_RECORD_INVALID", scope, detail: `${String(decision?.signatureId ?? "unknown")}: ${failure}` });
    if (decision?.scope !== scope) violations.push({ code: "DECISION_CHAIN_SCOPE_MISMATCH", scope, detail: `${String(decision?.signatureId ?? "unknown")} does not attest ${scope}` });
    if (!requiredRoles.includes(decision?.reviewer?.role)) violations.push({ code: "REVIEW_ROLE_UNKNOWN", scope, detail: `${String(decision?.signatureId ?? "unknown")} has a reviewer role not required for ${scope}` });
  }
  const linkedIds = new Set(linked.map((decision) => decision.signatureId));
  const children = new Map();
  for (const decision of linked) {
    const parentId = decision?.supersedesSignatureId;
    if (parentId === null) continue;
    const parent = byId.get(parentId);
    if (parent === undefined) {
      violations.push({ code: "DECISION_CHAIN_PARENT_MISSING", scope, detail: `${decision.signatureId} supersedes absent decision ${parentId}` });
      continue;
    }
    if (!linkedIds.has(parentId)) violations.push({ code: "DECISION_CHAIN_PARENT_UNLINKED", scope, detail: `${decision.signatureId} supersedes an unlinked decision ${parentId}` });
    if (parent.scope !== decision.scope) violations.push({ code: "DECISION_CHAIN_SCOPE_MISMATCH", scope, detail: `${decision.signatureId} supersedes a decision from ${String(parent.scope)}` });
    if (parent?.reviewer?.role !== decision?.reviewer?.role) violations.push({ code: "DECISION_CHAIN_ROLE_MISMATCH", scope, detail: `${decision.signatureId} supersedes a decision from another reviewer role` });
    if (exactUtc(parent?.signedAtUtc) && exactUtc(decision?.signedAtUtc) && Date.parse(decision.signedAtUtc) <= Date.parse(parent.signedAtUtc)) {
      violations.push({ code: "DECISION_CHAIN_TIME_INVALID", scope, detail: `${decision.signatureId} must be signed after ${parentId}` });
    }
    const followers = children.get(parentId) ?? [];
    followers.push(decision);
    children.set(parentId, followers);
  }
  for (const [parentId, followers] of children) {
    if (followers.length > 1) violations.push({ code: "DECISION_CHAIN_FORK", scope, detail: `${parentId} has ${followers.length} superseding decisions` });
  }
  const visiting = new Set();
  const visited = new Set();
  const hasCycle = (id) => {
    if (visiting.has(id)) return true;
    if (visited.has(id)) return false;
    visiting.add(id);
    const parentId = byId.get(id)?.supersedesSignatureId;
    const cycle = typeof parentId === "string" && linkedIds.has(parentId) && hasCycle(parentId);
    visiting.delete(id);
    visited.add(id);
    return cycle;
  };
  for (const decision of linked) {
    if (hasCycle(decision.signatureId)) {
      violations.push({ code: "DECISION_CHAIN_CYCLE", scope, detail: `decision chain for ${decision.signatureId} contains a cycle` });
      break;
    }
  }
  const roleHeads = [];
  for (const role of requiredRoles) {
    const roleDecisions = linked.filter((decision) => decision?.scope === scope && decision?.reviewer?.role === role);
    if (roleDecisions.length === 0) continue;
    const roots = roleDecisions.filter((decision) => decision.supersedesSignatureId === null);
    const heads = roleDecisions.filter((decision) => !(children.get(decision.signatureId) ?? [])
      .some((child) => child?.scope === scope && child?.reviewer?.role === role));
    if (roots.length !== 1) {
      violations.push({
        code: roots.length > 1 ? "DECISION_CHAIN_FORK" : "DECISION_CHAIN_ROOT_INVALID",
        scope,
        detail: `${role} must have exactly one root decision`,
      });
      continue;
    }
    if (heads.length !== 1) {
      violations.push({ code: "DECISION_CHAIN_HEAD_INVALID", scope, detail: `${role} must have exactly one current decision head` });
      continue;
    }
    const connected = new Set();
    const pending = [roots[0]];
    while (pending.length > 0) {
      const current = pending.pop();
      if (current === undefined || connected.has(current.signatureId)) continue;
      connected.add(current.signatureId);
      pending.push(...(children.get(current.signatureId) ?? []).filter((child) => child?.scope === scope && child?.reviewer?.role === role));
    }
    if (connected.size !== roleDecisions.length) {
      violations.push({ code: "DECISION_CHAIN_DISCONNECTED", scope, detail: `${role} has decisions disconnected from its root` });
      continue;
    }
    roleHeads.push({ role, signatureId: heads[0].signatureId, decision: heads[0].decision });
  }
  const missingRoles = requiredRoles.filter((role) => !roleHeads.some((head) => head.role === role));
  const headDecisions = roleHeads.map(({ decision }) => decision);
  const status = headDecisions.includes("reject")
    ? "rejected"
    : missingRoles.length > 0
      ? "pending"
      : headDecisions.includes("accept-with-conditions")
        ? "accepted-with-conditions"
        : "accepted";
  if (REVIEW_STATUSES.includes(review?.status) && review.status !== status) {
    violations.push({ code: "REVIEW_STATUS_DERIVATION_MISMATCH", scope, detail: `recorded status ${review.status} does not match derived status ${status}` });
  }
  return { status, missingRoles, roleHeads, violations };
}

export function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function sha256Bytes(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

export async function sha256File(path) {
  const handle = await open(path, "r");
  const hash = createHash("sha256");
  try {
    for await (const chunk of handle.createReadStream({ autoClose: false })) hash.update(chunk);
    return hash.digest("hex");
  } finally {
    await handle.close();
  }
}

export function nonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

export function exactUtc(value) {
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

export async function readJsonLines(path) {
  const contents = await readFile(path, "utf8");
  return contents.split(/\r?\n/u).flatMap((line, index) => {
    if (line.trim() === "") return [];
    try {
      return [JSON.parse(line)];
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      throw new Error(`JSON line ${index + 1} is invalid: ${detail}`, { cause: error });
    }
  });
}

export async function resolveContainedExistingFile(root, candidate, label = "file") {
  if (!nonEmptyString(candidate) || isAbsolute(candidate) || candidate.includes("\\") || candidate.includes("\0")) {
    throw new Error(`${label} path must be a relative POSIX path`);
  }
  const components = candidate.split("/");
  if (components.some((component) => component === "" || component === "." || component === "..")) {
    throw new Error(`${label} path contains traversal`);
  }

  const repositoryRoot = resolve(root);
  const target = resolve(repositoryRoot, candidate);
  const fromRoot = relative(repositoryRoot, target);
  if (fromRoot === "" || fromRoot === ".." || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot)) {
    throw new Error(`${label} path escapes the repository root`);
  }

  let current = repositoryRoot;
  for (const component of components) {
    current = resolve(current, component);
    const stat = await lstat(current);
    if (stat.isSymbolicLink()) throw new Error(`${label} path contains a symbolic link`);
  }
  const targetStat = await lstat(target);
  if (!targetStat.isFile()) throw new Error(`${label} path must reference a regular file`);

  const [realRoot, realTarget] = await Promise.all([realpath(repositoryRoot), realpath(target)]);
  const fromRealRoot = relative(realRoot, realTarget);
  if (fromRealRoot === "" || fromRealRoot === ".." || fromRealRoot.startsWith(`..${sep}`) || isAbsolute(fromRealRoot)) {
    throw new Error(`${label} path escapes the repository root`);
  }
  return target;
}
