export interface AcceptanceDecisionValidation {
  readonly ok: boolean;
  readonly mode: "dry-run";
  readonly signatureId: string;
  readonly scope: string;
  readonly requiredRole: string;
  readonly projectedStatus: "pending" | "accepted" | "accepted-with-conditions" | "rejected";
  readonly packetId: string;
  readonly artifactSha256: string;
}

export interface DecisionValidationOptions {
  readonly asOfUtc: string;
}

export function validateAcceptanceDecision(
  root: string,
  packetPath: string,
  decisionPath: string,
  options: DecisionValidationOptions,
): Promise<AcceptanceDecisionValidation>;
