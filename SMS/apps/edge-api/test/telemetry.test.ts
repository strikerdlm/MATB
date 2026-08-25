import { afterEach, describe, expect, it } from "vitest";
import type { EdgeServer } from "../src/server.js";
import { signReplayFixture, type CanonicalTelemetry } from "@fac-isr/telemetry";
import { authenticatedTestServer } from "./http-test-auth.js";
import { missionFixture, safetyResult } from "./mission-fixture.js";

const event: CanonicalTelemetry = {
  eventId: "telemetry-route-1",
  aircraftId: "aircraft-1",
  observedAtUtc: "2026-08-09T18:00:00.000Z",
  sourcePackageIds: ["telemetry-package-1"],
};

describe("edge telemetry routes", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
  });

  it("requires local authentication and a signed replay fixture", async () => {
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      [{ userId: "operator-1", roles: ["operator"], missionIds: ["mission-1"] }],
    );
    app = server.app;
    const unsigned = await app.inject({ method: "POST", url: "/api/telemetry/replay", payload: { events: [event], aircraftId: "aircraft-1" } });
    expect(unsigned.statusCode).toBe(401);

    const signed = signReplayFixture([event]);
    const response = await server.request({
      method: "POST",
      url: "/api/telemetry/replay",
      payload: { events: [event], aircraftId: "aircraft-1", signature: signed },
    });
    expect(response.statusCode).toBe(201);
  });

  it("serves only local read-only telemetry stream records", async () => {
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      [{ userId: "commander-1", roles: ["commander"], missionIds: ["mission-1"] }],
    );
    app = server.app;
    await server.request({
      method: "POST",
      url: "/api/missions",
      payload: { revision: missionFixture(), safetyResult: safetyResult() },
    });
    const signed = signReplayFixture([event]);
    await server.request({ method: "POST", url: "/api/telemetry/replay", payload: { revisionId: "mission-1:r0", events: [event], aircraftId: "aircraft-1", signature: signed } });

    const stream = await server.request({ method: "GET", url: "/api/revisions/mission-1:r0/telemetry/stream" });
    expect(stream.statusCode).toBe(200);
    expect(stream.headers["content-type"]).toMatch(/text\/event-stream/);
    expect(stream.body).toContain("telemetry-route-1");
  });

  it("authorizes telemetry from the revision's authoritative mission rather than ID delimiters", async () => {
    const server = await authenticatedTestServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      [{ userId: "commander-1", roles: ["commander"], missionIds: ["mission-1"] }],
    );
    app = server.app;
    const delimiterRevisionId = "mission-1:secret:r0";
    const unrelatedRevisionId = "mission-2:r0";
    for (const [revisionId, missionId] of [
      [delimiterRevisionId, "mission-1:secret"],
      [unrelatedRevisionId, "mission-2"],
    ] as const) {
      const created = await server.request({
        method: "POST",
        url: "/api/missions",
        payload: {
          revision: missionFixture({ id: revisionId, missionId }),
          safetyResult: safetyResult(revisionId),
        },
      });
      expect(created.statusCode).toBe(201);
      const replayed = await server.request({
        method: "POST",
        url: "/api/telemetry/replay",
        payload: {
          revisionId,
          events: [{ ...event, eventId: `telemetry-${missionId}` }],
          aircraftId: "aircraft-1",
          signature: signReplayFixture([{ ...event, eventId: `telemetry-${missionId}` }]),
        },
      });
      expect(replayed.statusCode).toBe(201);
    }

    const delimiterRead = await server.request({ method: "GET", url: `/api/revisions/${delimiterRevisionId}/telemetry/stream` });
    const unrelatedRead = await server.request({ method: "GET", url: `/api/revisions/${unrelatedRevisionId}/telemetry/stream` });

    expect(delimiterRead.statusCode).toBe(403);
    expect(delimiterRead.body).not.toContain("telemetry-mission-1:secret");
    expect(unrelatedRead.statusCode).toBe(403);
    expect(unrelatedRead.body).not.toContain("telemetry-mission-2");
  });
});
