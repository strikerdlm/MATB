import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { request as httpRequest, type ClientRequest, type IncomingMessage } from "node:http";
import { afterEach, describe, expect, it } from "vitest";
import type { FastifyRequest } from "fastify";
import type { EdgeServer } from "../src/server.js";
import type { CanonicalTelemetry } from "@fac-isr/telemetry";
import { authenticatedTestServer } from "./http-test-auth.js";
import { missionFixture } from "./mission-fixture.js";
import { BoundedSseStream } from "../src/runtime/bounded-sse-stream.js";

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
  const temporaryDirectories: string[] = [];

  afterEach(async () => {
    await app?.close();
    app = undefined;
    for (const directory of temporaryDirectories.splice(0)) rmSync(directory, { recursive: true, force: true });
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

  it("persists the stable adapter and aircraft sequence across restart and certificate rotation", async () => {
    const directory = mkdtempSync(join(tmpdir(), "sms-telemetry-watermark-"));
    temporaryDirectories.push(directory);
    const databaseUrl = join(directory, "edge.sqlite");
    const config = (fingerprintSha256: string) => ({
      databaseUrl,
      packageDirectory: directory,
      internet: "disabled" as const,
      telemetryAdapters: [{ fingerprintSha256, adapterId: "adapter-1", aircraftIds: ["aircraft-1"] }],
    });
    const first = await authenticatedTestServer(config(allowedFingerprint), undefined, { telemetryPeerIdentity: peerFromHeader });
    app = first.app;
    await first.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });
    expect((await app.inject({ method: "POST", url: "/api/telemetry/ingest", headers: { "x-test-peer-fingerprint": allowedFingerprint }, payload: { revisionId: "mission-1:r0", sequence: 10, event } })).statusCode).toBe(202);
    await app.close();
    app = undefined;

    const rotatedFingerprint = "b".repeat(64);
    const restarted = await authenticatedTestServer(config(rotatedFingerprint), undefined, { telemetryPeerIdentity: peerFromHeader });
    app = restarted.app;
    const replayedLowSequence = await app.inject({ method: "POST", url: "/api/telemetry/ingest", headers: { "x-test-peer-fingerprint": rotatedFingerprint }, payload: { revisionId: "mission-1:r0", sequence: 1, event: { ...event, eventId: "after-rotation-low" } } });
    const continued = await app.inject({ method: "POST", url: "/api/telemetry/ingest", headers: { "x-test-peer-fingerprint": rotatedFingerprint }, payload: { revisionId: "mission-1:r0", sequence: 11, event: { ...event, eventId: "after-rotation-next" } } });
    expect(replayedLowSequence.statusCode).toBe(409);
    expect(continued.statusCode).toBe(202);
  });

  it("rejects duplicate keys recursively, excessive JSON depth, and unsupported ingestion content types", async () => {
    const server = await authenticatedTestServer(telemetryConfig(), undefined, { telemetryPeerIdentity: peerFromHeader });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });
    const headers = { "content-type": "application/json", "x-test-peer-fingerprint": allowedFingerprint };
    const duplicateTopLevel = await app.inject({ method: "POST", url: "/api/telemetry/ingest", headers, payload: `{"revisionId":"mission-1:r0","sequence":1,"sequence":1,"event":${JSON.stringify(event)}}` });
    const duplicateNested = await app.inject({ method: "POST", url: "/api/telemetry/ingest", headers, payload: `{"revisionId":"mission-1:r0","sequence":1,"event":{"eventId":"duplicate-nested","aircraftId":"aircraft-1","position":{"lat":4.7,"lat":4.8,"lon":-74.1},"observedAtUtc":"2026-08-09T18:00:00.000Z","sourcePackageIds":["telemetry-package-1"]}}` });
    const tooDeep = await app.inject({ method: "POST", url: "/api/telemetry/ingest", headers, payload: `{"revisionId":"mission-1:r0","sequence":1,"event":{"eventId":"deep","aircraftId":"aircraft-1","observedAtUtc":"2026-08-09T18:00:00.000Z","sourcePackageIds":["telemetry-package-1"],"extra":${"[".repeat(40)}null${"]".repeat(40)}}}` });
    const unsupported = await app.inject({ method: "POST", url: "/api/telemetry/ingest", headers: { "content-type": "text/plain", "x-test-peer-fingerprint": allowedFingerprint }, payload: JSON.stringify({ revisionId: "mission-1:r0", sequence: 1, event }) });
    expect(duplicateTopLevel.statusCode).toBe(400);
    expect(duplicateTopLevel.json()).toMatchObject({ error: "INVALID_JSON" });
    expect(duplicateNested.statusCode).toBe(400);
    expect(duplicateNested.json()).toMatchObject({ error: "INVALID_JSON" });
    expect(tooDeep.statusCode).toBe(400);
    expect(tooDeep.json()).toMatchObject({ error: "INVALID_JSON" });
    expect(unsupported.statusCode).toBe(415);
    const supported = await app.inject({ method: "POST", url: "/api/telemetry/ingest", headers: { "content-type": "application/json; charset=utf-8", "x-test-peer-fingerprint": allowedFingerprint }, payload: JSON.stringify({ revisionId: "mission-1:r0", sequence: 1, event: { ...event, eventId: "supported-content-type" } }) });
    expect(supported.statusCode).toBe(202);
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

  it("caps a stalled SSE subscriber queue and disconnects it when the cap is exceeded", async () => {
    const output = new BoundedSseStream({ maxQueuedRecords: 2, highWaterMark: 1 });
    expect(output.enqueue("data: one\n\n")).toBe(true);
    expect(output.enqueue("data: two\n\n")).toBe(true);
    expect(output.enqueue("data: three\n\n")).toBe(true);
    expect(output.queuedRecordCount()).toBe(2);
    expect(output.enqueue("data: four\n\n")).toBe(false);
    expect(output.queuedRecordCount()).toBe(0);
    expect(output.destroyed).toBe(true);
  });

  it("unsubscribes an actual followed stream on client disconnect and server close", async () => {
    const server = await authenticatedTestServer(telemetryConfig(), undefined, { telemetryPeerIdentity: peerFromHeader });
    app = server.app;
    await server.request({ method: "POST", url: "/api/missions", payload: { revision: missionFixture() } });
    await app.inject({ method: "POST", url: "/api/telemetry/ingest", headers: { "x-test-peer-fingerprint": allowedFingerprint }, payload: { revisionId: "mission-1:r0", sequence: 1, event } });
    await app.listen({ host: "127.0.0.1", port: 0 });

    const first = await openFollowedStream(app, server.headers());
    expect(app.telemetryService.activeSubscriberCount()).toBe(1);
    first.response.destroy();
    first.request.destroy();
    await waitFor(() => app!.telemetryService.activeSubscriberCount() === 0);

    const second = await openFollowedStream(app, server.headers());
    expect(app.telemetryService.activeSubscriberCount()).toBe(1);
    const closing = app.close();
    await new Promise((resolve) => setTimeout(resolve, 50));
    const subscribersDuringClose = app.telemetryService.activeSubscriberCount();
    second.response.destroy();
    second.request.destroy();
    await closing;
    app = undefined;
    expect(subscribersDuringClose).toBe(0);
  });
});

async function openFollowedStream(app: EdgeServer, headers: Readonly<Record<string, string>>): Promise<{ request: ClientRequest; response: IncomingMessage }> {
  const address = app.server.address();
  if (address === null || typeof address === "string") throw new Error("test server did not bind TCP");
  return await new Promise((resolve, reject) => {
    const request = httpRequest({ host: "127.0.0.1", port: address.port, method: "GET", path: "/api/revisions/mission-1:r0/telemetry/stream?window=1", headers }, (response) => {
      response.once("data", () => resolve({ request, response }));
      response.once("error", reject);
    });
    request.once("error", reject);
    request.end();
  });
}

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  throw new Error("condition was not reached");
}
