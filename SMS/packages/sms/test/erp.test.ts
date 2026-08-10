import { describe, expect, it } from "vitest";
import { evaluateErpReadiness } from "../src/erp.js";

describe("SMS ERP readiness", () => {
  it("blocks when a current emergency plan is missing required coordination facts", () => {
    const result = evaluateErpReadiness({ ownerId: "ERP-OWNER", contactPlan: "", aircraftContingencies: [], crewContingencies: ["incapacitation"], routeContingencies: ["alternate"], exerciseDateUtc: "2026-08-01T00:00:00.000Z", nextReviewAtUtc: "2026-09-01T00:00:00.000Z", currentAtUtc: "2026-08-10T00:00:00.000Z" });
    expect(result.status).toBe("blocked");
    expect(result.missing).toContain("contactPlan");
    expect(result.missing).toContain("aircraftContingencies");
  });

  it("marks an overdue ERP review as expired", () => {
    const result = evaluateErpReadiness({ ownerId: "ERP-OWNER", contactPlan: "Ops room and fire service contacts", aircraftContingencies: ["lost-link"], crewContingencies: ["incapacitation"], routeContingencies: ["alternate"], exerciseDateUtc: "2026-07-01T00:00:00.000Z", nextReviewAtUtc: "2026-08-01T00:00:00.000Z", currentAtUtc: "2026-08-10T00:00:00.000Z" });
    expect(result.status).toBe("expired");
  });
});
