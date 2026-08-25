import { randomBytes, scryptSync, timingSafeEqual } from "node:crypto";
import type { IssuedSession, Session, SessionManager } from "./session.js";
import { isUserRole, type UserRole } from "./roles.js";
import type { EdgeDatabase } from "../db/migrate.js";

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
  readonly database?: EdgeDatabase;
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
  private readonly database?: EdgeDatabase;

  public constructor(options: IdentityStoreOptions = {}) {
    this.now = options.now ?? (() => new Date().toISOString());
    this.maxFailedAttempts = options.maxFailedAttempts ?? 5;
    this.lockoutDurationMs = options.lockoutDurationMs ?? 900_000;
    this.database = options.database;
    assertOptions({
      maxFailedAttempts: this.maxFailedAttempts,
      lockoutDurationMs: this.lockoutDurationMs,
    });
    this.load();
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
    const stored = {
      record,
      salt,
      passwordHash,
      failedAttempts: 0,
    };
    this.persistRegistration(stored);
    this.identities.set(userId, stored);
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
      this.persistLoginState(stored);
      throw new AuthenticationError();
    }

    stored.failedAttempts = 0;
    stored.lockedUntilEpochMs = undefined;
    this.persistLoginState(stored);
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

  public disable(userId: string, disabledAtUtc = this.currentTime()): IdentityRecord {
    const stored = this.identities.get(userId);
    if (stored === undefined) throw new Error("identity does not exist");
    const record = Object.freeze({ ...stored.record, disabledAtUtc });
    this.database?.sql().prepare("UPDATE identities SET disabled_at_utc = ? WHERE user_id = ?").run(disabledAtUtc, userId);
    this.identities.set(userId, { ...stored, record });
    return record;
  }

  public assign(userId: string, input: Pick<IdentityRegistration, "roles" | "missionIds" | "qualificationRefs">): IdentityRecord {
    const stored = this.identities.get(userId);
    if (stored === undefined) throw new Error("identity does not exist");
    const roles = [...input.roles];
    if (roles.length === 0 || roles.some((role) => !isUserRole(role))) throw new Error("identity must have at least one supported role");
    const missionIds = [...(input.missionIds ?? [])].map((missionId) => canonicalText(missionId, "missionId"));
    const qualificationRefs = [...(input.qualificationRefs ?? [])].map((reference) => canonicalText(reference, "qualificationRef"));
    const record = Object.freeze({ ...stored.record, roles: Object.freeze(roles), missionIds: Object.freeze(missionIds), qualificationRefs: Object.freeze(qualificationRefs) });
    if (this.database !== undefined) {
      const sql = this.database.sql();
      sql.exec("BEGIN IMMEDIATE");
      try {
        sql.prepare("UPDATE identities SET qualification_refs_json = ? WHERE user_id = ?").run(JSON.stringify(qualificationRefs), userId);
        sql.prepare("DELETE FROM identity_roles WHERE user_id = ?").run(userId);
        sql.prepare("DELETE FROM mission_assignments WHERE user_id = ?").run(userId);
        for (const role of roles) sql.prepare("INSERT INTO identity_roles (user_id, role) VALUES (?, ?)").run(userId, role);
        for (const missionId of missionIds) sql.prepare("INSERT INTO mission_assignments (user_id, mission_id, qualification_refs_json) VALUES (?, ?, ?)").run(userId, missionId, JSON.stringify(qualificationRefs));
        sql.exec("COMMIT");
      } catch (error) {
        sql.exec("ROLLBACK");
        throw error;
      }
    }
    this.identities.set(userId, { ...stored, record });
    return record;
  }

  public listIdentities(): readonly IdentityRecord[] {
    return Object.freeze([...this.identities.values()].map(({ record }) => record));
  }

  private persistRegistration(stored: StoredIdentity): void {
    if (this.database === undefined) return;
    const sql = this.database.sql();
    sql.exec("BEGIN IMMEDIATE");
    try {
      sql.prepare("INSERT INTO identities (user_id, display_name, qualification_refs_json, disabled_at_utc) VALUES (?, ?, ?, ?)")
        .run(stored.record.userId, stored.record.displayName, JSON.stringify(stored.record.qualificationRefs), stored.record.disabledAtUtc ?? null);
      sql.prepare("INSERT INTO credential_versions (user_id, version, salt, password_hash, created_at_utc) VALUES (?, 1, ?, ?, ?)")
        .run(stored.record.userId, stored.salt, stored.passwordHash, this.currentTime());
      for (const role of stored.record.roles) sql.prepare("INSERT INTO identity_roles (user_id, role) VALUES (?, ?)").run(stored.record.userId, role);
      for (const missionId of stored.record.missionIds) sql.prepare("INSERT INTO mission_assignments (user_id, mission_id, qualification_refs_json) VALUES (?, ?, ?)").run(stored.record.userId, missionId, JSON.stringify(stored.record.qualificationRefs));
      sql.prepare("INSERT INTO login_lockout_state (user_id, failed_attempts) VALUES (?, 0)").run(stored.record.userId);
      sql.exec("COMMIT");
    } catch (error) {
      sql.exec("ROLLBACK");
      throw error;
    }
  }

  private persistLoginState(stored: StoredIdentity): void {
    this.database?.sql().prepare("UPDATE login_lockout_state SET failed_attempts = ?, locked_until_utc = ? WHERE user_id = ?")
      .run(stored.failedAttempts, stored.lockedUntilEpochMs === undefined ? null : new Date(stored.lockedUntilEpochMs).toISOString(), stored.record.userId);
  }

  private load(): void {
    if (this.database === undefined) return;
    const sql = this.database.sql();
    const rows = sql.prepare(`SELECT i.user_id, i.display_name, i.qualification_refs_json, i.disabled_at_utc,
      c.salt, c.password_hash, l.failed_attempts, l.locked_until_utc
      FROM identities i
      JOIN credential_versions c ON c.user_id = i.user_id AND c.retired_at_utc IS NULL
      LEFT JOIN login_lockout_state l ON l.user_id = i.user_id
      ORDER BY i.user_id, c.version DESC`).all() as Array<Record<string, unknown>>;
    for (const row of rows) {
      const userId = String(row.user_id);
      if (this.identities.has(userId)) continue;
      const roles = (sql.prepare("SELECT role FROM identity_roles WHERE user_id = ? ORDER BY role").all(userId) as { role: string }[]).map(({ role }) => role as UserRole);
      const missionIds = (sql.prepare("SELECT mission_id FROM mission_assignments WHERE user_id = ? ORDER BY mission_id").all(userId) as { mission_id: string }[]).map(({ mission_id }) => mission_id);
      const qualificationRefs = JSON.parse(String(row.qualification_refs_json)) as string[];
      const record: IdentityRecord = Object.freeze({ userId, displayName: String(row.display_name), roles: Object.freeze(roles), missionIds: Object.freeze(missionIds), qualificationRefs: Object.freeze(qualificationRefs), ...(row.disabled_at_utc === null ? {} : { disabledAtUtc: String(row.disabled_at_utc) }) });
      this.identities.set(userId, { record, salt: Buffer.from(row.salt as Uint8Array), passwordHash: Buffer.from(row.password_hash as Uint8Array), failedAttempts: Number(row.failed_attempts ?? 0), ...(row.locked_until_utc === null || row.locked_until_utc === undefined ? {} : { lockedUntilEpochMs: Date.parse(String(row.locked_until_utc)) }) });
    }
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

  public async authenticateLocalWithCredential(credentials: LocalCredentials): Promise<IssuedSession> {
    const identity = this.identityStore.authenticate(credentials);
    return this.sessionManager.issueSession(identity);
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
