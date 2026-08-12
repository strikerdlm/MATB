import { useMemo, useState } from "react";
import type { JSX, ReactNode } from "react";
import { getLabels, type Locale } from "../i18n/registry.js";
import { MissionSafetyStrip } from "../components/MissionSafetyStrip.js";
import type { GateDescriptor } from "../components/GateStatus.js";
import { MapWorkspace, type MapFinding, type MapRoute } from "../components/MapWorkspace.js";
import { TelemetryPanel } from "../components/TelemetryPanel.js";
import { RiskPanel } from "../components/RiskPanel.js";
import { SmsDashboard } from "../components/SmsDashboard.js";
import { ResearchProtocolPanel } from "../components/ResearchProtocolPanel.js";
import { ResearchSessionPanel } from "../components/ResearchSessionPanel.js";
import { routeMode } from "./routes.js";

export interface AppShellProps {
  readonly initialPath?: string;
  readonly initialLocale?: Locale;
}

type IconName = "home" | "shield" | "warning" | "sliders" | "risk" | "route" | "pulse" | "file" | "folder" | "edit" | "settings" | "download" | "wifi" | "check" | "stop" | "clock" | "layers" | "crosshair";

const navItems: readonly { icon: IconName; labelKey: keyof ReturnType<typeof getLabels>; path: string }[] = [
  { icon: "home", labelKey: "overview", path: "/missions" },
  { icon: "shield", labelKey: "safetyReview", path: "/missions/mission-1/review" },
  { icon: "warning", labelKey: "hazards", path: "/missions/mission-1/review#hazards" },
  { icon: "sliders", labelKey: "controls", path: "/missions/mission-1/review#controls" },
  { icon: "risk", labelKey: "risk", path: "/missions/mission-1/review#risk" },
  { icon: "route", labelKey: "profile", path: "/missions/mission-1/plan" },
  { icon: "pulse", labelKey: "telemetry", path: "/missions/mission-1/monitor" },
  { icon: "file", labelKey: "evidence", path: "/missions/mission-1/review#evidence" },
  { icon: "file", labelKey: "reports", path: "/reports" },
  { icon: "folder", labelKey: "documents", path: "/documents" },
  { icon: "edit", labelKey: "notes", path: "/notes" },
  { icon: "settings", labelKey: "configuration", path: "/sms" },
  { icon: "pulse", labelKey: "research", path: "/research" },
];

const missionSafetyFixture = {
  missionId: "M24-0518-ISR",
  phase: "UnderReview",
  aircraftClass: "IA",
  flightRule: "VFR",
  visualCondition: "VLOS",
  configuration: "unarmed-isr",
  lastUpdatedLocal: "18 May 2024 09:28",
  freshness: { telemetry: "09:25", evidence: "09:25" },
  operatorState: "Assigned · current",
} as const;

const missionGateFixture: readonly GateDescriptor[] = [
  { gate: "maintenance", decision: "accept", requiredRole: "maintainer", details: ["Aircraft status · serviceable", "Deferred items · 0 active", "Maint. release · 18 May 08:10"], evidenceRef: "EV-MNT-00091" },
  { gate: "operator", decision: "accept", requiredRole: "operator", details: ["Crew currency · current", "Training · current", "Ops authorization · valid"], evidenceRef: "EV-OPR-00142" },
  { gate: "safety", decision: "block", requiredRole: "safety", details: ["Open hazards · 2 high", "Residual risk · not acceptable", "Mitigations · incomplete"], evidenceRef: "EV-SAF-00077" },
  { gate: "commander", decision: "pending", requiredRole: "commander", details: ["Mission approval · pending", "Risk acceptance · pending", "Comments · —"], evidenceRef: "—" },
];

const mapPackageFixture = { packageId: "MAP-COLOMBIA-2024Q2", version: "1.2.0", manifestHash: "sha256:deadbeef2024", freshness: "Current · 18 May 2024 09:25" } as const;
const mapRouteFixture: MapRoute = { routeId: "ISR_SWEEP_120", distanceNm: 214, waypoints: [{ id: "WP01", label: "Puerto Santander", x: 20, y: 65 }, { id: "WP02", label: "Tibú", x: 280, y: 118 }, { id: "WP03", label: "Sardinata", x: 398, y: 158 }, { id: "WP04", label: "La Gabarra", x: 555, y: 198 }, { id: "WP05", label: "Convención", x: 680, y: 318 }] };
const mapFindingsFixture: readonly MapFinding[] = [{ id: "F-01", label: "Wildlife strike risk", severity: "high", x: 398, y: 158 }, { id: "F-02", label: "Terrain clearance review", severity: "medium", x: 555, y: 198 }];
const telemetryFixture = { aircraft: { aircraftId: "FAC-1287", platform: "ISR-1", approvedMinimumReservePercent: 30 }, telemetry: { capturedAtLocal: "18 May 2024 09:25:31", latitude: "08° 23.456′ N", longitude: "072° 45.789′ W", altitude: "FL098", groundspeed: "210 KT", heading: "123°", verticalRate: "+500 FPM", energyPercent: 62, batteryHealth: "NOMINAL", linkLatencyMs: 70, linkLossPercent: 0, gnss: "3D FIX", activeLeg: "WP03 → WP04", deviation: "Within tolerance", reservePercent: 38 }, degraded: false } as const;
const researchProtocolFixture = { id: "PROTOCOL-MATB-01", version: "1.0.0", title: "MATB workload and interface study", ethicsApprovalId: "ETHICS-2026-041", status: "current", permittedSensors: ["matb", "hrv"], permittedInstruments: ["NASA-TLX", "SAGAT"] } as const;
const researchSessionFixture = { participantCode: "P-017", conditionAssignment: "baseline", startedAtUtc: "2026-08-10T15:00:00.000Z", instrumentProgress: "NASA-TLX · 1/1 · SAGAT · 2/3" } as const;

export function AppShell({ initialPath = "/missions", initialLocale = "en" }: AppShellProps): JSX.Element {
  const [path, setPath] = useState(initialPath);
  const [locale, setLocale] = useState<Locale>(initialLocale);
  const [night, setNight] = useState(true);
  const labels = useMemo(() => getLabels(locale), [locale]);
  const activePath = path.split("#")[0];

  return (
    <div className={`console-shell ${night ? "theme-night" : "theme-day"}`}>
      <aside className="side-rail" aria-label="Primary navigation">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">✦</span>
          <div>
            <strong>FAC ISR SMS</strong>
            <span>Safety management system</span>
          </div>
        </div>
        <nav aria-label="Mission navigation" className="nav-list">
          {navItems.map((item) => (
            <button
              aria-label={labels[item.labelKey]}
              className={`nav-item ${activePath === item.path.split("#")[0] ? "is-active" : ""}`}
              key={item.path}
              onClick={() => setPath(item.path)}
              type="button"
            >
              <Icon name={item.icon} />
              <span>{labels[item.labelKey]}</span>
            </button>
          ))}
        </nav>
        <div className="package-status">
          <div className="package-header"><Icon name="download" /><span>Data source</span></div>
          <strong>Local package</strong>
          <span className="mono">MAP-COLOMBIA-2024Q2</span>
          <span className="package-ok"><Icon name="check" /> {labels.mapCurrent}</span>
        </div>
      </aside>

      <main className="main-frame">
        <header className="top-bar">
          <div className="mission-meta">
            <Meta label="Mission ID" value="M24-0518-ISR" />
            <Meta label="Mission name" value="Vigilancia frontera norte" wide />
            <Meta label="Date (local)" value="18 May 2024 · 09:32" />
            <Meta label="Crew role" value="Safety officer (read-only)" />
          </div>
          <div className="top-controls">
            <span className="mode-label"><Icon name="check" /> {labels.offline}</span>
            <button className="locale-toggle" onClick={() => setLocale(locale === "en" ? "es" : "en")} type="button" aria-label="Change language">
              {locale.toUpperCase()} <span>/</span> {locale === "en" ? "ES" : "EN"}
            </button>
            <button className="theme-toggle" onClick={() => setNight(!night)} type="button" aria-label="Toggle day and night theme">
              <span aria-hidden="true">☼</span><span className={`toggle-track ${night ? "is-night" : ""}`}><span /></span><span aria-hidden="true">☾</span>
            </button>
          </div>
        </header>

        <div className="classification-banner">{labels.unclassified}</div>

        <MissionSafetyStrip
          mission={missionSafetyFixture}
          safetyResult={{ status: "blocked", blockers: [{ code: "SAFETY_GATE_BLOCKED", explanation: "GATE 03 · Safety blocker", severity: "hard" }] }}
          gates={missionGateFixture.map((gate) => ({ ...gate, label: labels[gate.gate === "maintenance" ? "gateMaintenance" : gate.gate === "operator" ? "gateOperator" : gate.gate === "safety" ? "gateSafety" : "gateCommander"] }))}
          locale={locale}
          governingRequirements={{ safety: { title: "Configuration out of scope", sourceExcerptEs: "La configuración declarada no está dentro del alcance autorizado.", translationEn: "The declared configuration is outside the authorized scope.", sourceEdition: "FAC ISR SMS 2024.2", sourceSection: "§ 4.3.1", freshness: "Current · 18 May 2024 09:25", evidenceHash: "sha256:ev-saf-00077", reviewerStatus: "Safety review required" } }}
        />

        {activePath === "/sms" ? <SmsDashboard /> : activePath === "/research" ? <section className="research-workspace"><ResearchProtocolPanel authorized protocol={researchProtocolFixture} /><ResearchSessionPanel authorized session={researchSessionFixture} /></section> : <section className="workspace" aria-label={labels.mapWorkspace}>
          <MapWorkspace packageDirectory={mapPackageFixture} route={mapRouteFixture} findings={mapFindingsFixture} mode={routeMode(path)} />
          <aside className="evidence-rail" aria-label="Mission evidence and telemetry">
            <TelemetryPanel {...telemetryFixture} locale={locale} />
            <RiskPanel findings={mapFindingsFixture} residualBand="High" approvedReservePercent={telemetryFixture.aircraft.approvedMinimumReservePercent} />
            <EvidencePanel labels={labels} />
            <NotesPanel labels={labels} />
          </aside>
        </section>}

        <footer className="system-footer"><FooterMetric icon="crosshair" label="System status" value={labels.statusNominal} /><FooterMetric icon="wifi" label="Network" value={labels.networkDisconnected} /><FooterMetric icon="check" label="Data integrity" value={labels.verified} /><FooterMetric icon="clock" label="Time (local)" value="18 May 2024 09:32" mono /><FooterMetric icon="download" label="Power" value="100%" /></footer>
      </main>
    </div>
  );
}

function Meta({ label, value, wide = false }: { label: string; value: string; wide?: boolean }): JSX.Element {
  return <div className={`meta-block ${wide ? "is-wide" : ""}`}><span>{label}</span><strong>{value}</strong></div>;
}

function EvidencePanel({ labels }: { labels: ReturnType<typeof getLabels> }): JSX.Element { return <section className="rail-panel evidence-panel"><div className="rail-title"><h2>{labels.evidenceLatest}</h2><button type="button">View all</button></div><div className="evidence-table"><div className="evidence-row evidence-head"><span>ID</span><span>Type</span><span>Description</span><span>Time</span></div>{[["EV-SAF-00077", "HAZ", "Wildlife strike risk", "09:20"], ["EV-OPR-00142", "OPS", "Ops auth letter", "09:15"], ["EV-MNT-00091", "DOC", "Maint. release", "08:10"], ["EV-WTH-00056", "WX", "Weather brief", "08:05"]].map((row) => <div className="evidence-row" key={row[0]}>{row.map((value) => <span key={value} className={value.startsWith("EV-") ? "mono" : ""}>{value}</span>)}</div>)}</div></section>; }

function NotesPanel({ labels }: { labels: ReturnType<typeof getLabels> }): JSX.Element { return <section className="rail-panel notes-panel"><div className="rail-title"><h2>{labels.notesSafety}</h2><button type="button">View all</button></div><p>Two high hazards remain with incomplete mitigations. See Hazards page for actions.</p><span className="note-author">— Safety officer</span></section>; }

function FooterMetric({ icon, label, value, mono = false }: { icon: IconName; label: string; value: string; mono?: boolean }): JSX.Element { return <div className="footer-metric"><Icon name={icon} /><div><span>{label}</span><strong className={mono ? "mono" : ""}>{value}</strong></div></div>; }
function Icon({ name }: { name: IconName }): JSX.Element {
  const paths: Record<IconName, ReactNode> = { home: <path d="M3 10.5 12 3l9 7.5v9h-6v-5h-6v5H3z" />, shield: <path d="M12 3 20 6v5c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6z" />, warning: <path d="m12 3 10 18H2zM12 9v5m0 3h.01" />, sliders: <path d="M4 6h16M4 12h16M4 18h16M8 4v4m8 2v4M10 16v4" />, risk: <path d="M4 19V5m0 14h16M8 15l3-4 3 2 4-6" />, route: <path d="M5 19c0-3 2-5 5-5h4c3 0 5-2 5-5M5 5h.01M19 19h.01" />, pulse: <path d="M2 12h4l2-6 4 12 2-6h8" />, file: <path d="M6 3h9l3 3v15H6zM15 3v4h4M9 12h6M9 16h6" />, folder: <path d="M3 6h7l2 2h9v11H3z" />, edit: <path d="m4 16-1 5 5-1 11-11-4-4zM13 6l4 4" />, settings: <path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0-5v3m0 13v3M3 12h3m12 0h3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1m0-12.8-2.1 2.1m-8.6 8.6-2.1 2.1" />, download: <path d="M12 3v12m-4-4 4 4 4-4M4 20h16" />, wifi: <path d="M3 8a14 14 0 0 1 18 0M6 12a9 9 0 0 1 12 0M9 16a4 4 0 0 1 6 0M12 20h.01" />, check: <path d="m5 12 4 4L19 6" />, stop: <path d="M5 5h14v14H5z" />, clock: <path d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 5v5l3 2" />, layers: <path d="m12 3 9 5-9 5-9-5zM3 12l9 5 9-5M3 16l9 5 9-5" />, crosshair: <path d="M12 3v3m0 12v3M3 12h3m12 0h3M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z" /> };
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
