import { afterEach, describe, expect, it } from "vitest";
import type { FastifyRequest } from "fastify";
import type { EdgeServer } from "../src/server.js";
import type { CanonicalTelemetry } from "@fac-isr/telemetry";
import { authenticatedTestServer } from "./http-test-auth.js";
import { missionFixture } from "./mission-fixture.js";

const allowedFingerprint = "a".repeat(64);
const event: CanonicalTelemetry = {
  eventId: "telemetry-route-1",
  aircraftId: "aircraft-1",
  observedAtUtc: "2026-08-09T18:00:00.000Z",
  sourcePackageIds: ["telemetry-package-1"],
};

function telemetryConfig() {
  return {
    databaseUrl: ":memory:" as const,
    internet: "disabled" as const,
    telemetryAdapters: [{ fingerprintSha256: allowedFingerprint, adapterId: "adapter-1", aircraftIds: ["aircraft-1"] }],
  };
}

function peerFromHeader(request: FastifyRequest) {
  const fingerprint = request.headers["x-test-peer-fingerprint"];
  return typeof fingerprint === "string"
    ? { authorized: true, fingerprintSha256: fingerprint, subject: "CN=adapter-1" }
    : { authorized: false };
}

describe("edge telemetry routes", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("does not register production telemetry replay", async () => {
    const server = await authenticatedTestServer(telemetryConfig());
    app = server.app;
    const response = await server.request({ method: "POST", url: "/api/telemetry/replay", payload: { revisionId: "mission-1:r0", events: [event] } });
    expect(response.statusCode).toBe(404);
    expect(app.hasRoute({ method: "POST", url: "/api/telemetry/replay" })).toBe(false);
  });

  it("requires an allowlisted verified client certificate instead of a user session", async () => {
    const server = await authenticatedTestServer(telemetryConfig(), undefined, { telemetryPeerIdentity: peerFromHeader });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });
    const payload = { revisionId: "mission-1:r0", sequence: 1, event };
    const noCertificate = await app.inject({ method: "POST", url: "/api/telemetry/ingest", payload });
    const userSessionOnly = await server.request({ method: "POST", url: "/api/telemetry/ingest", payload });
    const unknownCertificate = await app.inject({ method: "POST", url: "/api/telemetry/ingest", headers: { "x-test-peer-fingerprint": "b".repeat(64) }, payload });
    const accepted = await app.inject({ method: "POST", url: "/api/telemetry/ingest", headers: { "x-test-peer-fingerprint": allowedFingerprint }, payload });
    expect(noCertificate.statusCode).toBe(401);
    expect(userSessionOnly.statusCode).toBe(401);
    expect(unknownCertificate.statusCode).toBe(403);
    expect(accepted.statusCode).toBe(202);
    expect(accepted.json()).toMatchObject({ adapterId: "adapter-1", sequence: 1, status: "accepted" });
  });

  it("binds an allowlisted aircraft to the authoritative mission revision", async () => {
    const server = await authenticatedTestServer(
      telemetryConfig(),
      [{ userId: "commander-1", roles: ["commander"], missionIds: ["mission-foreign"] }],
      { telemetryPeerIdentity: peerFromHeader },
    );
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture({ id: "mission-foreign:r0", missionId: "mission-foreign", aircraft: [{ ...missionFixture().aircraft[0], aircraftId: "aircraft-2" }] }) } });
    const response = await app.inject({
      method: "POST", url: "/api/telemetry/ingest",
      headers: { "x-test-peer-fingerprint": allowedFingerprint },
      payload: { revisionId: "mission-foreign:r0", sequence: 1, event },
    });
    expect(response.statusCode).toBe(403);
    expect(response.json()).toMatchObject({ error: "TELEMETRY_MISSION_AIRCRAFT_FORBIDDEN" });
  });

  it("rejects malformed, out-of-order, oversized, wrong-aircraft, and operation-shaped telemetry", async () => {
    const server = await authenticatedTestServer(telemetryConfig(), undefined, { telemetryPeerIdentity: peerFromHeader });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });
    const headers = { "x-test-peer-fingerprint": allowedFingerprint };
    const ingest = (sequence: number, candidate: unknown) => app!.inject({ method: "POST", url: "/api/telemetry/ingest", headers, payload: { revisionId: "mission-1:r0", sequence, event: candidate } });
    expect((await ingest(1, event)).statusCode).toBe(202);
    expect((await ingest(1, { ...event, eventId: "duplicate-sequence" })).statusCode).toBe(409);
    expect((await ingest(2, { ...event, eventId: "bad-lat", position: { lat: 91, lon: 0 } })).statusCode).toBe(400);
    expect((await ingest(2, { ...event, eventId: "wrong-aircraft", aircraftId: "aircraft-2" })).statusCode).toBe(403);
    expect((await ingest(2, { ...event, eventId: "operation-shaped", operation: { action: "takeoff" } })).statusCode).toBe(400);
    const oversized = await app.inject({ method: "POST", url: "/api/telemetry/ingest", headers, payload: { revisionId: "mission-1:r0", sequence: 2, event: { ...event, eventId: "x".repeat(70_000) } } });
    expect(oversized.statusCode).toBe(413);
    expect(oversized.json()).toMatchObject({ error: "PAYLOAD_TOO_LARGE" });
  });

  it("authorizes bounded SSE windows for operational assignments, observers, and reviewers and cleans up", async () => {
    const identities = [
      { userId: "commander-1", roles: ["commander"] as const, missionIds: ["mission-1"] },
      { userId: "observer-1", roles: ["observer"] as const, missionIds: ["mission-1"] },
      { userId: "reviewer-1", roles: ["reviewer"] as const, missionIds: [] },
      { userId: "researcher-1", roles: ["researcher"] as const, missionIds: ["mission-1"] },
      { userId: "operator-2", roles: ["operator"] as const, missionIds: ["mission-2"] },
    ];
    const server = await authenticatedTestServer(telemetryConfig(), identities, { telemetryPeerIdentity: peerFromHeader });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } }, "commander-1");
    for (let sequence = 1; sequence <= 3; sequence += 1) {
      const accepted = await app.inject({ method: "POST", url: "/api/telemetry/ingest", headers: { "x-test-peer-fingerprint": allowedFingerprint }, payload: { revisionId: "mission-1:r0", sequence, event: { ...event, eventId: `event-${sequence}`, observedAtUtc: `2026-08-09T18:00:0${sequence}.000Z` } } });
      expect(accepted.statusCode).toBe(202);
    }
    for (const userId of ["commander-1", "observer-1", "reviewer-1"]) {
      const response = await server.request({ method: "GET", url: "/api/revisions/mission-1:r0/telemetry/stream?window=2&follow=false" }, userId);
      expect(response.statusCode).toBe(200);
      expect(response.headers["content-type"]).toMatch(/text\/event-stream/);
      expect(response.body).not.toContain("event-1");
      expect(response.body).toContain("event-2");
      expect(response.body).toContain("event-3");
    }
    expect((await server.request({ method: "GET", url: "/api/revisions/mission-1:r0/telemetry/stream?window=101&follow=false" }, "commander-1")).statusCode).toBe(400);
    expect((await server.request({ method: "GET", url: "/api/revisions/mission-1:r0/telemetry/stream?follow=false" }, "researcher-1")).statusCode).toBe(403);
    expect((await server.request({ method: "GET", url: "/api/revisions/mission-1:r0/telemetry/stream?follow=false" }, "operator-2")).statusCode).toBe(403);
    expect(app.telemetryService.activeSubscriberCount()).toBe(0);
  });
});
