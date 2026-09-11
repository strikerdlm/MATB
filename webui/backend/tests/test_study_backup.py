"""Whole-workspace safety contracts, using owned synthetic sources only."""

import json
import sqlite3
from pathlib import Path

import pytest


def workspace(tmp_path):
    from sqlmodel import SQLModel, create_engine, Session
    from tests.test_study_registry import seed, frozen
    from app import station_resources

    path = tmp_path / "original study ñ" / "study.sqlite3"
    path.parent.mkdir()
    engine = create_engine("sqlite:///" + str(path))
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        seed(db)
        version = frozen(db)
        station_resources.maintenance(
            db, True, actor="Dr Synthetic", reason="Restore rehearsal"
        )
        db.commit()
        identity = version.study_id
    engine.dispose()
    return path, identity


def test_backup_requires_exclusive_maintenance(tmp_path):
    from app.study_backup import backup

    path, _ = workspace(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE station_state SET maintenance=0")
    with pytest.raises(ValueError, match="maintenance"):
        backup(path, tmp_path / "denied.zip")
    assert not (tmp_path / "denied.zip").exists()


def test_restore_preserves_bytes_relocates_and_regenerates_authority(
    tmp_path, monkeypatch
):
    from app.study_backup import backup, restore
    from app.artifact_paths import resolve_artifact

    path, identity = workspace(tmp_path)
    root = tmp_path / "external raw ñ"
    root.mkdir()
    raw = b"original manifest\n"
    (root / "manifest.json").write_bytes(raw)
    monkeypatch.setenv("MATB_PHYSIOLOGY_DIR", str(root))
    archive = tmp_path / "whole.zip"
    backup(path, archive)
    root.rename(tmp_path / "original unavailable")
    destination = tmp_path / "restored study ñ"
    report = restore(archive, destination, expected_study_id=identity)
    monkeypatch.setenv("MATB_ARTIFACT_RELOCATION", str(destination / "relocation.json"))
    assert resolve_artifact(root / "manifest.json").read_bytes() == raw
    assert report["study_id"] == identity
    with sqlite3.connect(destination / "study.sqlite3") as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute(
            "SELECT maintenance, lanes_json FROM station_state"
        ).fetchone() == (1, "{}")
    with pytest.raises(ValueError, match="empty"):
        restore(archive, destination, expected_study_id=identity)


def test_restore_rejects_untrusted_archive_and_workspace_without_output(
    tmp_path, monkeypatch
):
    from app.study_backup import backup, restore
    import zipfile

    path, identity = workspace(tmp_path)
    archive = tmp_path / "whole.zip"
    backup(path, archive)
    destination = tmp_path / "restored"
    with pytest.raises(ValueError, match="study identity"):
        restore(archive, destination, expected_study_id="other")
    assert not destination.exists()
    with zipfile.ZipFile(archive, "a") as output:
        output.writestr("../escape", "bad")
    with pytest.raises(ValueError, match="archive"):
        restore(archive, destination, expected_study_id=identity)
    assert not destination.exists()


def test_actual_frozen_analysis_reproduces_offline_after_empty_restore(
    tmp_path, monkeypatch
):
    from sqlmodel import Session, create_engine, select
    from app import station_resources, study_analysis
    from app.study_registry import activate, assign
    from app.study_registry_models import StudyVersion
    from app.study_analysis_models import StudyAnalysisArtifact
    from app.assessment_service import create_attempt, transition
    from app.assessment_schemas import AttemptIn
    from app.routers.pvt import PvtAssessmentIn, ingest_pvt
    from app.study_backup import backup, restore, reproduce
    from app.purpose_service import classify_retrospectively

    path, identity = workspace(tmp_path)
    engine = create_engine("sqlite:///" + str(path))
    with Session(engine) as db:
        station_resources.maintenance(
            db, False, actor="Dr Synthetic", reason="Collect isolated fixture"
        )
        version = db.exec(select(StudyVersion)).one()
        activate(db, version.id, actor="Dr Synthetic", reason="Fixture")
        assignment = assign(db, version.id, "R01", 1, "A", actor="Dr Synthetic")
        occasion = json.loads(assignment.occasions_json)["pre"]
        attempt = create_attempt(db, occasion, AttemptIn(execution_purpose="study"))
        transition(db, attempt.id, "started")
        ingest_pvt(
            PvtAssessmentIn(
                participant_id="R01",
                visit_ordinal=1,
                execution_purpose="study",
                attempt_id=attempt.id,
                kss_score=3,
                administered_at="2026-09-10T00:00:00Z",
                duration_ms=12000,
                locale="es-419",
                trials=[
                    dict(
                        index=0,
                        wait_ms=2000,
                        stimulus_at_ms=2000,
                        response_at_ms=2300,
                        rt_ms=300,
                        outcome="response",
                    )
                ],
            ),
            db,
        )
        station_resources.close_visit(
            db, actor="Dr Synthetic", reason="Fixture recording stopped"
        )
        execution = study_analysis.execute(
            db,
            dict(
                version_id=version.id,
                attempts={occasion: attempt.id},
                actor="Dr Synthetic",
                reason="Offline descriptive fixture",
            ),
        )
        figure = db.get(StudyAnalysisArtifact, (execution.id, "figure.svg")).content
        classify_retrospectively(
            db,
            attempt.purpose_provenance_id,
            purpose="practice",
            reviewer="Dr Synthetic",
            reason="Retained correction after frozen analysis",
        )
        station_resources.maintenance(
            db, True, actor="Dr Synthetic", reason="Whole study backup"
        )
        db.commit()
    engine.dispose()
    archive = tmp_path / "archive.zip"
    backup(path, archive)
    path.parent.rename(tmp_path / "original database unavailable")
    destination = tmp_path / "restored ñ"
    restore(archive, destination, expected_study_id=identity)
    # Poisoning inherited search paths catches accidental dependence on the repository.
    monkeypatch.setenv(
        "PYTHONPATH", "/repository-must-not-be-used:/testdeps-must-not-be-used"
    )
    report = reproduce(destination, tmp_path / "offline proof ñ")
    assert len(report["executions"]) == 1
    result = report["executions"][0]
    assert result["status"] == "reproduced" and result["raw_attempts"] == 1
    assert result["isolated"] == 1 and result["system_site_packages"] is False
    assert result["network"] == "socket denied"
    restored_figure = (
        tmp_path / "offline proof ñ" / result["execution_id"] / "figure.svg"
    )
    assert restored_figure.read_bytes() == figure


@pytest.mark.parametrize(
    "bad_name",
    ["../escape", "/absolute", "C:/drive", "a\\b", "a/../b", "CON.txt", "trailing."],
)
def test_portable_archive_member_rules(bad_name):
    from app.study_backup import safe_member

    with pytest.raises(ValueError, match="archive"):
        safe_member(bad_name)


def test_missing_corrupt_and_partial_sources_remain_explicit(tmp_path, monkeypatch):
    from app.study_backup import backup

    path, _ = workspace(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE synthetic_required_source (id TEXT, artifact_root TEXT)"
        )
        db.execute(
            "INSERT INTO synthetic_required_source VALUES (?,?)",
            ("recorded", str(tmp_path / "absent required root")),
        )
    with pytest.raises(ValueError, match="missing"):
        backup(path, tmp_path / "missing.zip")
    assert not (tmp_path / "missing.zip").exists()


def test_tokens_and_pending_jobs_do_not_survive_as_authority(tmp_path):
    from app.study_backup import backup, restore
    import zipfile

    path, identity = workspace(tmp_path)
    secret = "original-controller-secret-must-not-survive"
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO station_job(id,kind,payload_json,deduplication,status,created_at) VALUES(?,?,?,?,?,?)",
            (
                "test-job",
                "http",
                json.dumps(
                    {"headers": [["X-Openmatb-Controller", secret]], "body": "e30="}
                ),
                "test",
                "queued",
                "2026-09-10",
            ),
        )
    archive = tmp_path / "bundle.zip"
    backup(path, archive)
    with zipfile.ZipFile(archive) as bundle:
        assert secret.encode() not in bundle.read("study.sqlite3")
    restored = tmp_path / "restored"
    report = restore(archive, restored, expected_study_id=identity)
    assert len((restored / ".station-secret").read_text()) >= 32
    assert report["environment"]["MATB_API_TOKEN_FILE"] == str(
        restored / ".station-secret"
    )
    with sqlite3.connect(restored / "study.sqlite3") as db:
        status, payload = db.execute(
            "SELECT status,payload_json FROM station_job"
        ).fetchone()
        assert status == "failed" and "headers" not in json.loads(payload)


def test_rehashed_database_tamper_fails_semantic_validation(tmp_path):
    from app.study_backup import backup, restore, digest
    import zipfile

    path, identity = workspace(tmp_path)
    archive = tmp_path / "original.zip"
    backup(path, archive)
    with zipfile.ZipFile(archive) as bundle:
        files = {name: bundle.read(name) for name in bundle.namelist()}
    altered = tmp_path / "altered.sqlite3"
    altered.write_bytes(files["study.sqlite3"])
    with sqlite3.connect(altered) as db:
        db.execute("UPDATE study_version SET study_sha256='tampered'")
    files["study.sqlite3"] = altered.read_bytes()
    manifest = json.loads(files["manifest.json"])
    manifest["files"]["study.sqlite3"] = digest(files["study.sqlite3"])
    files["manifest.json"] = json.dumps(manifest).encode()
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(tampered, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    destination = tmp_path / "must remain absent"
    with pytest.raises(ValueError, match="fingerprint"):
        restore(tampered, destination, expected_study_id=identity)
    assert not destination.exists()


def test_backup_writer_lock_covers_raw_artifact_copy(tmp_path, monkeypatch):
    from app import study_backup

    path, _ = workspace(tmp_path)
    original = study_backup.inventory

    def locked_inventory(db, database):
        with sqlite3.connect(database, timeout=0) as writer:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                writer.execute("UPDATE station_state SET maintenance=0")
        return original(db, database)

    monkeypatch.setattr(study_backup, "inventory", locked_inventory)
    study_backup.backup(path, tmp_path / "consistent.zip")


def test_restored_runtime_requires_explicit_new_acquisition(tmp_path):
    from app.artifact_paths import require_new_acquisition
    from fastapi import HTTPException
    from sqlmodel import Session, create_engine

    path, _ = workspace(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE study_restored_source (source_table TEXT, source_id TEXT)"
        )
        db.execute(
            "INSERT INTO study_restored_source VALUES ('openmatb_suite_session','original')"
        )
    engine = create_engine("sqlite:///" + str(path))
    with Session(engine) as db:
        with pytest.raises(HTTPException) as failure:
            require_new_acquisition(db, "openmatb_suite_session", "original")
        assert failure.value.detail["code"] == "restored_acquisition_requires_repeat"
        require_new_acquisition(db, "openmatb_suite_session", "new")
    engine.dispose()


def test_backup_retires_live_backend_lease_only_in_copy(tmp_path):
    from app.study_backup import backup, restore

    path, identity = workspace(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE matb_backend_instance_lease (lease_name TEXT PRIMARY KEY, owner_token TEXT, owner_pid INTEGER, owner_host TEXT)"
        )
        db.execute(
            "INSERT INTO matb_backend_instance_lease VALUES ('backend','original-private-token',123,'original-host')"
        )
    archive = tmp_path / "live-backend.zip"
    backup(path, archive)
    destination = tmp_path / "new station"
    restore(archive, destination, expected_study_id=identity)
    with sqlite3.connect(destination / "study.sqlite3") as db:
        assert db.execute("SELECT * FROM matb_backend_instance_lease").fetchall() == []
    with sqlite3.connect(path) as db:
        assert (
            db.execute(
                "SELECT owner_token FROM matb_backend_instance_lease"
            ).fetchone()[0]
            == "original-private-token"
        )


def test_unused_configured_root_is_preserved_as_empty_destination(
    tmp_path, monkeypatch
):
    from app.study_backup import backup, restore

    path, identity = workspace(tmp_path)
    unused = tmp_path / "not yet used output ñ"
    monkeypatch.setenv("MATB_SIMULATION_OUTPUT_DIR", str(unused))
    archive = tmp_path / "unused-root.zip"
    backup(path, archive)
    report = restore(archive, tmp_path / "restored", expected_study_id=identity)
    restored_root = Path(report["environment"]["MATB_SIMULATION_OUTPUT_DIR"])
    assert restored_root.is_dir() and list(restored_root.iterdir()) == []
    assert not unused.exists()
