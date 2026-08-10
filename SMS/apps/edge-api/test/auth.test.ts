import { describe, expect, it } from "vitest";
import {
  AuthenticationError,
  LocalAuthenticator,
  LocalIdentityStore,
} from "../src/auth/identity.js";
import { authorize } from "../src/auth/roles.js";
import {
  isSessionLocked,
  isSessionReauthenticationRequired,
  SessionManager,
} from "../src/auth/session.js";
import type { UserRole } from "../src/auth/roles.js";
import {
  authorizeTransport,
  recordTlsPeer,
  validateTlsConfig,
} from "../src/auth/tls.js";

const nowUtc = "2026-08-09T18:00:00.000Z";

function createStore() {
  return new LocalIdentityStore({
    now: () => nowUtc,
    maxFailedAttempts: 2,
    lockoutDurationMs: 60_000,
  });
}

function createSessions() {
  return new SessionManager({
    now: () => nowUtc,
    idleTimeoutMs: 60_000,
    maxLifetimeMs: 3_600_000,
    reauthenticationIntervalMs: 300_000,
  });
}

async function registerAndAuthenticate(
  store: LocalIdentityStore,
  sessions: SessionManager,
  input: { userId: string; roles: readonly UserRole[]; missionIds: readonly string[] },
) {
  store.register({
    ...input,
    displayName: input.userId,
    password: "correct horse battery staple",
  });
  return new LocalAuthenticator(store, sessions).authenticateLocal({
    userId: input.userId,
    password: "correct horse battery staple",
  });
}

describe("local identity and role separation", () => {
  it("does not let a commander sign the maintenance gate", async () => {
    const store = createStore();
    const sessions = createSessions();
    const commanderSession = await registerAndAuthenticate(store, sessions, {
      userId: "commander-1",
      roles: ["commander"],
      missionIds: ["mission-1"],
    });

    expect(authorize(commanderSession, {
      action: "gate:maintenance:accept",
      missionId: "mission-1",
    }).allowed).toBe(false);
  });

  it("requires the matching role and mission assignment for gate decisions", async () => {
    const store = createStore();
    const sessions = createSessions();
    const operatorSession = await registerAndAuthenticate(store, sessions, {
      userId: "operator-1",
      roles: ["operator"],
      missionIds: ["mission-1"],
    });

    expect(authorize(operatorSession, {
      action: "gate:operator:accept",
      missionId: "mission-1",
    }).allowed).toBe(true);
    expect(authorize(operatorSession, {
      action: "gate:operator:accept",
      missionId: "mission-2",
    }).allowed).toBe(false);
  });

  it("uses the same failure for an unknown user and an invalid password", async () => {
    const store = createStore();
    const sessions = createSessions();
    store.register({
      userId: "operator-1",
      displayName: "Operator",
      roles: ["operator"],
      missionIds: ["mission-1"],
      password: "correct horse battery staple",
    });
    const authenticator = new LocalAuthenticator(store, sessions);

    await expect(authenticator.authenticateLocal({ userId: "operator-1", password: "wrong" }))
      .rejects.toBeInstanceOf(AuthenticationError);
    await expect(authenticator.authenticateLocal({ userId: "missing", password: "wrong" }))
      .rejects.toThrow("invalid local credentials");
    expect(store.authenticationEvents()).toHaveLength(2);
  });

  it("locks an identity after repeated failures and records the lock event", async () => {
    const store = createStore();
    const sessions = createSessions();
    store.register({
      userId: "operator-1",
      displayName: "Operator",
      roles: ["operator"],
      missionIds: ["mission-1"],
      password: "correct horse battery staple",
    });
    const authenticator = new LocalAuthenticator(store, sessions);

    await expect(authenticator.authenticateLocal({ userId: "operator-1", password: "wrong" }))
      .rejects.toThrow("invalid local credentials");
    await expect(authenticator.authenticateLocal({ userId: "operator-1", password: "wrong" }))
      .rejects.toThrow("invalid local credentials");
    await expect(authenticator.authenticateLocal({ userId: "operator-1", password: "correct horse battery staple" }))
      .rejects.toThrow("invalid local credentials");

    expect(store.authenticationEvents()).toContainEqual(expect.objectContaining({
      type: "identity.locked",
      userId: "operator-1",
    }));
  });
});

describe("session lifecycle", () => {
  it("locks a session at the configured idle boundary", async () => {
    const store = createStore();
    const sessions = createSessions();
    const session = await registerAndAuthenticate(store, sessions, {
      userId: "operator-1",
      roles: ["operator"],
      missionIds: ["mission-1"],
    });
    const atIdleLimit = {
      ...session,
      lastActivityAtUtc: "2026-08-09T17:59:00.000Z",
    };

    expect(isSessionLocked(atIdleLimit, nowUtc)).toBe(true);
    sessions.lockSession(session.sessionId, "idle timeout", nowUtc);
    expect(sessions.getSession(session.sessionId)?.lockedAtUtc).toBe(nowUtc);
    expect(authorize(sessions.getSession(session.sessionId)!, {
      action: "gate:operator:accept",
      missionId: "mission-1",
    }).allowed).toBe(false);
  });

  it("requires re-authentication after the configured interval", async () => {
    const store = createStore();
    const sessions = createSessions();
    const identity = store.register({
      userId: "operator-1",
      displayName: "Operator",
      roles: ["operator"],
      missionIds: ["mission-1"],
      password: "correct horse battery staple",
    });
    const authenticator = new LocalAuthenticator(store, sessions);
    const session = await authenticator.authenticateLocal({
      userId: identity.userId,
      password: "correct horse battery staple",
    });

    expect(isSessionReauthenticationRequired(session, "2026-08-09T18:05:00.000Z")).toBe(true);
    expect(sessions.isReauthenticationRequired(session.sessionId, "2026-08-09T18:05:00.000Z")).toBe(true);
    expect(authorize(sessions.getSession(session.sessionId, "2026-08-09T18:05:00.000Z")!, {
      action: "gate:operator:accept",
      missionId: "mission-1",
    }).allowed).toBe(false);
    const refreshed = await authenticator.reauthenticateLocal(session.sessionId, {
      userId: identity.userId,
      password: "correct horse battery staple",
    });
    expect(refreshed.requiresReauthentication).toBe(false);
    expect(authorize(refreshed, {
      action: "gate:operator:accept",
      missionId: "mission-1",
    }).allowed).toBe(true);
  });
});

describe("tactical transport policy", () => {
  it("requires certificate and key paths in tactical mode", () => {
    expect(() => validateTlsConfig({
      tacticalMode: true,
      bindAddress: "192.168.10.20",
    })).toThrow(/certificate and key/i);

    expect(validateTlsConfig({
      tacticalMode: true,
      bindAddress: "192.168.10.20",
      certPath: "cert.pem",
      keyPath: "key.pem",
    })).toMatchObject({
      requireClientCertificate: true,
      certPath: expect.stringMatching(/cert\.pem$/),
    });
  });

  it("allows plaintext only for explicit loopback bootstrap", () => {
    expect(authorizeTransport({
      bindAddress: "127.0.0.1",
      encrypted: false,
      loopbackBootstrap: true,
    }).allowed).toBe(true);
    expect(authorizeTransport({
      bindAddress: "192.168.10.20",
      encrypted: false,
      loopbackBootstrap: true,
    }).allowed).toBe(false);
    expect(authorizeTransport({
      bindAddress: "192.168.10.20",
      encrypted: true,
      loopbackBootstrap: false,
    }).allowed).toBe(true);
    expect(authorizeTransport({
      bindAddress: "not-an-ip",
      encrypted: true,
      loopbackBootstrap: false,
    }).allowed).toBe(false);
  });

  it("records a validated certificate identity for audit", () => {
    expect(recordTlsPeer({
      subject: "CN=edge-client",
      fingerprintSha256: "a".repeat(64),
      observedAtUtc: nowUtc,
    })).toMatchObject({
      subject: "CN=edge-client",
      fingerprintSha256: "a".repeat(64),
      observedAtUtc: nowUtc,
    });
  });
});
