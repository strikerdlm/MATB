import { afterEach, describe, expect, it } from "vitest";
import { buildServer, type EdgeServer } from "../src/server.js";
import { signReplayFixture, type CanonicalTelemetry } from "@fac-isr/telemetry";

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
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });
    const unsigned = await app.inject({ method: "POST", url: "/api/telemetry/replay", payload: { events: [event], aircraftId: "aircraft-1" } });
    expect(unsigned.statusCode).toBe(401);

    const signed = signReplayFixture([event]);
    const response = await app.inject({
      method: "POST",
      url: "/api/telemetry/replay",
      headers: { "x-local-session": "session-1" },
      payload: { events: [event], aircraftId: "aircraft-1", signature: signed },
    });
    expect(response.statusCode).toBe(201);
  });

  it("serves only local read-only telemetry stream records", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });
    const signed = signReplayFixture([event]);
    await app.inject({ method: "POST", url: "/api/telemetry/replay", headers: { "x-local-session": "session-1" }, payload: { revisionId: "mission-1:r0", events: [event], aircraftId: "aircraft-1", signature: signed } });

    const stream = await app.inject({ method: "GET", url: "/api/revisions/mission-1:r0/telemetry/stream", headers: { "x-local-session": "session-1" } });
    expect(stream.statusCode).toBe(200);
    expect(stream.headers["content-type"]).toMatch(/text\/event-stream/);
    expect(stream.body).toContain("telemetry-route-1");
  });
});
