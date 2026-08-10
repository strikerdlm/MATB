import type { JSX } from "react";
import type { MapFinding } from "./MapWorkspace.js";

export interface RiskPanelProps {
  readonly findings: readonly MapFinding[];
  readonly residualBand: string;
  readonly approvedReservePercent: number;
}

export function RiskPanel({ findings, residualBand, approvedReservePercent }: RiskPanelProps): JSX.Element {
  return <section className="rail-panel risk-panel" aria-labelledby="risk-panel-heading"><div className="rail-title"><h2 id="risk-panel-heading">Risk and reserves</h2><span>{findings.length} findings</span></div><dl className="risk-list"><div><dt>Residual band</dt><dd className="risk-value">{residualBand}</dd></div><div><dt>Approved minimum reserve</dt><dd className="mono">{approvedReservePercent}%</dd></div><div><dt>High findings</dt><dd className="mono">{findings.filter((finding) => finding.severity === "high").length}</dd></div></dl><ul className="risk-findings">{findings.map((finding) => <li key={finding.id}><span className={`risk-dot risk-${finding.severity}`} aria-hidden="true" /> <span>{finding.label}</span><b className="mono">{finding.id}</b></li>)}</ul></section>;
}
