from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.liftoff_models import LiftoffArtifact, LiftoffSession
from app.liftoff_persistence import SQLModelLiftoffPersistence
from matb_integration.recording.records import ArtifactInfo


def liftoff_row(**overrides) -> LiftoffSession:
    values = {
        "id": "session-a",
        "participant_id": "P01",
        "visit_id": 1,
        "attempt_number": 1,
        "protocol_id": "astra-2026",
        "protocol_version": "1.0.0",
        "liftoff_build": "test-build",
        "configuration_sha256": "a" * 64,
        "track_id": "astra-neutral-time-trial-v1",
        "telemetry_profile": "liftoff-telemetry-all-v1",
        "status": "PREPARED",
        "validity": "pending_review",
        "artifact_root": "/tmp/liftoff/session-a",
        "controller_lease_hash": "b" * 64,
        "manifest_json": "{}",
    }
    values.update(overrides)
    return LiftoffSession(**values)


def test_attempt_numbers_are_unique(engine, seeded_participant):
    with Session(engine) as db:
        db.add(liftoff_row(id="a", attempt_number=1))
        db.commit()
        db.add(liftoff_row(id="b", attempt_number=1))
        with pytest.raises(IntegrityError):
            db.commit()


def test_analysis_attempt_is_first_valid(engine, seeded_participant):
    persistence = SQLModelLiftoffPersistence(engine)
    persistence.insert_session(liftoff_row(id="bad", attempt_number=1, validity="invalid"))
    persistence.insert_session(liftoff_row(id="good", attempt_number=2, validity="valid"))
    persistence.insert_session(liftoff_row(id="later", attempt_number=3, validity="valid"))

    assert persistence.analysis_attempt("P01", visit_id=1).id == "good"


def test_valid_practice_never_becomes_the_analysis_attempt(engine, seeded_participant):
    persistence = SQLModelLiftoffPersistence(engine)
    persistence.insert_session(liftoff_row(id="practice", attempt_number=1,
        validity="valid", execution_purpose="practice", status="FINISHED"))
    assert persistence.analysis_attempt("P01", visit_id=1) is None
    persistence.insert_session(liftoff_row(id="study", attempt_number=2,
        validity="valid", execution_purpose="study", status="FINISHED"))
    assert persistence.analysis_attempt("P01", visit_id=1).id == "study"


def test_orphaned_active_session_is_interrupted(engine, seeded_participant):
    persistence = SQLModelLiftoffPersistence(engine)
    persistence.insert_session(liftoff_row(status="TASK"))

    assert persistence.mark_orphaned_sessions() == 1
    interrupted = persistence.load_session("session-a")
    assert interrupted is not None
    assert interrupted.status == "INTERRUPTED"
    assert interrupted.validity == "pending_review"
    assert interrupted.interrupted_at is not None


def test_mutations_are_allowlisted_and_artifacts_use_relative_paths(engine, seeded_participant, tmp_path):
    run_dir = tmp_path / "session-a"
    run_dir.mkdir()
    artifact_path = run_dir / "metrics.json"
    artifact_path.write_text("{}", encoding="utf-8")
    persistence = SQLModelLiftoffPersistence(engine)
    persistence.insert_session(liftoff_row(artifact_root=str(run_dir)))

    with pytest.raises(ValueError, match="unsupported liftoff metadata fields"):
        persistence.update_session("session-a", controller_lease_hash="changed")
    persistence.replace_artifacts(
        "session-a",
        (
            ArtifactInfo(
                kind="metrics",
                path=artifact_path,
                sha256="c" * 64,
                size_bytes=2,
            ),
        ),
    )

    with Session(engine) as db:
        artifact = db.exec(select(LiftoffArtifact)).one()
        assert artifact.relative_path == "metrics.json"
