import { createHash } from "node:crypto";
import { canonicalJson, type NormalizedRequirement } from "@fac-isr/evidence";
import {
  evaluateMission,
  parseSafetyEvaluationResult,
  type GateName,
  type MissionRevision,
  type PolicyPackage,
  type RuleEvaluation,
  type SafetyBlocker,
  type SafetyEvaluationResult,
} from "@fac-isr/safety-kernel";

const SHA256 = /^[a-f0-9]{64}$/;

export interface PackageIdentity {
  readonly packageId: string;
  readonly version: string;
}

export interface SafetyEvaluationEnvelope {
  readonly revisionId: string;
  readonly kernelVersion: string;
  readonly policyPackage: PackageIdentity;
  readonly terminologyPackage: PackageIdentity;
  readonly evidencePackage: PackageIdentity;
  readonly canonicalInputSha256: string;
  readonly evidenceSnapshotSha256: string;
  readonly resultSha256: string;
  readonly evaluatedAtUtc: string;
  readonly evaluations: readonly RuleEvaluation[];
  readonly blockers: readonly SafetyBlocker[];
  readonly invalidatedGates: readonly GateName[];
  readonly status: SafetyEvaluationResult["status"];
}

export interface SafetyEvaluationView extends SafetyEvaluationEnvelope {
  readonly stale: boolean;
}

export interface SafetyEvaluationResolution {
  readonly requirements: readonly NormalizedRequirement[];
  readonly policy: PolicyPackage | undefined;
  readonly evidenceSnapshot: unknown;
  readonly policyPackage: PackageIdentity;
  readonly terminologyPackage: PackageIdentity;
  readonly evidencePackage: PackageIdentity;
}

export interface SafetyEvaluationProvider {
  evaluate(revision: MissionRevision): Promise<SafetyEvaluationEnvelope>;
  isCurrent(revision: MissionRevision, envelope: SafetyEvaluationEnvelope, asOfUtc: string): Promise<boolean>;
}

export interface DeterministicSafetyEvaluationProviderOptions {
  readonly resolve: (revision: MissionRevision, asOfUtc: string) => Promise<SafetyEvaluationResolution>;
  readonly now?: () => string;
}

export interface ActiveSafetyPackage {
  readonly packageId: string;
  readonly version: string;
  readonly documents: Readonly<Record<string, string>>;
}

export interface ActiveSafetyPackageSource {
  getReverifiedActivePackage(kind: "policy" | "terminology" | "regulatory", asOfUtc: string): Promise<ActiveSafetyPackage>;
}

function normalizedJson(value: unknown): unknown {
  return JSON.parse(JSON.stringify(value)) as unknown;
}

function sha256(value: unknown): string {
  return createHash("sha256").update(canonicalJson(normalizedJson(value))).digest("hex");
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const child of Object.values(value as Record<string, unknown>)) deepFreeze(child);
    Object.freeze(value);
  }
  return value;
}

function packageIdentity(value: PackageIdentity, field: string): PackageIdentity {
  if (value === null || typeof value !== "object"
    || typeof value.packageId !== "string" || value.packageId.trim() === ""
    || typeof value.version !== "string" || value.version.trim() === "") {
    throw new Error(`${field} identity is invalid`);
  }
  return Object.freeze({ packageId: value.packageId, version: value.version });
}

function validUtc(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/.exec(value);
  if (!match) return false;
  const [, year, month, day, hour, minute, second, fraction = ""] = match;
  const date = new Date(value);
  return Number.isFinite(date.getTime())
    && date.getUTCFullYear() === Number(year)
    && date.getUTCMonth() + 1 === Number(month)
    && date.getUTCDate() === Number(day)
    && date.getUTCHours() === Number(hour)
    && date.getUTCMinutes() === Number(minute)
    && date.getUTCSeconds() === Number(second)
    && date.getUTCMilliseconds() === Number(fraction.padEnd(3, "0") || 0);
}

function resultProjection(envelope: SafetyEvaluationEnvelope): SafetyEvaluationResult {
  return parseSafetyEvaluationResult({
    missionRevisionId: envelope.revisionId,
    status: envelope.status,
    evaluations: normalizedJson(envelope.evaluations),
    blockers: normalizedJson(envelope.blockers),
    invalidatedGates: normalizedJson(envelope.invalidatedGates),
    kernelVersion: envelope.kernelVersion,
  });
}

/** Resolves evaluation inputs exclusively from package records reverified by SafeModeService. */
export class ActivePackageSafetyResolver {
  public constructor(private readonly source: ActiveSafetyPackageSource) {}

  public async resolve(revision: MissionRevision, asOfUtc: string): Promise<SafetyEvaluationResolution> {
    if (!validUtc(asOfUtc)) throw new Error("package resolution time must be a valid UTC instant");
    const [policyPackage, terminologyPackage, evidencePackage] = await Promise.all([
      this.source.getReverifiedActivePackage("policy", asOfUtc),
      this.source.getReverifiedActivePackage("terminology", asOfUtc),
      this.source.getReverifiedActivePackage("regulatory", asOfUtc),
    ]);
    const policy = parseDocument(policyPackage, "policy.json");
    if (policy === null || typeof policy !== "object" || Array.isArray(policy)) throw new Error("active policy package policy.json must be an object");
    const candidatePolicy = policy as PolicyPackage;
    if (candidatePolicy.packageId !== policyPackage.packageId || candidatePolicy.version !== policyPackage.version) throw new Error("active policy document identity does not match its signed manifest");
    const requirements = parseRequirements(parseDocument(evidencePackage, "requirements.json"), asOfUtc);
    const evidenceSnapshot = parseEvidenceSnapshot(parseDocument(evidencePackage, "evidence-snapshot.json"), revision.evidenceSnapshotId, requirements);
    if (Object.keys(terminologyPackage.documents).length === 0) throw new Error("active terminology package has no immutable contents");
    return {
      requirements,
      policy: candidatePolicy,
      evidenceSnapshot,
      policyPackage,
      terminologyPackage,
      evidencePackage,
    };
  }
}

function parseDocument(pkg: ActiveSafetyPackage, name: string): unknown {
  const content = pkg.documents[name];
  if (content === undefined) throw new Error(`active package ${pkg.packageId}@${pkg.version} is missing ${name}`);
  return JSON.parse(content) as unknown;
}

interface BoundEvidenceSnapshot {
  readonly snapshotId: string;
  readonly requirementIds: readonly string[];
  readonly acceptedEvidenceIds: readonly string[];
}

function parseEvidenceSnapshot(value: unknown, requestedSnapshotId: string, requirements: readonly NormalizedRequirement[]): BoundEvidenceSnapshot {
  const snapshot = parseBoundEvidenceSnapshot(value);
  if (snapshot.snapshotId !== requestedSnapshotId) throw new Error(`active evidence snapshot identity does not match mission snapshot ${requestedSnapshotId}`);
  const requirementIds = requirements.map((requirement) => requirement.requirementId);
  if (!sameStringSet(snapshot.requirementIds, requirementIds)) throw new Error("evidence snapshot requirement references do not match the evaluated requirements");
  const referencedEvidenceIds = requirements.flatMap((requirement) => requirement.sourceRefs.map((reference) => String(reference.evidenceId)));
  if (!sameStringSet(snapshot.acceptedEvidenceIds, referencedEvidenceIds)) throw new Error("evidence snapshot accepted evidence references do not match requirement evidence");
  return deepFreeze(snapshot);
}

function parseBoundEvidenceSnapshot(value: unknown): BoundEvidenceSnapshot {
  const snapshot = strictObject(value, ["acceptedEvidenceIds", "requirementIds", "snapshotId"], "evidence snapshot");
  return {
    snapshotId: nonEmptyText(snapshot.snapshotId, "evidence snapshot snapshotId"),
    requirementIds: uniqueTextArray(snapshot.requirementIds, "evidence snapshot requirementIds"),
    acceptedEvidenceIds: uniqueTextArray(snapshot.acceptedEvidenceIds, "evidence snapshot acceptedEvidenceIds"),
  };
}

function parseRequirements(value: unknown, asOfUtc: string): readonly NormalizedRequirement[] {
  if (!Array.isArray(value)) throw new Error("active regulatory package requirements.json must be an array");
  const parsed = value.map((candidate, index) => parseRequirement(candidate, index, asOfUtc));
  const identifiers = parsed.map((requirement) => requirement.requirementId);
  if (new Set(identifiers).size !== identifiers.length) throw new Error("active regulatory package has duplicate requirement IDs");
  return deepFreeze(parsed);
}

function parseRequirement(value: unknown, index: number, asOfUtc: string): NormalizedRequirement {
  const field = `requirement ${index}`;
  const requirement = strictObject(value, ["EnglishControlled", "Spanish", "applicabilityExpression", "effectiveFromUtc", "evidenceRequired", "interpretationStatus", "requirementId", "reviewerIds", "severity", "sourceRefs"], field);
  const effectiveFromUtc = nonEmptyText(requirement.effectiveFromUtc, `${field} effectiveFromUtc`);
  if (!validUtc(effectiveFromUtc) || Date.parse(effectiveFromUtc) > Date.parse(asOfUtc)) throw new Error(`${field} effectiveFromUtc is invalid or not yet effective`);
  if (requirement.interpretationStatus !== "approved") throw new Error(`${field} must have approved interpretation status`);
  if (!["hard", "soft", "advisory"].includes(String(requirement.severity))) throw new Error(`${field} severity is invalid`);
  if (typeof requirement.evidenceRequired !== "boolean") throw new Error(`${field} evidenceRequired must be boolean`);
  const reviewerIds = uniqueTextArray(requirement.reviewerIds, `${field} reviewerIds`);
  if (reviewerIds.length === 0) throw new Error(`${field} requires an accountable reviewer`);
  if (!Array.isArray(requirement.sourceRefs)) throw new Error(`${field} sourceRefs must be an array`);
  const sourceRefs = requirement.sourceRefs.map((reference, referenceIndex) => parseEvidenceReference(reference, `${field} sourceRefs[${referenceIndex}]`));
  if (requirement.evidenceRequired && sourceRefs.length === 0) throw new Error(`${field} requires evidence references`);
  return {
    requirementId: nonEmptyText(requirement.requirementId, `${field} requirementId`),
    sourceRefs: sourceRefs as unknown as NormalizedRequirement["sourceRefs"],
    Spanish: nonEmptyText(requirement.Spanish, `${field} Spanish`),
    EnglishControlled: nonEmptyText(requirement.EnglishControlled, `${field} EnglishControlled`),
    applicabilityExpression: nonEmptyText(requirement.applicabilityExpression, `${field} applicabilityExpression`),
    severity: requirement.severity as NormalizedRequirement["severity"],
    evidenceRequired: requirement.evidenceRequired,
    effectiveFromUtc,
    interpretationStatus: "approved",
    reviewerIds,
  };
}

function parseEvidenceReference(value: unknown, field: string): Record<string, unknown> {
  const reference = strictObject(value, ["edition", "evidenceId", "extractionSha256", "locator", "quoteLanguage", "reviewState", "reviewerId", "sourceId"], field, ["reviewerId"]);
  if (reference.reviewState !== "accepted") throw new Error(`${field} must be accepted`);
  if (reference.quoteLanguage !== "es" && reference.quoteLanguage !== "en") throw new Error(`${field} quoteLanguage is invalid`);
  if (typeof reference.extractionSha256 !== "string" || !SHA256.test(reference.extractionSha256)) throw new Error(`${field} extractionSha256 is invalid`);
  const locator = strictObject(reference.locator, ["page", "paragraph", "section"], `${field} locator`, ["page", "paragraph", "section"]);
  if (locator.page !== undefined && (!Number.isSafeInteger(locator.page) || Number(locator.page) <= 0)) throw new Error(`${field} locator page is invalid`);
  if (locator.section !== undefined) nonEmptyText(locator.section, `${field} locator section`);
  if (locator.paragraph !== undefined) nonEmptyText(locator.paragraph, `${field} locator paragraph`);
  if (Object.keys(locator).length === 0) throw new Error(`${field} locator is empty`);
  return {
    evidenceId: nonEmptyText(reference.evidenceId, `${field} evidenceId`),
    sourceId: nonEmptyText(reference.sourceId, `${field} sourceId`),
    edition: nonEmptyText(reference.edition, `${field} edition`),
    locator,
    quoteLanguage: reference.quoteLanguage,
    extractionSha256: reference.extractionSha256,
    ...(reference.reviewerId === undefined ? {} : { reviewerId: nonEmptyText(reference.reviewerId, `${field} reviewerId`) }),
    reviewState: "accepted",
  };
}

function strictObject(value: unknown, allowedKeys: readonly string[], field: string, optionalKeys: readonly string[] = []): Record<string, unknown> {
  if (!isPlainObject(value)) throw new Error(`${field} must be an object`);
  const keys = Object.keys(value);
  if (keys.some((key) => !allowedKeys.includes(key)) || allowedKeys.some((key) => !optionalKeys.includes(key) && !keys.includes(key))) throw new Error(`${field} shape is invalid`);
  return value;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function nonEmptyText(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "" || value !== value.trim()) throw new Error(`${field} must be non-empty text`);
  return value;
}

function uniqueTextArray(value: unknown, field: string): string[] {
  if (!Array.isArray(value)) throw new Error(`${field} must be an array`);
  const output = value.map((item) => nonEmptyText(item, field));
  if (new Set(output).size !== output.length) throw new Error(`${field} must be unique`);
  return output;
}

function sameStringSet(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((value) => right.includes(value));
}

/** Resolves trusted local inputs, invokes the pure kernel, and hashes the canonical decision record. */
export class DeterministicSafetyEvaluationProvider implements SafetyEvaluationProvider {
  private readonly resolve: DeterministicSafetyEvaluationProviderOptions["resolve"];
  private readonly now: () => string;

  public constructor(options: DeterministicSafetyEvaluationProviderOptions) {
    this.resolve = options.resolve;
    this.now = options.now ?? (() => new Date().toISOString());
  }

  public async evaluate(revision: MissionRevision): Promise<SafetyEvaluationEnvelope> {
    const evaluatedAtUtc = this.now();
    if (!validUtc(evaluatedAtUtc)) throw new Error("evaluation time must be a valid UTC instant");
    const resolved = await this.resolve(revision, evaluatedAtUtc);
    const input = {
      mission: revision,
      requirements: resolved.requirements,
      policy: resolved.policy,
      nowUtc: evaluatedAtUtc,
    };
    const result = evaluateMission(input);
    const envelope: SafetyEvaluationEnvelope = {
      revisionId: revision.id,
      kernelVersion: result.kernelVersion,
      policyPackage: packageIdentity(resolved.policyPackage, "policy package"),
      terminologyPackage: packageIdentity(resolved.terminologyPackage, "terminology package"),
      evidencePackage: packageIdentity(resolved.evidencePackage, "evidence package"),
      canonicalInputSha256: sha256(input),
      evidenceSnapshotSha256: sha256(resolved.evidenceSnapshot),
      resultSha256: sha256(result),
      evaluatedAtUtc,
      evaluations: result.evaluations.map((evaluation) => ({ ...evaluation, evidenceRefs: [...evaluation.evidenceRefs], affectedGates: [...evaluation.affectedGates] })),
      blockers: result.blockers.map((blocker) => ({ ...blocker, evidenceRefs: [...blocker.evidenceRefs] })),
      invalidatedGates: [...result.invalidatedGates],
      status: result.status,
    };
    return deepFreeze(envelope);
  }

  public async isCurrent(revision: MissionRevision, envelope: SafetyEvaluationEnvelope, asOfUtc: string): Promise<boolean> {
    if (!validUtc(asOfUtc)) return false;
    validateSafetyEvaluationEnvelope(envelope, revision.id);
    const resolved = await this.resolve(revision, asOfUtc);
    const sameIdentity = (left: PackageIdentity, right: PackageIdentity): boolean => left.packageId === right.packageId && left.version === right.version;
    if (!sameIdentity(envelope.policyPackage, resolved.policyPackage)
      || !sameIdentity(envelope.terminologyPackage, resolved.terminologyPackage)
      || !sameIdentity(envelope.evidencePackage, resolved.evidencePackage)) return false;
    const originalInput = { mission: revision, requirements: resolved.requirements, policy: resolved.policy, nowUtc: envelope.evaluatedAtUtc };
    const currentInput = { mission: revision, requirements: resolved.requirements, policy: resolved.policy, nowUtc: asOfUtc };
    const currentResult = evaluateMission(currentInput);
    return sha256(originalInput) === envelope.canonicalInputSha256
      && sha256(resolved.evidenceSnapshot) === envelope.evidenceSnapshotSha256
      && sha256(currentResult) === envelope.resultSha256;
  }
}

export function validateSafetyEvaluationEnvelope(value: SafetyEvaluationEnvelope, revisionId: string): SafetyEvaluationEnvelope {
  if (value === null || typeof value !== "object") throw new Error("safety evaluation envelope must be an object");
  if (value.revisionId !== revisionId) throw new Error("safety evaluation revision does not match the mission revision");
  if (typeof value.kernelVersion !== "string" || value.kernelVersion.trim() === "") throw new Error("safety evaluation kernel version is required");
  packageIdentity(value.policyPackage, "policy package");
  packageIdentity(value.terminologyPackage, "terminology package");
  packageIdentity(value.evidencePackage, "evidence package");
  for (const [field, hash] of [
    ["canonicalInputSha256", value.canonicalInputSha256],
    ["evidenceSnapshotSha256", value.evidenceSnapshotSha256],
    ["resultSha256", value.resultSha256],
  ] as const) {
    if (!SHA256.test(hash)) throw new Error(`${field} must be a SHA-256 digest`);
  }
  if (!validUtc(value.evaluatedAtUtc)) throw new Error("evaluatedAtUtc must be a valid UTC instant");
  const result = resultProjection(value);
  if (sha256(result) !== value.resultSha256) throw new Error("resultSha256 does not match the safety evaluation result projection");
  const detached = normalizedJson(value) as SafetyEvaluationEnvelope;
  return deepFreeze(detached);
}

/** Production fail-closed default used until trusted active packages are configured. */
export class UnavailableSafetyEvaluationProvider implements SafetyEvaluationProvider {
  private readonly now: () => string;

  public constructor(now: () => string = () => new Date().toISOString()) {
    this.now = now;
  }

  public async evaluate(revision: MissionRevision): Promise<SafetyEvaluationEnvelope> {
    const evaluatedAtUtc = this.now();
    const result: SafetyEvaluationResult = {
      missionRevisionId: revision.id,
      status: "blocked",
      evaluations: [],
      blockers: [{
        code: "TRUSTED_SAFETY_PACKAGES_UNAVAILABLE",
        conceptId: "safety.packages.unavailable",
        severity: "policy",
        explanationKey: "TRUSTED_SAFETY_PACKAGES_UNAVAILABLE",
        evidenceRefs: [],
      }],
      invalidatedGates: ["operator", "safety", "commander"],
      kernelVersion: "0.1.0",
    };
    return deepFreeze({
      revisionId: revision.id,
      kernelVersion: result.kernelVersion,
      policyPackage: { packageId: "unavailable-policy", version: "0.0.0" },
      terminologyPackage: { packageId: "unavailable-terminology", version: "0.0.0" },
      evidencePackage: { packageId: "unavailable-evidence", version: "0.0.0" },
      canonicalInputSha256: sha256({ mission: revision, unavailable: true }),
      evidenceSnapshotSha256: sha256({ unavailable: true }),
      resultSha256: sha256(result),
      evaluatedAtUtc,
      evaluations: result.evaluations,
      blockers: result.blockers,
      invalidatedGates: result.invalidatedGates,
      status: result.status,
    });
  }

  public async isCurrent(_revision: MissionRevision, envelope: SafetyEvaluationEnvelope): Promise<boolean> {
    validateSafetyEvaluationEnvelope(envelope, envelope.revisionId);
    return true;
  }
}

export function asSafetyEvaluationResult(envelope: SafetyEvaluationEnvelope): SafetyEvaluationResult {
  return resultProjection(envelope);
}
