import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { openDatabase, type EdgeDatabase } from "../src/db/migrate.js";
import { AuditLedger } from "../src/audit/ledger.js";
import { MissionService, MissionServiceError } from "../src/services/mission-service.js";
import { missionFixture, nowUtc, testSafetyEvaluationProvider } from "./mission-fixture.js";

const actor = Object.freeze({ actorUserId: "commander-1", clientSessionId: "session-1", occurredAtUtc: nowUtc });
const operator = Object.freeze({ actorUserId: "operator-1", actorRole: "operator" as const, clientSessionId: "session-operator", occurredAtUtc: nowUtc });
const temporaryDirectories: string[] = [];

function databasePath(): string {
  const directory = mkdtempSync(join(tmpdir(), "sms-persistence-"));
  temporaryDirectories.push(directory);
  return join(directory, "edge.sqlite");
}

function service(database: EdgeDatabase): { missions: MissionService; audit: AuditLedger } {
  const audit = new AuditLedger({ database, now: () => nowUtc });
  const missions = new MissionService({ database, auditLedger: audit, now: () => nowUtc, safetyEvaluationProvider: testSafetyEvaluationProvider() });
  return { missions, audit };
}

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) rmSync(directory, { recursive: true, force: true });
});

describe("normalized atomic operational persistence", () => {
  it("writes mission, revision, evaluation, and audit state to normalized tables only", async () => {
    const database = openDatabase(":memory:");
    const { missions } = service(database);

    await missions.createMission({ revision: missionFixture() }, actor);

    expect(database.sql().prepare("SELECT mission_id, current_revision FROM missions").get()).toEqual({ mission_id: "mission-1", current_revision: 0 });
    expect(database.sql().prepare("SELECT revision_id FROM mission_revisions").get()).toEqual({ revision_id: "mission-1:r0" });
    expect(database.sql().prepare("SELECT revision_id, stale FROM evaluation_envelopes").get()).toEqual({ revision_id: "mission-1:r0", stale: 0 });
    expect(database.sql().prepare("SELECT type FROM audit_events").get()).toEqual({ type: "mission.created" });
    expect(database.sql().prepare("SELECT value FROM service_state WHERE key = 'mission_store'").get()).toBeUndefined();
    database.close();
  });

  it("rolls back business state and enters safe mode when the audit insert fails", async () => {
    const database = openDatabase(":memory:");
    const { missions, audit } = service(database);
    database.sql().exec("CREATE TRIGGER fail_audit BEFORE INSERT ON audit_events BEGIN SELECT RAISE(FAIL, 'audit fault'); END");

    await expect(missions.createMission({ revision: missionFixture() }, actor)).rejects.toMatchObject({ code: "AUDIT_LEDGER_UNAVAILABLE" });

    expect(database.sql().prepare("SELECT COUNT(*) AS count FROM missions").get()).toEqual({ count: 0 });
    expect(database.sql().prepare("SELECT COUNT(*) AS count FROM audit_events").get()).toEqual({ count: 0 });
    expect(() => missions.getMission("mission-1")).toThrow(MissionServiceError);
    expect(audit.isReadOnlySafeMode()).toBe(true);
    database.close();
  });

  it("does not append audit or publish memory when a domain insert fails", async () => {
    const database = openDatabase(":memory:");
    const { missions, audit } = service(database);
    database.sql().exec("CREATE TRIGGER fail_revision BEFORE INSERT ON mission_revisions BEGIN SELECT RAISE(FAIL, 'revision fault'); END");

    await expect(missions.createMission({ revision: missionFixture() }, actor)).rejects.toMatchObject({ code: "MISSION_STORE_UNAVAILABLE" });

    expect(database.sql().prepare("SELECT COUNT(*) AS count FROM missions").get()).toEqual({ count: 0 });
    expect(database.sql().prepare("SELECT COUNT(*) AS count FROM audit_events").get()).toEqual({ count: 0 });
    expect(() => missions.getMission("mission-1")).toThrow(MissionServiceError);
    expect(audit.isReadOnlySafeMode()).toBe(true);
    database.close();
  });

  it("allows exactly one concurrent gate decision for a revision and scope", async () => {
    const database = openDatabase(":memory:");
    const { missions } = service(database);
    await missions.createMission({ revision: missionFixture() }, actor);
    await missions.recordChecklistResponse("mission-1:r0", { responseId: "check-1", itemId: "operator-preflight", response: "pass" }, operator);
    const input = { decision: "accept", aircraftId: "aircraft-1", reason: "operator accepted", evidenceSnapshotId: "evidence-1", checklistResponseIds: ["check-1"] };

    const results = await Promise.allSettled([
      missions.recordGateDecision("mission-1:r0", "operator", input, operator),
      missions.recordGateDecision("mission-1:r0", "operator", input, operator),
    ]);

    expect(results.filter(({ status }) => status === "fulfilled")).toHaveLength(1);
    expect(results.filter(({ status }) => status === "rejected")).toHaveLength(1);
    expect(database.sql().prepare("SELECT COUNT(*) AS count FROM gate_decisions").get()).toEqual({ count: 1 });
    database.close();
  });

  it("reloads normalized missions and evaluation envelopes after a process restart", async () => {
    const path = databasePath();
    const first = openDatabase(path);
    await service(first).missions.createMission({ revision: missionFixture() }, actor);
    first.close();

    const reopened = openDatabase(path);
    const reloaded = service(reopened).missions;

    expect(reloaded.getMission("mission-1")).toMatchObject({ currentRevisionId: "mission-1:r0" });
    expect(reloaded.getSafetyResult("mission-1:r0")).toMatchObject({ revisionId: "mission-1:r0", stale: false });
    reopened.close();
  });

  it("reloads checklist, gate, postflight, and occurrence records from normalized tables", async () => {
    const path = databasePath();
    const first = openDatabase(path);
    const firstService = service(first).missions;
    await firstService.createMission({ revision: missionFixture() }, actor);
    await firstService.recordChecklistResponse("mission-1:r0", { responseId: "check-1", itemId: "operator-preflight", response: "pass" }, operator);
    await firstService.recordGateDecision("mission-1:r0", "operator", { decision: "accept", aircraftId: "aircraft-1", reason: "operator accepted", evidenceSnapshotId: "evidence-1", checklistResponseIds: ["check-1"] }, operator);
    await firstService.recordPostflight("mission-1:r0", {
      recordedAtUtc: nowUtc,
      recovery: { status: "recovered" },
      battery: { status: "isolated" },
      telemetry: { preserved: true, checksum: "a".repeat(64) },
      debrief: { completed: true },
    }, actor);
    await firstService.recordOccurrence("mission-1:r0", { occurrenceId: "occurrence-1", screenedAtUtc: nowUtc, reportable: false, disposition: "closed" }, actor);
    first.close();

    const reopened = openDatabase(path);
    const mission = service(reopened).missions.getMission("mission-1");

    expect(mission).toMatchObject({
      checklistResponses: [{ responseId: "check-1" }],
      gateApprovals: [{ gate: "operator", decision: "accept" }],
      postflight: { revisionId: "mission-1:r0" },
      occurrences: [{ occurrenceId: "occurrence-1" }],
    });
    reopened.close();
  });

  it("reloads a material revision and its fresh evaluation from normalized tables", async () => {
    const path = databasePath();
    const first = openDatabase(path);
    const firstService = service(first).missions;
    await firstService.createMission({ revision: missionFixture() }, actor);
    await firstService.createRevision("mission-1", {
      expectedRevisionId: "mission-1:r0",
      change: { field: "route", previous: missionFixture().route, next: { ...missionFixture().route, routeHash: "route-hash-2" } },
    }, actor);
    first.close();

    const reopened = openDatabase(path);
    const reloaded = service(reopened).missions;

    expect(reloaded.getMission("mission-1")).toMatchObject({ currentRevisionId: "mission-1:r1" });
    expect(reloaded.getSafetyResult("mission-1:r1")).toMatchObject({ revisionId: "mission-1:r1", stale: false });
    reopened.close();
  });

  it("rejects a stale checklist write from a second process-level repository instance", async () => {
    const database = openDatabase(":memory:");
    const creator = service(database).missions;
    await creator.createMission({ revision: missionFixture() }, actor);
    const first = service(database).missions;
    const second = service(database).missions;

    const results = await Promise.allSettled([
      first.recordChecklistResponse("mission-1:r0", { responseId: "check-a", itemId: "operator-preflight", response: "pass" }, operator),
      second.recordChecklistResponse("mission-1:r0", { responseId: "check-b", itemId: "operator-preflight", response: "pass" }, operator),
    ]);

    expect(results.filter(({ status }) => status === "fulfilled")).toHaveLength(1);
    expect(results.filter(({ status }) => status === "rejected")).toHaveLength(1);
    expect(database.sql().prepare("SELECT COUNT(*) AS count FROM checklist_responses").get()).toEqual({ count: 1 });
    expect(await first.getAuditLedger().verifyAuditChain()).toMatchObject({ ok: true });
    database.close();
  });

  it("rejects a stale revision write from a second process-level repository instance", async () => {
    const database = openDatabase(":memory:");
    await service(database).missions.createMission({ revision: missionFixture() }, actor);
    const first = service(database).missions;
    const second = service(database).missions;
    const input = { expectedRevisionId: "mission-1:r0", change: { field: "route", previous: missionFixture().route, next: { ...missionFixture().route, routeHash: "route-hash-2" } } };

    const results = await Promise.allSettled([
      first.createRevision("mission-1", input, actor),
      second.createRevision("mission-1", input, actor),
    ]);

    expect(results.filter(({ status }) => status === "fulfilled")).toHaveLength(1);
    expect(results.filter(({ status }) => status === "rejected")).toHaveLength(1);
    expect(database.sql().prepare("SELECT COUNT(*) AS count FROM mission_revisions").get()).toEqual({ count: 2 });
    database.close();
  });
});
