export interface TechnicalReleaseCheck {
  readonly id: string;
  readonly status: "pass" | "fail";
  readonly detail: string;
}

export interface TechnicalReleaseReport {
  readonly schemaVersion: "1.0";
  readonly ok: boolean;
  readonly technicalReady: boolean;
  readonly operationalReady: false;
  readonly releaseId: string;
  readonly sourceCommit: string;
  readonly checks: readonly TechnicalReleaseCheck[];
}

export interface TechnicalReleaseOptions {
  readonly expectedSourceCommit: string;
  readonly publicKeyPath: string;
  readonly manifestPath?: string;
  readonly signaturePath?: string;
  readonly publishDirectory?: string;
  readonly now?: Date;
  readonly maxEvidenceAgeMs?: number;
  readonly testOnlyFixture?: boolean;
}

export interface CandidateArtifactInspection {
  readonly target: "linux-x64" | "win32-x64" | "linux-amd64-oci";
  readonly kind: "native" | "oci";
  readonly artifactName: string;
  readonly artifactSha256: string;
  readonly artifactSizeBytes: number;
  readonly contentInventorySha256: string;
  readonly ociManifestDigest?: string;
  readonly ociConfigDigest?: string;
  readonly ociLayerDigests?: readonly string[];
  readonly ociDiffIds?: readonly string[];
  readonly ociReference?: string;
}

export function inspectCandidateArtifact(
  artifactPath: string,
  target: CandidateArtifactInspection["target"],
  options?: { readonly testOnlyFixture?: boolean; readonly expectedSourceCommit?: string },
): Promise<CandidateArtifactInspection>;

export function publishCandidateAtomic(
  root: string,
  manifest: unknown,
  manifestPath: string,
  signaturePath: string,
  publicKeyPath: string,
  destination: string,
): Promise<void>;

export function verifyTechnicalRelease(
  candidateRoot: string,
  options: TechnicalReleaseOptions,
): Promise<TechnicalReleaseReport>;
