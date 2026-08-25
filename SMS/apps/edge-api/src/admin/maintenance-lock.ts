import { existsSync, mkdirSync, realpathSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";

type LockDatabase = { exec(sql: string): void; close(): void };
const acquiredLocks = new WeakMap<MaintenanceLock, string>();

function sqliteConstructor(): new (path: string, options?: { timeout?: number }) => LockDatabase {
  const sqlite = process.getBuiltinModule("node:sqlite") as { DatabaseSync?: new (path: string, options?: { timeout?: number }) => LockDatabase } | undefined;
  if (sqlite?.DatabaseSync === undefined) throw new Error("SQLite is unavailable for maintenance locking");
  return sqlite.DatabaseSync;
}

export class MaintenanceLockError extends Error {
  public constructor(message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = "MaintenanceLockError";
  }
}

/**
 * A target-independent process lock. The exclusive transaction is held on a
 * separate SQLite file, so OS file locks are released automatically on crash
 * and remain usable when the operational database is physically corrupt.
 */
export class MaintenanceLock {
  private connection?: LockDatabase;
  private acquired = false;
  private readonly canonicalTargetPath: string;
  public readonly lockPath: string;

  public constructor(public readonly targetPath: string, private readonly timeoutMs = 0) {
    this.canonicalTargetPath = canonicalTarget(targetPath);
    this.lockPath = `${this.canonicalTargetPath}.maintenance-lock.sqlite`;
  }

  public acquire(): void {
    if (this.acquired) throw new MaintenanceLockError("maintenance lock is already acquired by this operation");
    if (this.targetPath === ":memory:") {
      this.acquired = true;
      acquiredLocks.set(this, this.canonicalTargetPath);
      return;
    }
    mkdirSync(dirname(this.lockPath), { recursive: true });
    const Sqlite = sqliteConstructor();
    const connection = new Sqlite(this.lockPath, { timeout: this.timeoutMs });
    try {
      connection.exec(`PRAGMA busy_timeout = ${Math.max(0, this.timeoutMs)}; PRAGMA journal_mode = DELETE; CREATE TABLE IF NOT EXISTS maintenance_lock (singleton INTEGER PRIMARY KEY CHECK (singleton = 1)) STRICT; BEGIN EXCLUSIVE`);
      this.connection = connection;
      this.acquired = true;
      acquiredLocks.set(this, this.canonicalTargetPath);
    } catch (error) {
      connection.close();
      throw new MaintenanceLockError("service must be stopped; exclusive maintenance lock is unavailable", { cause: error });
    }
  }

  public release(): void {
    if (!this.acquired) return;
    this.acquired = false;
    acquiredLocks.delete(this);
    if (this.connection === undefined) return;
    const connection = this.connection;
    this.connection = undefined;
    try {
      connection.exec("ROLLBACK");
    } finally {
      connection.close();
    }
  }

}

/**
 * Validate an ownership capability kept in module-private state. Callers
 * cannot forge it by constructing or monkeypatching a MaintenanceLock.
 */
export function assertMaintenanceLockOwnership(lock: unknown, targetPath: string): asserts lock is MaintenanceLock {
  if (!(lock instanceof MaintenanceLock)) throw new MaintenanceLockError("an acquired maintenance lock is required");
  const ownedTarget = acquiredLocks.get(lock);
  if (ownedTarget === undefined) throw new MaintenanceLockError("maintenance lock is not acquired by this operation");
  if (ownedTarget !== canonicalTarget(targetPath)) throw new MaintenanceLockError("maintenance lock target does not match the protected database");
}

function canonicalTarget(targetPath: string): string {
  if (targetPath === ":memory:") return targetPath;
  const absolute = resolve(targetPath);
  mkdirSync(dirname(absolute), { recursive: true });
  if (existsSync(absolute)) return realpathSync.native(absolute);
  return join(realpathSync.native(dirname(absolute)), basename(absolute));
}
