export const REQUIRED_REVIEW_SCOPES: readonly [
  "cybersecurity-deployment", "emergency-response", "human-factors-protocol",
  "official-geospatial-data", "operational-checklist", "racae-interpretation-translation",
  "research-separation", "risk-authority", "training-safety-promotion",
];
export const REVIEW_STATUSES: readonly ["pending", "accepted", "accepted-with-conditions", "rejected"];
export const KNOWN_LIMITATION_CATEGORIES: readonly [
  "aircraft-capability", "terrain-obstacle", "official-data-dependency", "telemetry-field",
  "profile-boundary", "translation-gap", "research-limitation", "human-factors",
  "cybersecurity-deployment", "performance-validation",
];
export const ACCEPTANCE_EVIDENCE_PATHS: readonly [
  "docs/release/known-limitations.md", "docs/release/release-manifest.json",
  "docs/release/release-manifest.sig", "docs/release/release-public-key.pem",
  "docs/release/sbom.cdx.json", "docs/release/security-scan.json",
  "docs/release/state-aviation-acceptance-checklist.md", "docs/release/test-report.json",
  "docs/release/verification-matrix.md",
];
export const ACCEPTANCE_STATE_PATHS: readonly [
  "docs/release/operational-readiness-record.json", "docs/release/verification-signatures.jsonl",
  "docs/release/state-aviation-acceptance-checklist.md", "docs/release/known-limitations.md",
  "docs/release/verification-matrix.md", "docs/release/release-manifest.json",
];

export type AcceptanceDecision = "accept" | "accept-with-conditions" | "reject";
export type ReviewStatus = "pending" | "accepted" | "accepted-with-conditions" | "rejected";
export interface EvidenceHash {
  readonly path: string;
  readonly sha256: string;
}
export interface InstitutionalDecision {
  readonly schemaVersion: "1.0";
  readonly recordType: "institutional-decision";
  readonly signatureId: string;
  readonly sourcePacketId: string;
  readonly sourcePacketPath: string;
  readonly sourcePacketSha256: string;
  readonly supersedesSignatureId: string | null;
  readonly releaseId: string;
  readonly reviewer: {
    readonly identity: string;
    readonly identityType: "human";
    readonly organizationUnit: string;
    readonly role: string;
  };
  readonly scope: string;
  readonly decision: AcceptanceDecision;
  readonly signedAtUtc: string;
  readonly evidenceHashes: readonly EvidenceHash[];
  readonly conflicts: readonly string[];
  readonly conditions: readonly string[];
  readonly reviewDueAtUtc: string;
  readonly systemOfRecordRef: string;
  readonly institutionalArtifact: EvidenceHash;
}
export interface RequiredReview {
  readonly scope: string;
  readonly status: ReviewStatus;
  readonly requiredReviewerRoles: readonly string[];
  readonly signatureIds: readonly string[];
}
export interface ReviewDecisionState {
  readonly status: ReviewStatus;
  readonly missingRoles: readonly string[];
  readonly roleHeads: readonly { readonly role: string; readonly signatureId: string; readonly decision: AcceptanceDecision }[];
  readonly violations: readonly { readonly code: string; readonly scope: string; readonly detail: string }[];
}

export function canonicalJson(value: unknown): string | undefined;
export function sha256Bytes(bytes: string | NodeJS.ArrayBufferView): string;
export function sha256File(path: string): Promise<string>;
export function nonEmptyString(value: unknown): value is string;
export function exactUtc(value: unknown): boolean;
export function readJsonLines(path: string): Promise<unknown[]>;
export function resolveContainedExistingFile(root: string, candidate: unknown, label?: string): Promise<string>;
export function isControlledAcceptanceArtifactPath(candidate: unknown): boolean;
export function signatureRecordFailure(decision: unknown): string | undefined;
export function deriveReviewDecisionState(review: RequiredReview | unknown, decisions: readonly InstitutionalDecision[] | readonly unknown[]): ReviewDecisionState;
