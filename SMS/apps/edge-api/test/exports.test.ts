import { afterEach, describe, expect, it } from "vitest";
import type { EdgeServer } from "../src/server.js";
import { missionFixture } from "./mission-fixture.js";
import { authenticatedTestServer } from "./http-test-auth.js";

describe("revision exports", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("exports a revision-bound audit manifest without changing the mission", async () => {
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled" });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });

    const response = await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/export", payload: {} });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({ revisionId: "mission-1:r0", missionId: "mission-1", auditManifest: { eventCount: 1 } });
    expect(response.json().hashes.payloadSha256).toMatch(/^[a-f0-9]{64}$/);
    await expect(app.auditLedger.queryAudit({ type: "export.created" })).resolves.toMatchObject([{
      actorUserId: "commander-1",
      clientSessionId: "test-session-1",
      missionRevisionId: "mission-1:r0",
    }]);
  });

  it("keeps a mission unchanged when export fails", async () => {
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled" });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });
    const before = await server.request({ method: "GET", url: "/api/missions/mission-1" });
    await app.safeModeService.simulateExportFailure();

    const failed = await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/export", payload: {} });
    const after = await server.request({ method: "GET", url: "/api/missions/mission-1" });
    expect(failed.statusCode).toBe(500);
    expect(failed.json()).toMatchObject({ error: "EXPORT_FAILED" });
    expect(after.json()).toEqual(before.json());
  });
});
