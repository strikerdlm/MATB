export interface BundledAcceptanceEvidence {
  readonly recordPath: "reports/acceptance/operational-readiness-record.json";
  readonly checklistPath: "reports/acceptance/state-aviation-acceptance-checklist.md";
  readonly knownLimitationsPath: "reports/acceptance/known-limitations.md";
  readonly signatureLogPath: "reports/acceptance/verification-signatures.jsonl";
  readonly qualification: "accepted" | "blocked";
  readonly operationalReady: boolean;
  readonly signatureCount: number;
  readonly workflow: BundledAcceptanceWorkflow;
}

export interface BundledAcceptanceWorkflow {
  readonly currentPackets: readonly { readonly scope: string; readonly packetId: string; readonly path: string; readonly sha256: string }[];
  readonly evidenceMappings: readonly { readonly sourcePath: string; readonly bundlePath: string; readonly sha256: string }[];
  readonly recordedDecisions: readonly {
    readonly signatureId: string;
    readonly scope: string;
    readonly role: string;
    readonly sourcePacketPath: string;
    readonly packetBundlePath: string;
    readonly sourcePacketSha256: string;
    readonly artifactSourcePath: string;
    readonly artifactBundlePath: string;
    readonly artifactSha256: string;
  }[];
  readonly roleHeads: readonly { readonly scope: string; readonly role: string; readonly signatureId: string; readonly decision: string }[];
}

export function copyAcceptanceEvidence(stage: string, options: { readonly asOfUtc: string }): Promise<BundledAcceptanceEvidence>;
