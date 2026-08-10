export interface OfflineVerificationCheck {
  readonly id: string;
  readonly status: "pass" | "fail" | "warn";
  readonly detail: string;
  readonly evidence: readonly string[];
}

export interface OfflineVerificationReport {
  readonly schemaVersion: "1.0";
  readonly ok: boolean;
  readonly operationalReady: boolean;
  readonly releaseId: string;
  readonly verifiedAtUtc: string | null;
  readonly checks: readonly OfflineVerificationCheck[];
}

export interface OfflineVerificationOptions {
  readonly asOfUtc?: string;
  readonly noNetwork: boolean;
  readonly reportRelative?: string;
}

export function verifyBundle(
  bundleRoot: string,
  options: OfflineVerificationOptions,
): Promise<OfflineVerificationReport>;
