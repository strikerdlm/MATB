import { describe, expect, it } from "vitest";
import { completeMoc, openManagementOfChange } from "../src/moc.js";

describe("SMS management of change", () => {
  it("does not close an MOC without impact analysis and verification", () => {
    const openCase = openManagementOfChange({ id: "MOC-1", changeDescription: "Update map package", affectedHazards: ["HZ-1"], affectedRequirements: ["REQ-1"], approvals: [], status: "open" });
    expect(() => completeMoc({ ...openCase, impactAnalysis: undefined }, [])).toThrow(/impact/i);
  });

  it("records evidence and verification before completing a change", () => {
    const openCase = openManagementOfChange({ id: "MOC-1", changeDescription: "Update map package", affectedHazards: ["HZ-1"], affectedRequirements: ["REQ-1"], approvals: ["safety-1"], status: "open", impactAnalysis: "Route and airspace checks rerun" });
    const completed = completeMoc(openCase, ["EV-MOC-1"]);
    expect(completed.status).toBe("verified");
    expect(completed.approvals).toContain("EV-MOC-1");
  });
});
