export interface OperationalReadinessFinding {
  readonly code: string;
  readonly scope?: string;
  readonly limitationId?: string;
  readonly detail: string;
}

export interface OperationalReadinessReport {
  readonly ok: boolean;
  readonly operationalReady: boolean;
  readonly qualification: "accepted" | "blocked";
  readonly verifiedAtUtc: string;
  readonly signatureCount: number;
  readonly pendingReviewScopes: readonly string[];
  readonly blockers: readonly OperationalReadinessFinding[];
  readonly violations: readonly OperationalReadinessFinding[];
}

export interface OperationalReadinessOptions {
  readonly asOfUtc?: string;
  readonly recordRelativePath?: string;
  readonly signatureLogRelativePath?: string;
  readonly allowTransactionJournal?: boolean;
}

export function verifyOperationalReadiness(root?: string, options?: OperationalReadinessOptions): Promise<OperationalReadinessReport>;
