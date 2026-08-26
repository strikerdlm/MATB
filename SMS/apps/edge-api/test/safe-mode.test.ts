import { afterEach, describe, expect, it } from "vitest";
import type { EdgeServer } from "../src/server.js";
import { authenticatedTestServer } from "./http-test-auth.js";

describe("safe failure modes", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("disables package writes after a database failure and keeps the service explicit", async () => {
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled" });
    app = server.app;
    await app.safeModeService.simulateDatabaseFailure();

    await expect(app.safeModeService.importPackage({}, {
      actorUserId: "administrator-1",
      clientSessionId: "offline-cli",
      occurredAtUtc: "2026-08-09T18:00:00.000Z",
    })).rejects.toMatchObject({ statusCode: 503, code: "SAFE_MODE_DATABASE_FAILURE", state: "read-only" });
  });

  it("keeps an imported mission in read-only review until an explicit clone", async () => {
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled" });
    app = server.app;
    const response = await server.request({ method: "POST", url: "/api/mission-import/review", payload: { missionId: "mission-import-1", revisionId: "mission-import-1:r0", requestedState: "Released" } });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({ state: "read-only-review", cloneRequired: true, missionId: "mission-import-1" });
    expect(response.json().requestedState).toBe("Released");
  });
});
