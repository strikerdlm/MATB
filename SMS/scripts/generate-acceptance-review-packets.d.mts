export interface GenerateReviewPacketOptions {
  readonly asOfUtc: string;
  readonly scopes?: readonly string[];
}

export interface ReviewPacketManifest {
  readonly schemaVersion: "1.0";
  readonly recordType: "review-packet";
  readonly packetId: string;
  readonly releaseId: string;
  readonly readinessRecordId: string;
  readonly asOfUtc: string;
  readonly scope: string;
  readonly title: string;
  readonly requiredReviewerRoles: readonly string[];
  readonly currentStatus: "pending" | "accepted" | "accepted-with-conditions" | "rejected";
  readonly roleCoverage: readonly { readonly role: string; readonly signatureId: string | null; readonly decision: "accept" | "accept-with-conditions" | "reject" | null }[];
  readonly checklistHeading: string;
  readonly blockers: readonly { readonly code: string; readonly scope?: string; readonly limitationId?: string; readonly detail: string }[];
  readonly acceptanceStateFingerprint: string;
  readonly evidence: readonly { readonly path: string; readonly sha256: string }[];
}

export interface UnsignedDecisionTemplate {
  readonly schemaVersion: "1.0";
  readonly recordType: "unsigned-decision-template";
  readonly signatureId: null;
  readonly sourcePacketId: string;
  readonly sourcePacketPath: string;
  readonly sourcePacketSha256: string;
  readonly supersedesSignatureId: null;
  readonly releaseId: string;
  readonly scope: string;
  readonly reviewer: { readonly identity: null; readonly identityType: "human"; readonly organizationUnit: null; readonly role: null };
  readonly decision: null;
  readonly signedAtUtc: null;
  readonly evidenceHashes: readonly { readonly path: string; readonly sha256: string }[];
  readonly conflicts: null;
  readonly conditions: null;
  readonly reviewDueAtUtc: null;
  readonly systemOfRecordRef: null;
  readonly institutionalArtifact: { readonly path: null; readonly sha256: null };
}

export function buildAcceptanceReviewPacketManifest(
  root: string,
  scope: string,
  options: { readonly asOfUtc: string },
): Promise<ReviewPacketManifest>;

export function generateAcceptanceReviewPackets(
  root: string,
  output: string,
  options: GenerateReviewPacketOptions,
): Promise<{ readonly packetCount: number; readonly packets: readonly { readonly manifest: ReviewPacketManifest; readonly template: UnsignedDecisionTemplate }[] }>;
