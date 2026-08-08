import { describe, expect, it } from "vitest";
import { SourceRegister, assertClaimTraceable } from "../src/index.js";
import type { EvidenceId, NormalizedRequirement, SourceRecord } from "../src/types.js";

const source: SourceRecord = {
  sourceId: "source-a" as SourceRecord["sourceId"], title: "Source", authority: "FAC", authorityRank: 1,
  canonicalUri: "https://example.gov/source.pdf", localPath: "source.pdf", mediaType: "application/pdf", language: "es",
  retrievedAtUtc: "2026-08-08T12:00:00Z", sha256: "a".repeat(64), extractionSha256: "b".repeat(64),
  sensitivity: "unclassified-controlled", licenseOrRestriction: "official", review: "accepted",
  reviewerId: "reviewer", reviewSignature: "signature", reviewedAtUtc: "2026-08-01T00:00:00Z",
  validFromUtc: "2026-01-01T00:00:00Z", validUntilUtc: "2027-01-01T00:00:00Z",
};
const claim: NormalizedRequirement = {
  requirementId: "req-1", sourceRefs: [{ evidenceId: "ev-1" as EvidenceId, sourceId: source.sourceId, edition: "1",
    locator: { section: "1" }, quoteLanguage: "es", extractionSha256: source.extractionSha256!, reviewState: "accepted" }],
  Spanish: "Debe", EnglishControlled: "Must", applicabilityExpression: "true", severity: "hard", evidenceRequired: true,
  effectiveFromUtc: "2026-01-01T00:00:00Z", interpretationStatus: "approved", reviewerIds: ["reviewer"],
};

describe("assertClaimTraceable", () => {
  it("accepts a reviewed requirement with accepted evidence", () => {
    const register = new SourceRegister(); register.append(source);
    expect(() => assertClaimTraceable(claim, register, "2026-08-08T00:00:00Z")).not.toThrow();
  });

  it("rejects a normalized requirement with no accepted evidence", () => {
    const register = new SourceRegister(); register.append(source);
    expect(() => assertClaimTraceable({ ...claim, sourceRefs: [{ ...claim.sourceRefs[0], reviewState: "unreviewed" }] }, register, "2026-08-08T00:00:00Z")).toThrow("accepted evidence");
  });

  it("rejects an English-only hard claim", () => {
    const register = new SourceRegister(); register.append({ ...source, language: "en", sourceId: "english" as SourceRecord["sourceId"] });
    const englishClaim = { ...claim, sourceRefs: [{ ...claim.sourceRefs[0], sourceId: "english" as SourceRecord["sourceId"], quoteLanguage: "en" as const }] };
    expect(() => assertClaimTraceable(englishClaim, register, "2026-08-08T00:00:00Z")).toThrow("Spanish");
  });

  it("requires an explicit, exact UTC as-of timestamp and bounded current evidence for hard claims", () => {
    const register = new SourceRegister(); register.append(source);
    expect(() => assertClaimTraceable(claim, new SourceRegister(), "2026-08-08T00:00:00Z")).toThrow("accepted evidence");
    const unsigned = new SourceRegister(); unsigned.append({ ...source, reviewSignature: undefined });
    expect(() => assertClaimTraceable(claim, unsigned, "2026-08-08T00:00:00Z")).toThrow("unsigned");
    const expired = new SourceRegister(); expired.append({ ...source, validUntilUtc: "2026-08-01T00:00:00Z" });
    expect(() => assertClaimTraceable(claim, expired, "2026-08-08T00:00:00Z")).toThrow("stale");
    const noExtraction = new SourceRegister(); noExtraction.append({ ...source, extractionSha256: undefined });
    expect(() => assertClaimTraceable(claim, noExtraction, "2026-08-08T00:00:00Z")).toThrow("extraction hash");
    expect(() => assertClaimTraceable(claim, register)).toThrow("asOfUtc required");
    expect(() => assertClaimTraceable(claim, register, "2026-02-29T00:00:00Z")).toThrow("valid UTC timestamp");
    const missingBounds = new SourceRegister(); missingBounds.append({ ...source, validUntilUtc: undefined });
    expect(() => assertClaimTraceable(claim, missingBounds, "2026-08-08T00:00:00Z")).toThrow("bounds");
  });
});
