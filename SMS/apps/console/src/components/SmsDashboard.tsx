import type { JSX } from "react";
import { HumanPerformancePanel, type HumanPerformanceAlertView, type HumanPerformanceStatusView } from "./HumanPerformancePanel.js";

export interface SmsHazardView { readonly id: string; readonly title: string; readonly residualRisk: string; readonly ownerId: string; readonly status: "open" | "controlled" | "accepted" | "closed" }
export interface SmsCapaView { readonly id: string; readonly ownerId: string; readonly dueAtUtc: string; readonly status: "open" | "verified" | "closed" }
export interface SmsDashboardProps {
  readonly hazards?: readonly SmsHazardView[];
  readonly capa?: readonly SmsCapaView[];
  readonly spi?: { readonly level: "normal" | "alert" | "action" | "unknown"; readonly reason: string; readonly dataQuality: "complete" | "incomplete" | "stale" };
  readonly erp?: { readonly status: "ready" | "blocked" | "expired" | "unknown"; readonly missing: readonly string[]; readonly nextReviewAtUtc?: string };
  readonly moc?: { readonly id: string; readonly changeDescription: string; readonly status: "open" | "approved" | "implemented" | "verified" | "closed" };
  readonly humanPerformance?: { readonly status: HumanPerformanceStatusView; readonly alert: HumanPerformanceAlertView };
}

const defaultHazards: readonly SmsHazardView[] = [
  { id: "HZ-024", title: "Wildlife strike exposure", residualRisk: "High", ownerId: "Safety · A. Rojas", status: "open" },
  { id: "HZ-031", title: "Link dropout on north sector", residualRisk: "Medium", ownerId: "Engineering · J. León", status: "controlled" },
];
const defaultCapa: readonly SmsCapaView[] = [{ id: "CAPA-018", ownerId: "A. Rojas", dueAtUtc: "2026-08-14", status: "open" }, { id: "CAPA-011", ownerId: "J. León", dueAtUtc: "2026-08-12", status: "verified" }];
const defaultHumanPerformance: NonNullable<SmsDashboardProps["humanPerformance"]> = { status: { userId: "OPS-17", role: "Safety officer", dutyPeriodId: "DUTY-042", qualificationStatus: "current", fatigueSelfDeclaration: "able", screenExposureMinutes: 94, workloadLevel: "moderate", alertLoad: 2, status: "available", evidenceRefs: ["policy:HP-1"] }, alert: { level: "moderate", unresolved: 2, escalationRequired: false, evidenceRefs: ["policy:AL-1"] } };

export function SmsDashboard({ hazards = defaultHazards, capa = defaultCapa, spi = { level: "alert", reason: "Two open high-severity findings", dataQuality: "complete" }, erp = { status: "ready", missing: [], nextReviewAtUtc: "2026-09-01" }, moc = { id: "MOC-007", changeDescription: "Offline map package refresh", status: "verified" }, humanPerformance = defaultHumanPerformance }: SmsDashboardProps): JSX.Element {
  return (
    <section className="sms-dashboard" aria-labelledby="sms-dashboard-heading">
      <div className="dashboard-heading"><div><span className="section-kicker">Organizational assurance</span><h1 id="sms-dashboard-heading">Safety management system</h1></div><span className="dashboard-badge">RACAE 219 · LOCAL EVIDENCE</span></div>
      <div className="sms-card-grid">
        <section className="sms-card sms-hazards"><CardHeading title="Hazards" detail={`${hazards.length} tracked`} /><div className="sms-items">{hazards.map((hazard) => <div className="sms-item" key={hazard.id}><div><strong>{hazard.title}</strong><span className="mono">{hazard.id} · {hazard.status}</span></div><div className="sms-item-meta"><b>{hazard.residualRisk}</b><span>{hazard.ownerId}</span></div></div>)}</div></section>
        <section className="sms-card"><CardHeading title="CAPA" detail={`${capa.filter((item) => item.status === "open").length} open`} /><div className="sms-items">{capa.map((item) => <div className="sms-item" key={item.id}><div><strong className="mono">{item.id}</strong><span>{item.status}</span></div><div className="sms-item-meta"><b>{item.ownerId}</b><span>Due {item.dueAtUtc}</span></div></div>)}</div></section>
        <section className="sms-card sms-indicator"><CardHeading title="SPI" detail="Safety performance indicator" /><div className={`sms-big-status status-${spi.level}`}>{spi.level}</div><p>{spi.reason}</p><span className="mono">Data quality · {spi.dataQuality}</span></section>
        <section className="sms-card"><CardHeading title="ERP" detail="Emergency response readiness" /><div className={`sms-big-status status-${erp.status}`}>{erp.status}</div><p>{erp.missing.length === 0 ? "No missing readiness elements" : `Missing · ${erp.missing.join(", ")}`}</p><span className="mono">Next review · {erp.nextReviewAtUtc ?? "—"}</span></section>
        <section className="sms-card"><CardHeading title="MOC" detail="Management of change" /><div className="sms-change"><strong className="mono">{moc.id}</strong><span>{moc.changeDescription}</span><b>{moc.status}</b></div></section>
      </div>
      <HumanPerformancePanel {...humanPerformance} />
    </section>
  );
}

function CardHeading({ title, detail }: { readonly title: string; readonly detail: string }): JSX.Element {
  return <div className="sms-card-heading"><h2>{title}</h2><span>{detail}</span></div>;
}
