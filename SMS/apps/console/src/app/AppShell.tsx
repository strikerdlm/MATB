import { useMemo, useState } from "react";
import type { JSX, ReactNode } from "react";
import { getLabels, type Locale } from "../i18n/registry.js";
import { routeTitle } from "./routes.js";

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
];

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

        <section className="safety-strip" aria-labelledby="safety-strip-heading">
          <div className="strip-summary">
            <h1 id="safety-strip-heading">{labels.missionStrip}</h1>
            <span className="strip-rule" />
            <span className="eyebrow">{labels.highestBlocker}</span>
            <div className="blocker-lockup"><StatusGlyph status="blocker" /><div><strong>GATE 03</strong><span>Safety blocker</span></div></div>
            <div className="strip-dates"><span>Last updated (local)</span><strong>18 May 2024 09:28</strong><span>Data freshness</span><strong className="mono">TEL: 09:25 · EVI: 09:25</strong></div>
          </div>
          <div className="gate-grid">
            <GateCard number="01" title={labels.gateMaintenance} status="pass" details={["Aircraft status · serviceable", "Deferred items · 0 active", "Maint. release · 18 May 08:10"]} evidence="EV-MNT-00091" />
            <GateCard number="02" title={labels.gateOperator} status="pass" details={["Crew currency · current", "Training · current", "Ops authorization · valid"]} evidence="EV-OPR-00142" />
            <GateCard number="03" title={labels.gateSafety} status="blocker" details={["Open hazards · 2 high", "Residual risk · not acceptable", "Mitigations · incomplete"]} evidence="EV-SAF-00077" />
            <GateCard number="04" title={labels.gateCommander} status="pending" details={["Mission approval · pending", "Risk acceptance · pending", "Comments · —"]} evidence="—" />
          </div>
        </section>

        <section className="workspace" aria-label={labels.mapWorkspace}>
          <div className="map-panel">
            <div className="panel-heading"><div><span className="section-kicker">{routeTitle(path)}</span><h2>{labels.mapWorkspace}</h2></div><span className="map-badge"><Icon name="layers" /> Offline tiles · current</span></div>
            <MapCanvas />
            <div className="map-footer"><MapMetric label="Flight profile" value="ISR_SWEEP_120" detail="VFR · VLOS" /><MapMetric label="Route" value="5 waypoints" detail="Total distance · 214 NM" /><MapMetric label="Altitude" value="Planned FL180" detail="Minimum safe · FL120" /><MapMetric label="Airspace" value="Class G" detail="No restrictions" /><MapMetric label="Weather (brief)" value="SCT020" detail="VIS 10 KM" /></div>
          </div>
          <aside className="evidence-rail" aria-label="Mission evidence and telemetry">
            <TelemetryPanel labels={labels} />
            <EvidencePanel labels={labels} />
            <NotesPanel labels={labels} />
          </aside>
        </section>

        <footer className="system-footer"><FooterMetric icon="crosshair" label="System status" value={labels.statusNominal} /><FooterMetric icon="wifi" label="Network" value={labels.networkDisconnected} /><FooterMetric icon="check" label="Data integrity" value={labels.verified} /><FooterMetric icon="clock" label="Time (local)" value="18 May 2024 09:32" mono /><FooterMetric icon="download" label="Power" value="100%" /></footer>
      </main>
    </div>
  );
}

function Meta({ label, value, wide = false }: { label: string; value: string; wide?: boolean }): JSX.Element {
  return <div className={`meta-block ${wide ? "is-wide" : ""}`}><span>{label}</span><strong>{value}</strong></div>;
}

function GateCard({ number, title, status, details, evidence }: { number: string; title: string; status: "pass" | "blocker" | "pending"; details: string[]; evidence: string }): JSX.Element {
  const label = status === "pass" ? "PASS" : status === "blocker" ? "BLOCKER" : "PENDING";
  return <article className={`gate-card gate-${status}`}><div className="gate-card-head"><div><span className="gate-number">GATE {number}</span><h3>{title}</h3></div><span className="gate-status"><StatusGlyph status={status} /> {label}</span></div><div className="gate-details">{details.map((detail) => <span key={detail}>{detail}</span>)}<span>Evidence · <b className="mono">{evidence}</b></span></div><div className="gate-action">{status === "pass" ? "All requirements satisfied" : status === "blocker" ? "Actions required" : "Awaiting accountable action"}</div></article>;
}

function MapCanvas(): JSX.Element {
  return <div className="map-canvas"><svg viewBox="0 0 900 470" role="img" aria-label="Offline map showing a five waypoint route"><defs><pattern id="contours" width="180" height="120" patternUnits="userSpaceOnUse"><path d="M-20 84 C 30 16, 82 34, 122 4 S 218 28, 220 100" fill="none" stroke="rgba(230,238,240,.13)" strokeWidth="1" /><path d="M-20 102 C 30 34, 82 52, 122 22 S 218 46, 220 118" fill="none" stroke="rgba(230,238,240,.09)" strokeWidth="1" /></pattern></defs><rect width="900" height="470" fill="#102936" /><rect width="900" height="470" fill="url(#contours)" /><path d="M20 65 C 170 118, 260 84, 398 158 S 630 124, 850 202" fill="none" stroke="#44B8C7" strokeWidth="3" strokeLinecap="round" /><path d="M398 158 C 488 178, 555 198, 680 318" fill="none" stroke="#44B8C7" strokeWidth="3" strokeDasharray="9 9" /><MapPoint x={20} y={65} label="WP01" /><MapPoint x={280} y={118} label="WP02" /><MapPoint x={398} y={158} label="WP03" /><MapPoint x={555} y={198} label="WP04" /><MapPoint x={680} y={318} label="WP05" /><text x="75" y="42" fill="#E6EEF0" fontSize="14" fontFamily="Atkinson Hyperlegible, sans-serif">Puerto Santander</text><text x="505" y="119" fill="#E6EEF0" fontSize="14" fontFamily="Atkinson Hyperlegible, sans-serif">Tibú</text><text x="725" y="245" fill="#E6EEF0" fontSize="14" fontFamily="Atkinson Hyperlegible, sans-serif">La Gabarra</text><text x="440" y="395" fill="#E6EEF0" opacity=".42" fontSize="26" letterSpacing="8" fontFamily="Archivo Narrow, sans-serif">COLOMBIA</text></svg><div className="map-tools"><button type="button" aria-label="Center map"><Icon name="crosshair" /></button><button type="button" aria-label="Map layers"><Icon name="layers" /></button><button type="button" aria-label="Measure route"><Icon name="route" /></button><button type="button" aria-label="Fit route"><Icon name="sliders" /></button></div><div className="north-arrow" aria-label="North arrow"><span>N</span><b>⌃</b></div><div className="map-scale">0&nbsp;&nbsp;&nbsp;10&nbsp;&nbsp;&nbsp;20&nbsp;&nbsp;&nbsp;30 KM</div></div>;
}

function MapPoint({ x, y, label }: { x: number; y: number; label: string }): JSX.Element { return <g><circle cx={x} cy={y} r="9" fill="#081B25" stroke="#44B8C7" strokeWidth="3" /><circle cx={x} cy={y} r="3" fill="#44B8C7" /><text x={x - 16} y={y + 28} fill="#E6EEF0" fontSize="12" fontFamily="IBM Plex Mono, monospace">{label}</text></g>; }

function TelemetryPanel({ labels }: { labels: ReturnType<typeof getLabels> }): JSX.Element { return <section className="rail-panel telemetry-panel"><div className="rail-title"><h2>{labels.readOnlyTelemetry}</h2><span>As of 09:25 local</span></div><dl className="telemetry-list"><DataLine label="Aircraft ID" value="FAC-1287" mono /><DataLine label="Time (local)" value="18 May 2024 09:25:31" mono /><DataLine label="Latitude" value="08° 23.456′ N" mono /><DataLine label="Longitude" value="072° 45.789′ W" mono /><DataLine label="Altitude" value="FL098" mono /><DataLine label="Ground speed" value="210 KT" mono /><DataLine label="Track" value="123°" mono /><DataLine label="Vertical speed" value="+500 FPM" mono /><DataLine label="Fuel remaining" value="3,450 L (62%)" mono /><DataLine label="Systems" value="NOMINAL" /></dl></section>; }

function EvidencePanel({ labels }: { labels: ReturnType<typeof getLabels> }): JSX.Element { return <section className="rail-panel evidence-panel"><div className="rail-title"><h2>{labels.evidenceLatest}</h2><button type="button">View all</button></div><div className="evidence-table"><div className="evidence-row evidence-head"><span>ID</span><span>Type</span><span>Description</span><span>Time</span></div>{[["EV-SAF-00077", "HAZ", "Wildlife strike risk", "09:20"], ["EV-OPR-00142", "OPS", "Ops auth letter", "09:15"], ["EV-MNT-00091", "DOC", "Maint. release", "08:10"], ["EV-WTH-00056", "WX", "Weather brief", "08:05"]].map((row) => <div className="evidence-row" key={row[0]}>{row.map((value) => <span key={value} className={value.startsWith("EV-") ? "mono" : ""}>{value}</span>)}</div>)}</div></section>; }

function NotesPanel({ labels }: { labels: ReturnType<typeof getLabels> }): JSX.Element { return <section className="rail-panel notes-panel"><div className="rail-title"><h2>{labels.notesSafety}</h2><button type="button">View all</button></div><p>Two high hazards remain with incomplete mitigations. See Hazards page for actions.</p><span className="note-author">— Safety officer</span></section>; }

function DataLine({ label, value, mono = false }: { label: string; value: string; mono?: boolean }): JSX.Element { return <div><dt>{label}</dt><dd className={mono ? "mono" : ""}>{value}</dd></div>; }
function MapMetric({ label, value, detail }: { label: string; value: string; detail: string }): JSX.Element { return <div className="map-metric"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>; }
function FooterMetric({ icon, label, value, mono = false }: { icon: IconName; label: string; value: string; mono?: boolean }): JSX.Element { return <div className="footer-metric"><Icon name={icon} /><div><span>{label}</span><strong className={mono ? "mono" : ""}>{value}</strong></div></div>; }
function StatusGlyph({ status }: { status: "pass" | "blocker" | "pending" }): JSX.Element { return <span className={`status-glyph ${status}`} aria-hidden="true">{status === "pass" ? "✓" : status === "blocker" ? "!" : "◷"}</span>; }

function Icon({ name }: { name: IconName }): JSX.Element {
  const paths: Record<IconName, ReactNode> = { home: <path d="M3 10.5 12 3l9 7.5v9h-6v-5h-6v5H3z" />, shield: <path d="M12 3 20 6v5c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6z" />, warning: <path d="m12 3 10 18H2zM12 9v5m0 3h.01" />, sliders: <path d="M4 6h16M4 12h16M4 18h16M8 4v4m8 2v4M10 16v4" />, risk: <path d="M4 19V5m0 14h16M8 15l3-4 3 2 4-6" />, route: <path d="M5 19c0-3 2-5 5-5h4c3 0 5-2 5-5M5 5h.01M19 19h.01" />, pulse: <path d="M2 12h4l2-6 4 12 2-6h8" />, file: <path d="M6 3h9l3 3v15H6zM15 3v4h4M9 12h6M9 16h6" />, folder: <path d="M3 6h7l2 2h9v11H3z" />, edit: <path d="m4 16-1 5 5-1 11-11-4-4zM13 6l4 4" />, settings: <path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0-5v3m0 13v3M3 12h3m12 0h3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1m0-12.8-2.1 2.1m-8.6 8.6-2.1 2.1" />, download: <path d="M12 3v12m-4-4 4 4 4-4M4 20h16" />, wifi: <path d="M3 8a14 14 0 0 1 18 0M6 12a9 9 0 0 1 12 0M9 16a4 4 0 0 1 6 0M12 20h.01" />, check: <path d="m5 12 4 4L19 6" />, stop: <path d="M5 5h14v14H5z" />, clock: <path d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 5v5l3 2" />, layers: <path d="m12 3 9 5-9 5-9-5zM3 12l9 5 9-5M3 16l9 5 9-5" />, crosshair: <path d="M12 3v3m0 12v3M3 12h3m12 0h3M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z" /> };
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
