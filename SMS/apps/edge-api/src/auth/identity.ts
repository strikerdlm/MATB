import { randomBytes, scryptSync, timingSafeEqual } from "node:crypto";
import type { Session, SessionManager } from "./session.js";
import { isUserRole, type UserRole } from "./roles.js";

export interface IdentityRegistration {
  readonly userId: string;
  readonly displayName: string;
  readonly roles: readonly UserRole[];
  readonly missionIds?: readonly string[];
  readonly qualificationRefs?: readonly string[];
  readonly password: string;
  readonly disabledAtUtc?: string;
}

export interface IdentityRecord {
  readonly userId: string;
  readonly displayName: string;
  readonly roles: readonly UserRole[];
  readonly missionIds: readonly string[];
  readonly qualificationRefs: readonly string[];
  readonly disabledAtUtc?: string;
}

export interface LocalCredentials {
  readonly userId: string;
  readonly password: string;
}

export type AuthenticationEventType =
  | "authentication.succeeded"
  | "authentication.failed"
  | "identity.locked";

export interface AuthenticationEvent {
  readonly type: AuthenticationEventType;
  readonly userId: string;
  readonly occurredAtUtc: string;
  readonly reason: "invalid_credentials" | "identity_locked" | "identity_disabled" | "too_many_failures" | "accepted";
}

export interface IdentityStoreOptions {
  readonly now?: () => string;
  readonly maxFailedAttempts?: number;
  readonly lockoutDurationMs?: number;
}

interface StoredIdentity {
  readonly record: IdentityRecord;
  readonly salt: Uint8Array;
  readonly passwordHash: Uint8Array;
  failedAttempts: number;
  lockedUntilEpochMs?: number;
}

export class AuthenticationError extends Error {
  public readonly code = "INVALID_LOCAL_CREDENTIALS";

  public constructor() {
    super("invalid local credentials");
    this.name = "AuthenticationError";
  }
}

function canonicalText(value: string, field: string): string {
  if (typeof value !== "string" || value.trim() === "" || value !== value.trim() || value.includes("\0")) {
    throw new Error(`${field} must be canonical non-empty text`);
  }
  return value;
}

function parseUtc(value: string): number | undefined {
  const timestamp = new Date(value);
  return Number.isFinite(timestamp.getTime()) ? timestamp.getTime() : undefined;
}

function assertOptions(options: Required<Pick<IdentityStoreOptions, "maxFailedAttempts" | "lockoutDurationMs">>): void {
  if (!Number.isInteger(options.maxFailedAttempts) || options.maxFailedAttempts <= 0) {
    throw new Error("maxFailedAttempts must be a positive integer");
  }
  if (!Number.isInteger(options.lockoutDurationMs) || options.lockoutDurationMs <= 0) {
    throw new Error("lockoutDurationMs must be a positive integer");
  }
}

export class LocalIdentityStore {
  private readonly identities = new Map<string, StoredIdentity>();
  private readonly events: AuthenticationEvent[] = [];
  private readonly now: () => string;
  private readonly maxFailedAttempts: number;
  private readonly lockoutDurationMs: number;

  public constructor(options: IdentityStoreOptions = {}) {
    this.now = options.now ?? (() => new Date().toISOString());
    this.maxFailedAttempts = options.maxFailedAttempts ?? 5;
    this.lockoutDurationMs = options.lockoutDurationMs ?? 300_000;
    assertOptions({
      maxFailedAttempts: this.maxFailedAttempts,
      lockoutDurationMs: this.lockoutDurationMs,
    });
  }

  public register(input: IdentityRegistration): IdentityRecord {
    const userId = canonicalText(input.userId, "userId");
    const displayName = canonicalText(input.displayName, "displayName");
    if (this.identities.has(userId)) throw new Error("identity already exists");
    if (typeof input.password !== "string" || input.password.length < 12) {
      throw new Error("password must contain at least 12 characters");
    }
    const roles = [...input.roles];
    if (roles.length === 0 || roles.some((role) => !isUserRole(role))) {
      throw new Error("identity must have at least one supported role");
    }
    const missionIds = [...(input.missionIds ?? [])].map((missionId) => canonicalText(missionId, "missionId"));
    const qualificationRefs = [...(input.qualificationRefs ?? [])]
      .map((reference) => canonicalText(reference, "qualificationRef"));
    const record: IdentityRecord = Object.freeze({
      userId,
      displayName,
      roles: Object.freeze(roles),
      missionIds: Object.freeze(missionIds),
      qualificationRefs: Object.freeze(qualificationRefs),
      ...(input.disabledAtUtc === undefined ? {} : { disabledAtUtc: canonicalText(input.disabledAtUtc, "disabledAtUtc") }),
    });
    const salt = randomBytes(16);
    const passwordHash = scryptSync(input.password, salt, 32);
    this.identities.set(userId, {
      record,
      salt,
      passwordHash,
      failedAttempts: 0,
    });
    return record;
  }

  public getIdentity(userId: string): IdentityRecord | undefined {
    return this.identities.get(userId)?.record;
  }

  public getLoginState(userId: string): { readonly failedAttempts: number; readonly lockedUntilUtc?: string } | undefined {
    const stored = this.identities.get(userId);
    if (stored === undefined) return undefined;
    return Object.freeze({
      failedAttempts: stored.failedAttempts,
      ...(stored.lockedUntilEpochMs === undefined ? {} : { lockedUntilUtc: new Date(stored.lockedUntilEpochMs).toISOString() }),
    });
  }

  public authenticationEvents(): readonly AuthenticationEvent[] {
    return Object.freeze(this.events.map((event) => Object.freeze({ ...event })));
  }

  public authenticate(credentials: LocalCredentials): IdentityRecord {
    const userId = typeof credentials?.userId === "string" ? credentials.userId : "unknown";
    const stored = this.identities.get(userId);
    const occurredAtUtc = this.currentTime();
    if (stored === undefined) {
      this.recordEvent({ type: "authentication.failed", userId, occurredAtUtc, reason: "invalid_credentials" });
      throw new AuthenticationError();
    }
    const now = parseUtc(occurredAtUtc);
    if (now === undefined) throw new Error("identity store clock returned an invalid timestamp");
    if (stored.record.disabledAtUtc !== undefined) {
      this.recordEvent({ type: "authentication.failed", userId, occurredAtUtc, reason: "identity_disabled" });
      throw new AuthenticationError();
    }
    if (stored.lockedUntilEpochMs !== undefined && now < stored.lockedUntilEpochMs) {
      this.recordEvent({ type: "authentication.failed", userId, occurredAtUtc, reason: "identity_locked" });
      throw new AuthenticationError();
    }
    if (stored.lockedUntilEpochMs !== undefined && now >= stored.lockedUntilEpochMs) {
      stored.lockedUntilEpochMs = undefined;
      stored.failedAttempts = 0;
    }

    const password = typeof credentials?.password === "string" ? credentials.password : "";
    const candidate = scryptSync(password, stored.salt, 32);
    const valid = candidate.length === stored.passwordHash.length
      && timingSafeEqual(candidate, stored.passwordHash);
    if (!valid) {
      stored.failedAttempts += 1;
      this.recordEvent({ type: "authentication.failed", userId, occurredAtUtc, reason: "invalid_credentials" });
      if (stored.failedAttempts >= this.maxFailedAttempts) {
        stored.lockedUntilEpochMs = now + this.lockoutDurationMs;
        this.recordEvent({ type: "identity.locked", userId, occurredAtUtc, reason: "too_many_failures" });
      }
      throw new AuthenticationError();
    }

    stored.failedAttempts = 0;
    stored.lockedUntilEpochMs = undefined;
    this.recordEvent({ type: "authentication.succeeded", userId, occurredAtUtc, reason: "accepted" });
    return stored.record;
  }

  private currentTime(): string {
    const value = this.now();
    if (parseUtc(value) === undefined) throw new Error("identity store clock returned an invalid timestamp");
    return new Date(value).toISOString();
  }

  private recordEvent(event: AuthenticationEvent): void {
    this.events.push(Object.freeze({ ...event }));
  }
}

export class LocalAuthenticator {
  public constructor(
    private readonly identityStore: LocalIdentityStore,
    private readonly sessionManager: SessionManager,
  ) {}

  public async authenticateLocal(credentials: LocalCredentials): Promise<Session> {
    const identity = this.identityStore.authenticate(credentials);
    return this.sessionManager.createSession(identity);
  }

  public async reauthenticateLocal(sessionId: string, credentials: LocalCredentials): Promise<Session> {
    const identity = this.identityStore.authenticate(credentials);
    return this.sessionManager.reauthenticate(sessionId, identity);
  }
}

export async function authenticateLocal(
  credentials: LocalCredentials,
  authenticator: LocalAuthenticator,
): Promise<Session> {
  return authenticator.authenticateLocal(credentials);
}
