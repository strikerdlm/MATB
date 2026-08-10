import { describe, expect, it } from "vitest";
import { ResearchSensorAdapter } from "../src/sensor-adapters.js";
import { registerProtocol, openConsentedSession } from "../src/protocol.js";

const protocol = registerProtocol({ id: "PROTOCOL-SENSOR", version: "1.0.0", title: "Sensor adapter", investigatorId: "INV-1", ethicsApprovalId: "ETHICS-SENSOR", permittedInstruments: [], permittedSensors: ["hrv", "eye-tracking", "psychomotor"], retentionDays: 30, status: "approved" });
const session = openConsentedSession({ protocol, ethicsApproval: { id: "ETHICS-SENSOR", protocolId: "PROTOCOL-SENSOR", status: "current", approvedFromUtc: "2026-08-01T00:00:00.000Z", expiresAtUtc: "2027-01-01T00:00:00.000Z" }, consent: { id: "CONSENT-SENSOR", protocolId: "PROTOCOL-SENSOR", participantCode: "P-SENSOR", consentVersion: "v1", consentedAtUtc: "2026-08-10T14:00:00.000Z" }, participantCode: "P-SENSOR", conditionAssignment: "baseline", startedAtUtc: "2026-08-10T15:00:00.000Z", sessionId: "SESSION-SENSOR" });

describe("research sensor adapters", () => {
  it("normalizes HRV device metadata and keeps the event non-dispatchable", async () => {
    const adapter = new ResearchSensorAdapter({ sensor: "hrv", deviceId: "POLAR-1", events: [{ occurredAtUtc: "2026-08-10T15:00:02.000Z", type: "rr-interval", payload: { milliseconds: 820 } }] });
    await adapter.connect(session, new AbortController().signal);
    const event = await adapter.readEvent(new AbortController().signal);
    expect(event?.type).toBe("hrv.rr-interval");
    expect(event?.payload).toMatchObject({ sensor: "hrv", deviceId: "POLAR-1", milliseconds: 820 });
    expect(event?.nonDispatchable).toBe(true);
  });

  it("requires the sensor to be in the approved scope", async () => {
    const adapter = new ResearchSensorAdapter({ sensor: "eye-tracking", events: [] });
    const restrictedSession = openConsentedSession({ protocol: registerProtocol({ id: "PROTOCOL-HRV", version: "1.0.0", title: "HRV only", investigatorId: "INV-1", ethicsApprovalId: "ETHICS-HRV", permittedInstruments: [], permittedSensors: ["hrv"], retentionDays: 30, status: "approved" }), ethicsApproval: { id: "ETHICS-HRV", protocolId: "PROTOCOL-HRV", status: "current", approvedFromUtc: "2026-08-01T00:00:00.000Z", expiresAtUtc: "2027-01-01T00:00:00.000Z" }, consent: { id: "CONSENT-HRV", protocolId: "PROTOCOL-HRV", participantCode: "P-HRV", consentVersion: "v1", consentedAtUtc: "2026-08-10T14:00:00.000Z" }, participantCode: "P-HRV", conditionAssignment: "baseline", startedAtUtc: "2026-08-10T15:00:00.000Z" });
    await expect(adapter.connect(restrictedSession, new AbortController().signal)).rejects.toThrow(/permitted|scope/i);
  });
});
