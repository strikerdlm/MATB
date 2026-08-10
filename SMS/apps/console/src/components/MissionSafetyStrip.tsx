import type { JSX } from "react";
import { GateStatus } from "./GateStatus.js";
import type { GateDescriptor, GateDecisionEvent, GateRole, GoverningRequirement } from "./gate-types.js";
import type { MissionSafetyLocale, MissionSafetyMission, MissionSafetyResult } from "./mission-safety-types.js";
import { useMissionSafety, type MissionSafetyInput } from "../hooks/useMissionSafety.js";
export type { MissionSafetyLocale, MissionSafetyMission, MissionSafetyResult } from "./mission-safety-types.js";

export interface MissionSafetyStripProps {
  readonly mission: MissionSafetyMission;
  readonly safetyResult: MissionSafetyResult;
  readonly gates: readonly GateDescriptor[];
  readonly locale?: MissionSafetyLocale;
  readonly reviewerRole?: GateRole;
  readonly governingRequirements?: Partial<Record<GateDescriptor["gate"], GoverningRequirement>>;
  readonly onDecision?: (event: GateDecisionEvent) => void;
}

function statusLabel(status: MissionSafetyResult["status"]): string {
  if (status === "ready") return "READY";
  if (status === "conditional") return "CONDITIONAL";
  if (status === "degraded") return "DEGRADED";
  return "BLOCKED";
}

export function MissionSafetyStrip({ mission, safetyResult, gates, locale = "en", reviewerRole, governingRequirements, onDecision }: MissionSafetyStripProps): JSX.Element {
  const safety = useMissionSafety({ mission, safetyResult, gates });
  const highestBlocker = safety.highestBlocker ?? (locale === "es" ? "Sin bloqueadores activos" : "No active blockers");

  return (
    <section className="safety-strip mission-safety-strip" aria-labelledby="mission-safety-strip-heading" data-mission-id={mission.missionId}>
      <div className="strip-summary">
        <h1 id="mission-safety-strip-heading">{locale === "es" ? "Franja de seguridad de misión" : "Mission safety strip"}</h1>
        <span className="strip-rule" />
        <span className="eyebrow">{locale === "es" ? "Bloqueador principal" : "Highest blocker"}</span>
        <div className="blocker-lockup"><span className={`status-glyph ${safetyResult.status === "ready" ? "pass" : "blocker"}`} aria-hidden="true">{safetyResult.status === "ready" ? "✓" : "!"}</span><div><strong>{highestBlocker}</strong><span>{statusLabel(safetyResult.status)}</span></div></div>
        <div className="strip-facts">
          <span>Phase · <b>{mission.phase}</b></span>
          <span>Class · <b>{mission.aircraftClass}</b></span>
          <span>Rule · <b>{mission.flightRule}</b> · <b>{mission.visualCondition}</b></span>
          <span>Configuration · <b>{mission.configuration}</b></span>
          <span>Operator · <b>{mission.operatorState}</b></span>
        </div>
        <div className="strip-dates"><span>Last updated (local)</span><strong>{mission.lastUpdatedLocal}</strong><span>Data freshness</span><strong className="mono">TEL: {mission.freshness.telemetry} · EVI: {mission.freshness.evidence}</strong></div>
      </div>
      <div className="gate-grid">
        {gates.map((gate) => <GateStatus key={`${gate.gate}-${gate.requiredRole}`} gate={gate} reviewerRole={reviewerRole} kernelBlocked={safetyResult.status === "blocked"} governingRequirement={governingRequirements?.[gate.gate]} onDecision={onDecision} />)}
      </div>
    </section>
  );
}

export type { MissionSafetyInput };
