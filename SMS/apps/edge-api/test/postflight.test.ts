import { afterEach, describe, expect, it } from "vitest";
import type { EdgeServer } from "../src/server.js";
import { missionFixture, safetyResult } from "./mission-fixture.js";
import { authenticatedTestServer } from "./http-test-auth.js";

describe("post-flight and occurrence routes", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
  });

  it("requires preserved telemetry and structured recovery evidence", async () => {
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled" });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture(), safetyResult: safetyResult() } });

    const missing = await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/postflight", payload: { recovery: { status: "recovered" } } });
    expect(missing.statusCode).toBe(400);

    const complete = await server.request({
      method: "POST",
      url: "/api/revisions/mission-1:r0/postflight",
      payload: {
        recovery: { status: "recovered", aircraftId: "aircraft-1", shutdownAtUtc: "2026-08-09T19:30:00.000Z" },
        battery: { temperatureC: 28, damage: "none", quarantine: false, cycleCount: 13, storageAction: "storage-charge" },
        telemetry: { checksum: "a".repeat(64), preserved: true, reviewState: "pending" },
        debrief: { crewUserIds: ["operator-1", "commander-1"], lessonsLearned: ["normal sortie"], hazardIds: [] },
      },
    });
    expect(complete.statusCode).toBe(201);

    const occurrence = await server.request({ method: "POST", url: "/api/revisions/mission-1:r0/occurrences", payload: { occurrenceId: "occurrence-1", screenedAtUtc: "2026-08-09T20:00:00.000Z", reportable: false, disposition: "no-report" } });
    expect(occurrence.statusCode).toBe(201);
  });
});
