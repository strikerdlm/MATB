"""SQLite engine + FastAPI session dependency."""

from __future__ import annotations

from collections.abc import Iterator
import os
from pathlib import Path

from sqlalchemy import event, inspect, text
from sqlmodel import Session, SQLModel, create_engine

from matb_integration.physiology.durability import (
    fsync_directory,
    make_private_directory,
)

_DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "matb_webui.db"
_configured_db_path = os.getenv("MATB_DB_PATH")
if _configured_db_path is not None and not _configured_db_path.strip():
    raise ValueError("MATB_DB_PATH must not be empty")
_DB_PATH = (
    Path(_configured_db_path).expanduser().resolve()
    if _configured_db_path
    else _DEFAULT_DB_PATH
)
_engine = create_engine(f"sqlite:///{_DB_PATH}", connect_args={"check_same_thread": False})


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """Enable SQLite's opt-in referential-integrity checks per connection."""

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


event.listen(_engine, "connect", _enable_sqlite_foreign_keys)


def get_engine():
    return _engine


def init_db() -> None:
    """Create tables. Import models for side-effect registration first."""
    from app import models  # noqa: F401
    from app import liftoff_models  # noqa: F401
    from app import classic_models  # noqa: F401
    from app import simulation_models  # noqa: F401
    from app import study_models  # noqa: F401

    database_path = _database_path(_engine)
    database_existed = database_path.is_file() if database_path is not None else True
    if database_path is not None and not database_path.parent.exists():
        make_private_directory(database_path.parent)
    SQLModel.metadata.create_all(_engine)
    if database_path is not None and database_path.is_file():
        if os.name != "nt":
            os.chmod(database_path, 0o600)
        if not database_existed:
            fsync_directory(database_path.parent)
    _migrate_classic_attempt_provenance()


def _database_path(engine) -> Path | None:
    """Return the on-disk SQLite path, excluding memory/URI databases."""

    if engine.dialect.name != "sqlite":
        return None
    raw = engine.url.database
    if not raw or raw == ":memory:" or raw.startswith("file:"):
        return None
    return Path(raw).expanduser().resolve()


def _migrate_classic_attempt_provenance() -> None:
    """Add provenance columns to databases created before classic v1.1."""

    additions = {
        "scenario_sha256": "VARCHAR",
        "openmatb_source_sha256": "VARCHAR",
        "test_mode": "BOOLEAN NOT NULL DEFAULT 0",
        "wall_time_scale": "FLOAT NOT NULL DEFAULT 1.0",
        "recovery_started_at": "DATETIME",
        "terminal_intent_status": "VARCHAR",
        "terminal_intent_reason_code": "VARCHAR",
    }
    with _engine.begin() as connection:
        existing = {
            column["name"]
            for column in inspect(connection).get_columns("classic_session_attempt")
        }
        for name, declaration in additions.items():
            if name not in existing:
                connection.execute(
                    text(
                        f"ALTER TABLE classic_session_attempt ADD COLUMN {name} {declaration}"
                    )
                )


def get_session() -> Iterator[Session]:
    with Session(_engine) as session:
        yield session
