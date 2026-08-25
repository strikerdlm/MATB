import { createHash, randomBytes } from "node:crypto";
import { closeSync, copyFileSync, existsSync, fsyncSync, linkSync, openSync, readFileSync, renameSync, rmSync, unlinkSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { SCHEMA_VERSION } from "../db/schema.js";
import { MaintenanceLock } from "./maintenance-lock.js";

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

function sqlitePathLiteral(path: string): string {
  return `'${path.replaceAll("'", "''")}'`;
}

function syncFile(path: string): void {
  const descriptor = openSync(path, "r");
  try {
    fsyncSync(descriptor);
  } finally {
    closeSync(descriptor);
  }
}

function syncDirectory(path: string): void {
  const descriptor = openSync(dirname(path), "r");
  try {
    fsyncSync(descriptor);
  } finally {
    closeSync(descriptor);
  }
}

export function createDatabaseBackup(databasePath: string, backupPath: string): BackupVerification {
  if (!existsSync(databasePath)) throw new Error("database does not exist");
  if (existsSync(backupPath)) throw new Error("backup output already exists and will not be overwritten");
  const Sqlite = DatabaseSync();
  const source = new Sqlite(databasePath);
  const temporary = join(dirname(backupPath), `.${basename(backupPath)}.${randomBytes(8).toString("hex")}.tmp`);
  try {
    const result = source.prepare("PRAGMA integrity_check").get() as Record<string, unknown>;
    if (String(Object.values(result)[0]) !== "ok") throw new Error("database integrity check failed before backup");
    source.exec(`VACUUM INTO ${sqlitePathLiteral(temporary)}`);
  } finally {
    source.close();
  }
  try {
    const backup = new Sqlite(temporary);
    try {
      backup.prepare("DELETE FROM runtime_lease").run();
    } finally {
      backup.close();
    }
    verifyDatabaseBackup(temporary);
    syncFile(temporary);
    linkSync(temporary, backupPath);
    unlinkSync(temporary);
    syncDirectory(backupPath);
    return verifyDatabaseBackup(backupPath);
  } catch (error) {
    rmSync(temporary, { force: true });
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
    if (!Number.isInteger(schemaVersion) || schemaVersion !== SCHEMA_VERSION) throw new Error(`backup schema version ${schemaVersion} is unsupported`);
    return { ok: true, schemaVersion, sha256: sha256(backupPath) };
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`backup integrity verification failed: ${detail}`, { cause: error });
  } finally {
    database.close();
  }
}

export function restoreDatabaseBackup(backupPath: string, databasePath: string, maintenanceLock?: MaintenanceLock): void {
  const ownedMaintenanceLock = maintenanceLock === undefined ? new MaintenanceLock(databasePath) : undefined;
  ownedMaintenanceLock?.acquire();
  try {
    restoreDatabaseBackupLocked(backupPath, databasePath);
  } finally {
    ownedMaintenanceLock?.release();
  }
}

function restoreDatabaseBackupLocked(backupPath: string, databasePath: string): void {
  verifyDatabaseBackup(backupPath);
  const temporary = join(dirname(databasePath), `.sms-restore-${randomBytes(8).toString("hex")}.sqlite`);
  const rollbackStem = `${databasePath}.pre-restore-${new Date().toISOString().replace(/[-:.]/g, "")}-${randomBytes(4).toString("hex")}`;
  const moved: Array<{ from: string; to: string }> = [];
  try {
    copyFileSync(backupPath, temporary);
    verifyDatabaseBackup(temporary);
    syncFile(temporary);
    for (const suffix of ["", "-wal", "-shm"] as const) {
      const source = `${databasePath}${suffix}`;
      if (!existsSync(source)) continue;
      const retained = `${rollbackStem}${suffix}`;
      renameSync(source, retained);
      moved.push({ from: retained, to: source });
    }
    renameSync(temporary, databasePath);
    verifyDatabaseBackup(databasePath);
    syncFile(databasePath);
    syncDirectory(databasePath);
  } catch (error) {
    if (existsSync(databasePath)) renameSync(databasePath, `${rollbackStem}.failed`);
    for (const entry of moved.reverse()) renameSync(entry.from, entry.to);
    throw error;
  } finally {
    rmSync(temporary, { force: true });
  }
}
