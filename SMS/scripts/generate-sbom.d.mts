export interface ReleaseVerificationCheck {
  readonly id: string;
  readonly status: "pass" | "fail" | "warn";
  readonly detail: string;
  readonly evidence: readonly string[];
}

export interface ReleaseVerificationReport {
  readonly schemaVersion: "1.0";
  readonly ok: boolean;
  readonly operationalReady: boolean;
  readonly releaseId: string;
  readonly sourceCommit: string;
  readonly checks: readonly ReleaseVerificationCheck[];
}

export function verifyRelease(
  repositoryRoot?: string,
  options?: { readonly artifactSource?: "worktree" | "source-commit" },
): Promise<ReleaseVerificationReport>;
