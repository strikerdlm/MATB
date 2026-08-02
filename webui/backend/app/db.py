"""SQLite engine + FastAPI session dependency."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

_DB_PATH = Path(__file__).resolve().parents[1] / "matb_webui.db"
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
