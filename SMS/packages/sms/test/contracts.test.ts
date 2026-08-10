import { describe, expect, it } from "vitest";
import { parseHazard } from "../src/index.js";

describe("SMS contracts", () => {
  it("parses a source-traceable hazard and preserves its stable identity", () => {
    const hazard = parseHazard({
      id: "HZ-001",
      title: "Wildlife strike",
      source: "mission",
      description: "Bird activity near the planned route",
      causes: ["seasonal activity"],
      consequences: ["aircraft damage"],
      ownerId: "SMS-OWNER-1",
      status: "open",
      riskAssessmentIds: ["RISK-001"],
    });

    expect(Object.isFrozen(hazard)).toBe(true);
    expect(hazard.id).toBe("HZ-001");
    expect(hazard.source).toBe("mission");
  });

  it("rejects diagnosis fields at the operational SMS boundary", () => {
    expect(() => parseHazard({ id: "HZ-001", title: "Hazard", source: "mission", description: "d", causes: [], consequences: [], ownerId: "owner", status: "open", riskAssessmentIds: [], diagnosis: "not permitted" })).toThrow(/unknown|diagnosis/i);
  });
});
