import { afterEach, describe, expect, it } from "vitest";
import { buildServer, type EdgeServer } from "../src/server.js";

describe("safe failure modes", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("disables package writes after a database failure and keeps the service explicit", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });
    await app.safeModeService.simulateDatabaseFailure();

    const response = await app.inject({ method: "POST", url: "/api/packages/import", payload: {} });
    expect(response.statusCode).toBe(503);
    expect(response.json()).toMatchObject({ error: "SAFE_MODE_DATABASE_FAILURE", state: "read-only" });
  });

  it("keeps an imported mission in read-only review until an explicit clone", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });
    const response = await app.inject({ method: "POST", url: "/api/mission-import/review", payload: { missionId: "mission-import-1", revisionId: "mission-import-1:r0", requestedState: "Released" } });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({ state: "read-only-review", cloneRequired: true, missionId: "mission-import-1" });
    expect(response.json().requestedState).toBe("Released");
  });
});
