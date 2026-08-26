import type { ChecklistResponse, GateDecision, GateName, MissionState, PackageState, SafetyStatus, UserRole } from "../api/types.js";
import type { Labels } from "../i18n/registry.js";

export type OperatorValue = MissionState | SafetyStatus | ChecklistResponse | GateName | GateDecision | PackageState | UserRole
  | "healthy" | "safe-mode" | "ok" | "pending" | "not_ready";

const VALUE_LABELS: Readonly<Record<OperatorValue, keyof Labels>> = {
  Draft: "draftState", Planned: "plannedState", UnderReview: "underReviewState", ReadyForRelease: "readyForReleaseState", Released: "releasedState",
  Active: "activeMissionState", Completed: "completedState", Suspended: "suspendedState", Aborted: "abortedState", PostFlightReview: "postFlightReviewState", Closed: "closedState",
  ready: "ready", conditional: "conditionalState", blocked: "blockedApiState", degraded: "degradedState", pass: "passState", block: "block", "not-applicable": "notApplicableState",
  maintenance: "maintenanceRole", operator: "operatorRole", safety: "safetyRole", commander: "commanderRole", accept: "acceptState", escalate: "escalate",
  verified: "verifiedState", active: "activeState", quarantined: "quarantinedApiState", administrator: "administratorRole", "safety-officer": "safetyOfficerRole",
  maintainer: "maintainerRole", observer: "observerRole", reviewer: "reviewerRole", healthy: "healthyState", "safe-mode": "safeModeApiState", ok: "okState", pending: "pending", not_ready: "notReadyState",
};

export function operatorLabel(labels: Labels, value: OperatorValue): string { return String(labels[VALUE_LABELS[value]]); }

const ERROR_LABELS = {
  AUTHENTICATION_REQUIRED: "invalidCredentials",
  AUTHORIZATION_FORBIDDEN: "forbiddenRole",
  CSRF_TOKEN_INVALID: "sessionExpired",
  REAUTHENTICATION_REQUIRED: "reauthenticationRequired",
  SAFE_MODE_DATABASE_FAILURE: "readOnlySafeMode",
  READ_ONLY_DEGRADED_STARTUP: "readOnlySafeMode",
  EXPORT_FAILED: "exportFailed",
  EDGE_UNAVAILABLE: "edgeDisconnected",
  INTERNAL_ERROR: "requestFailed",
  GATE_DEPENDENCY_BLOCKED: "gateDependencyBlocked",
} as const satisfies Readonly<Record<string, keyof Labels>>;

export function errorLabel(labels: Labels, code: string): string {
  const key = ERROR_LABELS[code as keyof typeof ERROR_LABELS] ?? "requestFailed";
  return String(labels[key]);
}
