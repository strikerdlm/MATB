import { describe, expect, it } from "vitest";
import { createConsentRecord, withdrawConsent } from "../src/consent.js";

describe("research consent", () => {
  it("records consent version and supports withdrawal without deleting provenance", () => {
    const consent = createConsentRecord({ id: "CONSENT-1", protocolId: "PROTOCOL-1", participantCode: "P-001", consentVersion: "v1", consentedAtUtc: "2026-08-10T14:00:00.000Z" });
    const withdrawn = withdrawConsent(consent, "2026-08-10T16:00:00.000Z");
    expect(withdrawn.withdrawnAtUtc).toBe("2026-08-10T16:00:00.000Z");
    expect(withdrawn.id).toBe(consent.id);
  });
});
