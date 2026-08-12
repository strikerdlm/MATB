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

export function canonicalJson(value: unknown): string | undefined;
export function sha256Bytes(bytes: string | NodeJS.ArrayBufferView): string;
export function sha256File(path: string): Promise<string>;
export function nonEmptyString(value: unknown): value is string;
export function exactUtc(value: unknown): boolean;
export function readJsonLines(path: string): Promise<unknown[]>;
export function resolveContainedExistingFile(root: string, candidate: unknown, label?: string): Promise<string>;
