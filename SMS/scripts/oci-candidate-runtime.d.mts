export interface VerifiedOciIdentity {
  readonly artifactSha256: string;
  readonly ociReference: string;
  readonly ociConfigDigest: string;
  readonly ociDiffIds: readonly string[];
}

export function verifiedOciReference(artifactSha256: string): string;
export function validateLoadedOciIdentity(loaded: unknown, expected: Pick<VerifiedOciIdentity, "ociConfigDigest" | "ociDiffIds">): { layerCount: number };
export function prepareVerifiedOciCandidate(sourceReference: string, expected: VerifiedOciIdentity): Promise<string>;
export function removeVerifiedOciCandidate(reference: string): Promise<void>;
