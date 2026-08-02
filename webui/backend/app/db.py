"""SQLite engine + FastAPI session dependency."""

from __future__ import annotations

from collections.abc import Iterator
import os
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

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


def get_engine():
    return _engine


def init_db() -> None:
    """Create tables. Import models for side-effect registration first."""
    from app import models  # noqa: F401
    from app import simulation_models  # noqa: F401

    SQLModel.metadata.create_all(_engine)


def get_session() -> Iterator[Session]:
    with Session(_engine) as session:
        yield session
