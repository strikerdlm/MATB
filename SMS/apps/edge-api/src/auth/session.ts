import { createHash, randomBytes } from "node:crypto";
import type { IdentityRecord } from "./identity.js";
import type { AuthorizationSubject, UserRole } from "./roles.js";
import type { EdgeDatabase } from "../db/migrate.js";

export interface Session extends AuthorizationSubject {
  readonly sessionId: string;
  readonly csrfToken: string;
  readonly issuedAtUtc: string;
  readonly expiresAtUtc: string;
  readonly lastActivityAtUtc: string;
  readonly idleTimeoutMs: number;
  readonly reauthenticationIntervalMs: number;
  readonly reauthenticationDueAtUtc?: string;
  readonly lockReason?: string;
}

export interface SessionPolicy {
  readonly idleTimeoutMs: number;
  readonly maxLifetimeMs: number;
  readonly reauthenticationIntervalMs: number;
}

export interface IssuedSession {
  readonly session: Session;
  readonly credential: string;
}

export interface SessionManagerOptions extends SessionPolicy {
  readonly now?: () => string;
  readonly sessionIdFactory?: () => string;
  readonly sessionCredentialFactory?: () => string;
  readonly csrfTokenFactory?: () => string;
  readonly database?: EdgeDatabase;
}

function parseUtc(value: string): number | undefined {
  const timestamp = new Date(value);
  return Number.isFinite(timestamp.getTime()) ? timestamp.getTime() : undefined;
}

function formatUtc(epochMs: number): string {
  return new Date(epochMs).toISOString();
}

function assertPolicy(policy: SessionPolicy): void {
  if (!Number.isInteger(policy.idleTimeoutMs) || policy.idleTimeoutMs <= 0) {
    throw new Error("idleTimeoutMs must be a positive integer");
  }
  if (!Number.isInteger(policy.maxLifetimeMs) || policy.maxLifetimeMs <= 0) {
    throw new Error("maxLifetimeMs must be a positive integer");
  }
  if (!Number.isInteger(policy.reauthenticationIntervalMs) || policy.reauthenticationIntervalMs < 0) {
    throw new Error("reauthenticationIntervalMs must be a non-negative integer");
  }
}

export function isSessionLocked(session: Session, nowUtc: string): boolean {
  if (session.state === "locked" || session.state === "expired" || session.lockedAtUtc !== undefined) {
    return true;
  }
  const issuedAt = parseUtc(session.issuedAtUtc);
  const expiresAt = parseUtc(session.expiresAtUtc);
  const lastActivityAt = parseUtc(session.lastActivityAtUtc);
  const now = parseUtc(nowUtc);
  if (issuedAt === undefined || expiresAt === undefined || lastActivityAt === undefined || now === undefined) {
    return true;
  }
  if (now < issuedAt || now >= expiresAt) return true;
  return now - lastActivityAt >= session.idleTimeoutMs;
}

export function isSessionReauthenticationRequired(session: Session, nowUtc: string): boolean {
  if (session.requiresReauthentication === true) return true;
  if (session.reauthenticationDueAtUtc === undefined) return false;
  const dueAt = parseUtc(session.reauthenticationDueAtUtc);
  const now = parseUtc(nowUtc);
  return dueAt === undefined || now === undefined || now >= dueAt;
}

export class SessionManager {
  private readonly sessionsByCredentialHash = new Map<string, Session>();
  private readonly credentialHashBySessionId = new Map<string, string>();
  private readonly now: () => string;
  private readonly sessionIdFactory: () => string;
  private readonly sessionCredentialFactory: () => string;
  private readonly csrfTokenFactory: () => string;
  private readonly policy: SessionPolicy;
  private readonly database?: EdgeDatabase;

  public constructor(options: SessionManagerOptions) {
    assertPolicy(options);
    this.policy = Object.freeze({
      idleTimeoutMs: options.idleTimeoutMs,
      maxLifetimeMs: options.maxLifetimeMs,
      reauthenticationIntervalMs: options.reauthenticationIntervalMs,
    });
    this.now = options.now ?? (() => new Date().toISOString());
    this.sessionIdFactory = options.sessionIdFactory ?? (() => randomBytes(18).toString("base64url"));
    this.sessionCredentialFactory = options.sessionCredentialFactory ?? (() => randomBytes(32).toString("base64url"));
    this.csrfTokenFactory = options.csrfTokenFactory ?? (() => randomBytes(32).toString("base64url"));
    this.database = options.database;
    this.load();
  }

  public createSession(identity: IdentityRecord, issuedAtUtc = this.now()): Session {
    return this.issueSession(identity, issuedAtUtc).session;
  }

  public issueSession(identity: IdentityRecord, issuedAtUtc = this.now()): IssuedSession {
    const issuedAt = parseUtc(issuedAtUtc);
    if (issuedAt === undefined) throw new Error("issuedAtUtc must be a valid timestamp");
    const sessionId = this.sessionIdFactory();
    if (sessionId.trim() === "" || this.credentialHashBySessionId.has(sessionId)) {
      throw new Error("session ID must be unique and non-empty");
    }
    const credential = this.sessionCredentialFactory();
    const credentialHash = hashSessionCredential(credential);
    if (credential.trim() === "" || this.sessionsByCredentialHash.has(credentialHash)) {
      throw new Error("session credential must be unique and non-empty");
    }
    const csrfToken = this.csrfTokenFactory();
    if (csrfToken.trim() === "") throw new Error("CSRF token must be non-empty");
    const session: Session = Object.freeze({
      sessionId,
      csrfToken,
      userId: identity.userId,
      roles: Object.freeze([...identity.roles]) as readonly UserRole[],
      missionIds: Object.freeze([...identity.missionIds]),
      issuedAtUtc: new Date(issuedAt).toISOString(),
      expiresAtUtc: formatUtc(issuedAt + this.policy.maxLifetimeMs),
      lastActivityAtUtc: new Date(issuedAt).toISOString(),
      idleTimeoutMs: this.policy.idleTimeoutMs,
      reauthenticationIntervalMs: this.policy.reauthenticationIntervalMs,
      reauthenticationDueAtUtc: this.policy.reauthenticationIntervalMs === 0
        ? undefined
        : formatUtc(issuedAt + this.policy.reauthenticationIntervalMs),
      state: "active",
      requiresReauthentication: false,
    });
    this.sessionsByCredentialHash.set(credentialHash, session);
    this.credentialHashBySessionId.set(sessionId, credentialHash);
    this.persist(credentialHash, session);
    return Object.freeze({ session, credential });
  }

  public getSession(sessionId: string, nowUtc = this.now()): Session | undefined {
    const credentialHash = this.credentialHashBySessionId.get(sessionId);
    if (credentialHash === undefined) return undefined;
    const session = this.sessionsByCredentialHash.get(credentialHash);
    if (session === undefined) return undefined;
    return this.evaluated(session, nowUtc);
  }

  public getSessionByCredential(credential: string, nowUtc = this.now()): Session | undefined {
    const session = this.sessionsByCredentialHash.get(hashSessionCredential(credential));
    if (session === undefined) return undefined;
    return this.evaluated(session, nowUtc);
  }

  public lockSession(sessionId: string, reason: string, lockedAtUtc = this.now()): void {
    const { credentialHash, session } = this.requireSession(sessionId);
    if (reason.trim() === "") throw new Error("session lock reason is required");
    this.sessionsByCredentialHash.set(credentialHash, Object.freeze({
      ...session,
      state: "locked",
      lockedAtUtc,
      lockReason: reason,
    }));
    this.persist(credentialHash, this.sessionsByCredentialHash.get(credentialHash)!);
  }

  public deleteSession(sessionId: string): void {
    const credentialHash = this.credentialHashBySessionId.get(sessionId);
    if (credentialHash === undefined) return;
    this.credentialHashBySessionId.delete(sessionId);
    this.sessionsByCredentialHash.delete(credentialHash);
    this.database?.sql().prepare("DELETE FROM sessions WHERE session_id = ?").run(sessionId);
  }

  public isReauthenticationRequired(sessionId: string, nowUtc = this.now()): boolean {
    const credentialHash = this.credentialHashBySessionId.get(sessionId);
    const session = credentialHash === undefined ? undefined : this.sessionsByCredentialHash.get(credentialHash);
    return session === undefined || isSessionReauthenticationRequired(session, nowUtc);
  }

  public touchSession(sessionId: string, nowUtc = this.now()): Session {
    const stored = this.requireSession(sessionId);
    return this.touchStoredSession(stored.credentialHash, stored.session, nowUtc);
  }

  public touchSessionByCredential(credential: string, nowUtc = this.now()): Session | undefined {
    const credentialHash = hashSessionCredential(credential);
    const session = this.sessionsByCredentialHash.get(credentialHash);
    if (session === undefined) return undefined;
    return this.touchStoredSession(credentialHash, session, nowUtc);
  }

  private touchStoredSession(credentialHash: string, session: Session, nowUtc: string): Session {
    const evaluated = this.evaluated(session, nowUtc);
    if (isSessionLocked(evaluated, nowUtc)) {
      const locked = Object.freeze({
        ...evaluated,
        state: "locked" as const,
        lockedAtUtc: evaluated.lockedAtUtc ?? nowUtc,
        lockReason: evaluated.lockReason ?? "idle timeout",
      });
      this.sessionsByCredentialHash.set(credentialHash, locked);
      this.persist(credentialHash, locked);
      return locked;
    }
    const touched = Object.freeze({
      ...evaluated,
      lastActivityAtUtc: nowUtc,
      requiresReauthentication: isSessionReauthenticationRequired(evaluated, nowUtc),
    });
    this.sessionsByCredentialHash.set(credentialHash, touched);
    this.persist(credentialHash, touched);
    return touched;
  }

  public reauthenticate(sessionId: string, identity: IdentityRecord, atUtc = this.now()): Session {
    const { credentialHash, session } = this.requireSession(sessionId);
    if (session.userId !== identity.userId) throw new Error("identity does not match session");
    if (isSessionLocked(session, atUtc)) throw new Error("session is locked or expired");
    const at = parseUtc(atUtc);
    if (at === undefined) throw new Error("reauthentication timestamp is invalid");
    const refreshed = Object.freeze({
      ...session,
      state: "active" as const,
      lastActivityAtUtc: new Date(at).toISOString(),
      requiresReauthentication: false,
      reauthenticationDueAtUtc: this.policy.reauthenticationIntervalMs === 0
        ? undefined
        : formatUtc(at + this.policy.reauthenticationIntervalMs),
    });
    this.sessionsByCredentialHash.set(credentialHash, refreshed);
    this.persist(credentialHash, refreshed);
    return refreshed;
  }

  private requireSession(sessionId: string): { credentialHash: string; session: Session } {
    const credentialHash = this.credentialHashBySessionId.get(sessionId);
    const session = credentialHash === undefined ? undefined : this.sessionsByCredentialHash.get(credentialHash);
    if (credentialHash === undefined || session === undefined) throw new Error("session does not exist");
    return { credentialHash, session };
  }

  private evaluated(session: Session, nowUtc: string): Session {
    if (isSessionLocked(session, nowUtc)) {
      const expiry = parseUtc(session.expiresAtUtc);
      const now = parseUtc(nowUtc);
      const expired = expiry !== undefined && now !== undefined && now >= expiry;
      return Object.freeze({
        ...session,
        state: expired ? "expired" as const : "locked" as const,
        lockedAtUtc: session.lockedAtUtc ?? nowUtc,
        lockReason: session.lockReason ?? (expired ? "session expired" : "idle timeout"),
      });
    }
    return Object.freeze({
      ...session,
      state: "active" as const,
      requiresReauthentication: isSessionReauthenticationRequired(session, nowUtc),
    });
  }

  private persist(credentialHash: string, session: Session): void {
    this.database?.sql().prepare(`INSERT INTO sessions (session_id, credential_hash, session_json, updated_at_utc)
      VALUES (?, ?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET credential_hash = excluded.credential_hash,
      session_json = excluded.session_json, updated_at_utc = excluded.updated_at_utc`)
      .run(session.sessionId, credentialHash, JSON.stringify(session), this.now());
  }

  private load(): void {
    if (this.database === undefined) return;
    const rows = this.database.sql().prepare("SELECT credential_hash, session_json FROM sessions ORDER BY session_id").all() as { credential_hash: string; session_json: string }[];
    for (const row of rows) {
      const session = Object.freeze(JSON.parse(row.session_json) as Session);
      this.sessionsByCredentialHash.set(row.credential_hash, session);
      this.credentialHashBySessionId.set(session.sessionId, row.credential_hash);
    }
  }
}

function hashSessionCredential(credential: string): string {
  return createHash("sha256").update(credential, "utf8").digest("base64url");
}

export function lockSession(manager: SessionManager, sessionId: string, reason: string): void {
  manager.lockSession(sessionId, reason);
}
