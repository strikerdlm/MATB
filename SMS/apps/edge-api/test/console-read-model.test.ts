import { afterEach, describe, expect, it } from "vitest";
import type { EdgeServer } from "../src/server.js";
import { authenticatedTestServer } from "./http-test-auth.js";
import { missionFixture } from "./mission-fixture.js";

describe("live console read model", () => {
  let app: EdgeServer | undefined;
  afterEach(async () => app?.close());

  it("lists assigned missions and exposes server-owned audit health", async () => {
    const server = await authenticatedTestServer({ databaseUrl: ":memory:" }, [
      { userId: "commander-1", roles: ["commander"], missionIds: ["mission-1"] },
    ]);
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: missionFixture() });

    const missions = await server.request({ method: "GET", url: "/api/missions" });
    expect(missions.statusCode).toBe(200);
    expect(missions.json()).toMatchObject({ missions: [{ missionId: "mission-1", currentRevisionId: "mission-1:r0" }] });

    const audit = await server.request({ method: "GET", url: "/api/audit/health" });
    expect(audit.statusCode).toBe(200);
    expect(audit.json()).toMatchObject({ state: "healthy", eventCount: 1 });
  });
});
