import { describe, expect, it } from "vitest";
import { closeCorrectiveAction, createCorrectiveAction, verifyCorrectiveAction } from "../src/capa.js";

const openAction = { id: "CAPA-1", ownerId: "OWNER-1", dueAtUtc: "2026-09-01T00:00:00.000Z", evidence: ["EV-1"], status: "open" as const };

describe("SMS corrective action workflows", () => {
  it("requires evidence and effectiveness review before CAPA closure", () => {
    expect(() => closeCorrectiveAction({ ...openAction, evidence: [], effectivenessReview: undefined })).toThrow(/closure/i);
  });

  it("records verification before closing an evidence-linked action", () => {
    const action = createCorrectiveAction(openAction);
    const verification = verifyCorrectiveAction(action, { reviewerId: "REVIEWER-1", evidenceRefs: ["EV-VERIFY-1"], verification: "Mitigation observed in exercise" });
    expect(verification.status).toBe("verified");
    const closed = closeCorrectiveAction({ ...action, evidence: ["EV-1", "EV-VERIFY-1"], verification: verification.reviewerId, effectivenessReview: "Effective in two observations", closureAuthorityId: "SMS-OWNER-1" });
    expect(closed.status).toBe("closed");
  });
});
