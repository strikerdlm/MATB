export interface OperationalBlockReport {
  readonly ok: boolean; readonly operationalReady: boolean; readonly qualification: string;
  readonly pendingReviewScopes: readonly string[]; readonly violations: readonly unknown[];
  readonly blockers: readonly { readonly code?: string; readonly scope?: string }[];
}
export function validateExpectedOperationalBlock(report: OperationalBlockReport, exitCode: number): { readonly pendingReviewCount: number };
