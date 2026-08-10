import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HumanPerformancePanel } from "../src/components/HumanPerformancePanel.js";

describe("HumanPerformancePanel", () => {
  it("displays operational status and escalation without medical detail", () => {
    const html = renderToStaticMarkup(<HumanPerformancePanel status={{ userId: "OPS-17", role: "Safety officer", dutyPeriodId: "DUTY-1", qualificationStatus: "current", fatigueSelfDeclaration: "able", screenExposureMinutes: 94, workloadLevel: "moderate", alertLoad: 2, status: "available", evidenceRefs: ["policy:HP-1", "EV-HP-01"] }} alert={{ level: "moderate", unresolved: 2, escalationRequired: false, evidenceRefs: ["policy:AL-1"] }} />);
    expect(html).toMatch(/Human performance/);
    expect(html).toMatch(/Current/);
    expect(html).toMatch(/94 min/);
    expect(html).not.toMatch(/diagnosis|fitness.to.fly|medical clearance/i);
  });
});
