from __future__ import annotations

from pathlib import Path

import pytest
from app.db import (
    _audit_sqlite_foreign_keys,
    _configure_sqlite_foreign_keys,
    _migrate_analysisresult_v2,
    _migrate_bayesresult_v3,
    _migrate_openmatb_visual_profile_v1,
    _migrate_openmatb_visual_theme_v1,
    _resolve_db_path,
)
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import create_engine


def test_receipt_migration_keeps_historical_state_unknown(tmp_path):
    from app.db import _migrate_openmatb_receipts_v1
    engine = create_engine(f"sqlite:///{tmp_path / 'receipts.sqlite3'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE openmatb_suite_session (id VARCHAR PRIMARY KEY, lifecycle VARCHAR)"))
        connection.execute(text("INSERT INTO openmatb_suite_session VALUES ('old', 'COMPLETE')"))
    _migrate_openmatb_receipts_v1(engine)
    _migrate_openmatb_receipts_v1(engine)
    with engine.begin() as connection:
        assert tuple(connection.execute(text("SELECT lifecycle, active_block_instance_id, receipt_version FROM openmatb_suite_session")).one()) == ("COMPLETE", None, 0)


def test_evidence_parent_migration_only_uses_valid_matching_manifests(tmp_path):
    from app.db import _migrate_evidence_parent_v1
    from matb_integration.evidence.reference import synthetic_capture
    from matb_integration.evidence.contracts import strict_json, canonical_bytes
    from uuid import uuid4
    engine = create_engine(f"sqlite:///{tmp_path / 'parent.sqlite3'}")
    manifest = strict_json(synthetic_capture(tmp_path / 'capture')["capture_manifest"])
    manifest["parent_session_id"] = str(uuid4())
    raw = canonical_bytes(manifest).decode()
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE evidence_capture (id VARCHAR PRIMARY KEY, session_id VARCHAR, block_instance_id VARCHAR, manifest_json VARCHAR)"))
        for cid, value in ((manifest["capture_id"], raw), ("malformed", "{"), ("wrong-identity", raw)):
            connection.execute(text("INSERT INTO evidence_capture VALUES (:id, :sid, :bid, :raw)"),
                {"id": cid, "sid": manifest["session_id"], "bid": manifest["block_instance_id"], "raw": value})
    _migrate_evidence_parent_v1(engine)
    _migrate_evidence_parent_v1(engine)
    with engine.begin() as connection:
        rows = connection.execute(text("SELECT id, parent_session_id, manifest_json FROM evidence_capture")).all()
        assert {row[0]: row[1] for row in rows} == {manifest["capture_id"]: manifest["parent_session_id"], "malformed": None, "wrong-identity": None}
        assert rows[0][2] == raw
        assert "ix_evidence_capture_parent_session_id" in {i["name"] for i in inspect(connection).get_indexes("evidence_capture")}


@pytest.mark.parametrize("days", [(0, 8, 15), (0, 3, 6, 9, 12, 15)])
def test_execution_migration_preserves_schedule_and_raw_observations(tmp_path, days):
    from app.db import _migrate_experiment_execution_v1
    engine = create_engine(f"sqlite:///{tmp_path / 'execution.sqlite3'}")
    raw = '{"fast_mode":true,"simple_rt":{"trials":[]}}'
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE visit (id INTEGER PRIMARY KEY, scheduled_day INTEGER)"))
        for index, day in enumerate(days):
            connection.execute(text("INSERT INTO visit VALUES (:i, :day)"), {"i": index, "day": day})
        connection.execute(text("CREATE TABLE screenresult (id INTEGER PRIMARY KEY, raw_trials_json TEXT, scores_json TEXT)"))
        connection.execute(text("INSERT INTO screenresult VALUES (1, :raw, :score)"), {"raw": raw, "score": '{"legacy":12}'})
        connection.execute(text("CREATE TABLE pvt_assessment (id INTEGER PRIMARY KEY, pvt_version INTEGER, protocol_valid BOOLEAN)"))
        connection.execute(text("INSERT INTO pvt_assessment VALUES (1, 1, 1), (2, 1, 0)"))
    _migrate_experiment_execution_v1(engine)
    _migrate_experiment_execution_v1(engine)
    with engine.begin() as connection:
        assert tuple(connection.execute(text("SELECT scheduled_day FROM visit ORDER BY id")).scalars()) == days
        assert tuple(connection.execute(text("SELECT raw_trials_json, scores_json, execution_purpose FROM screenresult")).one()) == (raw, '{"legacy":12}', "study")
        assert list(connection.execute(text("SELECT protocol_valid, execution_purpose FROM pvt_assessment ORDER BY id"))) == [(1, "study"), (0, "study")]
        assert connection.execute(text("SELECT COUNT(*) FROM matb_schema_migration WHERE version='experiment-execution-v1'")).scalar_one() == 1


def test_relative_database_path_is_anchored_to_repository() -> None:
    resolved = _resolve_db_path("var/data con espacios/datos ñ.sqlite")

    assert resolved == (
        Path(__file__).resolve().parents[3]
        / "var"
        / "data con espacios"
        / "datos ñ.sqlite"
    ).resolve()


def test_empty_database_path_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        _resolve_db_path("   ")


def test_openmatb_visual_theme_migration_defaults_legacy_sessions_to_classic(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-openmatb.sqlite3'}")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE openmatb_suite_session (
                id VARCHAR PRIMARY KEY,
                participant_id VARCHAR NOT NULL
            )
        """))
        connection.execute(text(
            "INSERT INTO openmatb_suite_session (id, participant_id) VALUES ('s1', 'P01')"
        ))

    _migrate_openmatb_visual_theme_v1(engine)
    _migrate_openmatb_visual_theme_v1(engine)

    with engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("openmatb_suite_session")}
        assert "visual_theme" in columns
        assert connection.execute(text(
            "SELECT visual_theme FROM openmatb_suite_session WHERE id = 's1'"
        )).scalar_one() == "classic"
        assert connection.execute(text(
            "SELECT COUNT(*) FROM matb_schema_migration WHERE version = 'openmatb-visual-theme-v1'"
        )).scalar_one() == 1


def test_openmatb_visual_profile_migration_is_nullable_and_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-openmatb-profile.sqlite3'}")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE openmatb_suite_session (
                id VARCHAR PRIMARY KEY,
                participant_id VARCHAR NOT NULL,
                visual_theme VARCHAR NOT NULL DEFAULT 'classic'
            )
        """))
        connection.execute(text(
            "INSERT INTO openmatb_suite_session (id, participant_id) VALUES ('s1', 'P01')"
        ))

    _migrate_openmatb_visual_profile_v1(engine)
    _migrate_openmatb_visual_profile_v1(engine)

    with engine.begin() as connection:
        row = connection.execute(text("""
            SELECT visual_theme, visual_profile_id, visual_profile_version,
                   visual_profile_schema_version, visual_profile_sha256
            FROM openmatb_suite_session WHERE id = 's1'
        """)).mappings().one()
        assert dict(row) == {
            "visual_theme": "classic",
            "visual_profile_id": None,
            "visual_profile_version": None,
            "visual_profile_schema_version": None,
            "visual_profile_sha256": None,
        }
        assert connection.execute(text(
            "SELECT COUNT(*) FROM matb_schema_migration WHERE version = 'openmatb-visual-profile-v1'"
        )).scalar_one() == 1


def _legacy_bayesresult_database(path):
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE bayesresult (
                id INTEGER PRIMARY KEY,
                fingerprint VARCHAR NOT NULL,
                bayes_version VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                artifact_json VARCHAR,
                error VARCHAR,
                created_at DATETIME NOT NULL,
                finished_at DATETIME
            )
        """))
        connection.execute(
            text("""
                INSERT INTO bayesresult
                    (id, fingerprint, bayes_version, status, artifact_json,
                     error, created_at, finished_at)
                VALUES
                    (1, :fingerprint, '1.0', 'failed', NULL, 'old failure',
                     '2026-01-01T00:00:00Z', '2026-01-01T00:01:00Z'),
                    (2, :fingerprint, '1.0', 'done', '{"result": true}', NULL,
                     '2026-01-02T00:00:00Z', '2026-01-02T00:01:00Z')
            """),
            {"fingerprint": "a" * 64},
        )
    return engine


def test_bayesresult_v3_migration_upgrades_and_archives_duplicates(tmp_path):
    engine = _legacy_bayesresult_database(tmp_path / "legacy.sqlite3")

    _migrate_bayesresult_v3(engine)
    _migrate_bayesresult_v3(engine)  # restart/idempotence

    with engine.begin() as connection:
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("bayesresult")
        }
        assert {
            "attempt_count", "error_history_json", "last_attempt_at", "owner_token"
        } <= columns
        rows = connection.execute(
            text("SELECT id, status, attempt_count, error_history_json FROM bayesresult")
        ).mappings().all()
        assert rows == [{
            "id": 2,
            "status": "done",
            "attempt_count": 1,
            "error_history_json": "[]",
        }]
        archived = connection.execute(
            text("""
                SELECT source_id, status, error, reason
                FROM bayesresult_migration_archive_v1
            """)
        ).mappings().all()
        assert archived == [{
            "source_id": 1,
            "status": "failed",
            "error": "old failure",
            "reason": "duplicate_fingerprint_and_bayes_version",
        }]
        versions = connection.execute(
            text("SELECT version FROM matb_schema_migration")
        ).scalars().all()
        assert versions == ["bayesresult-v3"]

        indexes = set(connection.execute(text("""
            SELECT name FROM sqlite_master
            WHERE type = 'index' AND tbl_name = 'bayesresult'
        """)).scalars().all())
        assert "uq_bayesresult_one_active" in indexes

    try:
        with engine.begin() as connection:
            connection.execute(
                text("""
                    INSERT INTO bayesresult
                        (fingerprint, bayes_version, status, created_at)
                    VALUES (:fingerprint, '1.0', 'queued', '2026-01-03T00:00:00Z')
                """),
                {"fingerprint": "a" * 64},
            )
    except IntegrityError:
        pass
    else:
        raise AssertionError("migration did not enforce Bayesian cache-key uniqueness")


def test_analysisresult_v2_migration_archives_duplicates_and_enforces_cache_key(
    tmp_path,
):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-analysis.sqlite3'}")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE analysisresult (
                id INTEGER PRIMARY KEY,
                fingerprint VARCHAR NOT NULL,
                engine_version VARCHAR NOT NULL,
                artifact_json VARCHAR NOT NULL,
                created_at DATETIME NOT NULL
            )
        """))
        connection.execute(text("""
            INSERT INTO analysisresult
                (id, fingerprint, engine_version, artifact_json, created_at)
            VALUES
                (1, 'same', '2.0', '{"winner": false}', '2026-01-01T00:00:00Z'),
                (2, 'same', '2.0', '{"winner": true}', '2026-01-02T00:00:00Z')
        """))

    _migrate_analysisresult_v2(engine)
    _migrate_analysisresult_v2(engine)

    with engine.begin() as connection:
        rows = connection.execute(text(
            "SELECT id, artifact_json FROM analysisresult ORDER BY id"
        )).mappings().all()
        assert rows == [{"id": 2, "artifact_json": '{"winner": true}'}]
        archived = connection.execute(text("""
            SELECT source_id, reason
            FROM analysisresult_migration_archive_v1
        """)).mappings().all()
        assert archived == [{
            "source_id": 1,
            "reason": "duplicate_fingerprint_and_engine_version",
        }]

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO analysisresult
                    (fingerprint, engine_version, artifact_json, created_at)
                VALUES ('same', '2.0', '{}', '2026-01-03T00:00:00Z')
            """))


def test_sqlite_connections_enforce_foreign_keys(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fk.sqlite3'}")
    _configure_sqlite_foreign_keys(engine)
    with engine.begin() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        connection.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
        connection.execute(text(
            "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER "
            "REFERENCES parent(id))"
        ))

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO child (id, parent_id) VALUES (1, 999)"))


def test_startup_audit_rejects_legacy_foreign_key_orphans(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'orphan.sqlite3'}")
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
        connection.execute(text(
            "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER "
            "REFERENCES parent(id))"
        ))
        connection.execute(text("INSERT INTO child (id, parent_id) VALUES (1, 999)"))
    engine.dispose()

    _configure_sqlite_foreign_keys(engine)
    with pytest.raises(RuntimeError, match="foreign-key orphan.*child"):
        _audit_sqlite_foreign_keys(engine)
