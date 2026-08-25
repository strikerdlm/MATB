import type { AuthenticatedSession, MissionList, PackageList, ReadinessReport, AuditHealth, SignedMissionExport } from "../api/types.js";

export interface OperationalData {
  readonly missions: MissionList;
  readonly packages: PackageList;
  readonly readiness: ReadinessReport;
  readonly audit: AuditHealth;
}

export interface MissionScopedState {
  readonly session?: AuthenticatedSession;
  readonly data?: OperationalData;
  readonly selectedMissionId?: string;
  readonly signedExport?: SignedMissionExport;
}

export function emptyMissionScopedState(): MissionScopedState {
  return { session: undefined, data: undefined, selectedMissionId: undefined, signedExport: undefined };
}

interface RevisionIdentityData { readonly missions: { readonly missions: readonly { readonly missionId: string; readonly currentRevisionId: string }[] } }
export function missionRevisionChanged(previous: RevisionIdentityData | undefined, next: RevisionIdentityData, selectedMissionId: string | undefined): boolean {
  if (previous === undefined || selectedMissionId === undefined) return false;
  const before = previous.missions.missions.find(({ missionId }) => missionId === selectedMissionId)?.currentRevisionId;
  const after = next.missions.missions.find(({ missionId }) => missionId === selectedMissionId)?.currentRevisionId;
  return before !== undefined && before !== after;
}

export interface RequestTicket {
  readonly signal: AbortSignal;
  readonly isCurrent: () => boolean;
  readonly finish: () => void;
}

export class RequestEpoch {
  private generation = 0;
  private readonly controllers = new Set<AbortController>();

  public begin(): RequestTicket {
    const controller = new AbortController();
    const generation = this.generation;
    this.controllers.add(controller);
    return Object.freeze({
      signal: controller.signal,
      isCurrent: () => generation === this.generation && !controller.signal.aborted,
      finish: () => { this.controllers.delete(controller); },
    });
  }

  public beginLatest(): RequestTicket { this.invalidate(); return this.begin(); }

  public snapshot(): number { return this.generation; }
  public isCurrent(snapshot: number): boolean { return snapshot === this.generation; }

  public invalidate(): void {
    this.generation += 1;
    for (const controller of this.controllers) controller.abort();
    this.controllers.clear();
  }
}
const SAFE_MODE_CODES = new Set(["SAFE_MODE_DATABASE_FAILURE", "READ_ONLY_DEGRADED_STARTUP", "MISSION_STORE_UNAVAILABLE", "AUDIT_LEDGER_UNAVAILABLE", "SAFETY_EVALUATION_INTEGRITY_FAILURE"]);
export function isOperationalSafeModeFailure(status: number, code: string): boolean {
  return status >= 500 && SAFE_MODE_CODES.has(code);
}
