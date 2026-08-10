import { afterEach, describe, expect, it } from "vitest";
import { buildServer, type EdgeServer } from "../src/server.js";
import { missionFixture, safetyResult } from "./mission-fixture.js";

describe("revision exports", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("exports a revision-bound audit manifest without changing the mission", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });
    await app.inject({ method: "POST", url: "/api/missions", payload: { revision: missionFixture(), safetyResult: safetyResult() } });

    const response = await app.inject({ method: "POST", url: "/api/revisions/mission-1:r0/export", payload: {} });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({ revisionId: "mission-1:r0", missionId: "mission-1", auditManifest: { eventCount: 1 } });
    expect(response.json().hashes.payloadSha256).toMatch(/^[a-f0-9]{64}$/);
  });

  it("keeps a mission unchanged when export fails", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });
    await app.inject({ method: "POST", url: "/api/missions", payload: { revision: missionFixture(), safetyResult: safetyResult() } });
    const before = await app.inject({ method: "GET", url: "/api/missions/mission-1" });
    await app.safeModeService.simulateExportFailure();

    const failed = await app.inject({ method: "POST", url: "/api/revisions/mission-1:r0/export", payload: {} });
    const after = await app.inject({ method: "GET", url: "/api/missions/mission-1" });
    expect(failed.statusCode).toBe(500);
    expect(failed.json()).toMatchObject({ error: "EXPORT_FAILED" });
    expect(after.json()).toEqual(before.json());
  });
});
