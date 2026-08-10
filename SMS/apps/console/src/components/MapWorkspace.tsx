import type { JSX } from "react";
import { localMapSource, verifyLocalMapPackage, type LocalMapPackageDirectory } from "../lib/local-map.js";

export type MapWorkspaceMode = "planning" | "review" | "monitoring";

export interface MapWaypoint {
  readonly id: string;
  readonly label: string;
  readonly x: number;
  readonly y: number;
}

export interface MapRoute {
  readonly routeId: string;
  readonly distanceNm: number;
  readonly waypoints: readonly MapWaypoint[];
}

export interface MapFinding {
  readonly id: string;
  readonly label: string;
  readonly severity: "low" | "medium" | "high";
  readonly x: number;
  readonly y: number;
}

export interface MapWorkspaceProps {
  readonly packageDirectory: LocalMapPackageDirectory;
  readonly route: MapRoute;
  readonly findings: readonly MapFinding[];
  readonly mode: MapWorkspaceMode;
}

function modeLabel(mode: MapWorkspaceMode): string {
  if (mode === "planning") return "Planning mode";
  if (mode === "monitoring") return "Monitoring mode";
  return "Review mode";
}

function pathForRoute(waypoints: readonly MapWaypoint[]): string {
  return waypoints.map((point, index) => `${index === 0 ? "M" : "L"}${point.x} ${point.y}`).join(" ");
}

function MapPoint({ waypoint }: { waypoint: MapWaypoint }): JSX.Element {
  return <g><circle cx={waypoint.x} cy={waypoint.y} r="9" fill="#081B25" stroke="#44B8C7" strokeWidth="3" /><circle cx={waypoint.x} cy={waypoint.y} r="3" fill="#44B8C7" /><text x={waypoint.x - 16} y={waypoint.y + 28} fill="#E6EEF0" fontSize="12" fontFamily="IBM Plex Mono, monospace">{waypoint.id}</text><text x={waypoint.x + 12} y={waypoint.y - 12} fill="#E6EEF0" fontSize="13" fontFamily="Atkinson Hyperlegible, sans-serif">{waypoint.label}</text></g>;
}

function FindingMarker({ finding }: { finding: MapFinding }): JSX.Element {
  const color = finding.severity === "high" ? "#D64E4B" : finding.severity === "medium" ? "#F2AA3C" : "#44B8C7";
  return <g><circle cx={finding.x} cy={finding.y} r="13" fill="rgba(8,27,37,.85)" stroke={color} strokeWidth="2" strokeDasharray="4 3" /><text x={finding.x + 17} y={finding.y + 4} fill={color} fontSize="11" fontFamily="IBM Plex Mono, monospace">{finding.id}</text></g>;
}

export function MapWorkspace({ packageDirectory, route, findings, mode }: MapWorkspaceProps): JSX.Element {
  const verification = verifyLocalMapPackage(packageDirectory);
  const routePath = pathForRoute(route.waypoints);

  if (!verification.ok) {
    return <section className="map-panel map-workspace map-workspace-error" aria-labelledby="map-workspace-heading"><div className="panel-heading"><div><span className="section-kicker">{modeLabel(mode)}</span><h2 id="map-workspace-heading">Offline map workspace</h2></div></div><div className="map-safe-failure" role="alert"><strong>Map package unavailable</strong><p>{verification.reason}</p><span>Planning and monitoring remain read-only until a verified local package is loaded.</span></div></section>;
  }

  return (
    <section className="map-panel map-workspace" aria-labelledby="map-workspace-heading">
      <div className="panel-heading"><div><span className="section-kicker">{modeLabel(mode)}</span><h2 id="map-workspace-heading">Offline map workspace</h2></div><span className="map-badge"><span aria-hidden="true">▧</span> Offline tiles · current</span></div>
      <div className="map-canvas" data-testid="map-canvas" data-map-source="local-package" data-map-source-id={localMapSource(packageDirectory)}>
        <svg viewBox="0 0 900 470" role="img" aria-label="Offline map showing the approved route and safety findings">
          <defs><pattern id="local-contours" width="180" height="120" patternUnits="userSpaceOnUse"><path d="M-20 84 C 30 16, 82 34, 122 4 S 218 28, 220 100" fill="none" stroke="rgba(230,238,240,.13)" strokeWidth="1" /><path d="M-20 102 C 30 34, 82 52, 122 22 S 218 46, 220 118" fill="none" stroke="rgba(230,238,240,.09)" strokeWidth="1" /></pattern></defs>
          <rect width="900" height="470" fill="#102936" /><rect width="900" height="470" fill="url(#local-contours)" />
          <path d={routePath} fill="none" stroke="#44B8C7" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          {route.waypoints.map((waypoint) => <MapPoint key={waypoint.id} waypoint={waypoint} />)}
          {findings.map((finding) => <FindingMarker key={finding.id} finding={finding} />)}
          <text x="440" y="395" fill="#E6EEF0" opacity=".42" fontSize="26" letterSpacing="8" fontFamily="Archivo Narrow, sans-serif">COLOMBIA</text>
        </svg>
        <div className="map-tools" aria-label="Map display tools"><span>⊕</span><span>▱</span><span>⌁</span><span>⊞</span></div>
        <div className="north-arrow" aria-label="North arrow"><span>N</span><b>⌃</b></div><div className="map-scale">0&nbsp;&nbsp;&nbsp;10&nbsp;&nbsp;&nbsp;20&nbsp;&nbsp;&nbsp;30 KM</div>
        {findings.length > 0 && <div className="map-findings" aria-label="Map findings"><strong>Findings</strong>{findings.map((finding) => <span key={finding.id} className={`finding-${finding.severity}`}><b className="mono">{finding.id}</b> {finding.label}</span>)}</div>}
      </div>
      <div className="map-footer map-workspace-footer"><MapMetric label="Route" value={route.routeId} detail={`${route.waypoints.length} waypoints · ${route.distanceNm} NM`} /><MapMetric label="Source package" value={packageDirectory.packageId} detail={`v${packageDirectory.version}`} /><MapMetric label="Source freshness" value={packageDirectory.freshness} detail={packageDirectory.manifestHash} /><MapMetric label="Findings" value={`${findings.length} mapped`} detail={findings.filter((finding) => finding.severity === "high").length + " high"} /></div>
    </section>
  );
}

function MapMetric({ label, value, detail }: { label: string; value: string; detail: string }): JSX.Element {
  return <div className="map-metric"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>;
}
