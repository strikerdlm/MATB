export type UserRole = "administrator" | "commander" | "safety-officer" | "maintainer" | "operator" | "observer" | "reviewer";

export interface AuthenticatedSession {
  readonly userId: string;
  readonly roles: readonly UserRole[];
  readonly missionIds: readonly string[];
  readonly sessionId: string;
  readonly csrfToken: string;
  readonly requiresReauthentication: boolean;
}

export interface SafetyView {
  readonly revisionId: string;
  readonly status: string;
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
    readonly state: string;
    readonly crew?: readonly { readonly userId: string; readonly role: string }[];
    readonly aircraft?: readonly { readonly aircraftId: string; readonly aircraftClass?: string }[];
    readonly flightRule?: string;
    readonly visualCondition?: string;
    readonly configuration?: string;
  };
  readonly revisions: readonly Record<string, unknown>[];
  readonly safetyResults: readonly SafetyView[];
  readonly checklistResponses: readonly {
    readonly responseId: string; readonly revisionId: string; readonly itemId: string; readonly response: string;
    readonly actorUserId: string; readonly occurredAtUtc: string; readonly evidenceRef?: string; readonly reason?: string;
  }[];
  readonly gateApprovals: readonly {
    readonly missionRevisionId: string; readonly gate: string; readonly decision: string;
    readonly actorUserId: string; readonly occurredAtUtc: string; readonly reason?: string;
  }[];
}

export interface MissionList { readonly missions: readonly MissionView[] }
export interface PackageList { readonly active: readonly PackageView[]; readonly quarantined: readonly PackageView[] }
export interface PackageView { readonly packageId: string; readonly version: string; readonly state: string; readonly reason: string; readonly manifest?: { readonly kind?: string } }
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
