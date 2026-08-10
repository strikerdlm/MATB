import type { JSX } from "react";

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

export interface GateStatusProps {
  readonly gate: GateDescriptor;
  readonly reviewerRole?: GateRole;
  readonly kernelBlocked?: boolean;
  readonly governingRequirement?: GoverningRequirement;
  readonly onDecision?: (event: GateDecisionEvent) => void;
}

const ROLE_LABELS: Record<GateRole, string> = {
  maintainer: "Maintainer",
  operator: "Operator",
  safety: "Safety",
  commander: "Commander",
};

const GATE_NUMBERS: Record<GateName, string> = {
  maintenance: "01",
  operator: "02",
  safety: "03",
  commander: "04",
};

function visualStatus(decision: GateDecision): "pass" | "blocker" | "pending" {
  if (decision === "accept") return "pass";
  if (decision === "pending") return "pending";
  return "blocker";
}

function decisionLabel(decision: GateDecision): string {
  if (decision === "accept") return "PASS";
  if (decision === "block") return "BLOCKER";
  if (decision === "invalid") return "INVALID";
  if (decision === "escalate") return "ESCALATED";
  return "PENDING";
}

function statusGlyph(status: "pass" | "blocker" | "pending"): string {
  if (status === "pass") return "✓";
  if (status === "blocker") return "!";
  return "◷";
}

export function GateStatus({ gate, reviewerRole, kernelBlocked = false, governingRequirement, onDecision }: GateStatusProps): JSX.Element {
  const status = visualStatus(gate.decision);
  const authorized = reviewerRole === gate.requiredRole;
  const canAct = authorized && !kernelBlocked && gate.decision === "pending";
  const label = gate.label ?? gate.gate;
  const details = gate.details ?? [];
  const evidenceRef = gate.evidenceRef ?? "—";

  return (
    <article className={`gate-card gate-${status}`} data-gate={gate.gate}>
      <div className="gate-card-head">
        <div>
          <span className="gate-number">GATE {GATE_NUMBERS[gate.gate]}</span>
          <h3>{label}</h3>
        </div>
        <span className="gate-status" role="status" aria-label={`${label}: ${decisionLabel(gate.decision).toLowerCase()}`}>
          <span className={`status-glyph ${status}`} aria-hidden="true">{statusGlyph(status)}</span>
          {decisionLabel(gate.decision)}
        </span>
      </div>
      {details.length > 0 && (
        <div className="gate-details">
          {details.map((detail) => <span key={detail}>{detail}</span>)}
          <span>Evidence · <b className="mono">{evidenceRef}</b></span>
        </div>
      )}
      <div className="gate-action">
        {gate.decision === "accept" ? "All requirements satisfied" : gate.decision === "pending" ? "Awaiting accountable action" : "Actions required"}
      </div>
      <div className="gate-controls" aria-label={`${label} gate actions`}>
        <span className="gate-role">Required role · {ROLE_LABELS[gate.requiredRole]}</span>
        {authorized && <>
          <button type="button" disabled={!canAct} onClick={() => onDecision?.({ gate: gate.gate, decision: "accept" })}>
            Accept gate
          </button>
          <button type="button" disabled={!canAct} onClick={() => onDecision?.({ gate: gate.gate, decision: "block" })}>
            Block gate
          </button>
        </>}
      </div>
      <details className="gate-requirement" open={governingRequirement !== undefined}>
        <summary>Governing requirement</summary>
        {governingRequirement === undefined ? (
          <p>Requirement source is available in the evidence package.</p>
        ) : (
          <div className="requirement-detail">
            <strong>{governingRequirement.title}</strong>
            <p lang="es">{governingRequirement.sourceExcerptEs}</p>
            <p>{governingRequirement.translationEn}</p>
            <dl>
              <div><dt>Source</dt><dd>{governingRequirement.sourceEdition} · {governingRequirement.sourceSection}</dd></div>
              <div><dt>Freshness</dt><dd>{governingRequirement.freshness}</dd></div>
              <div><dt>Evidence hash</dt><dd className="mono">{governingRequirement.evidenceHash}</dd></div>
              <div><dt>Reviewer</dt><dd>{governingRequirement.reviewerStatus}</dd></div>
            </dl>
          </div>
        )}
      </details>
    </article>
  );
}
