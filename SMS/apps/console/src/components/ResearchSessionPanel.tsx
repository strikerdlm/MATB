import type { JSX } from "react";
import { PrivacyBanner } from "./PrivacyBanner.js";

export interface ResearchSessionView { readonly participantCode: string; readonly conditionAssignment: string; readonly startedAtUtc: string; readonly instrumentProgress: string }
export interface ResearchSessionPanelProps { readonly authorized?: boolean; readonly session: ResearchSessionView; readonly onExport?: () => void }

export function ResearchSessionPanel({ authorized = false, session, onExport }: ResearchSessionPanelProps): JSX.Element {
  return <section className="research-panel research-session-panel" aria-labelledby="research-session-heading"><PrivacyBanner>{authorized ? "Participant code only · operational identity is unavailable in this route." : "A researcher role is required to view the session."}</PrivacyBanner>{authorized ? <><div className="research-heading"><div><span className="section-kicker">Session timeline</span><h2 id="research-session-heading">Research session</h2></div><span className="research-state state-current">Consented</span></div><div className="research-session-grid"><div><span>Participant code</span><strong className="mono">{session.participantCode}</strong></div><div><span>Condition</span><strong>{session.conditionAssignment}</strong></div><div><span>Started UTC</span><strong className="mono">{session.startedAtUtc}</strong></div><div><span>Instrument progress</span><strong>{session.instrumentProgress}</strong></div></div><button className="research-export-button" type="button" onClick={onExport}>Export deidentified evidence</button></> : <div className="research-locked"><strong>Consent-gated session controls</strong><span>Participant identity and instrument responses remain unavailable.</span></div>}</section>;
}
