import { useMemo } from "react";
import type { GateDescriptor } from "../components/gate-types.js";
import type { MissionSafetyMission, MissionSafetyResult } from "../components/mission-safety-types.js";

export interface MissionSafetyInput {
  readonly mission: MissionSafetyMission;
  readonly safetyResult: MissionSafetyResult;
  readonly gates: readonly GateDescriptor[];
}

export interface MissionSafetyState {
  readonly highestBlocker?: string;
  readonly overallStatus: MissionSafetyResult["status"];
  readonly acceptedGates: number;
  readonly gateCount: number;
  readonly freshnessLabel: string;
  readonly operatorState: string;
}

export function useMissionSafety({ mission, safetyResult, gates }: MissionSafetyInput): MissionSafetyState {
  return useMemo(() => ({
    highestBlocker: safetyResult.blockers[0]?.explanation,
    overallStatus: safetyResult.status,
    acceptedGates: gates.filter((gate) => gate.decision === "accept").length,
    gateCount: gates.length,
    freshnessLabel: `TEL: ${mission.freshness.telemetry} · EVI: ${mission.freshness.evidence}`,
    operatorState: mission.operatorState,
  }), [gates, mission.freshness.evidence, mission.freshness.telemetry, mission.operatorState, safetyResult.blockers, safetyResult.status]);
}
