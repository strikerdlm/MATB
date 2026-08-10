import { afterEach, describe, expect, it } from "vitest";
import { buildServer, type EdgeServer } from "../src/server.js";
import { MissionService } from "../src/services/mission-service.js";
import { missionFixture, safetyResult } from "./mission-fixture.js";

describe("mission and revision routes", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
  });

  it("creates and returns an immutable mission revision", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });
    const create = await app.inject({ method: "POST", url: "/api/missions", payload: { revision: missionFixture(), safetyResult: safetyResult() } });

    expect(create.statusCode).toBe(201);
    const response = await app.inject({ method: "GET", url: "/api/missions/mission-1" });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({ missionId: "mission-1", currentRevisionId: "mission-1:r0" });
  });

  it("creates a new planned revision for a material route change and rejects stale writes", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });
    await app.inject({ method: "POST", url: "/api/missions", payload: { revision: missionFixture(), safetyResult: safetyResult() } });

    const revision = await app.inject({
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

    const stale = await app.inject({
      method: "POST",
      url: "/api/missions/mission-1/revisions",
      payload: { expectedRevisionId: "mission-1:r0", revision: missionFixture({ id: "mission-1:r1", revision: 1 }) },
    });
    expect(stale.statusCode).toBe(409);
  });

  it("reloads mission snapshots from the local operational store", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });
    await app.inject({ method: "POST", url: "/api/missions", payload: { revision: missionFixture(), safetyResult: safetyResult() } });

    const reloaded = new MissionService({ database: app.edgeDatabase, auditLedger: app.auditLedger });

    expect(reloaded.getMission("mission-1")).toMatchObject({ currentRevisionId: "mission-1:r0" });
  });
});
