import { describe, expect, it } from "vitest";

import { isParticipantId, normalizeParticipantId } from "@/lib/participant-id";

describe("participant pseudonym contract", () => {
  it("normalizes the common shorthand before registration", () => {
    expect(normalizeParticipantId(" p1 ")).toBe("P01");
    expect(normalizeParticipantId("p012")).toBe("P012");
  });

  it("rejects identifiers that would fail research session creation", () => {
    expect(isParticipantId("P01")).toBe(true);
    expect(isParticipantId("pilot-01")).toBe(false);
    expect(isParticipantId("P1")).toBe(false);
  });
});
