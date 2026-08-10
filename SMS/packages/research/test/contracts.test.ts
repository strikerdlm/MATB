import { describe, expect, it } from "vitest";
import { parseResearchEvent, parseResearchSession } from "../src/index.js";

const validSession = {
  id: "SESSION-1",
  protocolId: "PROTOCOL-1",
  ethicsApprovalId: "ETHICS-1",
  participantCode: "P-001",
  conditionAssignment: "baseline",
  startedAtUtc: "2026-08-10T15:00:00.000Z",
  nonDispatchable: true,
  events: [],
};

describe("research boundary contracts", () => {
  it("requires ethics approval and non-dispatchable marking", () => {
    const session = parseResearchSession(validSession);
    expect(Object.isFrozen(session)).toBe(true);
    expect(session.nonDispatchable).toBe(true);
    expect(() => parseResearchSession({ ...validSession, ethicsApprovalId: "" })).toThrow(/ethics/i);
    expect(() => parseResearchSession({ ...validSession, nonDispatchable: false })).toThrow(/dispatchable/i);
  });

  it("does not accept operational user IDs in a research event", () => {
    const event = {
      eventId: "EVENT-1",
      sessionId: "SESSION-1",
      occurredAtUtc: "2026-08-10T15:00:01.000Z",
      sequence: 0,
      type: "matb.response",
      dataDomain: "research",
      nonDispatchable: true,
      payload: { response: 1 },
      quality: "valid",
    } as const;
    expect(parseResearchEvent(event).dataDomain).toBe("research");
    expect(() => parseResearchEvent({ ...event, operationalUserId: "U-1" })).toThrow(/separation/i);
  });
});
