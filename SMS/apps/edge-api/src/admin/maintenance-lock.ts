import { mkdirSync } from "node:fs";
import { dirname } from "node:path";

type LockDatabase = { exec(sql: string): void; close(): void };

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
  public readonly lockPath: string;

  public constructor(public readonly targetPath: string, private readonly timeoutMs = 0) {
    this.lockPath = `${targetPath}.maintenance-lock.sqlite`;
  }

  public acquire(): void {
    if (this.targetPath === ":memory:") return;
    if (this.connection !== undefined) throw new MaintenanceLockError("maintenance lock is already acquired by this operation");
    mkdirSync(dirname(this.lockPath), { recursive: true });
    const Sqlite = sqliteConstructor();
    const connection = new Sqlite(this.lockPath, { timeout: this.timeoutMs });
    try {
      connection.exec(`PRAGMA busy_timeout = ${Math.max(0, this.timeoutMs)}; PRAGMA journal_mode = DELETE; CREATE TABLE IF NOT EXISTS maintenance_lock (singleton INTEGER PRIMARY KEY CHECK (singleton = 1)) STRICT; BEGIN EXCLUSIVE`);
      this.connection = connection;
    } catch (error) {
      connection.close();
      throw new MaintenanceLockError("service must be stopped; exclusive maintenance lock is unavailable", { cause: error });
    }
  }

  public release(): void {
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
