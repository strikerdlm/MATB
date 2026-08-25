export type UserRole = "administrator" | "commander" | "safety-officer" | "maintainer" | "operator" | "observer" | "reviewer";

export interface AuthenticatedSession {
  readonly userId: string;
  readonly roles: readonly UserRole[];
  readonly missionIds: readonly string[];
  readonly sessionId: string;
  readonly csrfToken: string;
  readonly requiresReauthentication: boolean;
  readonly expiresAtUtc: string;
  readonly lastActivityAtUtc: string;
  readonly idleTimeoutMs: number;
}

export type AuthenticatedSessionStatus = Pick<AuthenticatedSession, "sessionId" | "expiresAtUtc" | "lastActivityAtUtc" | "idleTimeoutMs" | "requiresReauthentication">;
export type MissionState = "Draft" | "Planned" | "UnderReview" | "ReadyForRelease" | "Released" | "Active" | "Completed" | "Suspended" | "Aborted" | "PostFlightReview" | "Closed";
export type SafetyStatus = "ready" | "conditional" | "blocked" | "degraded";
export type ChecklistResponse = "pass" | "block" | "not-applicable";
export type GateName = "maintenance" | "operator" | "safety" | "commander";
export type GateDecision = "accept" | "block" | "escalate";
export type PackageState = "verified" | "active" | "quarantined";

export interface SafetyView {
  readonly revisionId: string;
  readonly status: SafetyStatus;
  readonly stale: boolean;
  readonly evaluatedAtUtc?: string;
  readonly blockers: readonly { readonly code: string; readonly explanation?: string; readonly severity?: string }[];
  readonly evaluations?: readonly unknown[];
  readonly [key: string]: unknown;
}

export interface MissionView {
  readonly missionId: string;
  readonly currentRevisionId: string;
  readonly currentRevision: Record<string, unknown> & {
    readonly id: string;
    readonly revision: number;
    readonly state: MissionState;
    readonly crew?: readonly { readonly userId: string; readonly role: string }[];
    readonly aircraft?: readonly { readonly aircraftId: string; readonly aircraftClass?: string }[];
    readonly flightRule?: string;
    readonly visualCondition?: string;
    readonly configuration?: string;
  };
  readonly revisions: readonly Record<string, unknown>[];
  readonly safetyResults: readonly SafetyView[];
  readonly checklistResponses: readonly {
    readonly responseId: string; readonly revisionId: string; readonly itemId: string; readonly response: ChecklistResponse;
    readonly actorUserId: string; readonly occurredAtUtc: string; readonly evidenceRef?: string; readonly reason?: string;
  }[];
  readonly gateApprovals: readonly {
    readonly missionRevisionId: string; readonly gate: GateName; readonly decision: GateDecision;
    readonly actorUserId: string; readonly occurredAtUtc: string; readonly reason?: string;
  }[];
}

export interface MissionList { readonly missions: readonly MissionView[] }
export interface PackageList { readonly active: readonly PackageView[]; readonly quarantined: readonly PackageView[] }
export interface PackageView { readonly packageId: string; readonly version: string; readonly state: PackageState; readonly reason: string; readonly manifest?: { readonly kind?: string } }
export interface AuditHealth { readonly state: "healthy" | "safe-mode"; readonly eventCount: number; readonly lastEventHash?: string }
export interface ReadinessReport {
  readonly status: "ready" | "not_ready";
  readonly technicalReady: boolean;
  readonly operationalReady: false;
  readonly checks: Readonly<Record<string, { readonly status: "ok" | "pending"; readonly detail?: string }>>;
}

export interface SignedMissionExport {
  readonly exportSchemaVersion: "2.0";
  readonly exportId: string;
  readonly signatureKeyId: string;
  readonly signatureAlgorithm: "Ed25519";
  readonly detachedSignature: string;
  readonly [key: string]: unknown;
}

export interface TelemetryRecord {
  readonly adapterId: string;
  readonly revisionId: string;
  readonly sequence: number;
  readonly status: "accepted";
  readonly event: Readonly<Record<string, unknown>>;
}
