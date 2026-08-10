import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { configureDatabase, MIGRATIONS, SCHEMA_VERSION } from "./schema.js";
import type { SqlDatabase } from "./schema.js";

type SqlRow = Record<string, unknown>;

export class EdgeDatabase {
  public constructor(private readonly database: SqlDatabase) {}

  /** Exposes the configured local connection to services that own their tables. */
  public sql(): SqlDatabase {
    return this.database;
  }

  public migrate(): void {
    const highestVersion = this.schemaVersion();
    if (highestVersion > SCHEMA_VERSION) {
      throw new Error(`database schema ${highestVersion} is newer than supported ${SCHEMA_VERSION}`);
    }

    this.database.exec("BEGIN IMMEDIATE");
    try {
      for (const migration of MIGRATIONS) {
        if (migration.version <= highestVersion) continue;
        for (const statement of migration.statements) this.database.exec(statement);
        this.database
          .prepare("INSERT INTO schema_migrations (version, applied_at_utc) VALUES (?, ?)")
          .run(migration.version, new Date().toISOString());
      }
      this.database.exec("COMMIT");
    } catch (error) {
      this.database.exec("ROLLBACK");
      throw error;
    }
  }

  public schemaVersion(): number {
    const tableExists = this.database
      .prepare("SELECT 1 AS present FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'")
      .get() as SqlRow | undefined;
    if (tableExists === undefined) return 0;
    const row = this.database
      .prepare("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations")
      .get() as SqlRow;
    return Number(row.version);
  }

  public pragma(name: "foreign_keys" | "journal_mode" | "busy_timeout"): number | string {
    const row = this.database.prepare(`PRAGMA ${name}`).get() as SqlRow;
    const value = Object.values(row)[0];
    if (typeof value !== "number" && typeof value !== "string") {
      throw new Error(`PRAGMA ${name} returned no scalar value`);
    }
    return value;
  }

  public tableNames(): string[] {
    const rows = this.database
      .prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
      .all() as SqlRow[];
    return rows.map((row) => String(row.name));
  }

  public close(): void {
    this.database.close();
  }
}

export function openDatabase(databaseUrl: string, lockTimeoutMs = 5_000): EdgeDatabase {
  if (databaseUrl !== ":memory:") {
    mkdirSync(dirname(databaseUrl), { recursive: true });
  }
  const sqlite = process.getBuiltinModule("node:sqlite") as
    | { DatabaseSync: new (path: string, options: { enableForeignKeyConstraints: boolean; timeout: number }) => SqlDatabase }
    | undefined;
  if (sqlite === undefined) {
    throw new Error("the Node.js built-in SQLite module is unavailable");
  }
  const database = new sqlite.DatabaseSync(databaseUrl, {
    enableForeignKeyConstraints: true,
    timeout: lockTimeoutMs,
  });
  configureDatabase(database, lockTimeoutMs);
  const edgeDatabase = new EdgeDatabase(database);
  edgeDatabase.migrate();
  return edgeDatabase;
}
