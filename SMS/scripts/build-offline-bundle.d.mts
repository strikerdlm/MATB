export interface BundledAcceptanceEvidence {
  readonly recordPath: "reports/acceptance/operational-readiness-record.json";
  readonly checklistPath: "reports/acceptance/state-aviation-acceptance-checklist.md";
  readonly knownLimitationsPath: "reports/acceptance/known-limitations.md";
  readonly signatureLogPath: "reports/acceptance/verification-signatures.jsonl";
  readonly qualification: "accepted" | "blocked";
  readonly operationalReady: boolean;
  readonly signatureCount: number;
}

export function copyAcceptanceEvidence(stage: string): Promise<BundledAcceptanceEvidence>;
