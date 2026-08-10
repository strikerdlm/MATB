import type { NormalizedRequirement, SourceId } from "./types.js";
import type { SourceRegister } from "./source-register.js";
import { isUtcTimestamp } from "./source-validation.js";

/** Ensures every source-backed requirement is supported by accepted evidence. */
export function assertClaimTraceable(claim: NormalizedRequirement, register: SourceRegister, asOfUtc?: string): void {
  if (claim.severity === "hard" && asOfUtc === undefined) throw new Error("asOfUtc required for hard claims");
  if (asOfUtc !== undefined && !isUtcTimestamp(asOfUtc)) throw new Error("asOfUtc must be a valid UTC timestamp");
  if (!claim.sourceRefs || claim.sourceRefs.length === 0) {
    throw new Error(`Claim ${claim.requirementId} has no accepted evidence`);
  }
  for (const evidence of claim.sourceRefs) {
    const source = register.get(evidence.sourceId as SourceId);
    if (source === undefined || source.review !== "accepted" || source.supersededBy !== undefined || register.isSuperseded(evidence.sourceId as SourceId)) {
      throw new Error(`Claim ${claim.requirementId} has no accepted evidence for source ${evidence.sourceId}`);
    }
    if (evidence.reviewState !== "accepted") {
      throw new Error(`Claim ${claim.requirementId} has no accepted evidence for ${evidence.evidenceId}`);
    }
    if (claim.severity === "hard" && (!source.extractionSha256 || source.extractionSha256 !== evidence.extractionSha256)) {
      throw new Error(`Claim ${claim.requirementId} evidence extraction hash does not match source`);
    }
    if (claim.severity === "hard" && (!source.reviewerId || !source.reviewSignature || !source.reviewedAtUtc)) throw new Error(`Claim ${claim.requirementId} source review is unsigned`);
    if (claim.severity === "hard" && (!source.validFromUtc || !source.validUntilUtc)) throw new Error(`Claim ${claim.requirementId} source validity bounds are missing`);
    if (claim.severity === "hard" && ((Date.parse(asOfUtc!) < Date.parse(source.validFromUtc!)) || Date.parse(asOfUtc!) >= Date.parse(source.validUntilUtc!))) throw new Error(`Claim ${claim.requirementId} source evidence is stale`);
  }
  if (claim.severity === "hard" && !claim.sourceRefs.some((e) => e.reviewState === "accepted" && e.quoteLanguage === "es" && register.get(e.sourceId)?.language !== "en" && !register.isSuperseded(e.sourceId))) throw new Error(`Claim ${claim.requirementId} has no accepted Spanish evidence`);
}
