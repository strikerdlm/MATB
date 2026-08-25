import { describe, expect, it } from "vitest";
import {
  AuthenticationError,
  authenticateLocal,
  LocalAuthenticator,
  LocalIdentityStore,
} from "../src/auth/identity.js";
import { authorize } from "../src/auth/roles.js";
import {
  isSessionLocked,
  isSessionReauthenticationRequired,
  lockSession,
  SessionManager,
} from "../src/auth/session.js";
import type { UserRole } from "../src/auth/roles.js";
import {
  authorizeTransport,
  recordTlsPeer,
  validateTlsConfig,
} from "../src/auth/tls.js";
import { openDatabase } from "../src/db/migrate.js";

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
  it("locks a default identity after five failures for fifteen minutes", () => {
    let current = nowUtc;
    const store = new LocalIdentityStore({ now: () => current });
    store.register({
      userId: "operator-defaults",
      displayName: "Operator Defaults",
      roles: ["operator"],
      missionIds: ["mission-1"],
      password: "correct horse battery staple",
    });

    for (let attempt = 0; attempt < 5; attempt += 1) {
      expect(() => store.authenticate({ userId: "operator-defaults", password: "wrong" })).toThrow("invalid local credentials");
    }
    expect(store.getLoginState("operator-defaults")).toEqual({
      failedAttempts: 5,
      lockedUntilUtc: "2026-08-09T18:15:00.000Z",
    });
    expect(() => store.authenticate({ userId: "operator-defaults", password: "correct horse battery staple" })).toThrow("invalid local credentials");

    current = "2026-08-09T18:15:00.000Z";
    expect(store.authenticate({ userId: "operator-defaults", password: "correct horse battery staple" }).userId).toBe("operator-defaults");
  });

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

  it("exposes the plan-level authentication contract", async () => {
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

    const session = await authenticateLocal({
      userId: "operator-1",
      password: "correct horse battery staple",
    }, authenticator);
    lockSession(sessions, session.sessionId, "operator requested lock");

    expect(sessions.getSession(session.sessionId)?.lockedAtUtc).toBe(nowUtc);
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

  it("persists credential hashes, roles, assignments, and lockout state across restart", () => {
    const database = openDatabase(":memory:");
    const first = new LocalIdentityStore({ database, now: () => "2026-08-09T18:00:00.000Z" });
    first.register({
      userId: "operator-persistent",
      displayName: "Persistent Operator",
      roles: ["operator"],
      missionIds: ["mission-1"],
      qualificationRefs: ["qualification-1"],
      password: "persistent-password",
    });
    for (let attempt = 0; attempt < 5; attempt += 1) {
      expect(() => first.authenticate({ userId: "operator-persistent", password: "wrong-password" })).toThrow(AuthenticationError);
    }

    const reopened = new LocalIdentityStore({ database, now: () => "2026-08-09T18:01:00.000Z" });

    expect(reopened.getIdentity("operator-persistent")).toEqual({
      userId: "operator-persistent",
      displayName: "Persistent Operator",
      roles: ["operator"],
      missionIds: ["mission-1"],
      qualificationRefs: ["qualification-1"],
    });
    expect(reopened.getLoginState("operator-persistent")).toEqual({ failedAttempts: 5, lockedUntilUtc: "2026-08-09T18:15:00.000Z" });
    expect(() => reopened.authenticate({ userId: "operator-persistent", password: "persistent-password" })).toThrow(AuthenticationError);
    expect(database.sql().prepare("SELECT version, length(salt) AS salt_bytes, length(password_hash) AS hash_bytes FROM credential_versions WHERE user_id = ?").get("operator-persistent"))
      .toEqual({ version: 1, salt_bytes: 16, hash_bytes: 32 });
    database.close();
  });

  it("persists only a session credential hash and reloads an active session", () => {
    const database = openDatabase(":memory:");
    const identityStore = new LocalIdentityStore({ database });
    const identity = identityStore.register({ userId: "session-user", displayName: "Session User", roles: ["reviewer"], missionIds: ["*"], password: "session-password" });
    const policy = { idleTimeoutMs: 60_000, maxLifetimeMs: 3_600_000, reauthenticationIntervalMs: 300_000 };
    const first = new SessionManager({
      ...policy,
      database,
      now: () => "2026-08-09T18:00:00.000Z",
      sessionIdFactory: () => "session-persistent",
      sessionCredentialFactory: () => "raw-session-secret",
      csrfTokenFactory: () => "csrf-secret",
    });
    const issued = first.issueSession(identity);

    const reopened = new SessionManager({ ...policy, database, now: () => "2026-08-09T18:00:30.000Z" });

    expect(reopened.getSessionByCredential(issued.credential)).toMatchObject({ sessionId: "session-persistent", userId: "session-user", state: "active" });
    const stored = database.sql().prepare("SELECT credential_hash, csrf_hash, session_json FROM sessions WHERE session_id = ?").get("session-persistent") as { credential_hash: string; csrf_hash: string; session_json: string };
    expect(stored.credential_hash).not.toContain("raw-session-secret");
    expect(stored.session_json).not.toContain("raw-session-secret");
    expect(stored.csrf_hash).not.toContain("csrf-secret");
    expect(stored.session_json).not.toContain("csrf-secret");
    database.close();
  });

  it("does not publish a session in memory when its durable insert fails", () => {
    const database = openDatabase(":memory:");
    const identities = new LocalIdentityStore({ database });
    const identity = identities.register({ userId: "session-fault", displayName: "Session Fault", roles: ["reviewer"], missionIds: ["*"], password: "session-fault-password" });
    database.sql().exec("CREATE TRIGGER fail_session_insert BEFORE INSERT ON sessions BEGIN SELECT RAISE(FAIL, 'session persistence fault'); END");
    let sequence = 0;
    const manager = new SessionManager({ idleTimeoutMs: 60_000, maxLifetimeMs: 3_600_000, reauthenticationIntervalMs: 300_000, database, sessionIdFactory: () => `fault-session-${++sequence}`, sessionCredentialFactory: () => `fault-credential-${sequence}`, csrfTokenFactory: () => `fault-csrf-${sequence}` });

    expect(() => manager.issueSession(identity)).toThrow(/persist|session|fault/i);
    expect(manager.getSession("fault-session-1")).toBeUndefined();
    database.sql().exec("DROP TRIGGER fail_session_insert");
    expect(() => manager.issueSession(identity)).toThrow(/safe|read.only|persist/i);
    expect(database.sql().prepare("SELECT COUNT(*) AS count FROM sessions").get()).toEqual({ count: 0 });
    database.close();
  });

  it("does not publish lockout state in memory when its durable update fails", () => {
    const database = openDatabase(":memory:");
    const identities = new LocalIdentityStore({ database, now: () => "2026-08-09T18:00:00.000Z" });
    identities.register({ userId: "lockout-fault", displayName: "Lockout Fault", roles: ["operator"], password: "lockout-fault-password" });
    database.sql().exec("CREATE TRIGGER fail_lockout_update BEFORE UPDATE ON login_lockout_state BEGIN SELECT RAISE(FAIL, 'lockout persistence fault'); END");

    expect(() => identities.authenticate({ userId: "lockout-fault", password: "wrong-password" })).toThrow(/persist|lockout|fault|read.only/i);
    expect(identities.getLoginState("lockout-fault")).toEqual({ failedAttempts: 0 });
    expect(identities.isReadOnlySafeMode()).toBe(true);
    expect(database.sql().prepare("SELECT failed_attempts FROM login_lockout_state WHERE user_id = 'lockout-fault'").get()).toEqual({ failed_attempts: 0 });
    database.close();
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
