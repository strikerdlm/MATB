import { createHash } from "node:crypto";
import { canonicalJson } from "@fac-isr/evidence";
import type { EvidenceReference, NormalizedRequirement, RequirementTranslation, SourceId, SourceRegister } from "@fac-isr/evidence";

const SHA256 = /^[a-f0-9]{64}$/;
const SECTION = /^94\.\d{3}$/;
const STATUSES = ["draft", "qualified-review", "approved", "superseded"] as const;
type InterpretationStatus = (typeof STATUSES)[number];

export interface RequirementReview {
  status: "pending" | "qualified-review" | "accepted";
  reviewerRole: string;
  reviewerId: string;
  reviewedAtUtc?: string;
  rationale: string;
}

export interface NormalizationInput {
  sourceRefs: EvidenceReference[];
  Spanish: string;
  EnglishControlled: string;
  applicabilityExpression: string;
  severity: NormalizedRequirement["severity"];
  evidenceRequired: boolean;
  effectiveFromUtc: string;
  interpretationStatus: InterpretationStatus;
  reviewerIds?: string[];
  /** Stable machine predicate; it must not be generated from UI locale. */
  predicate: string;
  sourceLanguageReview: RequirementReview;
  applicabilityReview: RequirementReview;
  unresolvedRationale?: string;
}

export interface ReviewedNormalizedRequirement extends NormalizedRequirement {
  readonly predicate: string;
  readonly sourceLanguageReview: RequirementReview;
  readonly applicabilityReview: RequirementReview;
  readonly unresolvedRationale?: string;
}

export interface ControlledTranslationEvidence {
  requirementId: string;
  sourceRef: EvidenceReference;
  sourceLanguageReview: RequirementReview;
}

/** Exact UTC validation deliberately rejects calendar rollovers such as 2026-02-30. */
function isExactUtc(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{3})?Z$/.exec(value);
  if (match === null) return false;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  if (month < 1 || month > 12 || hour > 23 || minute > 59 || second > 59) return false;
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
  return day >= 1 && day <= daysInMonth;
}

function assertUtc(value: unknown, field: string): asserts value is string {
  if (!isExactUtc(value)) throw new Error(`${field} must be an exact UTC timestamp`);
}

function assertNonEmpty(value: unknown, field: string): asserts value is string {
  if (typeof value !== "string" || value.trim() === "") throw new Error(`${field} must be a non-empty string`);
}

function assertLocator(reference: EvidenceReference): void {
  const { locator } = reference;
  if (!SECTION.test(locator.section ?? "")) throw new Error(`Evidence ${reference.evidenceId} has malformed section locator`);
  if (!Number.isInteger(locator.page) || (locator.page ?? 0) < 1) throw new Error(`Evidence ${reference.evidenceId} has malformed page locator`);
  if (locator.paragraph !== undefined && !/^\([a-z]\)(?:\([0-9]+\))?$/.test(locator.paragraph)) {
    throw new Error(`Evidence ${reference.evidenceId} has malformed paragraph locator`);
  }
}

function assertReference(reference: EvidenceReference): void {
  assertNonEmpty(reference.evidenceId, "evidenceId");
  assertNonEmpty(reference.sourceId, "sourceId");
  assertNonEmpty(reference.edition, "edition");
  assertLocator(reference);
  if (reference.quoteLanguage !== "es" && reference.quoteLanguage !== "en") throw new Error(`Evidence ${reference.evidenceId} has unsupported quote language`);
  if (!SHA256.test(reference.extractionSha256)) throw new Error(`Evidence ${reference.evidenceId} has malformed extraction hash`);
  if (!["unreviewed", "accepted", "rejected"].includes(reference.reviewState)) throw new Error(`Evidence ${reference.evidenceId} has invalid review state`);
}

function assertReview(review: RequirementReview, field: string): void {
  if (review === null || typeof review !== "object") throw new Error(`${field} must be a review object`);
  if (!["pending", "qualified-review", "accepted"].includes(review.status)) throw new Error(`${field} has invalid status`);
  assertNonEmpty(review.reviewerRole, `${field}.reviewerRole`);
  assertNonEmpty(review.reviewerId, `${field}.reviewerId`);
  assertNonEmpty(review.rationale, `${field}.rationale`);
  if (review.reviewedAtUtc !== undefined) assertUtc(review.reviewedAtUtc, `${field}.reviewedAtUtc`);
}

/**
 * Convert a reviewed source excerpt into a locale-independent normalized rule.
 * The function deliberately produces draft/qualified-review artefacts only: promotion to
 * approved is validated against the immutable source register by validateRequirementCitations.
 */
export function normalizeRequirement(input: NormalizationInput): ReviewedNormalizedRequirement {
  if (input === null || typeof input !== "object") throw new Error("normalization input must be an object");
  if (!Array.isArray(input.sourceRefs) || input.sourceRefs.length === 0) throw new Error("normalized requirement requires source evidence");
  input.sourceRefs.forEach(assertReference);
  assertNonEmpty(input.Spanish, "Spanish");
  assertNonEmpty(input.EnglishControlled, "EnglishControlled");
  assertNonEmpty(input.applicabilityExpression, "applicabilityExpression");
  assertNonEmpty(input.predicate, "predicate");
  if (!["hard", "soft", "advisory"].includes(input.severity)) throw new Error("severity is invalid");
  if (typeof input.evidenceRequired !== "boolean") throw new Error("evidenceRequired must be boolean");
  assertUtc(input.effectiveFromUtc, "effectiveFromUtc");
  if (!STATUSES.includes(input.interpretationStatus)) throw new Error("interpretationStatus is invalid");
  assertReview(input.sourceLanguageReview, "sourceLanguageReview");
  assertReview(input.applicabilityReview, "applicabilityReview");
  if (input.interpretationStatus === "approved" && (input.sourceLanguageReview.status !== "accepted" || input.applicabilityReview.status !== "accepted")) {
    throw new Error("approved requirement requires accepted source-language and applicability reviews");
  }
  if (input.unresolvedRationale !== undefined) assertNonEmpty(input.unresolvedRationale, "unresolvedRationale");

  const sourceKey = input.sourceRefs.map((reference) => ({
    sourceId: reference.sourceId,
    edition: reference.edition,
    section: reference.locator.section,
    paragraph: reference.locator.paragraph ?? "",
  })).sort((left, right) => {
    const leftKey = canonicalJson(left);
    const rightKey = canonicalJson(right);
    return leftKey < rightKey ? -1 : leftKey > rightKey ? 1 : 0;
  });
  const requirementId = `req-${createHash("sha256").update(canonicalJson({ predicate: input.predicate, sourceKey })).digest("hex").slice(0, 20)}`;
  return Object.freeze({
    requirementId,
    sourceRefs: input.sourceRefs.map((reference) => ({ ...reference, locator: { ...reference.locator } })),
    Spanish: input.Spanish,
    EnglishControlled: input.EnglishControlled,
    applicabilityExpression: input.applicabilityExpression,
    severity: input.severity,
    evidenceRequired: input.evidenceRequired,
    effectiveFromUtc: input.effectiveFromUtc,
    interpretationStatus: input.interpretationStatus,
    reviewerIds: [...(input.reviewerIds ?? [])],
    predicate: input.predicate,
    sourceLanguageReview: Object.freeze({ ...input.sourceLanguageReview }),
    applicabilityReview: Object.freeze({ ...input.applicabilityReview }),
    ...(input.unresolvedRationale === undefined ? {} : { unresolvedRationale: input.unresolvedRationale }),
  });
}

/** Verify locators and source/extraction/review provenance before a rule can be used. */
/**
 * Validate citation provenance. For approved hard requirements `asOfUtc` is mandatory:
 * approval is a deterministic claim about an explicitly stated point in time, never about
 * the machine clock used to run validation.
 */
export function validateRequirementCitations(
  requirements: readonly ReviewedNormalizedRequirement[],
  register: SourceRegister,
  asOfUtc?: string,
): void {
  for (const requirement of requirements) {
    if (!Array.isArray(requirement.sourceRefs) || requirement.sourceRefs.length === 0) throw new Error(`${requirement.requirementId} has no evidence`);
    let spanishAuthority = false;
    for (const reference of requirement.sourceRefs) {
      assertReference(reference);
      const source = register.get(reference.sourceId as SourceId);
      if (source === undefined) throw new Error(`${requirement.requirementId} cites an unregistered source ${reference.sourceId}`);
      if (source.extractionSha256 === undefined || source.extractionSha256 !== reference.extractionSha256) {
        throw new Error(`${requirement.requirementId} extraction hash does not match ${reference.sourceId}`);
      }
      if (reference.quoteLanguage === "es" && (source.language === "es" || source.language === "multi")) spanishAuthority = true;
      if (requirement.interpretationStatus === "approved" && requirement.severity === "hard") {
        assertUtc(asOfUtc, `${requirement.requirementId} approved hard requirement asOfUtc`);
        if (
          source.review !== "accepted" ||
          source.supersededBy !== undefined ||
          reference.reviewState !== "accepted" ||
          register.isSuperseded(reference.sourceId as SourceId) ||
          typeof source.reviewerId !== "string" || source.reviewerId.trim() === "" ||
          typeof source.reviewSignature !== "string" || source.reviewSignature.trim() === "" ||
          !isExactUtc(source.reviewedAtUtc) ||
          !isExactUtc(source.validFromUtc) ||
          !isExactUtc(source.validUntilUtc) ||
          Date.parse(source.validFromUtc) > Date.parse(asOfUtc) ||
          Date.parse(source.validUntilUtc) <= Date.parse(asOfUtc)
        ) {
          throw new Error(`${requirement.requirementId} is approved without current signed source evidence`);
        }
      }
    }
    if (!spanishAuthority) throw new Error(`${requirement.requirementId} lacks Spanish-language authority`);
    if (requirement.interpretationStatus === "approved" && requirement.severity === "hard") {
      if (
        requirement.sourceLanguageReview.status !== "accepted" ||
        requirement.applicabilityReview.status !== "accepted" ||
        !isExactUtc(requirement.sourceLanguageReview.reviewedAtUtc) ||
        !isExactUtc(requirement.applicabilityReview.reviewedAtUtc)
      ) {
        throw new Error(`${requirement.requirementId} is approved without accepted timestamped review`);
      }
    }
  }
}

/** Build a labelled English controlled translation; it has no independent regulatory authority. */
export function buildControlledTranslation(sourceText: string, translation: string, evidence: ControlledTranslationEvidence): RequirementTranslation {
  assertNonEmpty(sourceText, "sourceText");
  assertNonEmpty(translation, "translation");
  assertNonEmpty(evidence.requirementId, "translation requirementId");
  assertReference(evidence.sourceRef);
  if (evidence.sourceRef.quoteLanguage !== "es") throw new Error("controlled translation requires Spanish source evidence");
  assertReview(evidence.sourceLanguageReview, "translation sourceLanguageReview");
  return Object.freeze({
    requirementId: evidence.requirementId,
    sourceLanguage: "es",
    targetLanguage: "en",
    translatedText: translation,
    translationStatus: evidence.sourceLanguageReview.status === "accepted" ? "reviewed" : "draft",
    reviewerIds: Object.freeze([evidence.sourceLanguageReview.reviewerId]),
  });
}
