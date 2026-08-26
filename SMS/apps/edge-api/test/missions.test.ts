import { afterEach, describe, expect, it } from "vitest";
import type { EdgeServer } from "../src/server.js";
import { MissionService } from "../src/services/mission-service.js";
import { missionFixture, testSafetyEvaluationProvider } from "./mission-fixture.js";
import { authenticatedTestServer } from "./http-test-auth.js";

describe("mission and revision routes", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
  });

  it("creates and returns an immutable mission revision", async () => {
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled" });
    app = server.app;
    const create = await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });

    expect(create.statusCode).toBe(201);
    const response = await server.request({ method: "GET", url: "/api/missions/mission-1" });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({ missionId: "mission-1", currentRevisionId: "mission-1:r0" });
  });

  it("creates a new planned revision for a material route change and rejects stale writes", async () => {
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled" });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });

    const revision = await server.request({
      method: "POST",
      url: "/api/missions/mission-1/revisions",
      payload: {
        expectedRevisionId: "mission-1:r0",
        change: {
          field: "route",
          previous: missionFixture().route,
          next: { ...missionFixture().route, routeHash: "route-hash-2" },
        },
      },
    });
    expect(revision.statusCode).toBe(201);
    expect(revision.json()).toMatchObject({ id: "mission-1:r1", state: "Planned", revision: 1 });

    const stale = await server.request({
      method: "POST",
      url: "/api/missions/mission-1/revisions",
      payload: { expectedRevisionId: "mission-1:r0", revision: missionFixture({ id: "mission-1:r1", revision: 1 }) },
    });
    expect(stale.statusCode).toBe(409);
  });

  it("reloads mission snapshots from the local operational store", async () => {
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled" });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });

    const reloaded = new MissionService({ database: app.edgeDatabase, auditLedger: app.auditLedger, safetyEvaluationProvider: testSafetyEvaluationProvider() });

    expect(reloaded.getMission("mission-1")).toMatchObject({ currentRevisionId: "mission-1:r0" });
  });
});
