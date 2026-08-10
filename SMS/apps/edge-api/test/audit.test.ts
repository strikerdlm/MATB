import { describe, expect, it } from "vitest";
import {
  AuditLedger,
  GENESIS_HASH,
  type AuditEventInput,
} from "../src/audit/ledger.js";
import { openDatabase } from "../src/db/migrate.js";

const gateAcceptedEvent: AuditEventInput = {
  eventId: "audit-1",
  type: "gate.accepted",
  actorUserId: "commander-1",
  missionRevisionId: "mission-1-r1",
  occurredAtUtc: "2026-08-09T18:00:00.000Z",
  action: "accept",
  reason: "four gates accepted",
  evidenceSnapshotId: "evidence-1",
  clientSessionId: "session-1",
  schemaVersion: 1,
  payload: { gate: "commander", decision: "accept" },
};

function event(overrides: Partial<AuditEventInput> = {}): AuditEventInput {
  return {
    ...gateAcceptedEvent,
    ...overrides,
    eventId: overrides.eventId ?? `audit-${Math.random().toString(16).slice(2)}`,
  };
}

describe("operational audit ledger", () => {
  it("appends canonical events with operational context and verifies the chain", async () => {
    const ledger = new AuditLedger();

    const first = await ledger.append(gateAcceptedEvent);
    const second = await ledger.append(event({
      eventId: "audit-2",
      type: "checklist.response",
      actorUserId: "safety-1",
      action: "record",
      reason: "checklist complete",
      payload: { checklistResponseId: "check-1", answer: "pass" },
    }));

    expect(first).toMatchObject({
      sequence: 0,
      eventId: "audit-1",
      actorUserId: "commander-1",
      missionRevisionId: "mission-1-r1",
      action: "accept",
      reason: "four gates accepted",
      evidenceSnapshotId: "evidence-1",
      clientSessionId: "session-1",
      schemaVersion: 1,
      previousHash: GENESIS_HASH,
    });
    expect(first.hash).toMatch(/^[a-f0-9]{64}$/);
    expect(second.sequence).toBe(1);
    expect(second.previousHash).toBe(first.hash);
    expect(await ledger.verifyAuditChain()).toEqual({ ok: true, checkedEvents: 2 });
  });

  it("detects a changed prior decision", async () => {
    const ledger = new AuditLedger();
    await ledger.append(gateAcceptedEvent);
    await ledger.tamperForFixture(0, { reason: "changed" });

    const report = await ledger.verifyAuditChain();

    expect(report.ok).toBe(false);
    expect(report.firstBrokenSequence).toBe(0);
  });

  it("disables approval writes when the database cannot append", async () => {
    const ledger = new AuditLedger();

    expect(await ledger.canApprove()).toBe(true);
    await ledger.simulateWriteFailure();

    expect(await ledger.canApprove()).toBe(false);
    await expect(ledger.append(gateAcceptedEvent)).rejects.toThrow(/read-only|append|database/i);
  });

  it("queries an immutable snapshot by actor, mission, and event type", async () => {
    const ledger = new AuditLedger();
    await ledger.append(gateAcceptedEvent);
    await ledger.append(event({
      eventId: "audit-2",
      type: "gate.blocked",
      actorUserId: "safety-1",
      reason: "weather data expired",
    }));

    await expect(ledger.queryAudit({ actorUserId: "safety-1" })).resolves.toMatchObject([
      { eventId: "audit-2", type: "gate.blocked" },
    ]);
    await expect(ledger.queryAudit({ missionRevisionId: "mission-1-r1", type: "gate.accepted" })).resolves.toMatchObject([
      { eventId: "audit-1" },
    ]);
  });

  it("persists the chain in the local SQLite connection", async () => {
    const database = openDatabase(":memory:");
    const ledger = new AuditLedger({ database });
    await ledger.append(gateAcceptedEvent);

    const reopenedLedger = new AuditLedger({ database });

    await expect(reopenedLedger.queryAudit()).resolves.toMatchObject([{ eventId: "audit-1" }]);
    await expect(reopenedLedger.verifyAuditChain()).resolves.toEqual({ ok: true, checkedEvents: 1 });
    database.close();
  });
});
