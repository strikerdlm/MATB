"""SQLite engine + FastAPI session dependency."""

from __future__ import annotations

import os
from collections.abc import Iterator
from importlib import import_module
from pathlib import Path

from sqlalchemy import event, inspect, text
from sqlmodel import Session, SQLModel, create_engine

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "matb_webui.db"


def _resolve_db_path(configured_path: str | None) -> Path:
    """Resolve configured database paths independently of the caller's cwd."""

    if configured_path is None:
        return _DEFAULT_DB_PATH
    if not configured_path.strip():
        raise ValueError("MATB_DB_PATH must not be empty")
    candidate = Path(configured_path).expanduser()
    if not candidate.is_absolute():
        candidate = _REPOSITORY_ROOT / candidate
    return candidate.resolve()


_configured_db_path = os.getenv("MATB_DB_PATH")
_DB_PATH = _resolve_db_path(_configured_db_path)
_engine = create_engine(f"sqlite:///{_DB_PATH}", connect_args={"check_same_thread": False})


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA foreign_keys")
        enabled = cursor.fetchone()
    finally:
        cursor.close()
    if enabled is None or int(enabled[0]) != 1:
        raise RuntimeError("SQLite foreign-key enforcement could not be enabled")


def _configure_sqlite_foreign_keys(engine) -> None:
    """Enable SQLite referential integrity on every DB-API connection."""

    if engine.dialect.name != "sqlite":
        raise RuntimeError("MATB Research Console requires SQLite")
    if not event.contains(engine, "connect", _enable_sqlite_foreign_keys):
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)


def _audit_sqlite_foreign_keys(engine) -> None:
    """Fail startup if a legacy database already contains orphaned rows."""

    if engine.dialect.name != "sqlite":
        raise RuntimeError("MATB Research Console requires SQLite")
    with engine.connect() as connection:
        violations = connection.execute(text("PRAGMA foreign_key_check")).all()
    if violations:
        preview = ", ".join(
            f"{row[0]} rowid={row[1]} parent={row[2]} constraint={row[3]}"
            for row in violations[:10]
        )
        suffix = "" if len(violations) <= 10 else f" (+{len(violations) - 10} more)"
        raise RuntimeError(
            "SQLite foreign-key orphan audit failed: " + preview + suffix
        )


_configure_sqlite_foreign_keys(_engine)


def get_engine():
    return _engine


def init_db(*, component_model_modules: tuple[str, ...] = ()) -> None:
    """Create tables. Import models for side-effect registration first."""
    from app import (
        models,  # noqa: F401
        study_models,  # noqa: F401
    )

    for module_name in component_model_modules:
        import_module(module_name)

    SQLModel.metadata.create_all(_engine)
    _migrate_openmatb_visual_theme_v1(_engine)
    _migrate_openmatb_visual_profile_v1(_engine)
    _migrate_analysisresult_v2(_engine)
    _migrate_bayesresult_v3(_engine)
    _audit_sqlite_foreign_keys(_engine)


def _migrate_openmatb_visual_theme_v1(engine) -> None:
    """Add an immutable presentation condition to legacy OpenMATB sessions."""
    if engine.dialect.name != "sqlite":
        raise RuntimeError("MATB Research Console migrations require SQLite")

    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "openmatb_suite_session" not in tables:
            return
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS matb_schema_migration (
                version VARCHAR PRIMARY KEY,
                applied_at DATETIME NOT NULL
            )
        """))
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("openmatb_suite_session")
        }
        if "visual_theme" not in columns:
            connection.execute(text(
                "ALTER TABLE openmatb_suite_session "
                "ADD COLUMN visual_theme VARCHAR NOT NULL DEFAULT 'classic'"
            ))
        connection.execute(text("""
            INSERT OR IGNORE INTO matb_schema_migration (version, applied_at)
            VALUES ('openmatb-visual-theme-v1', CURRENT_TIMESTAMP)
        """))


def _migrate_openmatb_visual_profile_v1(engine) -> None:
    """Add nullable immutable visual-profile provenance to legacy sessions.

    Existing rows deliberately remain null. Their historical ``visual_theme``
    value is preserved and no profile hash is fabricated during migration.
    """

    if engine.dialect.name != "sqlite":
        raise RuntimeError("MATB Research Console migrations require SQLite")

    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "openmatb_suite_session" not in tables:
            return
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS matb_schema_migration (
                version VARCHAR PRIMARY KEY,
                applied_at DATETIME NOT NULL
            )
        """))
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("openmatb_suite_session")
        }
        additions = {
            "visual_profile_id": "VARCHAR",
            "visual_profile_version": "VARCHAR",
            "visual_profile_schema_version": "VARCHAR",
            "visual_profile_sha256": "VARCHAR",
        }
        for column, sql_type in additions.items():
            if column not in columns:
                connection.execute(text(
                    f"ALTER TABLE openmatb_suite_session ADD COLUMN {column} {sql_type}"
                ))
        connection.execute(text("""
            INSERT OR IGNORE INTO matb_schema_migration (version, applied_at)
            VALUES ('openmatb-visual-profile-v1', CURRENT_TIMESTAMP)
        """))


def _migrate_analysisresult_v2(engine) -> None:
    """Archive legacy duplicate cache rows before enforcing cache identity."""

    if engine.dialect.name != "sqlite":
        raise RuntimeError("MATB Research Console migrations require SQLite")

    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "analysisresult" not in tables:
            return

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS matb_schema_migration (
                version VARCHAR PRIMARY KEY,
                applied_at DATETIME NOT NULL
            )
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS analysisresult_migration_archive_v1 (
                source_id INTEGER PRIMARY KEY,
                fingerprint VARCHAR NOT NULL,
                engine_version VARCHAR NOT NULL,
                artifact_json TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                archived_at DATETIME NOT NULL,
                reason VARCHAR NOT NULL
            )
        """))

        duplicate_keys = connection.execute(text("""
            SELECT fingerprint, engine_version
            FROM analysisresult
            GROUP BY fingerprint, engine_version
            HAVING COUNT(*) > 1
        """)).mappings().all()
        for key in duplicate_keys:
            rows = connection.execute(
                text("""
                    SELECT id
                    FROM analysisresult
                    WHERE fingerprint = :fingerprint
                      AND engine_version = :engine_version
                    ORDER BY created_at DESC, id DESC
                """),
                dict(key),
            ).mappings().all()
            for duplicate in rows[1:]:
                connection.execute(
                    text("""
                        INSERT OR IGNORE INTO analysisresult_migration_archive_v1 (
                            source_id, fingerprint, engine_version, artifact_json,
                            created_at, archived_at, reason
                        )
                        SELECT
                            id, fingerprint, engine_version, artifact_json,
                            created_at, CURRENT_TIMESTAMP,
                            'duplicate_fingerprint_and_engine_version'
                        FROM analysisresult
                        WHERE id = :source_id
                    """),
                    {"source_id": duplicate["id"]},
                )
                connection.execute(
                    text("DELETE FROM analysisresult WHERE id = :source_id"),
                    {"source_id": duplicate["id"]},
                )

        connection.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS
                uq_analysisresult_fingerprint_version
            ON analysisresult (fingerprint, engine_version)
        """))
        connection.execute(text("""
            INSERT OR IGNORE INTO matb_schema_migration (version, applied_at)
            VALUES ('analysisresult-v2', CURRENT_TIMESTAMP)
        """))


def _migrate_bayesresult_v3(engine) -> None:
    """Upgrade the durable Bayesian-job cache without losing legacy rows.

    ``create_all`` deliberately does not mutate existing tables.  This small,
    versioned SQLite migration therefore adds the retry fields introduced in
    v3, archives duplicate legacy cache keys, and only then enforces the cache
    identity used by the current ORM model. It is safe to run on every start.
    """

    if engine.dialect.name != "sqlite":
        raise RuntimeError("MATB Research Console migrations require SQLite")

    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "bayesresult" not in tables:
            return

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS matb_schema_migration (
                version VARCHAR PRIMARY KEY,
                applied_at DATETIME NOT NULL
            )
        """))
        existing = {
            column["name"]
            for column in inspect(connection).get_columns("bayesresult")
        }
        if "attempt_count" not in existing:
            connection.execute(text(
                "ALTER TABLE bayesresult "
                "ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 1"
            ))
        if "error_history_json" not in existing:
            connection.execute(text(
                "ALTER TABLE bayesresult "
                "ADD COLUMN error_history_json TEXT NOT NULL DEFAULT '[]'"
            ))
        if "last_attempt_at" not in existing:
            connection.execute(text(
                "ALTER TABLE bayesresult ADD COLUMN last_attempt_at DATETIME"
            ))
        if "owner_token" not in existing:
            connection.execute(text(
                "ALTER TABLE bayesresult ADD COLUMN owner_token VARCHAR"
            ))
        connection.execute(text(
            "UPDATE bayesresult "
            "SET last_attempt_at = COALESCE(last_attempt_at, created_at)"
        ))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS bayesresult_migration_archive_v1 (
                source_id INTEGER PRIMARY KEY,
                fingerprint VARCHAR NOT NULL,
                bayes_version VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                artifact_json TEXT,
                error TEXT,
                attempt_count INTEGER NOT NULL,
                error_history_json TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                last_attempt_at DATETIME,
                finished_at DATETIME,
                archived_at DATETIME NOT NULL,
                reason VARCHAR NOT NULL
            )
        """))
        archive_columns = {
            column["name"]
            for column in inspect(connection).get_columns(
                "bayesresult_migration_archive_v1"
            )
        }
        if "last_attempt_at" not in archive_columns:
            connection.execute(text(
                "ALTER TABLE bayesresult_migration_archive_v1 "
                "ADD COLUMN last_attempt_at DATETIME"
            ))

        duplicate_keys = connection.execute(text("""
            SELECT fingerprint, bayes_version
            FROM bayesresult
            GROUP BY fingerprint, bayes_version
            HAVING COUNT(*) > 1
        """)).mappings().all()
        for key in duplicate_keys:
            rows = connection.execute(
                text("""
                    SELECT id, status, created_at, finished_at
                    FROM bayesresult
                    WHERE fingerprint = :fingerprint
                      AND bayes_version = :bayes_version
                    ORDER BY
                        CASE status
                            WHEN 'done' THEN 0
                            WHEN 'running' THEN 1
                            WHEN 'queued' THEN 2
                            ELSE 3
                        END,
                        COALESCE(finished_at, created_at) DESC,
                        id DESC
                """),
                dict(key),
            ).mappings().all()
            for duplicate in rows[1:]:
                connection.execute(
                    text("""
                        INSERT OR IGNORE INTO bayesresult_migration_archive_v1 (
                            source_id, fingerprint, bayes_version, status,
                            artifact_json, error, attempt_count,
                            error_history_json, created_at, last_attempt_at, finished_at,
                            archived_at, reason
                        )
                        SELECT
                            id, fingerprint, bayes_version, status,
                            artifact_json, error, attempt_count,
                            error_history_json, created_at, last_attempt_at, finished_at,
                            CURRENT_TIMESTAMP,
                            'duplicate_fingerprint_and_bayes_version'
                        FROM bayesresult
                        WHERE id = :source_id
                    """),
                    {"source_id": duplicate["id"]},
                )
                connection.execute(
                    text("DELETE FROM bayesresult WHERE id = :source_id"),
                    {"source_id": duplicate["id"]},
                )

        connection.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS
                uq_bayesresult_fingerprint_version
            ON bayesresult (fingerprint, bayes_version)
        """))
        active_rows = connection.execute(text("""
            SELECT id
            FROM bayesresult
            WHERE status IN ('queued', 'running')
            ORDER BY COALESCE(last_attempt_at, created_at) DESC, id DESC
        """)).mappings().all()
        for superseded in active_rows[1:]:
            connection.execute(text("""
                UPDATE bayesresult
                SET status = 'failed',
                    error = COALESCE(error, 'migration_concurrent_active_job'),
                    finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP)
                WHERE id = :source_id
            """), {"source_id": superseded["id"]})
        connection.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS
                uq_bayesresult_one_active
            ON bayesresult ((1))
            WHERE status IN ('queued', 'running')
        """))
        connection.execute(text("""
            INSERT OR IGNORE INTO matb_schema_migration (version, applied_at)
            VALUES ('bayesresult-v3', CURRENT_TIMESTAMP)
        """))


def get_session() -> Iterator[Session]:
    with Session(_engine) as session:
        yield session
