import { afterEach, describe, expect, it } from "vitest";
import { buildServer, type EdgeServer } from "../src/server.js";
import { missionFixture, safetyResult } from "./mission-fixture.js";

describe("post-flight and occurrence routes", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
  });

  it("requires preserved telemetry and structured recovery evidence", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });
    await app.inject({ method: "POST", url: "/api/missions", payload: { revision: missionFixture(), safetyResult: safetyResult() } });

    const missing = await app.inject({ method: "POST", url: "/api/revisions/mission-1:r0/postflight", payload: { recovery: { status: "recovered" } } });
    expect(missing.statusCode).toBe(400);

    const complete = await app.inject({
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

    const occurrence = await app.inject({ method: "POST", url: "/api/revisions/mission-1:r0/occurrences", payload: { occurrenceId: "occurrence-1", screenedAtUtc: "2026-08-09T20:00:00.000Z", reportable: false, disposition: "no-report" } });
    expect(occurrence.statusCode).toBe(201);
  });
});
