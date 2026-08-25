import { randomBytes } from "node:crypto";
import type { IdentityRecord } from "./identity.js";
import type { AuthorizationSubject, UserRole } from "./roles.js";

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

export interface SessionManagerOptions extends SessionPolicy {
  readonly now?: () => string;
  readonly sessionIdFactory?: () => string;
  readonly csrfTokenFactory?: () => string;
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
  private readonly sessions = new Map<string, Session>();
  private readonly now: () => string;
  private readonly sessionIdFactory: () => string;
  private readonly csrfTokenFactory: () => string;
  private readonly policy: SessionPolicy;

  public constructor(options: SessionManagerOptions) {
    assertPolicy(options);
    this.policy = Object.freeze({
      idleTimeoutMs: options.idleTimeoutMs,
      maxLifetimeMs: options.maxLifetimeMs,
      reauthenticationIntervalMs: options.reauthenticationIntervalMs,
    });
    this.now = options.now ?? (() => new Date().toISOString());
    this.sessionIdFactory = options.sessionIdFactory ?? (() => randomBytes(24).toString("base64url"));
    this.csrfTokenFactory = options.csrfTokenFactory ?? (() => randomBytes(32).toString("base64url"));
  }

  public createSession(identity: IdentityRecord, issuedAtUtc = this.now()): Session {
    const issuedAt = parseUtc(issuedAtUtc);
    if (issuedAt === undefined) throw new Error("issuedAtUtc must be a valid timestamp");
    const sessionId = this.sessionIdFactory();
    if (sessionId.trim() === "" || this.sessions.has(sessionId)) {
      throw new Error("session ID must be unique and non-empty");
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
    this.sessions.set(sessionId, session);
    return session;
  }

  public getSession(sessionId: string, nowUtc = this.now()): Session | undefined {
    const session = this.sessions.get(sessionId);
    if (session === undefined) return undefined;
    return this.evaluated(session, nowUtc);
  }

  public lockSession(sessionId: string, reason: string, lockedAtUtc = this.now()): void {
    const session = this.sessions.get(sessionId);
    if (session === undefined) throw new Error("session does not exist");
    if (reason.trim() === "") throw new Error("session lock reason is required");
    this.sessions.set(sessionId, Object.freeze({
      ...session,
      state: "locked",
      lockedAtUtc,
      lockReason: reason,
    }));
  }

  public deleteSession(sessionId: string): void {
    this.sessions.delete(sessionId);
  }

  public isReauthenticationRequired(sessionId: string, nowUtc = this.now()): boolean {
    const session = this.sessions.get(sessionId);
    return session === undefined || isSessionReauthenticationRequired(session, nowUtc);
  }

  public touchSession(sessionId: string, nowUtc = this.now()): Session {
    const session = this.requireSession(sessionId);
    const evaluated = this.evaluated(session, nowUtc);
    if (isSessionLocked(evaluated, nowUtc)) {
      this.lockSession(sessionId, "idle timeout", nowUtc);
      return this.sessions.get(sessionId)!;
    }
    const touched = Object.freeze({
      ...evaluated,
      lastActivityAtUtc: nowUtc,
      requiresReauthentication: isSessionReauthenticationRequired(evaluated, nowUtc),
    });
    this.sessions.set(sessionId, touched);
    return touched;
  }

  public reauthenticate(sessionId: string, identity: IdentityRecord, atUtc = this.now()): Session {
    const session = this.requireSession(sessionId);
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
    this.sessions.set(sessionId, refreshed);
    return refreshed;
  }

  private requireSession(sessionId: string): Session {
    const session = this.sessions.get(sessionId);
    if (session === undefined) throw new Error("session does not exist");
    return session;
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
}

export function lockSession(manager: SessionManager, sessionId: string, reason: string): void {
  manager.lockSession(sessionId, reason);
}
