import { describe, expect, it } from "vitest";
import { promoteMissionHazard } from "../src/hazards.js";

describe("SMS hazard workflows", () => {
  it("promotes a mission hazard with its source and residual risk", () => {
    const result = promoteMissionHazard({
      missionHazard: { id: "MH-1", title: "Wildlife strike", description: "Bird activity", causes: ["seasonal activity"], consequences: ["aircraft damage"], residualRiskId: "RISK-1" },
      organizationalOwnerId: "SMS-OWNER-1",
    });

    expect(result.hazard.source).toBe("mission");
    expect(result.hazard.riskAssessmentIds).toContain("RISK-1");
    expect(result.sourceMissionId).toBe("MH-1");
    expect(Object.isFrozen(result.hazard)).toBe(true);
  });
});
