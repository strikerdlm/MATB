import {
  createExceptionResult,
  createFreshnessResult,
  createRiskEvaluation,
  type ControlledExceptionInput,
  type DataSnapshotRef,
  type ExceptionResult,
  type FreshnessResult,
  type PolicyPackage,
  type RiskEvaluation,
  type RiskEvaluationInput,
} from "./types.js";

const UTC_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/;
const MANIFEST_UTC_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{3})?Z$/;
const PACKAGE_ID_PATTERN = /^[a-z0-9][a-z0-9._-]{2,127}$/;
const VERSION_PATTERN = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const SHA256_PATTERN = /^[a-f0-9]{64}$/;
const SIGNATURE_PATTERN = /^[A-Za-z0-9+/]+={0,2}$/;

function compareStable(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function nonBlankString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function parseUtc(value: string): number {
  const timestamp = utcTimestamp(value);
  if (timestamp === undefined) throw new RangeError("timestamp must be a valid UTC ISO-8601 instant");
  return timestamp;
}

function utcTimestamp(value: unknown): number | undefined {
  if (typeof value !== "string") return undefined;
  const match = UTC_PATTERN.exec(value);
  if (!match) return undefined;
  const [, year, month, day, hour, minute, second, fraction = ""] = match;
  const timestamp = Date.parse(value);
  const date = new Date(timestamp);
  if (!Number.isFinite(timestamp)
    || date.getUTCFullYear() !== Number(year)
    || date.getUTCMonth() + 1 !== Number(month)
    || date.getUTCDate() !== Number(day)
    || date.getUTCHours() !== Number(hour)
    || date.getUTCMinutes() !== Number(minute)
    || date.getUTCSeconds() !== Number(second)
    || date.getUTCMilliseconds() !== Number(fraction.padEnd(3, "0") || 0)) {
    return undefined;
  }
  return timestamp;
}

function approvedPolicy(policy: PolicyPackage | undefined): policy is PolicyPackage {
  return isRecord(policy) && policy.status === "approved" && typeof policy.signature === "string" && policy.signature.trim().length > 0;
}

function manifestTimestamp(value: unknown): number | undefined {
  return typeof value === "string" && MANIFEST_UTC_PATTERN.test(value) ? utcTimestamp(value) : undefined;
}

function validManifestDependency(value: unknown): boolean {
  return isRecord(value)
    && typeof value.packageId === "string" && PACKAGE_ID_PATTERN.test(value.packageId)
    && typeof value.version === "string" && VERSION_PATTERN.test(value.version)
    && typeof value.contentSha256 === "string" && SHA256_PATTERN.test(value.contentSha256);
}

function validManifestFile(value: unknown): boolean {
  return isRecord(value)
    && nonBlankString(value.path) && !value.path.startsWith("/") && !value.path.includes("\\")
    && value.path.split("/").every((part) => part !== "" && part !== "." && part !== "..")
    && typeof value.sha256 === "string" && SHA256_PATTERN.test(value.sha256)
    && typeof value.sizeBytes === "number" && Number.isSafeInteger(value.sizeBytes) && value.sizeBytes >= 0;
}

/** Validates policy-manifest shape and its effective window without I/O or signature verification. */
function validApprovedManifestAt(manifest: unknown, now: number): boolean {
  if (!isRecord(manifest)
    || manifest.schemaVersion !== "1.0"
    || typeof manifest.packageId !== "string" || !PACKAGE_ID_PATTERN.test(manifest.packageId)
    || manifest.kind !== "policy"
    || !nonBlankString(manifest.issuer)
    || typeof manifest.version !== "string" || !VERSION_PATTERN.test(manifest.version)
    || !nonBlankString(manifest.geographicScope)
    || typeof manifest.contentSha256 !== "string" || !SHA256_PATTERN.test(manifest.contentSha256)
    || typeof manifest.signature !== "string" || !SIGNATURE_PATTERN.test(manifest.signature)
    || !nonBlankString(manifest.keyId)
    || !Array.isArray(manifest.dependencies) || !manifest.dependencies.every(validManifestDependency)
    || !Array.isArray(manifest.files) || manifest.files.length === 0 || !manifest.files.every(validManifestFile)
    || manifest.qualification !== "approved"
    || !Array.isArray(manifest.caveats) || !manifest.caveats.every(nonBlankString)) return false;
  const issuedAt = manifestTimestamp(manifest.issuedAtUtc);
  const effectiveFrom = manifestTimestamp(manifest.effectiveFromUtc);
  if (issuedAt === undefined || effectiveFrom === undefined || issuedAt > effectiveFrom || effectiveFrom > now) return false;
  if (manifest.expiresAtUtc === undefined) return true;
  const expiresAt = manifestTimestamp(manifest.expiresAtUtc);
  return expiresAt !== undefined && expiresAt > effectiveFrom && expiresAt > now;
}

function policyCurrentAt(policy: PolicyPackage | undefined, now: number): policy is PolicyPackage {
  if (!approvedPolicy(policy)) return false;
  if (policy.manifest === undefined) return true;
  return validApprovedManifestAt(policy.manifest, now);
}

function validMatrix(policy: PolicyPackage): boolean {
  const matrix = policy.riskMatrix;
  return isRecord(matrix)
    && Number.isInteger(matrix.probabilityLevels) && matrix.probabilityLevels > 0
    && Number.isInteger(matrix.severityLevels) && matrix.severityLevels > 0
    && Array.isArray(matrix.cells)
    && matrix.cells.length === matrix.probabilityLevels * matrix.severityLevels
    && matrix.cells.every((cell) => typeof cell === "string" && cell.trim().length > 0);
}

function matrixBand(input: RiskEvaluationInput, policy: PolicyPackage): string | undefined {
  const matrix = policy.riskMatrix;
  if (!matrix || input.severity === undefined) return undefined;
  if (!Number.isInteger(input.probabilityLevel) || input.probabilityLevel <= 0 || input.probabilityLevel > matrix.probabilityLevels
    || !Number.isInteger(input.severity) || input.severity <= 0 || input.severity > matrix.severityLevels) return undefined;
  return matrix.cells[(input.probabilityLevel - 1) * matrix.severityLevels + input.severity - 1];
}

function matrixIncludesBand(policy: PolicyPackage, band: string): boolean {
  return validMatrix(policy) && policy.riskMatrix?.cells.includes(band) === true;
}

function nasoThreshold(policy: PolicyPackage, band: string): { band: string; maxDurationHours?: number } | undefined {
  const thresholds = policy.nasoThresholds;
  if (!Array.isArray(thresholds) || thresholds.length === 0) return undefined;
  const matches = thresholds.filter((threshold): threshold is { band: string; maxDurationHours?: number } => isRecord(threshold)
    && typeof threshold.band === "string" && threshold.band === band
    && (threshold.maxDurationHours === undefined || (typeof threshold.maxDurationHours === "number" && Number.isFinite(threshold.maxDurationHours) && threshold.maxDurationHours >= 0)));
  return matches.length === 1 ? matches[0] : undefined;
}

function delegatedAuthority(policy: PolicyPackage, authorityId: string, band: string): boolean {
  if (!Array.isArray(policy.delegatedAuthorities)) return false;
  return policy.delegatedAuthorities
    .slice()
    .filter((authority): authority is { role: string; userRole: string; bands: readonly string[] } => isRecord(authority)
      && typeof authority.role === "string" && typeof authority.userRole === "string"
      && Array.isArray(authority.bands) && authority.bands.every((item) => typeof item === "string"))
    .sort((left, right) => compareStable(`${left.role}:${left.userRole}`, `${right.role}:${right.userRole}`))
    .some((authority) => authority.userRole === authorityId && authority.bands.includes(band));
}

/** Evaluates only thresholds and authorities explicitly supplied by a signed, approved policy package. */
export function evaluateRisk(input: RiskEvaluationInput): RiskEvaluation {
  const now = parseUtc(input.nowUtc);
  if (!policyCurrentAt(input.policy, now)) return createRiskEvaluation({ status: "blocked", reason: "APPROVED_RISK_POLICY_REQUIRED" });
  if (!validMatrix(input.policy)) return createRiskEvaluation({ status: "blocked", reason: "APPROVED_RISK_MATRIX_REQUIRED" });
  if (input.status === "draft" || input.status === "blocked" || input.hazardIds.length === 0) return createRiskEvaluation({ status: "blocked", reason: "RISK_ASSESSMENT_INCOMPLETE" });
  const band = matrixBand(input, input.policy);
  if (!band) return createRiskEvaluation({ status: "blocked", reason: "RISK_MATRIX_ASSIGNMENT_REQUIRED" });
  if (input.residualRiskBand !== band) return createRiskEvaluation({ status: "blocked", band, reason: "RESIDUAL_RISK_BAND_MISMATCH" });
  const threshold = nasoThreshold(input.policy, band);
  if (!threshold) return createRiskEvaluation({ status: "blocked", band, reason: "NASO_THRESHOLD_REQUIRED" });
  if (threshold.maxDurationHours !== undefined) {
    if (input.durationHours === undefined || !Number.isFinite(input.durationHours) || input.durationHours < 0) return createRiskEvaluation({ status: "blocked", band, reason: "NASO_DURATION_REQUIRED" });
    if (input.durationHours > threshold.maxDurationHours) return createRiskEvaluation({ status: "blocked", band, reason: "NASO_DURATION_EXCEEDED" });
  }
  if (!input.acceptanceAuthorityId || !delegatedAuthority(input.policy, input.acceptanceAuthorityId, band)) return createRiskEvaluation({ status: "blocked", band, reason: "RISK_ACCEPTANCE_AUTHORITY_MISSING" });
  return createRiskEvaluation({ status: "accepted", band, reason: "RISK_ACCEPTED" });
}

/** Determines freshness from explicit UTC evidence facts and the active policy; it never reads a clock. */
export function evaluateFreshness(snapshot: DataSnapshotRef, policy: PolicyPackage | undefined, nowUtc: string): FreshnessResult {
  const now = parseUtc(nowUtc);
  if (!policyCurrentAt(policy, now)) return createFreshnessResult({ status: "blocked", reason: "APPROVED_FRESHNESS_POLICY_REQUIRED" });
  const rule = isRecord(policy.freshness) && isRecord(snapshot) && typeof snapshot.kind === "string" ? policy.freshness[snapshot.kind] : undefined;
  if (!isRecord(rule) || typeof rule.maxAgeMinutes !== "number" || !Number.isFinite(rule.maxAgeMinutes) || rule.maxAgeMinutes < 0 || typeof rule.critical !== "boolean") return createFreshnessResult({ status: "blocked", reason: "FRESHNESS_THRESHOLD_REQUIRED" });
  const capturedAt = parseUtc(snapshot.capturedAtUtc);
  if (snapshot.status === "expired") return createFreshnessResult({ status: "expired", reason: rule.critical ? "CRITICAL_DATA_EXPIRED" : "DATA_EXPIRED" });
  if (snapshot.status === "missing") return createFreshnessResult({ status: "unknown", reason: "DATA_MISSING" });
  if (snapshot.status === "conflicting") return createFreshnessResult({ status: "unknown", reason: "DATA_CONFLICTING" });
  if (snapshot.status === "unverified") return createFreshnessResult({ status: "unknown", reason: "DATA_UNVERIFIED" });
  if (snapshot.status !== "current") return createFreshnessResult({ status: "blocked", reason: "DATA_STATUS_INVALID" });
  if (capturedAt > now) return createFreshnessResult({ status: "blocked", reason: "DATA_CAPTURE_TIME_INVALID" });
  if (now - capturedAt > rule.maxAgeMinutes * 60_000) return createFreshnessResult({ status: rule.critical ? "expired" : "unknown", reason: rule.critical ? "CRITICAL_DATA_EXPIRED" : "DATA_STALE" });
  return createFreshnessResult({ status: "current", reason: "DATA_CURRENT" });
}

function hasId(value: string | undefined): value is string {
  return nonBlankString(value);
}

/** Evaluates an exception as a current, revision-bound fact; it cannot be copied to a different revision. */
export function evaluateException(exception: ControlledExceptionInput, policy: PolicyPackage | undefined, nowUtc: string): ExceptionResult {
  const now = parseUtc(nowUtc);
  if (!policyCurrentAt(policy, now)) return createExceptionResult({ status: "blocked", reason: "APPROVED_EXCEPTION_POLICY_REQUIRED" });
  if (!validMatrix(policy)) return createExceptionResult({ status: "blocked", reason: "APPROVED_RISK_MATRIX_REQUIRED" });
  if (!hasId(exception.missionRevisionId) || !hasId(exception.sourceRevisionId)) return createExceptionResult({ status: "blocked", reason: "EXCEPTION_REVISION_REQUIRED" });
  if (exception.sourceRevisionId !== exception.missionRevisionId) return createExceptionResult({ status: "blocked", reason: "EXCEPTION_REVISION_MISMATCH" });
  const sourceFreshness = evaluateFreshness(exception.snapshot, policy, nowUtc);
  const staleOrMissing = sourceFreshness.status === "expired"
    || (exception.snapshot.status === "missing" && sourceFreshness.status === "unknown" && sourceFreshness.reason === "DATA_MISSING")
    || (exception.snapshot.status === "current" && sourceFreshness.status === "unknown" && sourceFreshness.reason === "DATA_STALE");
  if (!staleOrMissing) return createExceptionResult({ status: "blocked", reason: "EXCEPTION_DEGRADED_DATA_REQUIRED" });
  if (!exception.alternateVerifiedSource) return createExceptionResult({ status: "blocked", reason: "EXCEPTION_ALTERNATE_SOURCE_REQUIRED" });
  if (exception.alternateVerifiedSource.snapshotId === exception.snapshot.snapshotId || exception.alternateVerifiedSource.packageId === exception.snapshot.packageId) return createExceptionResult({ status: "blocked", reason: "EXCEPTION_ALTERNATE_SOURCE_NOT_DISTINCT" });
  if (evaluateFreshness(exception.alternateVerifiedSource, policy, nowUtc).status !== "current") return createExceptionResult({ status: "blocked", reason: "EXCEPTION_ALTERNATE_SOURCE_UNVERIFIED" });
  if (!hasId(exception.consequence)) return createExceptionResult({ status: "blocked", reason: "EXCEPTION_CONSEQUENCE_REQUIRED" });
  if (!hasId(exception.mitigation)) return createExceptionResult({ status: "blocked", reason: "EXCEPTION_MITIGATION_REQUIRED" });
  if (!exception.validityEndUtc) return createExceptionResult({ status: "blocked", reason: "EXCEPTION_VALIDITY_REQUIRED" });
  if (parseUtc(exception.validityEndUtc) <= now) return createExceptionResult({ status: "expired", reason: "EXCEPTION_EXPIRED" });
  if (!exception.safetyReview?.approved || !hasId(exception.safetyReview.reviewerId)) return createExceptionResult({ status: "blocked", reason: "EXCEPTION_SAFETY_REVIEW_REQUIRED" });
  if (!exception.operatorAcknowledged) return createExceptionResult({ status: "blocked", reason: "EXCEPTION_OPERATOR_ACKNOWLEDGEMENT_REQUIRED" });
  if (!hasId(exception.residualRiskBand) || !matrixIncludesBand(policy, exception.residualRiskBand)) return createExceptionResult({ status: "blocked", reason: "EXCEPTION_RISK_BAND_REQUIRED" });
  if (!nasoThreshold(policy, exception.residualRiskBand)) return createExceptionResult({ status: "blocked", reason: "EXCEPTION_NASO_BAND_REQUIRED" });
  if (!hasId(exception.riskAuthorityId) || !delegatedAuthority(policy, exception.riskAuthorityId, exception.residualRiskBand)) return createExceptionResult({ status: "blocked", reason: "EXCEPTION_RISK_AUTHORITY_REQUIRED" });
  return createExceptionResult({ status: "accepted", reason: "EXCEPTION_ACCEPTED" });
}
