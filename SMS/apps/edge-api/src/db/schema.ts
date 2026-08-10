export interface SqlStatement {
  run(...bindings: readonly unknown[]): unknown;
  get(...bindings: readonly unknown[]): unknown;
  all(...bindings: readonly unknown[]): unknown[];
}

export interface SqlDatabase {
  exec(sql: string): void;
  prepare(sql: string): SqlStatement;
  close(): void;
}

export const SCHEMA_VERSION = 1;

export interface Migration {
  readonly version: number;
  readonly statements: readonly string[];
}

export const MIGRATIONS: readonly Migration[] = [
  {
    version: 1,
    statements: [
      `CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY CHECK (version > 0),
        applied_at_utc TEXT NOT NULL
      ) STRICT`,
      `CREATE TABLE IF NOT EXISTS service_state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
      ) STRICT`,
    ],
  },
];

export function configureDatabase(database: SqlDatabase, lockTimeoutMs: number): void {
  database.exec("PRAGMA foreign_keys = ON");
  database.exec("PRAGMA journal_mode = WAL");
  database.exec(`PRAGMA busy_timeout = ${lockTimeoutMs}`);
}
