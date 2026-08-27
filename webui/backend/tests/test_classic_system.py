from __future__ import annotations

import sqlite3
import os
from pathlib import Path
import stat

import pytest
from sqlalchemy import inspect
from sqlmodel import create_engine

from app import db as db_module
from app.db import _enable_sqlite_foreign_keys
from app.main import _classic_wall_time_scale, _polar_backend
from matb_integration.physiology.backend import BleakPolarBackend, SimulatedPolarBackend


def test_sqlite_connections_enable_foreign_key_enforcement() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        _enable_sqlite_foreign_keys(connection, None)
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
    finally:
        connection.close()


def test_init_db_migrates_existing_classic_attempt_provenance_columns(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE classic_session_attempt (id VARCHAR PRIMARY KEY)"
        )
    monkeypatch.setattr(db_module, "_engine", engine)

    db_module.init_db()

    with engine.connect() as connection:
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("classic_session_attempt")
        }
    assert {
        "scenario_sha256",
        "openmatb_source_sha256",
        "test_mode",
        "wall_time_scale",
        "recovery_started_at",
        "terminal_intent_status",
        "terminal_intent_reason_code",
    } <= columns
    if os.name != "nt":
        assert stat.S_IMODE((tmp_path / "legacy.db").stat().st_mode) == 0o600


def test_classic_wall_time_acceleration_is_locked_behind_explicit_test_mode(
    monkeypatch,
) -> None:
    monkeypatch.delenv("MATB_CLASSIC_TEST_MODE", raising=False)
    monkeypatch.setenv("MATB_CLASSIC_WALL_TIME_SCALE", "0.001")
    assert _classic_wall_time_scale() == 1.0

    monkeypatch.setenv("MATB_CLASSIC_TEST_MODE", "1")
    assert _classic_wall_time_scale() == 0.001
    monkeypatch.setenv("MATB_CLASSIC_WALL_TIME_SCALE", "nan")
    with pytest.raises(ValueError, match="finite decimal"):
        _classic_wall_time_scale()


def test_polar_backend_is_real_by_default_and_simulated_only_in_test_mode(
    monkeypatch,
) -> None:
    monkeypatch.delenv("MATB_CLASSIC_TEST_MODE", raising=False)
    monkeypatch.delenv("MATB_POLAR_BACKEND", raising=False)
    assert isinstance(_polar_backend(), BleakPolarBackend)

    monkeypatch.setenv("MATB_POLAR_BACKEND", "simulated")
    with pytest.raises(ValueError, match="MATB_CLASSIC_TEST_MODE"):
        _polar_backend()

    monkeypatch.setenv("MATB_CLASSIC_TEST_MODE", "1")
    assert isinstance(_polar_backend(), SimulatedPolarBackend)

    monkeypatch.setenv("MATB_POLAR_BACKEND", "unknown")
    with pytest.raises(ValueError, match="MATB_POLAR_BACKEND"):
        _polar_backend()
