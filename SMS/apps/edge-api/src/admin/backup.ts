import { createHash, randomBytes } from "node:crypto";
import { copyFileSync, existsSync, readFileSync, renameSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";

export interface BackupVerification {
  readonly ok: boolean;
  readonly schemaVersion: number;
  readonly sha256: string;
}

type ReadonlySqlite = {
  prepare(sql: string): {
    get(...bindings: readonly unknown[]): unknown;
    all(...bindings: readonly unknown[]): unknown[];
    run(...bindings: readonly unknown[]): unknown;
  };
  exec(sql: string): void;
  close(): void;
};

function DatabaseSync(): new (path: string, options?: { readOnly?: boolean }) => ReadonlySqlite {
  const sqlite = process.getBuiltinModule("node:sqlite") as { DatabaseSync: new (path: string, options?: { readOnly?: boolean }) => ReadonlySqlite } | undefined;
  if (sqlite === undefined) throw new Error("SQLite is unavailable for backup verification");
  return sqlite.DatabaseSync;
}

function sha256(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

export function createDatabaseBackup(databasePath: string, backupPath: string): BackupVerification {
  if (!existsSync(databasePath)) throw new Error("database does not exist");
  const Sqlite = DatabaseSync();
  const source = new Sqlite(databasePath);
  try {
    source.exec("PRAGMA wal_checkpoint(TRUNCATE)");
    const result = source.prepare("PRAGMA integrity_check").get() as Record<string, unknown>;
    if (String(Object.values(result)[0]) !== "ok") throw new Error("database integrity check failed before backup");
  } finally {
    source.close();
  }
  copyFileSync(databasePath, backupPath);
  try {
    const backup = new Sqlite(backupPath);
    try {
      backup.prepare("DELETE FROM runtime_lease").run();
    } finally {
      backup.close();
    }
    return verifyDatabaseBackup(backupPath);
  } catch (error) {
    rmSync(backupPath, { force: true });
    throw error;
  }
}

export function verifyDatabaseBackup(backupPath: string): BackupVerification {
  if (!existsSync(backupPath)) throw new Error("backup does not exist");
  const Sqlite = DatabaseSync();
  let database: ReadonlySqlite;
  try {
    database = new Sqlite(backupPath, { readOnly: true });
  } catch (error) {
    throw new Error("backup is not a readable SQLite database", { cause: error });
  }
  try {
    const integrity = database.prepare("PRAGMA integrity_check").get() as Record<string, unknown>;
    if (String(Object.values(integrity)[0]) !== "ok") throw new Error("backup integrity check failed");
    const row = database.prepare("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations").get() as { version?: unknown };
    const schemaVersion = Number(row.version);
    if (!Number.isInteger(schemaVersion) || schemaVersion <= 0) throw new Error("backup schema version is invalid");
    return { ok: true, schemaVersion, sha256: sha256(backupPath) };
  } catch (error) {
    throw new Error("backup integrity verification failed", { cause: error });
  } finally {
    database.close();
  }
}

export function restoreDatabaseBackup(backupPath: string, databasePath: string): void {
  verifyDatabaseBackup(backupPath);
  const temporary = join(dirname(databasePath), `.sms-restore-${randomBytes(8).toString("hex")}.sqlite`);
  try {
    copyFileSync(backupPath, temporary);
    verifyDatabaseBackup(temporary);
    renameSync(temporary, databasePath);
    rmSync(`${databasePath}-wal`, { force: true });
    rmSync(`${databasePath}-shm`, { force: true });
  } finally {
    rmSync(temporary, { force: true });
  }
}
