import type { NormalizedRequirement, SourceId } from "./types.js";
import { SourceRegister } from "./source-register.js";

/** Ensures every source-backed requirement is supported by accepted evidence. */
export function assertClaimTraceable(claim: NormalizedRequirement, register: SourceRegister): void {
  if (!claim.sourceRefs || claim.sourceRefs.length === 0) {
    throw new Error(`Claim ${claim.requirementId} has no accepted evidence`);
  }
  for (const evidence of claim.sourceRefs) {
    const source = register.get(evidence.sourceId as SourceId);
    if (source === undefined || source.review !== "accepted" || source.supersededBy !== undefined) {
      throw new Error(`Claim ${claim.requirementId} has no accepted evidence for source ${evidence.sourceId}`);
    }
    if (evidence.reviewState !== "accepted") {
      throw new Error(`Claim ${claim.requirementId} has no accepted evidence for ${evidence.evidenceId}`);
    }
    if (source.extractionSha256 !== undefined && source.extractionSha256 !== evidence.extractionSha256) {
      throw new Error(`Claim ${claim.requirementId} evidence extraction hash does not match source`);
    }
  }
}

