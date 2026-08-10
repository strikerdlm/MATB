import type { JSX } from "react";
import { PrivacyBanner } from "./PrivacyBanner.js";

export interface ResearchProtocolView { readonly id: string; readonly version: string; readonly title: string; readonly ethicsApprovalId: string; readonly status: "current" | "expired" | "withdrawn"; readonly permittedSensors: readonly string[]; readonly permittedInstruments: readonly string[] }
export interface ResearchProtocolPanelProps { readonly authorized?: boolean; readonly protocol: ResearchProtocolView }

export function ResearchProtocolPanel({ authorized = false, protocol }: ResearchProtocolPanelProps): JSX.Element {
  return <section className="research-panel" aria-labelledby="research-protocol-heading"><PrivacyBanner />{authorized ? <><div className="research-heading"><div><span className="section-kicker">Governed study</span><h2 id="research-protocol-heading">{protocol.title}</h2></div><span className={`research-state state-${protocol.status}`}>{protocol.status}</span></div><div className="research-metadata"><Meta label="Protocol" value={`${protocol.id} · v${protocol.version}`} /><Meta label="Ethics approval" value={`${protocol.ethicsApprovalId} · ${protocol.status}`} /><Meta label="Instruments" value={protocol.permittedInstruments.join(" · ")} /><Meta label="Sensors" value={protocol.permittedSensors.join(" · ") || "None"} /></div></> : <div className="research-locked"><strong>Research access restricted</strong><span>Protocol and participant controls require an authorized research role.</span></div>}</section>;
}

function Meta({ label, value }: { readonly label: string; readonly value: string }): JSX.Element { return <div><span>{label}</span><strong>{value}</strong></div>; }
