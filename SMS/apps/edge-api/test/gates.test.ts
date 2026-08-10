import { afterEach, describe, expect, it } from "vitest";
import { buildServer, type EdgeServer } from "../src/server.js";
import { missionFixture, nowUtc, safetyResult } from "./mission-fixture.js";

describe("checklist and four-gate routes", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
  });

  async function createMission(): Promise<void> {
    await app!.inject({ method: "POST", url: "/api/missions", payload: { revision: missionFixture(), safetyResult: safetyResult() } });
  }

  it("requires accountable checklist responses and refuses bulk completion", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });
    await createMission();

    const response = await app.inject({
      method: "POST",
      url: "/api/revisions/mission-1:r0/checklist-responses",
      payload: { checkAll: true },
    });
    expect(response.statusCode).toBe(400);
  });

  it("rejects commander authorization when an operator gate is no-go", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });
    await createMission();
    await app.inject({
      method: "POST",
      url: "/api/revisions/mission-1:r0/checklist-responses",
      payload: { responseId: "check-1", itemId: "operator-preflight", response: "pass", actorUserId: "operator-1", occurredAtUtc: nowUtc },
    });

    const operator = await app.inject({
      method: "POST",
      url: "/api/revisions/mission-1:r0/gates/operator",
      payload: { decision: "block", actorUserId: "operator-1", actorRole: "operator", aircraftId: "aircraft-1", reason: "operator no-go", evidenceSnapshotId: "evidence-1", checklistResponseIds: ["check-1"], occurredAtUtc: nowUtc },
    });
    expect(operator.statusCode).toBe(201);

    const commander = await app.inject({
      method: "POST",
      url: "/api/revisions/mission-1:r0/gates/commander",
      payload: { decision: "accept", actorUserId: "commander-1", actorRole: "commander", reason: "attempted release", evidenceSnapshotId: "evidence-1", checklistResponseIds: ["check-1"], occurredAtUtc: nowUtc },
    });
    expect(commander.statusCode).toBe(409);
  });

  it("accepts the commander gate only after all four accountable gates are accepted", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });
    await createMission();
    for (const [responseId, itemId, actorUserId] of [
      ["check-maint", "maintenance", "maintainer-1"],
      ["check-op", "operator", "operator-1"],
      ["check-safety", "safety", "safety-1"],
      ["check-command", "command", "commander-1"],
    ]) {
      const response = await app.inject({
        method: "POST",
        url: "/api/revisions/mission-1:r0/checklist-responses",
        payload: { responseId, itemId, response: "pass", actorUserId, occurredAtUtc: nowUtc },
      });
      expect(response.statusCode).toBe(201);
    }
    const gate = async (name: string, actorUserId: string, actorRole: string, checklistResponseIds: string[], aircraftId?: string) => app!.inject({
      method: "POST",
      url: `/api/revisions/mission-1:r0/gates/${name}`,
      payload: { decision: "accept", actorUserId, actorRole, ...(aircraftId === undefined ? {} : { aircraftId }), reason: `${name} accepted`, evidenceSnapshotId: "evidence-1", checklistResponseIds, occurredAtUtc: nowUtc },
    });
    expect((await gate("maintenance", "maintainer-1", "maintainer", ["check-maint"])).statusCode).toBe(201);
    expect((await gate("operator", "operator-1", "operator", ["check-op"], "aircraft-1")).statusCode).toBe(201);
    expect((await gate("safety", "safety-1", "safety", ["check-safety"])).statusCode).toBe(201);
    expect((await gate("commander", "commander-1", "commander", ["check-command"])).statusCode).toBe(201);
  });
});
