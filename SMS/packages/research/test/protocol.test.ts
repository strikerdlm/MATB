import { describe, expect, it } from "vitest";
import { openConsentedSession, registerProtocol } from "../src/protocol.js";

const protocol = registerProtocol({ id: "PROTOCOL-1", version: "1.0.0", title: "MATB workload study", investigatorId: "INV-1", ethicsApprovalId: "ETHICS-1", permittedInstruments: ["NASA-TLX"], permittedSensors: ["matb"], retentionDays: 365, status: "approved" });

describe("research protocol gates", () => {
  it("cannot open a session without current ethics approval and consent", () => {
    expect(() => openConsentedSession({ protocol, ethicsApproval: { id: "ETHICS-1", protocolId: "PROTOCOL-1", status: "current", approvedFromUtc: "2026-08-01T00:00:00.000Z", expiresAtUtc: "2027-08-01T00:00:00.000Z" }, consent: undefined, participantCode: "P-001", conditionAssignment: "baseline", startedAtUtc: "2026-08-10T15:00:00.000Z" })).toThrow(/consent/i);
  });

  it("opens only a current, consented, non-dispatchable session", () => {
    const session = openConsentedSession({ protocol, ethicsApproval: { id: "ETHICS-1", protocolId: "PROTOCOL-1", status: "current", approvedFromUtc: "2026-08-01T00:00:00.000Z", expiresAtUtc: "2027-08-01T00:00:00.000Z" }, consent: { id: "CONSENT-1", protocolId: "PROTOCOL-1", participantCode: "P-001", consentVersion: "v1", consentedAtUtc: "2026-08-10T14:00:00.000Z" }, participantCode: "P-001", conditionAssignment: "baseline", startedAtUtc: "2026-08-10T15:00:00.000Z" });
    expect(session.nonDispatchable).toBe(true);
    expect(session.protocolId).toBe("PROTOCOL-1");
  });
});
