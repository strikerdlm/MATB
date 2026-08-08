export type EvidenceId = string & { readonly __brand: "EvidenceId" };
export type SourceId = string & { readonly __brand: "SourceId" };

export interface SourceRecord {
  sourceId: SourceId;
  title: string;
  authority: string;
  authorityRank: 1 | 2 | 3 | 4 | 5 | 6 | 7;
  canonicalUri: string;
  localPath: string;
  mediaType: string;
  language: "es" | "en" | "multi";
  publicationDate?: string;
  amendmentDate?: string;
  effectiveFromUtc?: string;
  retrievedAtUtc: string;
  sha256: string;
  extractionSha256?: string;
  sensitivity: "unclassified-controlled";
  licenseOrRestriction: string;
  review: "unreviewed" | "in-review" | "accepted" | "superseded" | "rejected";
  supersededBy?: SourceId;
}

export interface EvidenceReference {
  evidenceId: EvidenceId;
  sourceId: SourceId;
  edition: string;
  locator: { section?: string; page?: number; paragraph?: string };
  quoteLanguage: "es" | "en";
  extractionSha256: string;
  reviewerId?: string;
  reviewState: "unreviewed" | "accepted" | "rejected";
}

export interface NormalizedRequirement {
  requirementId: string;
  sourceRefs: EvidenceReference[];
  Spanish: string;
  EnglishControlled: string;
  applicabilityExpression: string;
  severity: "hard" | "soft" | "advisory";
  evidenceRequired: boolean;
  effectiveFromUtc: string;
  interpretationStatus: "draft" | "qualified-review" | "approved" | "superseded";
  reviewerIds: string[];
}
