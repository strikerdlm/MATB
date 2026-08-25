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

export const SCHEMA_VERSION = 2;

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
  {
    version: 2,
    statements: [
      `CREATE TABLE identities (
        user_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        qualification_refs_json TEXT NOT NULL DEFAULT '[]',
        disabled_at_utc TEXT
      ) STRICT`,
      `CREATE TABLE credential_versions (
        user_id TEXT NOT NULL REFERENCES identities(user_id) ON DELETE CASCADE,
        version INTEGER NOT NULL CHECK (version > 0),
        salt BLOB NOT NULL,
        password_hash BLOB NOT NULL,
        created_at_utc TEXT NOT NULL,
        retired_at_utc TEXT,
        PRIMARY KEY (user_id, version)
      ) STRICT`,
      `CREATE TABLE identity_roles (
        user_id TEXT NOT NULL REFERENCES identities(user_id) ON DELETE CASCADE,
        role TEXT NOT NULL,
        PRIMARY KEY (user_id, role)
      ) STRICT`,
      `CREATE TABLE mission_assignments (
        user_id TEXT NOT NULL REFERENCES identities(user_id) ON DELETE CASCADE,
        mission_id TEXT NOT NULL,
        qualification_refs_json TEXT NOT NULL DEFAULT '[]',
        PRIMARY KEY (user_id, mission_id)
      ) STRICT`,
      `CREATE TABLE login_lockout_state (
        user_id TEXT PRIMARY KEY REFERENCES identities(user_id) ON DELETE CASCADE,
        failed_attempts INTEGER NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
        locked_until_utc TEXT
      ) STRICT`,
      `CREATE TABLE sessions (
        session_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        credential_version INTEGER NOT NULL CHECK (credential_version > 0),
        credential_hash TEXT NOT NULL UNIQUE,
        csrf_hash TEXT NOT NULL,
        session_json TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL,
        FOREIGN KEY (user_id, credential_version) REFERENCES credential_versions(user_id, version) ON DELETE CASCADE
      ) STRICT`,
      `CREATE TABLE trusted_keys (
        key_id TEXT PRIMARY KEY,
        scope TEXT NOT NULL,
        algorithm TEXT NOT NULL,
        public_key_pem TEXT NOT NULL,
        added_at_utc TEXT NOT NULL,
        added_by_user_id TEXT NOT NULL
      ) STRICT`,
      `CREATE TABLE packages (
        package_id TEXT NOT NULL,
        version TEXT NOT NULL,
        kind TEXT,
        state TEXT NOT NULL,
        imported_at_utc TEXT NOT NULL,
        record_json TEXT NOT NULL,
        PRIMARY KEY (package_id, version)
      ) STRICT`,
      `CREATE TABLE package_state_generation (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        generation INTEGER NOT NULL CHECK (generation >= 0)
      ) STRICT`,
      `INSERT INTO package_state_generation (singleton, generation) VALUES (1, 0)`,
      `CREATE TABLE active_package_roles (
        role TEXT PRIMARY KEY,
        package_id TEXT NOT NULL,
        version TEXT NOT NULL,
        FOREIGN KEY (package_id, version) REFERENCES packages(package_id, version)
      ) STRICT`,
      `CREATE TABLE missions (
        mission_id TEXT PRIMARY KEY,
        current_revision INTEGER NOT NULL CHECK (current_revision >= 0),
        state_version INTEGER NOT NULL DEFAULT 1 CHECK (state_version > 0)
      ) STRICT`,
      `CREATE TABLE mission_revisions (
        revision_id TEXT PRIMARY KEY,
        mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
        revision INTEGER NOT NULL CHECK (revision >= 0),
        revision_json TEXT NOT NULL,
        UNIQUE (mission_id, revision)
      ) STRICT`,
      `CREATE TABLE evaluation_envelopes (
        revision_id TEXT PRIMARY KEY REFERENCES mission_revisions(revision_id) ON DELETE CASCADE,
        envelope_json TEXT NOT NULL,
        stale INTEGER NOT NULL CHECK (stale IN (0, 1))
      ) STRICT`,
      `CREATE TABLE checklist_responses (
        response_id TEXT PRIMARY KEY,
        revision_id TEXT NOT NULL REFERENCES mission_revisions(revision_id) ON DELETE CASCADE,
        item_id TEXT NOT NULL,
        response_json TEXT NOT NULL,
        UNIQUE (revision_id, item_id)
      ) STRICT`,
      `CREATE TABLE gate_decisions (
        decision_id TEXT PRIMARY KEY,
        revision_id TEXT NOT NULL REFERENCES mission_revisions(revision_id) ON DELETE CASCADE,
        gate TEXT NOT NULL,
        aircraft_scope TEXT NOT NULL DEFAULT '',
        decision_json TEXT NOT NULL,
        UNIQUE (revision_id, gate, aircraft_scope)
      ) STRICT`,
      `CREATE TABLE postflight_records (
        revision_id TEXT PRIMARY KEY REFERENCES mission_revisions(revision_id) ON DELETE CASCADE,
        record_json TEXT NOT NULL
      ) STRICT`,
      `CREATE TABLE occurrences (
        occurrence_id TEXT PRIMARY KEY,
        revision_id TEXT NOT NULL REFERENCES mission_revisions(revision_id) ON DELETE CASCADE,
        record_json TEXT NOT NULL,
        UNIQUE (revision_id, occurrence_id)
      ) STRICT`,
      `CREATE TABLE audit_events (
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
      ) STRICT`,
      `CREATE TABLE runtime_lease (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        holder_id TEXT NOT NULL,
        fencing_token INTEGER NOT NULL CHECK (fencing_token > 0),
        acquired_at_utc TEXT NOT NULL,
        expires_at_utc TEXT NOT NULL
      ) STRICT`,
    ],
  },
];

export function configureDatabase(database: SqlDatabase, lockTimeoutMs: number): void {
  database.exec("PRAGMA foreign_keys = ON");
  database.exec("PRAGMA journal_mode = WAL");
  database.exec(`PRAGMA busy_timeout = ${lockTimeoutMs}`);
}
