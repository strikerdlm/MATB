import { describe, expect, it } from "vitest";
import { createAggregateReview } from "../src/aggregate.js";
import { exportDeidentified } from "../src/export.js";
import { parseResearchSession } from "../src/types.js";

describe("research boundary", () => {
  it("denies operational identity and classified fields in an export", () => {
    const session = parseResearchSession({ id: "SESSION-BOUNDARY", protocolId: "PROTOCOL-1", ethicsApprovalId: "ETHICS-1", participantCode: "P-BOUNDARY", conditionAssignment: "baseline", startedAtUtc: "2026-08-10T15:00:00.000Z", nonDispatchable: true, events: [{ eventId: "EVENT-1", sessionId: "SESSION-BOUNDARY", occurredAtUtc: "2026-08-10T15:00:01.000Z", sequence: 0, type: "matb.response", dataDomain: "research", nonDispatchable: true, payload: { operationalUserId: "U-1" }, quality: "valid" }] });
    expect(() => exportDeidentified(session, "json")).toThrow(/boundary|operational/i);
  });

  it("requires a privacy-preserving aggregate review", () => {
    const review = createAggregateReview({ id: "REVIEW-1", protocolIds: ["PROTOCOL-1"], ethicsApprovalIds: ["ETHICS-1"], analysisScope: "workload by condition", minimumCellSize: 5, permittedUses: ["training", "interface-change"], findings: ["Training effect observed"], limitations: ["Single-site sample"], reviewerId: "REVIEWER-1" });
    expect(review.minimumCellSize).toBe(5);
    expect(review.permittedUses).not.toContain("operational-release");
  });
});
