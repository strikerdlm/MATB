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

export interface JsonSnapshot {
  readonly bytes: Buffer;
  readonly sha256: string;
  readonly value: unknown;
}

/** Testable regular-file snapshot reader used by decision, packet, record, and artifact validation. */
export function readRegularJsonSnapshot(
  path: string,
  label: string,
  afterBytesRead?: () => void | Promise<void>,
): Promise<JsonSnapshot>;

export function validateAcceptanceDecision(
  root: string,
  packetPath: string,
  decisionPath: string,
  options: DecisionValidationOptions,
): Promise<AcceptanceDecisionValidation>;
