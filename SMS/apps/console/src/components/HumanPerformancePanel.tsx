import type { JSX } from "react";

export interface HumanPerformanceStatusView {
  readonly userId: string;
  readonly role: string;
  readonly dutyPeriodId: string;
  readonly qualificationStatus: "current" | "restricted" | "expired" | "unknown";
  readonly fatigueSelfDeclaration: "able" | "not-able" | "not-recorded";
  readonly screenExposureMinutes: number;
  readonly workloadLevel: "low" | "moderate" | "high" | "unknown";
  readonly alertLoad: number;
  readonly status: "available" | "restricted" | "unavailable" | "unknown";
  readonly evidenceRefs: readonly string[];
}

export interface HumanPerformanceAlertView {
  readonly level: "low" | "moderate" | "high" | "unknown";
  readonly unresolved: number;
  readonly escalationRequired: boolean;
  readonly evidenceRefs: readonly string[];
}

export interface HumanPerformancePanelProps {
  readonly status: HumanPerformanceStatusView;
  readonly alert: HumanPerformanceAlertView;
  readonly title?: string;
}

function titleCase(value: string): string {
  return value.replaceAll("-", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export function HumanPerformancePanel({ status, alert, title = "Human performance" }: HumanPerformancePanelProps): JSX.Element {
  const restricted = status.status !== "available" || alert.escalationRequired;
  return (
    <section className="control-panel human-performance-panel" aria-labelledby="human-performance-heading">
      <div className="control-panel-heading">
        <div><span className="section-kicker">Operational controls</span><h2 id="human-performance-heading">{title}</h2></div>
        <span className={`control-status ${restricted ? "is-restricted" : "is-clear"}`} role="status">{titleCase(status.status)}</span>
      </div>
      <div className="control-grid">
        <Metric label="Qualification" value={titleCase(status.qualificationStatus)} />
        <Metric label="Fatigue self-report" value={titleCase(status.fatigueSelfDeclaration)} />
        <Metric label="Duty period" value={status.dutyPeriodId} mono />
        <Metric label="Screen exposure" value={`${status.screenExposureMinutes} min`} />
        <Metric label="Workload" value={titleCase(status.workloadLevel)} />
        <Metric label="Alert load" value={`${status.alertLoad}`} />
      </div>
      <div className={`control-escalation ${alert.escalationRequired ? "is-alert" : ""}`}>
        <strong>{alert.escalationRequired ? "Human action required" : "Monitor and communicate"}</strong>
        <span>{titleCase(alert.level)} alert load · {alert.unresolved} unresolved · {status.role}</span>
      </div>
      <div className="control-evidence"><span>Evidence</span><b className="mono">{[...status.evidenceRefs, ...alert.evidenceRefs].join(" · ")}</b></div>
    </section>
  );
}

function Metric({ label, value, mono = false }: { readonly label: string; readonly value: string; readonly mono?: boolean }): JSX.Element {
  return <div className="control-metric"><span>{label}</span><strong className={mono ? "mono" : ""}>{value}</strong></div>;
}
