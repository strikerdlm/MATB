import { afterEach, describe, expect, it } from "vitest";
import type { InjectOptions } from "fastify";
import { LocalIdentityStore } from "../src/auth/identity.js";
import { createDefaultHttpAuthDependencies } from "../src/auth/http.js";
import type { UserRole } from "../src/auth/roles.js";
import { SessionManager } from "../src/auth/session.js";
import { buildServer, type EdgeServer } from "../src/server.js";
import { missionFixture, nowUtc, safetyResult, testSafetyEvaluationProvider } from "./mission-fixture.js";

const password = "correct horse battery staple";

interface TestIdentity {
  readonly userId: string;
  readonly roles: readonly UserRole[];
  readonly missionIds?: readonly string[];
}

interface LoginSession {
  readonly cookie: string;
  readonly csrfToken: string;
  readonly sessionId: string;
}

function testAuth(identities: readonly TestIdentity[], clock: { now: string }) {
  const identityStore = new LocalIdentityStore({ now: () => clock.now });
  for (const identity of identities) {
    identityStore.register({
      userId: identity.userId,
      displayName: identity.userId,
      roles: identity.roles,
      missionIds: identity.missionIds ?? [],
      password,
    });
  }
  let sequence = 0;
  const sessionManager = new SessionManager({
    now: () => clock.now,
    idleTimeoutMs: 15 * 60_000,
    maxLifetimeMs: 8 * 60 * 60_000,
    reauthenticationIntervalMs: 5 * 60_000,
    sessionIdFactory: () => `session-${++sequence}`,
    sessionCredentialFactory: () => `bearer-secret-${sequence}`,
  });
  return { identityStore, sessionManager, safetyEvaluationProvider: testSafetyEvaluationProvider() };
}

async function login(app: EdgeServer, userId: string): Promise<LoginSession> {
  const response = await app.inject({
    method: "POST",
    url: "/api/auth/login",
    payload: { userId, password },
  });
  expect(response.statusCode).toBe(200);
  const setCookie = response.headers["set-cookie"];
  const cookie = (Array.isArray(setCookie) ? setCookie[0] : setCookie)?.split(";", 1)[0];
  expect(cookie).toBeTypeOf("string");
  const body = response.json() as { csrfToken: string; sessionId: string };
  return { cookie: cookie!, csrfToken: body.csrfToken, sessionId: body.sessionId };
}

function authenticated(
  session: LoginSession,
  input: InjectOptions,
  csrfToken = session.csrfToken,
): InjectOptions {
  return {
    ...input,
    headers: {
      ...input.headers,
      cookie: session.cookie,
      ...(input.method === "GET" || input.method === "HEAD"
        ? {}
        : { "x-csrf-token": csrfToken }),
    },
  };
}

describe("HTTP authentication boundary", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("denies anonymous mission, gate, checklist, package, export, and post-flight requests", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });

    const createMission = await app.inject({
      method: "POST",
      url: "/api/missions",
      payload: { revision: missionFixture() },
    });
    const checklist = await app.inject({
      method: "POST",
      url: "/api/revisions/mission-1:r0/checklist-responses",
      payload: {
        responseId: "check-1",
        itemId: "operator-preflight",
        response: "pass",
        actorUserId: "operator-1",
        occurredAtUtc: nowUtc,
      },
    });
    const gate = await app.inject({
      method: "POST",
      url: "/api/revisions/mission-1:r0/gates/operator",
      payload: {
        decision: "block",
        actorUserId: "operator-1",
        actorRole: "operator",
        aircraftId: "aircraft-1",
        reason: "operator no-go",
        evidenceSnapshotId: "evidence-1",
        checklistResponseIds: ["check-1"],
        occurredAtUtc: nowUtc,
      },
    });
    const packageRead = await app.inject({ method: "GET", url: "/api/packages/quarantine" });
    const revisionExport = await app.inject({ method: "POST", url: "/api/revisions/mission-1:r0/export", payload: {} });
    const postflight = await app.inject({
      method: "POST",
      url: "/api/revisions/mission-1:r0/postflight",
      payload: {
        recovery: { status: "recovered" },
        battery: {},
        telemetry: { checksum: "a".repeat(64), preserved: true },
        debrief: {},
      },
    });
    const researchPayload = await app.inject({
      method: "POST",
      url: "/api/missions",
      payload: { dataDomain: "research" },
    });

    expect([
      createMission.statusCode,
      checklist.statusCode,
      gate.statusCode,
      packageRead.statusCode,
      revisionExport.statusCode,
      postflight.statusCode,
      researchPayload.statusCode,
    ]).toEqual([401, 401, 401, 401, 401, 401, 401]);
  });

  it("ships deny-by-default with no production login identities", async () => {
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });

    const response = await app.inject({
      method: "POST",
      url: "/api/auth/login",
      payload: { userId: "operator-1", password },
    });

    expect(response.statusCode).toBe(401);
  });

  it("recognizes the login route when the request includes a query string", async () => {
    const clock = { now: nowUtc };
    app = await buildServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      testAuth([{ userId: "operator-1", roles: ["operator"], missionIds: ["mission-1"] }], clock),
    );

    const response = await app.inject({
      method: "POST",
      url: "/api/auth/login?locale=es",
      payload: { userId: "operator-1", password },
    });

    expect(response.statusCode).toBe(200);
  });

  it("keeps the hardened cookie credential secret and requires the exact CSRF token", async () => {
    const clock = { now: nowUtc };
    app = await buildServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      testAuth([{ userId: "commander-1", roles: ["commander"], missionIds: ["mission-1"] }], clock),
    );
    const loginResponse = await app.inject({
      method: "POST",
      url: "/api/auth/login",
      payload: { userId: "commander-1", password },
    });

    expect(loginResponse.statusCode).toBe(200);
    expect(loginResponse.headers["set-cookie"]).toBe(
      "__Host-sms_session=bearer-secret-1; Secure; HttpOnly; SameSite=Strict; Path=/",
    );
    const session = {
      cookie: "__Host-sms_session=bearer-secret-1",
      ...(loginResponse.json() as { csrfToken: string; sessionId: string }),
    };
    expect(session.sessionId).toBe("session-1");
    expect(loginResponse.body).not.toContain("bearer-secret-1");
    const safeRead = await app.inject(authenticated(session, { method: "GET", url: "/api/auth/session" }));
    const publicIdAsCredential = await app.inject({
      method: "GET",
      url: "/api/auth/session",
      headers: { cookie: "__Host-sms_session=session-1" },
    });
    const missing = await app.inject({
      method: "POST",
      url: "/api/auth/lock",
      headers: { cookie: session.cookie },
      payload: {},
    });
    const incorrect = await app.inject(authenticated(session, { method: "POST", url: "/api/auth/lock", payload: {} }, `${session.csrfToken}-wrong`));

    expect(safeRead.statusCode).toBe(200);
    expect(safeRead.body).not.toContain("bearer-secret-1");
    expect(publicIdAsCredential.statusCode).toBe(401);
    expect(missing.statusCode).toBe(403);
    expect(incorrect.statusCode).toBe(403);
  });

  it("expires sessions at the idle and maximum-lifetime boundaries", async () => {
    const clock = { now: nowUtc };
    const dependencies = testAuth([{ userId: "operator-1", roles: ["operator"], missionIds: ["mission-1"] }], clock);
    app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" }, dependencies);
    const idleSession = await login(app, "operator-1");

    clock.now = "2026-08-09T18:15:00.000Z";
    const idleExpired = await app.inject(authenticated(idleSession, { method: "GET", url: "/api/auth/session" }));
    expect(idleExpired.statusCode).toBe(401);

    clock.now = "2026-08-10T00:00:00.000Z";
    const maxSession = await login(app, "operator-1");
    clock.now = "2026-08-10T08:00:00.000Z";
    const maxExpired = await app.inject(authenticated(maxSession, { method: "GET", url: "/api/auth/session" }));
    expect(maxExpired.statusCode).toBe(401);
  });

  it("uses the production idle, lifetime, and signing reauthentication defaults", () => {
    const identity = {
      userId: "operator-default-policy",
      displayName: "Operator Default Policy",
      roles: ["operator"] as const,
      missionIds: ["mission-1"],
      qualificationRefs: [],
    };
    const idleDependencies = createDefaultHttpAuthDependencies();
    const idle = idleDependencies.sessionManager.createSession(identity, nowUtc);
    expect(idleDependencies.sessionManager.getSession(idle.sessionId, "2026-08-09T18:15:00.000Z")?.state).toBe("locked");

    const signingDependencies = createDefaultHttpAuthDependencies();
    const signing = signingDependencies.sessionManager.createSession(identity, nowUtc);
    expect(signingDependencies.sessionManager.getSession(signing.sessionId, "2026-08-09T18:04:59.999Z")?.requiresReauthentication).toBe(false);
    expect(signingDependencies.sessionManager.getSession(signing.sessionId, "2026-08-09T18:05:00.000Z")?.requiresReauthentication).toBe(true);

    const lifetimeDependencies = createDefaultHttpAuthDependencies();
    const lifetime = lifetimeDependencies.sessionManager.createSession(identity, nowUtc);
    for (let minutes = 10; minutes < 480; minutes += 10) {
      lifetimeDependencies.sessionManager.touchSession(lifetime.sessionId, new Date(Date.parse(nowUtc) + minutes * 60_000).toISOString());
    }
    expect(lifetimeDependencies.sessionManager.getSession(lifetime.sessionId, "2026-08-10T02:00:00.000Z")?.state).toBe("expired");
  });

  it("locks and logs out server-side sessions", async () => {
    const clock = { now: nowUtc };
    app = await buildServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      testAuth([{ userId: "operator-1", roles: ["operator"], missionIds: ["mission-1"] }], clock),
    );
    const lockedSession = await login(app, "operator-1");

    const locked = await app.inject(authenticated(lockedSession, { method: "POST", url: "/api/auth/lock", payload: {} }));
    const afterLock = await app.inject(authenticated(lockedSession, { method: "GET", url: "/api/auth/session" }));
    const logoutSession = await login(app, "operator-1");
    const logout = await app.inject(authenticated(logoutSession, { method: "POST", url: "/api/auth/logout", payload: {} }));
    const afterLogout = await app.inject(authenticated(logoutSession, { method: "GET", url: "/api/auth/session" }));

    expect(locked.statusCode).toBe(204);
    expect(afterLock.statusCode).toBe(401);
    expect(logout.statusCode).toBe(204);
    expect(logout.headers["set-cookie"]).toContain("Max-Age=0");
    expect(afterLogout.statusCode).toBe(401);
  });

  it("enforces the five-attempt, fifteen-minute lockout through login requests", async () => {
    const clock = { now: nowUtc };
    app = await buildServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      testAuth([{ userId: "operator-1", roles: ["operator"], missionIds: ["mission-1"] }], clock),
    );
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const rejected = await app.inject({ method: "POST", url: "/api/auth/login", payload: { userId: "operator-1", password: "wrong" } });
      expect(rejected.statusCode).toBe(401);
    }
    const locked = await app.inject({ method: "POST", url: "/api/auth/login", payload: { userId: "operator-1", password } });
    expect(locked.statusCode).toBe(401);

    clock.now = "2026-08-09T18:15:00.000Z";
    const recovered = await app.inject({ method: "POST", url: "/api/auth/login", payload: { userId: "operator-1", password } });
    expect(recovered.statusCode).toBe(200);
  });
});

describe("HTTP principal authorization", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("scopes mission reads and writes to assignments, reviewer visibility, and command roles", async () => {
    const clock = { now: nowUtc };
    app = await buildServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      testAuth([
        { userId: "commander-1", roles: ["commander"], missionIds: ["mission-1"] },
        { userId: "operator-1", roles: ["operator"], missionIds: ["mission-1"] },
        { userId: "operator-2", roles: ["operator"], missionIds: ["mission-2"] },
        { userId: "reviewer-1", roles: ["reviewer"] },
        { userId: "safety-1", roles: ["safety-officer"], missionIds: ["mission-1"] },
      ], clock),
    );
    const commander = await login(app, "commander-1");
    const operator = await login(app, "operator-1");
    const unassigned = await login(app, "operator-2");
    const reviewer = await login(app, "reviewer-1");
    const safety = await login(app, "safety-1");

    const operatorCreate = await app.inject(authenticated(operator, {
      method: "POST",
      url: "/api/missions",
      payload: { revision: missionFixture() },
    }));
    const created = await app.inject(authenticated(commander, {
      method: "POST",
      url: "/api/missions",
      payload: { revision: missionFixture() },
    }));
    const assignedRead = await app.inject(authenticated(operator, { method: "GET", url: "/api/missions/mission-1" }));
    const unassignedRead = await app.inject(authenticated(unassigned, { method: "GET", url: "/api/missions/mission-1" }));
    const reviewerRead = await app.inject(authenticated(reviewer, { method: "GET", url: "/api/missions/mission-1" }));
    const revised = await app.inject(authenticated(safety, {
      method: "POST",
      url: "/api/missions/mission-1/revisions",
      payload: {
        expectedRevisionId: "mission-1:r0",
        change: {
          field: "route",
          previous: missionFixture().route,
          next: { ...missionFixture().route, routeHash: "route-hash-2" },
        },
      },
    }));

    expect(operatorCreate.statusCode).toBe(403);
    expect(created.statusCode).toBe(201);
    expect(assignedRead.statusCode).toBe(200);
    expect(unassignedRead.statusCode).toBe(403);
    expect(reviewerRead.statusCode).toBe(200);
    expect(revised.statusCode).toBe(201);
  });

  it("derives checklist identity from an assigned crew principal", async () => {
    const clock = { now: nowUtc };
    app = await buildServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      testAuth([
        { userId: "commander-1", roles: ["commander"], missionIds: ["mission-1"] },
        { userId: "operator-1", roles: ["operator"], missionIds: ["mission-1"] },
        { userId: "administrator-1", roles: ["administrator"], missionIds: ["mission-1"] },
      ], clock),
    );
    const commander = await login(app, "commander-1");
    const operator = await login(app, "operator-1");
    const administrator = await login(app, "administrator-1");
    await app.inject(authenticated(commander, {
      method: "POST",
      url: "/api/missions",
      payload: { revision: missionFixture() },
    }));

    const assigned = await app.inject(authenticated(operator, {
      method: "POST",
      url: "/api/revisions/mission-1:r0/checklist-responses",
      payload: { responseId: "check-op", itemId: "operator", response: "pass" },
    }));
    const notCrew = await app.inject(authenticated(administrator, {
      method: "POST",
      url: "/api/revisions/mission-1:r0/checklist-responses",
      payload: { responseId: "check-admin", itemId: "administrator", response: "pass" },
    }));

    expect(assigned.statusCode).toBe(201);
    expect(assigned.json()).toMatchObject({ actorUserId: "operator-1" });
    expect(notCrew.statusCode).toBe(403);
  });

  it("requires fresh reauthentication and the exact gate role without administrator override", async () => {
    const clock = { now: nowUtc };
    app = await buildServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      testAuth([
        { userId: "commander-1", roles: ["commander"], missionIds: ["mission-1"] },
        { userId: "operator-1", roles: ["operator"], missionIds: ["mission-1"] },
        { userId: "administrator-1", roles: ["administrator"], missionIds: ["mission-1"] },
      ], clock),
    );
    const commander = await login(app, "commander-1");
    const operator = await login(app, "operator-1");
    const administrator = await login(app, "administrator-1");
    await app.inject(authenticated(commander, {
      method: "POST",
      url: "/api/missions",
      payload: { revision: missionFixture() },
    }));
    await app.inject(authenticated(operator, {
      method: "POST",
      url: "/api/revisions/mission-1:r0/checklist-responses",
      payload: { responseId: "check-op", itemId: "operator", response: "pass" },
    }));

    const decision = {
      decision: "block",
      aircraftId: "aircraft-1",
      reason: "operator no-go",
      evidenceSnapshotId: "evidence-1",
      checklistResponseIds: ["check-op"],
    };
    const wrongRole = await app.inject(authenticated(operator, {
      method: "POST",
      url: "/api/revisions/mission-1:r0/gates/maintenance",
      payload: { ...decision, aircraftId: undefined },
    }));
    const adminOverride = await app.inject(authenticated(administrator, {
      method: "POST",
      url: "/api/revisions/mission-1:r0/gates/operator",
      payload: decision,
    }));
    clock.now = "2026-08-09T18:05:00.000Z";
    const stale = await app.inject(authenticated(operator, {
      method: "POST",
      url: "/api/revisions/mission-1:r0/gates/operator",
      payload: decision,
    }));
    const reauthenticated = await app.inject(authenticated(operator, {
      method: "POST",
      url: "/api/auth/reauthenticate",
      payload: { password },
    }));
    const accepted = await app.inject(authenticated(operator, {
      method: "POST",
      url: "/api/revisions/mission-1:r0/gates/operator",
      payload: decision,
    }));

    expect(wrongRole.statusCode).toBe(403);
    expect(adminOverride.statusCode).toBe(403);
    expect(stale.statusCode).toBe(403);
    expect(reauthenticated.statusCode).toBe(200);
    expect(accepted.statusCode).toBe(201);
    expect(accepted.json()).toMatchObject({ actorUserId: "operator-1", actorRole: "operator" });
  });

  it("rejects caller-supplied accountable identity and audits the server principal", async () => {
    const clock = { now: nowUtc };
    app = await buildServer(
      { databaseUrl: ":memory:", internet: "disabled" },
      testAuth([{ userId: "commander-1", roles: ["commander"], missionIds: ["mission-1"] }], clock),
    );
    const commander = await login(app, "commander-1");

    for (const field of ["actorUserId", "actorRole", "clientSessionId", "accountableUserId", "sessionId", "signerUserId", "signerRole"]) {
      const rejected = await app.inject(authenticated(commander, {
        method: "POST",
        url: "/api/missions",
        payload: { revision: missionFixture(), safetyResult: safetyResult(), [field]: "spoofed" },
      }));
      expect(rejected.statusCode, field).toBe(400);
      expect(rejected.json()).toMatchObject({ error: "ACCOUNTABLE_IDENTITY_FORBIDDEN" });
    }
    const rejectedLoginIdentity = await app.inject({
      method: "POST",
      url: "/api/auth/login",
      payload: { userId: "commander-1", password, actorUserId: "spoofed" },
    });
    expect(rejectedLoginIdentity.statusCode).toBe(400);

    const created = await app.inject(authenticated(commander, {
      method: "POST",
      url: "/api/missions",
      payload: { revision: missionFixture() },
    }));
    const events = await app.auditLedger.queryAudit({ type: "mission.created" });
    const packageImport = await app.inject(authenticated(commander, {
      method: "POST",
      url: "/api/packages/import",
      payload: { manifest: { packageId: "map-1", version: "1.0.0" } },
    }));
    const packageEvents = await app.auditLedger.queryAudit({ type: "package.quarantined" });

    expect(created.statusCode).toBe(201);
    expect(events).toMatchObject([{
      actorUserId: "commander-1",
      clientSessionId: commander.sessionId,
    }]);
    expect(packageImport.statusCode).toBe(404);
    expect(packageEvents).toEqual([]);
    expect(JSON.stringify([...events, ...packageEvents])).not.toContain("bearer-secret-1");
  });
});
