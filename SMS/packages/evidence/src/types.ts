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
  /** Workspace-relative text extraction whose hash is extractionSha256. */
  extractionPath?: string;
  sensitivity: "unclassified-controlled";
  licenseOrRestriction: string;
  review: "unreviewed" | "in-review" | "accepted" | "superseded" | "rejected";
  supersededBy?: SourceId;
  reviewerId?: string;
  reviewSignature?: string;
  reviewedAtUtc?: string;
  validFromUtc?: string;
  validUntilUtc?: string;
}

export interface SupersessionRelationship {
  relationshipId: string;
  supersededSourceId: SourceId;
  replacementSourceId: SourceId;
  recordedAtUtc: string;
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

export interface RequirementTranslation {
  requirementId: string;
  sourceLanguage: "es";
  targetLanguage: "en";
  translatedText: string;
  translationStatus: "draft" | "reviewed" | "approved";
  reviewerIds: readonly string[];
}

export interface SignedPackageManifest {
  packageId: string;
  kind: "regulatory" | "policy" | "map" | "weather" | "notam" | "terminology" | "software";
  issuer: string;
  version: string;
  issuedAtUtc: string;
  effectiveFromUtc: string;
  expiresAtUtc?: string;
  geographicScope?: string;
  contentSha256: string;
  signature: string;
  keyId: string;
  dependencies: string[];
}
