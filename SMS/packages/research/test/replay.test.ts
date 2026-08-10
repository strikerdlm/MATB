import { describe, expect, it } from "vitest";
import { replaySession } from "../src/replay.js";
import { parseResearchSession } from "../src/types.js";

const sessionPackage = {
  schemaVersion: "research-events-v1",
  session: parseResearchSession({ id: "SESSION-REPLAY", protocolId: "PROTOCOL-1", protocolVersion: "1.0.0", ethicsApprovalId: "ETHICS-1", consentVersion: "v1", participantCode: "P-REPLAY", conditionAssignment: "baseline", startedAtUtc: "2026-08-10T15:00:00.000Z", nonDispatchable: true, events: [
    { eventId: "EVENT-2", sessionId: "SESSION-REPLAY", occurredAtUtc: "2026-08-10T15:00:02.000Z", sequence: 2, type: "matb.response", dataDomain: "research", nonDispatchable: true, payload: { response: 2 }, quality: "valid" },
    { eventId: "EVENT-1", sessionId: "SESSION-REPLAY", occurredAtUtc: "2026-08-10T15:00:01.000Z", sequence: 1, type: "matb.response", dataDomain: "research", nonDispatchable: true, payload: { response: 1 }, quality: "valid" },
  ] }),
};

async function collect(events: AsyncIterable<unknown>): Promise<unknown[]> {
  const result: unknown[] = [];
  for await (const event of events) result.push(event);
  return result;
}

describe("research replay", () => {
  it("replays the same event ordering and timing for a fixed package", async () => {
    const first = await collect(replaySession(sessionPackage));
    const second = await collect(replaySession(sessionPackage));
    expect(first).toEqual(second);
    expect((first[0] as { eventId: string }).eventId).toBe("EVENT-1");
  });

  it("rejects a package that is marked dispatchable", async () => {
    const invalid = { ...sessionPackage, session: { ...sessionPackage.session, nonDispatchable: false } };
    await expect(collect(replaySession(invalid))).rejects.toThrow(/dispatchable/i);
  });
});
