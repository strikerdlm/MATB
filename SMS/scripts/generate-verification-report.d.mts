export type VerificationResult = "not-run" | "pass" | "fail" | "conditional";

export interface VerificationArtifact {
  readonly kind: "source" | "command-output";
  readonly path: string;
  readonly sha256: string;
}

export interface VerificationReviewer {
  readonly type: "automated";
  readonly id: "fac-isr-sms-ci";
}

export interface VerificationRequirement {
  readonly coverage: string;
  readonly title: string;
  readonly command: string;
  readonly result: VerificationResult;
  readonly artifacts: readonly VerificationArtifact[];
  readonly reviewer: VerificationReviewer;
  readonly unresolvedLimitation: string;
}

export interface VerificationCommandResult {
  readonly key: string;
  readonly command: string;
  readonly result: Exclude<VerificationResult, "not-run">;
  readonly exitCode: number | null;
  readonly signal: NodeJS.Signals | null;
  readonly startedAtUtc: string;
  readonly finishedAtUtc: string;
  readonly durationMs: number;
  readonly stdoutSha256: string;
  readonly stderrSha256: string;
  readonly artifact: VerificationArtifact;
}

export interface VerificationReport {
  readonly schemaVersion: "1.0";
  readonly generatedAtUtc: string;
  readonly environment: { readonly node: string; readonly platform: string; readonly arch: string };
  readonly operationalReady: false;
  readonly readinessBlockers: readonly string[];
  readonly commands: readonly VerificationCommandResult[];
  readonly requirements: readonly VerificationRequirement[];
}

export function buildVerificationReport(
  root?: string,
  options?: { readonly execute?: boolean; readonly write?: boolean },
): Promise<VerificationReport>;
