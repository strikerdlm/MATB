import { describe, expect, it } from "vitest";
import { createAuditFinding } from "../src/audits.js";

describe("SMS audit findings", () => {
  it("requires an accountable owner, due date, and traceable evidence", () => {
    const finding = createAuditFinding({ id: "FND-1", criterion: "RACAE 219", scope: "flight operations", evidenceRefs: ["EV-AUD-1"], ownerId: "OWNER-1", dueAtUtc: "2026-09-01T00:00:00.000Z", status: "open" });
    expect(finding.status).toBe("open");
    expect(finding.evidenceRefs).toContain("EV-AUD-1");
    expect(() => createAuditFinding({ id: "FND-1", criterion: "RACAE 219", scope: "flight operations", evidenceRefs: [], ownerId: "OWNER-1", dueAtUtc: "2026-09-01T00:00:00.000Z", status: "open" })).toThrow(/evidence/i);
  });
});
