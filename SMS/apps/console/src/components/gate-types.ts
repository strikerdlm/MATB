export type GateName = "maintenance" | "operator" | "safety" | "commander";
export type GateDecision = "accept" | "block" | "escalate" | "pending" | "invalid";
export type GateRole = "maintainer" | "operator" | "safety" | "commander";

export interface GoverningRequirement {
  readonly title: string;
  readonly sourceExcerptEs: string;
  readonly translationEn: string;
  readonly sourceEdition: string;
  readonly sourceSection: string;
  readonly freshness: string;
  readonly evidenceHash: string;
  readonly reviewerStatus: string;
}

export interface GateDescriptor {
  readonly gate: GateName;
  readonly decision: GateDecision;
  readonly requiredRole: GateRole;
  readonly label?: string;
  readonly details?: readonly string[];
  readonly evidenceRef?: string;
}

export interface GateDecisionEvent {
  readonly gate: GateName;
  readonly decision: "accept" | "block" | "escalate";
}
