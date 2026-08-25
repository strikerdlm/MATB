import { describe, expect, it } from "vitest";
import { RequestEpoch, emptyMissionScopedState, isOperationalSafeModeFailure, missionRevisionChanged } from "../src/app/operational-state.js";

describe("operational session state", () => {
  it("centralizes a complete principal and mission reset", () => {
    expect(emptyMissionScopedState()).toEqual({
      session: undefined,
      data: undefined,
      selectedMissionId: undefined,
      signedExport: undefined,
    });
  });

  it("aborts and invalidates every outstanding request when the principal or revision changes", () => {
    const epoch = new RequestEpoch();
    const first = epoch.begin();
    const second = epoch.begin();

    expect(first.isCurrent()).toBe(true);
    expect(second.isCurrent()).toBe(true);
    epoch.invalidate();

    expect(first.signal.aborted).toBe(true);
    expect(second.signal.aborted).toBe(true);
    expect(first.isCurrent()).toBe(false);
    expect(second.isCurrent()).toBe(false);
    expect(epoch.begin().isCurrent()).toBe(true);
  });

  it("detects the selected mission revision boundary so signed export state is discarded", () => {
    const operationalData = (revisionId: string) => ({ missions: { missions: [{ missionId: "mission-1", currentRevisionId: revisionId }] } });
    expect(missionRevisionChanged(operationalData("mission-1:r0"), operationalData("mission-1:r1"), "mission-1")).toBe(true);
    expect(missionRevisionChanged(operationalData("mission-1:r1"), operationalData("mission-1:r1"), "mission-1")).toBe(false);
  });

  it("makes each authoritative refresh supersede every older same-principal load", () => {
    const epoch = new RequestEpoch();
    const older = epoch.beginLatest();
    const newer = epoch.beginLatest();

    expect(older.signal.aborted).toBe(true);
    expect(older.isCurrent()).toBe(false);
    expect(newer.isCurrent()).toBe(true);
  });

  it("recognizes only stable server safe-mode failures", () => {
    expect(isOperationalSafeModeFailure(503, "SAFE_MODE_DATABASE_FAILURE")).toBe(true);
    expect(isOperationalSafeModeFailure(503, "READ_ONLY_DEGRADED_STARTUP")).toBe(true);
    expect(isOperationalSafeModeFailure(503, "MISSION_STORE_UNAVAILABLE")).toBe(true);
    expect(isOperationalSafeModeFailure(503, "AUDIT_LEDGER_UNAVAILABLE")).toBe(true);
    expect(isOperationalSafeModeFailure(503, "SAFETY_EVALUATION_INTEGRITY_FAILURE")).toBe(true);
    expect(isOperationalSafeModeFailure(500, "INTERNAL_ERROR")).toBe(false);
    expect(isOperationalSafeModeFailure(409, "SAFE_MODE_DATABASE_FAILURE")).toBe(false);
  });
});
