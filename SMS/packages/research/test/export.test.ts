import { describe, expect, it } from "vitest";
import { exportDeidentified } from "../src/export.js";
import { parseResearchSession } from "../src/types.js";

const session = parseResearchSession({ id: "SESSION-EXPORT", protocolId: "PROTOCOL-1", protocolVersion: "1.0.0", ethicsApprovalId: "ETHICS-1", consentVersion: "v1", participantCode: "P-EXPORT", conditionAssignment: "high", startedAtUtc: "2026-08-10T15:00:00.000Z", nonDispatchable: true, events: [{ eventId: "EVENT-1", sessionId: "SESSION-EXPORT", occurredAtUtc: "2026-08-10T15:00:01.000Z", sequence: 0, type: "matb.response", dataDomain: "research", nonDispatchable: true, payload: { workload: 44 }, quality: "valid" }] });

describe("deidentified research exports", () => {
  it("exports only participant codes and approved research variables", () => {
    const exported = JSON.stringify(exportDeidentified(session, "json"));
    expect(exported).toContain("P-EXPORT");
    expect(exported).toContain("workload");
    expect(exported).not.toMatch(/name|operationalUserId|diagnosis|missionRelease/i);
  });

  it("provides deterministic CSV and Parquet bytes", () => {
    const csv = exportDeidentified(session, "csv");
    const parquet = exportDeidentified(session, "parquet");
    expect(csv).toContain("eventId,sessionId");
    expect(csv).toContain("EVENT-1");
    expect(parquet).toBeInstanceOf(Uint8Array);
    expect(new TextDecoder().decode(parquet.slice(0, 4))).toBe("PAR1");
  });
});
