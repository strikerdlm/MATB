import { afterEach, describe, expect, it } from "vitest";
import type { EdgeServer } from "../src/server.js";
import { missionFixture } from "./mission-fixture.js";
import { authenticatedTestServer, type AuthenticatedTestServer } from "./http-test-auth.js";

describe("checklist and four-gate routes", () => {
  let app: EdgeServer | undefined;
  let server: AuthenticatedTestServer;

  afterEach(async () => {
    await app?.close();
  });

  async function startServer(): Promise<void> {
    server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      [
        { userId: "commander-1", roles: ["commander"], missionIds: ["mission-1"] },
        { userId: "operator-1", roles: ["operator"], missionIds: ["mission-1"] },
        { userId: "maintainer-1", roles: ["maintainer"], missionIds: ["mission-1"] },
        { userId: "safety-1", roles: ["safety-officer"], missionIds: ["mission-1"] },
      ],
    );
    app = server.app;
  }

  async function createMission(): Promise<void> {
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } }, "commander-1");
  }

  it("requires accountable checklist responses and refuses bulk completion", async () => {
    await startServer();
    await createMission();

    const response = await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/checklist-responses", payload: { checkAll: true } }, "operator-1");
    expect(response.statusCode).toBe(400);
  });

  it("rejects commander authorization when an operator gate is no-go", async () => {
    await startServer();
    await createMission();
    await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/checklist-responses", payload: { responseId: "check-1", itemId: "operator-preflight", response: "pass" } }, "operator-1");

    const operator = await server.request({
      method: "POST",
      url: "/api/revisions/mission-1:r0/gates/operator",
      payload: { decision: "block", aircraftId: "aircraft-1", reason: "operator no-go", evidenceSnapshotId: "evidence-1", checklistResponseIds: ["check-1"] },
    }, "operator-1");
    expect(operator.statusCode).toBe(201);

    const commander = await server.request({
      method: "POST",
      url: "/api/revisions/mission-1:r0/gates/commander",
      payload: { decision: "accept", reason: "attempted release", evidenceSnapshotId: "evidence-1", checklistResponseIds: ["check-1"] },
    }, "commander-1");
    expect(commander.statusCode).toBe(409);
  });

  it("accepts the commander gate only after all four accountable gates are accepted", async () => {
    await startServer();
    await createMission();
    for (const [responseId, itemId, actorUserId] of [
      ["check-maint", "maintenance", "maintainer-1"],
      ["check-op", "operator", "operator-1"],
      ["check-safety", "safety", "safety-1"],
      ["check-command", "command", "commander-1"],
    ]) {
      const response = await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/checklist-responses", payload: { responseId, itemId, response: "pass" } }, actorUserId);
      expect(response.statusCode).toBe(201);
    }
    const gate = async (name: string, actorUserId: string, checklistResponseIds: string[], aircraftId?: string) => server.request({
      method: "POST",
      url: `/api/revisions/mission-1:r0/gates/${name}`,
      payload: { decision: "accept", ...(aircraftId === undefined ? {} : { aircraftId }), reason: `${name} accepted`, evidenceSnapshotId: "evidence-1", checklistResponseIds },
    }, actorUserId);
    expect((await gate("maintenance", "maintainer-1", ["check-maint"])).statusCode).toBe(201);
    expect((await gate("operator", "operator-1", ["check-op"], "aircraft-1")).statusCode).toBe(201);
    expect((await gate("safety", "safety-1", ["check-safety"])).statusCode).toBe(201);
    expect((await gate("commander", "commander-1", ["check-command"])).statusCode).toBe(201);
  });
});
