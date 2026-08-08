import { describe, expect, it } from "vitest";
import { SourceRegister, assertClaimTraceable } from "../src/index.js";
import type { EvidenceId, NormalizedRequirement, SourceRecord } from "../src/types.js";

const source: SourceRecord = {
  sourceId: "source-a" as SourceRecord["sourceId"], title: "Source", authority: "FAC", authorityRank: 1,
  canonicalUri: "https://example.gov/source.pdf", localPath: "source.pdf", mediaType: "application/pdf", language: "es",
  retrievedAtUtc: "2026-08-08T12:00:00Z", sha256: "a".repeat(64), extractionSha256: "b".repeat(64),
  sensitivity: "unclassified-controlled", licenseOrRestriction: "official", review: "accepted",
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
    expect(() => assertClaimTraceable(claim, register)).not.toThrow();
  });

  it("rejects a normalized requirement with no accepted evidence", () => {
    const register = new SourceRegister(); register.append(source);
    expect(() => assertClaimTraceable({ ...claim, sourceRefs: [{ ...claim.sourceRefs[0], reviewState: "unreviewed" }] }, register)).toThrow("accepted evidence");
  });
});
