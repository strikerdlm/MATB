import { describe, expect, it } from "vitest";
import { MatbResearchAdapter } from "../src/matb-adapter.js";
import { registerProtocol, openConsentedSession } from "../src/protocol.js";

const protocol = registerProtocol({ id: "PROTOCOL-MATB", version: "1.0.0", title: "MATB adapter", investigatorId: "INV-1", ethicsApprovalId: "ETHICS-MATB", permittedInstruments: ["NASA-TLX"], permittedSensors: ["matb"], retentionDays: 30, status: "approved" });
const session = openConsentedSession({ protocol, ethicsApproval: { id: "ETHICS-MATB", protocolId: "PROTOCOL-MATB", status: "current", approvedFromUtc: "2026-08-01T00:00:00.000Z", expiresAtUtc: "2027-01-01T00:00:00.000Z" }, consent: { id: "CONSENT-MATB", protocolId: "PROTOCOL-MATB", participantCode: "P-MATB", consentVersion: "v1", consentedAtUtc: "2026-08-10T14:00:00.000Z" }, participantCode: "P-MATB", conditionAssignment: "baseline", startedAtUtc: "2026-08-10T15:00:00.000Z", sessionId: "SESSION-MATB" });

describe("MATB research adapter", () => {
  it("marks MATB events as research-only", async () => {
    const adapter = new MatbResearchAdapter([{ occurredAtUtc: "2026-08-10T15:00:01.000Z", type: "response", payload: { response: 1 } }]);
    await adapter.connect(session, new AbortController().signal);
    const event = await adapter.readEvent(new AbortController().signal);
    expect(event?.dataDomain).toBe("research");
    expect(event?.nonDispatchable).toBe(true);
    expect(event?.type).toBe("matb.response");
  });

  it("cannot write to operational qualification or mission release stores", () => {
    const adapter = new MatbResearchAdapter([]);
    expect(Object.keys(adapter)).not.toContain("updateQualification");
    expect(Object.keys(adapter)).not.toContain("approveMission");
  });

  it("rejects an event for a different session", async () => {
    const adapter = new MatbResearchAdapter([{ sessionId: "OTHER", occurredAtUtc: "2026-08-10T15:00:01.000Z", type: "response", payload: {} }]);
    await expect(adapter.connect(session, new AbortController().signal)).rejects.toThrow(/session/i);
  });
});
