import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { SourceRegister } from "@fac-isr/evidence";
import type { SourceRecord } from "@fac-isr/evidence";
import { describe, expect, it } from "vitest";
import {
  buildControlledTranslation,
  normalizeRequirement,
  validateRequirementCitations,
} from "../src/normalize.js";
import type { NormalizationInput, ReviewedNormalizedRequirement } from "../src/normalize.js";

const extractionSha = "77cc55931dd862884751fc2510ef4d16def1546e8712195fff2500f2ea482a69";
const root = resolve(process.cwd(), "../..");

function source(overrides: Partial<SourceRecord> = {}): SourceRecord {
  return {
    sourceId: "racae-94-enm2" as never,
    title: "RACAE 94 Enmienda 2",
    authority: "AAAES",
    authorityRank: 1,
    canonicalUri: "https://aaaes.fac.mil.co/racae94.pdf",
    localPath: "docs/regulations/original/racae94.pdf",
    mediaType: "application/pdf",
    language: "es",
    retrievedAtUtc: "2026-08-08T17:54:59Z",
    sha256: "312458744b5e4f5097492d4b1c58b0e05229cc5e738058c757d4464e0f155976",
    extractionSha256: extractionSha,
    extractionPath: "docs/regulations/extracted/racae_94_enm2.txt",
    sensitivity: "unclassified-controlled",
    licenseOrRestriction: "Official public source",
    review: "accepted",
    reviewerId: "qualified-reviewer",
    reviewSignature: "test-signature",
    reviewedAtUtc: "2026-08-08T18:00:00Z",
    validFromUtc: "2025-06-16T05:00:00Z",
    validUntilUtc: "2030-01-01T00:00:00Z",
    ...overrides,
  };
}

function input(overrides: Partial<NormalizationInput> = {}): NormalizationInput {
  return {
    sourceRefs: [{
      evidenceId: "racae94-94.155-a" as never,
      sourceId: "racae-94-enm2" as never,
      edition: "Enmienda 2",
      locator: { section: "94.155", page: 38, paragraph: "(a)" },
      quoteLanguage: "es",
      extractionSha256: extractionSha,
      reviewState: "accepted",
    }],
    Spanish: "La operación en modo de vuelo autónomo o con aeronaves autónomas está prohibida.",
    EnglishControlled: "Autonomous flight is prohibited.",
    applicabilityExpression: "state_aviation && uas_rpas_operation",
    severity: "hard",
    evidenceRequired: true,
    effectiveFromUtc: "2025-06-16T05:00:00Z",
    interpretationStatus: "qualified-review",
    predicate: "fac.racae94.autonomous-flight.prohibited",
    sourceLanguageReview: { status: "qualified-review", reviewerRole: "Spanish reviewer", reviewerId: "pending-review", rationale: "Pending qualified review." },
    applicabilityReview: { status: "pending", reviewerRole: "Operational authority", reviewerId: "pending-operational-review", rationale: "Pending operational review." },
    ...overrides,
  };
}

function register(record = source()): SourceRegister {
  const result = new SourceRegister();
  result.append(record);
  return result;
}

describe("RACAE 94 normalized evidence", () => {
  it("contains the six checksum-linked golden controls with exact section/page locators", async () => {
    const raw = await readFile(resolve(root, "docs/regulations/normalized/racae94-amendment-2.json"), "utf8");
    const artifact = JSON.parse(raw) as { source: { extractionSha256: string }; requirements: Array<ReviewedNormalizedRequirement & { sourceTextSpanish: string }> };
    expect(artifact.source.extractionSha256).toBe(extractionSha);
    const expected = new Map([
      ["94.155", 38], ["94.201", 39], ["94.250", 42], ["94.705", 66], ["94.710", 68], ["94.715", 69],
    ]);
    expect(artifact.requirements).toHaveLength(6);
    for (const requirement of artifact.requirements) {
      const first = requirement.sourceRefs[0];
      expect(first.extractionSha256).toBe(extractionSha);
      expect(first.quoteLanguage).toBe("es");
      expect(first.locator.section).toMatch(/^94\.\d{3}$/);
      expect(first.locator.page).toBe(expected.get(first.locator.section!));
      expect(requirement.sourceTextSpanish.length).toBeGreaterThan(20);
      expect(requirement.interpretationStatus).not.toBe("approved");
      const regenerated = normalizeRequirement({
        sourceRefs: requirement.sourceRefs,
        Spanish: requirement.Spanish,
        EnglishControlled: requirement.EnglishControlled,
        applicabilityExpression: requirement.applicabilityExpression,
        severity: requirement.severity,
        evidenceRequired: requirement.evidenceRequired,
        effectiveFromUtc: requirement.effectiveFromUtc,
        interpretationStatus: requirement.interpretationStatus,
        reviewerIds: requirement.reviewerIds,
        predicate: requirement.predicate,
        sourceLanguageReview: requirement.sourceLanguageReview,
        applicabilityReview: requirement.applicabilityReview,
        ...(requirement.unresolvedRationale === undefined ? {} : { unresolvedRationale: requirement.unresolvedRationale }),
      });
      expect(regenerated.requirementId).toBe(requirement.requirementId);
    }
    expect(artifact.requirements.find((item) => item.sourceRefs[0].locator.section === "94.250")?.unresolvedRationale).toContain("Reserved");
  });

  it("keeps RACAE 219 explicitly blocked and free of invented controls", async () => {
    const artifact = JSON.parse(await readFile(resolve(root, "docs/regulations/normalized/racae219-sms.json"), "utf8")) as { artifactStatus: string; requirements: unknown[]; claims: unknown[]; reason: string };
    expect(artifact.artifactStatus).toBe("blocked");
    expect(artifact.requirements).toEqual([]);
    expect(artifact.claims).toEqual([]);
    expect(artifact.reason).toContain("not available");
  });

  it("validates citations against the immutable register without requiring production review promotion", () => {
    const requirement = normalizeRequirement(input());
    expect(() => validateRequirementCitations([requirement], register())).not.toThrow();
  });

  it("rejects malformed locators and mismatched extraction hashes", () => {
    expect(() => normalizeRequirement(input({ sourceRefs: [{ ...input().sourceRefs[0], locator: { section: "94.15", page: 0 } }] }))).toThrow("malformed section locator");
    const requirement = normalizeRequirement(input());
    expect(() => validateRequirementCitations([requirement], register(source({ extractionSha256: "a".repeat(64) })))).toThrow("extraction hash does not match");
  });

  it("rejects falsely approved rules without accepted source evidence", () => {
    const accepted = { status: "accepted", reviewerRole: "qualified authority", reviewerId: "qualified-reviewer", rationale: "Accepted." } as const;
    const requirement = normalizeRequirement(input({ interpretationStatus: "approved", sourceLanguageReview: accepted, applicabilityReview: accepted }));
    expect(() => validateRequirementCitations([requirement], register(source({ review: "in-review" })))).toThrow("approved without accepted source evidence");
    expect(() => validateRequirementCitations([requirement], register(source()))).not.toThrow();
  });

  it("rejects English-only authority and preserves IDs/predicates across locale changes", () => {
    const english = normalizeRequirement(input({ sourceRefs: [{ ...input().sourceRefs[0], sourceId: "english-source" as never, quoteLanguage: "en" }] }));
    expect(() => validateRequirementCitations([english], register(source({ sourceId: "english-source" as never, language: "en" })))).toThrow("Spanish-language authority");
    const first = normalizeRequirement(input());
    const priorLocale = process.env.LANG;
    process.env.LANG = "en_US.UTF-8";
    const second = normalizeRequirement(input());
    process.env.LANG = priorLocale;
    expect(second.requirementId).toBe(first.requirementId);
    expect(second.predicate).toBe(first.predicate);
  });

  it("builds only Spanish-evidence-backed controlled translations", () => {
    const evidence = { requirementId: "req-test", sourceRef: input().sourceRefs[0], sourceLanguageReview: input().sourceLanguageReview };
    expect(buildControlledTranslation("Texto fuente", "Source text", evidence)).toMatchObject({ sourceLanguage: "es", targetLanguage: "en", translationStatus: "draft" });
    expect(() => buildControlledTranslation("Texto", "Text", { ...evidence, sourceRef: { ...evidence.sourceRef, quoteLanguage: "en" } })).toThrow("Spanish source evidence");
  });
});
