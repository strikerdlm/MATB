import { createHash } from "node:crypto";
import { canonicalJson } from "@fac-isr/evidence";
import type { EdgeDatabase } from "../db/migrate.js";
import type { SqlDatabase } from "../db/schema.js";

export const AUDIT_SCHEMA_VERSION = 1;
export const GENESIS_HASH = "0".repeat(64);

export interface AuditEvent {
  readonly sequence: number;
  readonly eventId: string;
  readonly type: string;
  readonly actorUserId: string;
  readonly missionRevisionId?: string;
  readonly occurredAtUtc: string;
  readonly action: string;
  readonly reason: string;
  readonly evidenceSnapshotId?: string;
  readonly clientSessionId?: string;
  readonly schemaVersion: number;
  readonly payload: Readonly<Record<string, unknown>>;
  readonly previousHash: string;
  readonly hash: string;
}

/** Caller-supplied business facts. Sequence, predecessor, and hash are ledger-owned. */
export interface AuditEventInput {
  readonly eventId?: string;
  readonly type: string;
  readonly actorUserId: string;
  readonly missionRevisionId?: string;
  readonly occurredAtUtc?: string;
  readonly action?: string;
  readonly reason?: string;
  readonly evidenceSnapshotId?: string;
  readonly clientSessionId?: string;
  readonly schemaVersion?: number;
  readonly payload?: Readonly<Record<string, unknown>>;
}

export interface AuditVerificationReport {
  readonly ok: boolean;
  readonly firstBrokenSequence?: number;
  readonly checkedEvents: number;
}

export interface AuditFilter {
  readonly eventId?: string;
  readonly type?: string;
  readonly actorUserId?: string;
  readonly missionRevisionId?: string;
  readonly action?: string;
  readonly fromUtc?: string;
  readonly toUtc?: string;
}

export interface AuditPersistence {
  append(event: AuditEvent): Promise<void>;
  list(): Promise<readonly AuditEvent[]>;
  /** Test-only mutation hook; production callers have no update operation. */
  tamperForFixture?(sequence: number, changes: Partial<AuditEvent>): Promise<void>;
}

export class AtomicDomainWriteError extends Error {
  public constructor(message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = "AtomicDomainWriteError";
  }
}

export class AtomicConflictError extends Error {
  public constructor(message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = "AtomicConflictError";
  }
}

export type AuditDatabase = SqlDatabase | Pick<EdgeDatabase, "sql" | "assertFencingToken">;

export interface AuditLedgerOptions {
  readonly persistence?: AuditPersistence;
  readonly database?: AuditDatabase;
  readonly now?: () => string;
  readonly schemaVersion?: number;
}

export class AuditWriteError extends Error {
  public readonly code = "AUDIT_WRITE_FAILED";

  public constructor(message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = "AuditWriteError";
  }
}

function requiredText(value: unknown, field: string): string {
  if (typeof value !== "string" || value.length === 0 || value.trim() !== value || value.includes("\0")) {
    throw new TypeError(`${field} must be canonical non-empty text`);
  }
  return value;
}

function optionalText(value: unknown, field: string): string | undefined {
  if (value === undefined) return undefined;
  return requiredText(value, field);
}

function canonicalUtc(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(value)) {
    throw new TypeError("occurredAtUtc must be a UTC ISO-8601 timestamp");
  }
  const timestamp = new Date(value);
  if (!Number.isFinite(timestamp.getTime())) {
    throw new TypeError("occurredAtUtc must be a valid UTC instant");
  }
  return timestamp.toISOString();
}

function plainObject(value: unknown, field: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError(`${field} must be a plain object`);
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    throw new TypeError(`${field} must be a plain object`);
  }
  // This validates nested values and makes a detached copy before the event is stored.
  const copy = JSON.parse(canonicalJson(value)) as Record<string, unknown>;
  return copy;
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const child of Object.values(value as Record<string, unknown>)) deepFreeze(child);
    Object.freeze(value);
  }
  return value;
}

function optionalFields(event: AuditEvent): Record<string, unknown> {
  return {
    ...(event.missionRevisionId === undefined ? {} : { missionRevisionId: event.missionRevisionId }),
    ...(event.evidenceSnapshotId === undefined ? {} : { evidenceSnapshotId: event.evidenceSnapshotId }),
    ...(event.clientSessionId === undefined ? {} : { clientSessionId: event.clientSessionId }),
  };
}

function hashPayload(event: Omit<AuditEvent, "hash">): Record<string, unknown> {
  return {
    sequence: event.sequence,
    eventId: event.eventId,
    type: event.type,
    actorUserId: event.actorUserId,
    ...optionalFields(event as AuditEvent),
    occurredAtUtc: event.occurredAtUtc,
    action: event.action,
    reason: event.reason,
    schemaVersion: event.schemaVersion,
    payload: event.payload,
    previousHash: event.previousHash,
  };
}

/** Computes the deterministic SHA-256 digest over the event body and predecessor. */
export function hashAuditEvent(event: Omit<AuditEvent, "hash">): string {
  return createHash("sha256").update(canonicalJson(hashPayload(event))).digest("hex");
}

function cloneEvent(event: AuditEvent): AuditEvent {
  const payload = JSON.parse(canonicalJson(event.payload)) as Record<string, unknown>;
  return deepFreeze({ ...event, payload }) as AuditEvent;
}

function normalizeEvent(
  input: AuditEventInput,
  sequence: number,
  previousHash: string,
  now: () => string,
  defaultSchemaVersion: number,
): AuditEvent {
  if (!Number.isInteger(sequence) || sequence < 0) throw new RangeError("audit sequence must be non-negative");
  if (!/^[a-f0-9]{64}$/.test(previousHash)) throw new TypeError("previousHash must be a SHA-256 digest");

  const type = requiredText(input.type, "type");
  const eventId = input.eventId === undefined ? `${type}:${sequence}` : requiredText(input.eventId, "eventId");
  const actorUserId = requiredText(input.actorUserId, "actorUserId");
  const missionRevisionId = optionalText(input.missionRevisionId, "missionRevisionId");
  const occurredAtUtc = canonicalUtc(input.occurredAtUtc ?? now());
  const payload = plainObject(input.payload ?? {}, "payload");
  const action = requiredText(
    input.action ?? (typeof payload.action === "string" ? payload.action : type),
    "action",
  );
  const reason = requiredText(
    input.reason ?? (typeof payload.reason === "string" ? payload.reason : "unspecified"),
    "reason",
  );
  const evidenceSnapshotId = optionalText(input.evidenceSnapshotId, "evidenceSnapshotId")
    ?? optionalText(payload.evidenceSnapshotId, "payload.evidenceSnapshotId");
  const clientSessionId = optionalText(input.clientSessionId, "clientSessionId")
    ?? optionalText(payload.clientSessionId, "payload.clientSessionId");
  const schemaVersion = input.schemaVersion ?? defaultSchemaVersion;
  if (!Number.isInteger(schemaVersion) || schemaVersion <= 0) {
    throw new RangeError("schemaVersion must be a positive integer");
  }

  const body = {
    sequence,
    eventId,
    type,
    actorUserId,
    ...(missionRevisionId === undefined ? {} : { missionRevisionId }),
    occurredAtUtc,
    action,
    reason,
    ...(evidenceSnapshotId === undefined ? {} : { evidenceSnapshotId }),
    ...(clientSessionId === undefined ? {} : { clientSessionId }),
    schemaVersion,
    payload: deepFreeze(payload),
    previousHash,
  } as Omit<AuditEvent, "hash">;
  const hash = hashAuditEvent(body);
  return deepFreeze({ ...body, hash }) as AuditEvent;
}

function verifyEvents(events: readonly AuditEvent[]): AuditVerificationReport {
  let previousHash = GENESIS_HASH;
  let firstBrokenSequence: number | undefined;
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index];
    let hashMatches = false;
    if (event !== undefined) {
      try {
        hashMatches = event.hash === hashAuditEvent(event);
      } catch {
        hashMatches = false;
      }
    }
    const valid = event !== undefined
      && event.sequence === index
      && event.previousHash === previousHash
      && hashMatches;
    if (!valid && firstBrokenSequence === undefined) firstBrokenSequence = event?.sequence ?? index;
    if (event !== undefined) previousHash = event.hash;
  }
  return firstBrokenSequence === undefined
    ? { ok: true, checkedEvents: events.length }
    : { ok: false, firstBrokenSequence, checkedEvents: events.length };
}

export class MemoryAuditPersistence implements AuditPersistence {
  private readonly events: AuditEvent[] = [];

  public async append(event: AuditEvent): Promise<void> {
    if (event.sequence !== this.events.length) throw new Error("audit sequence is not append-only");
    if (this.events.some((item) => item.eventId === event.eventId)) throw new Error("audit event ID already exists");
    this.events.push(cloneEvent(event));
  }

  public async list(): Promise<readonly AuditEvent[]> {
    return this.events.map(cloneEvent);
  }

  public async tamperForFixture(sequence: number, changes: Partial<AuditEvent>): Promise<void> {
    const index = this.events.findIndex((event) => event.sequence === sequence);
    if (index < 0) throw new RangeError(`audit sequence ${sequence} does not exist`);
    const existing = this.events[index]!;
    const payload = changes.payload === undefined
      ? existing.payload
      : deepFreeze(plainObject(changes.payload, "payload"));
    this.events[index] = deepFreeze({ ...existing, ...changes, payload }) as AuditEvent;
  }
}

function resolveDatabase(database: AuditDatabase): SqlDatabase {
  if ("exec" in database && "prepare" in database && "close" in database) return database;
  return database.sql();
}

interface StoredAuditRow {
  sequence: number;
  event_id: string;
  type: string;
  actor_user_id: string;
  mission_revision_id: string | null;
  occurred_at_utc: string;
  action: string;
  reason: string;
  evidence_snapshot_id: string | null;
  client_session_id: string | null;
  schema_version: number;
  payload_json: string;
  previous_hash: string;
  hash: string;
}

/** SQLite persistence used by the edge node; the table is created without a schema-version bump. */
export class SqliteAuditPersistence implements AuditPersistence {
  private readonly database: SqlDatabase;
  private readonly edgeDatabase?: Pick<EdgeDatabase, "assertFencingToken">;

  public constructor(database: AuditDatabase) {
    this.database = resolveDatabase(database);
    this.edgeDatabase = "assertFencingToken" in database ? database : undefined;
    this.database.exec(`
      CREATE TABLE IF NOT EXISTS audit_events (
        sequence INTEGER PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        type TEXT NOT NULL,
        actor_user_id TEXT NOT NULL,
        mission_revision_id TEXT,
        occurred_at_utc TEXT NOT NULL,
        action TEXT NOT NULL,
        reason TEXT NOT NULL,
        evidence_snapshot_id TEXT,
        client_session_id TEXT,
        schema_version INTEGER NOT NULL,
        payload_json TEXT NOT NULL,
        previous_hash TEXT NOT NULL,
        hash TEXT NOT NULL
      ) STRICT
    `);
  }

  public async append(event: AuditEvent): Promise<void> {
    this.database.exec("BEGIN IMMEDIATE");
    try {
      this.appendSync(event);
      this.database.exec("COMMIT");
    } catch (error) {
      this.database.exec("ROLLBACK");
      throw error;
    }
  }

  private appendSync(event: AuditEvent): void {
    this.edgeDatabase?.assertFencingToken();
    this.database.prepare(`
      INSERT INTO audit_events
        (sequence, event_id, type, actor_user_id, mission_revision_id, occurred_at_utc,
         action, reason, evidence_snapshot_id, client_session_id, schema_version,
         payload_json, previous_hash, hash)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      event.sequence,
      event.eventId,
      event.type,
      event.actorUserId,
      event.missionRevisionId ?? null,
      event.occurredAtUtc,
      event.action,
      event.reason,
      event.evidenceSnapshotId ?? null,
      event.clientSessionId ?? null,
      event.schemaVersion,
      canonicalJson(event.payload),
      event.previousHash,
      event.hash,
    );
  }

  public async list(): Promise<readonly AuditEvent[]> {
    return this.listSync();
  }

  private listSync(): AuditEvent[] {
    const rows = this.database
      .prepare("SELECT * FROM audit_events ORDER BY sequence ASC")
      .all() as StoredAuditRow[];
    return rows.map((row) => deepFreeze({
      sequence: Number(row.sequence),
      eventId: String(row.event_id),
      type: String(row.type),
      actorUserId: String(row.actor_user_id),
      ...(row.mission_revision_id === null ? {} : { missionRevisionId: String(row.mission_revision_id) }),
      occurredAtUtc: String(row.occurred_at_utc),
      action: String(row.action),
      reason: String(row.reason),
      ...(row.evidence_snapshot_id === null ? {} : { evidenceSnapshotId: String(row.evidence_snapshot_id) }),
      ...(row.client_session_id === null ? {} : { clientSessionId: String(row.client_session_id) }),
      schemaVersion: Number(row.schema_version),
      payload: deepFreeze(JSON.parse(String(row.payload_json)) as Record<string, unknown>),
      previousHash: String(row.previous_hash),
      hash: String(row.hash),
    })) as AuditEvent[];
  }

  public commitAtomic(
    inputs: readonly AuditEventInput[],
    now: () => string,
    schemaVersion: number,
    writeDomain: () => void,
  ): AuditEvent[] {
    this.database.exec("BEGIN IMMEDIATE");
    try {
      this.edgeDatabase?.assertFencingToken();
      const integrity = this.database.prepare("PRAGMA quick_check").get() as Record<string, unknown>;
      if (String(Object.values(integrity)[0] ?? "") !== "ok") throw new AuditWriteError("database integrity check failed; approval writes are disabled");
      const existing = this.listSync();
      const report = verifyEvents(existing);
      if (!report.ok) throw new AuditWriteError("audit chain is corrupted; approval writes are disabled");
      const events: AuditEvent[] = [];
      let sequence = existing.length;
      let previousHash = existing.at(-1)?.hash ?? GENESIS_HASH;
      for (const input of inputs) {
        const event = normalizeEvent(input, sequence, previousHash, now, schemaVersion);
        if (existing.some(({ eventId }) => eventId === event.eventId) || events.some(({ eventId }) => eventId === event.eventId)) {
          throw new Error("audit event ID already exists");
        }
        events.push(event);
        sequence += 1;
        previousHash = event.hash;
      }
      writeDomain();
      for (const event of events) this.appendSync(event);
      this.database.exec("COMMIT");
      return events.map(cloneEvent);
    } catch (error) {
      this.database.exec("ROLLBACK");
      throw error;
    }
  }

  public async tamperForFixture(sequence: number, changes: Partial<AuditEvent>): Promise<void> {
    const updates: string[] = [];
    const bindings: unknown[] = [];
    const add = (column: string, value: unknown): void => {
      updates.push(`${column} = ?`);
      bindings.push(value);
    };
    if (Object.prototype.hasOwnProperty.call(changes, "eventId")) add("event_id", changes.eventId);
    if (Object.prototype.hasOwnProperty.call(changes, "type")) add("type", changes.type);
    if (Object.prototype.hasOwnProperty.call(changes, "actorUserId")) add("actor_user_id", changes.actorUserId);
    if (Object.prototype.hasOwnProperty.call(changes, "missionRevisionId")) add("mission_revision_id", changes.missionRevisionId ?? null);
    if (Object.prototype.hasOwnProperty.call(changes, "occurredAtUtc")) add("occurred_at_utc", changes.occurredAtUtc);
    if (Object.prototype.hasOwnProperty.call(changes, "action")) add("action", changes.action);
    if (Object.prototype.hasOwnProperty.call(changes, "reason")) add("reason", changes.reason);
    if (Object.prototype.hasOwnProperty.call(changes, "evidenceSnapshotId")) add("evidence_snapshot_id", changes.evidenceSnapshotId ?? null);
    if (Object.prototype.hasOwnProperty.call(changes, "clientSessionId")) add("client_session_id", changes.clientSessionId ?? null);
    if (Object.prototype.hasOwnProperty.call(changes, "schemaVersion")) add("schema_version", changes.schemaVersion);
    if (Object.prototype.hasOwnProperty.call(changes, "payload")) add("payload_json", canonicalJson(changes.payload ?? {}));
    if (Object.prototype.hasOwnProperty.call(changes, "previousHash")) add("previous_hash", changes.previousHash);
    if (Object.prototype.hasOwnProperty.call(changes, "hash")) add("hash", changes.hash);
    if (updates.length === 0) throw new Error("fixture tamper requires at least one field");
    bindings.push(sequence);
    this.database.prepare(`UPDATE audit_events SET ${updates.join(", ")} WHERE sequence = ?`).run(...bindings);
  }
}

export class AuditLedger {
  private readonly persistence: AuditPersistence;
  private readonly now: () => string;
  private readonly schemaVersion: number;
  private readOnlySafeMode = false;
  private appendTail: Promise<void> = Promise.resolve();

  public constructor(options: AuditLedgerOptions = {}) {
    if (options.persistence !== undefined && options.database !== undefined) {
      throw new Error("provide either audit persistence or a database, not both");
    }
    this.persistence = options.persistence
      ?? (options.database === undefined ? new MemoryAuditPersistence() : new SqliteAuditPersistence(options.database));
    this.now = options.now ?? (() => new Date().toISOString());
    this.schemaVersion = options.schemaVersion ?? AUDIT_SCHEMA_VERSION;
    if (!Number.isInteger(this.schemaVersion) || this.schemaVersion <= 0) {
      throw new RangeError("schemaVersion must be a positive integer");
    }
  }

  public append(input: AuditEventInput): Promise<AuditEvent> {
    const operation = this.appendTail.then(() => this.appendInternal(input));
    this.appendTail = operation.then(() => undefined, () => undefined);
    return operation;
  }

  public appendAuditEvent(input: AuditEventInput): Promise<AuditEvent> {
    return this.append(input);
  }

  public commitAtomic(inputs: readonly AuditEventInput[], writeDomain: () => void): Promise<readonly AuditEvent[]> {
    const operation = this.appendTail.then(() => this.commitAtomicInternal(inputs, writeDomain));
    this.appendTail = operation.then(() => undefined, () => undefined);
    return operation;
  }

  public async verifyAuditChain(): Promise<AuditVerificationReport> {
    let events: readonly AuditEvent[];
    try {
      events = await this.persistence.list();
    } catch {
      this.readOnlySafeMode = true;
      return { ok: false, checkedEvents: 0 };
    }
    const report = verifyEvents(events);
    if (!report.ok) this.readOnlySafeMode = true;
    return report;
  }

  public async queryAudit(filter: AuditFilter = {}): Promise<AuditEvent[]> {
    const events = await this.persistence.list();
    return events
      .filter((event) => filter.eventId === undefined || event.eventId === filter.eventId)
      .filter((event) => filter.type === undefined || event.type === filter.type)
      .filter((event) => filter.actorUserId === undefined || event.actorUserId === filter.actorUserId)
      .filter((event) => filter.missionRevisionId === undefined || event.missionRevisionId === filter.missionRevisionId)
      .filter((event) => filter.action === undefined || event.action === filter.action)
      .filter((event) => filter.fromUtc === undefined || event.occurredAtUtc >= filter.fromUtc)
      .filter((event) => filter.toUtc === undefined || event.occurredAtUtc <= filter.toUtc)
      .map(cloneEvent);
  }

  public async canApprove(): Promise<boolean> {
    if (this.readOnlySafeMode) return false;
    const report = await this.verifyAuditChain();
    return !this.readOnlySafeMode && report.ok;
  }

  public async simulateWriteFailure(): Promise<void> {
    this.readOnlySafeMode = true;
  }

  public isReadOnlySafeMode(): boolean {
    return this.readOnlySafeMode;
  }

  /** Fixture-only recovery hook for tests that model a repaired local database. */
  public clearReadOnlySafeMode(): void {
    this.readOnlySafeMode = false;
  }

  public async tamperForFixture(sequence: number, changes: Partial<AuditEvent>): Promise<void> {
    if (this.persistence.tamperForFixture === undefined) {
      throw new Error("audit persistence does not expose fixture tampering");
    }
    await this.persistence.tamperForFixture(sequence, changes);
  }

  private async appendInternal(input: AuditEventInput): Promise<AuditEvent> {
    if (this.readOnlySafeMode) throw new AuditWriteError("audit ledger is in read-only safe mode");

    let existing: readonly AuditEvent[];
    try {
      existing = await this.persistence.list();
    } catch (error) {
      this.readOnlySafeMode = true;
      throw new AuditWriteError("audit database cannot be read", { cause: error });
    }
    const currentReport = verifyEvents(existing);
    if (!currentReport.ok) {
      this.readOnlySafeMode = true;
      throw new AuditWriteError("audit chain is corrupted; approval writes are disabled");
    }
    const eventId = input.eventId === undefined ? `${input.type}:${existing.length}` : requiredText(input.eventId, "eventId");
    if (existing.some((event) => event.eventId === eventId)) throw new Error("audit event ID already exists");
    const event = normalizeEvent(
      input,
      existing.length,
      existing.at(-1)?.hash ?? GENESIS_HASH,
      this.now,
      this.schemaVersion,
    );
    try {
      await this.persistence.append(event);
    } catch (error) {
      this.readOnlySafeMode = true;
      throw new AuditWriteError("audit database cannot append; approval writes are disabled", { cause: error });
    }
    return cloneEvent(event);
  }

  private async commitAtomicInternal(inputs: readonly AuditEventInput[], writeDomain: () => void): Promise<readonly AuditEvent[]> {
    if (this.readOnlySafeMode) throw new AuditWriteError("audit ledger is in read-only safe mode");
    if (!(this.persistence instanceof SqliteAuditPersistence)) {
      const events: AuditEvent[] = [];
      writeDomain();
      for (const input of inputs) events.push(await this.appendInternal(input));
      return events;
    }
    try {
      return this.persistence.commitAtomic(inputs, this.now, this.schemaVersion, writeDomain);
    } catch (error) {
      if (error instanceof AtomicConflictError) throw error;
      this.readOnlySafeMode = true;
      if (error instanceof AtomicDomainWriteError) throw error;
      if (error instanceof AuditWriteError) throw error;
      throw new AuditWriteError("atomic audit and domain commit failed; writes are disabled", { cause: error });
    }
  }
}

export { AuditLedger as OperationalAuditLedger };

const defaultAuditLedger = new AuditLedger();

export function appendAuditEvent(event: AuditEventInput, ledger: AuditLedger = defaultAuditLedger): Promise<AuditEvent> {
  return ledger.append(event);
}

export function verifyAuditChain(ledger: AuditLedger = defaultAuditLedger): Promise<AuditVerificationReport> {
  return ledger.verifyAuditChain();
}

export function queryAudit(filter: AuditFilter = {}, ledger: AuditLedger = defaultAuditLedger): Promise<AuditEvent[]> {
  return ledger.queryAudit(filter);
}
