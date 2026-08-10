export type MissionSafetyLocale = "en" | "es";

export interface MissionSafetyMission {
  readonly missionId: string;
  readonly phase: string;
  readonly aircraftClass: string;
  readonly flightRule: string;
  readonly visualCondition: string;
  readonly configuration: string;
  readonly lastUpdatedLocal: string;
  readonly freshness: { readonly telemetry: string; readonly evidence: string };
  readonly operatorState: string;
}

export interface MissionSafetyResult {
  readonly status: "ready" | "conditional" | "blocked" | "degraded";
  readonly blockers: readonly { readonly code: string; readonly explanation: string; readonly severity: string }[];
}
