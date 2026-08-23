from __future__ import annotations

from datetime import date
import json

import pytest
from sqlmodel import Session, select

from app.classic_models import (
    ClassicSessionArtifact,
    ClassicSessionAttempt,
    ClassicSessionSelection,
    ClassicSessionSelectionAudit,
)
from app.classic_persistence import ClassicPersistenceError, SQLModelClassicPersistence
from app.models import Block, BlockProvenance, DepdfFit, Participant, Visit


def _seed(engine) -> None:
    with Session(engine) as db:
        db.add(Participant(id="P20", enrollment_date=date(2026, 8, 23)))
        db.add(Visit(participant_id="P20", visit_ordinal=1, scheduled_day=0))
        db.commit()


def test_first_task_valid_attempt_is_selected_without_deleting_retakes(engine) -> None:
    _seed(engine)
    persistence = SQLModelClassicPersistence(engine)
    first = persistence.create_attempt(
        participant_id="P20",
        visit_ordinal=1,
        workload_level="LOW",
        scenario_name="military_aviation/low_workload.txt",
        artifact_root="P20/visit-1/LOW/first",
    )
    second = persistence.create_attempt(
        participant_id="P20",
        visit_ordinal=1,
        workload_level="LOW",
        scenario_name="military_aviation/low_workload.txt",
        artifact_root="P20/visit-1/LOW/second",
    )

    persistence.finalize_attempt(
        first.id,
        task_validity="invalid",
        physiology_quality="excellent",
        source_csv_filename="first.csv",
        source_csv_sha256="1" * 64,
        metrics={"attempt": 1},
        hrv={"quality": "excellent"},
    )
    persistence.finalize_attempt(
        second.id,
        task_validity="valid",
        physiology_quality="partial",
        source_csv_filename="second.csv",
        source_csv_sha256="2" * 64,
        metrics={"attempt": 2},
        hrv={"quality": "partial"},
    )

    with Session(engine) as db:
        assert len(db.exec(select(ClassicSessionAttempt)).all()) == 2
        selection = db.exec(select(ClassicSessionSelection)).one()
        assert selection.attempt_id == second.id
        block = db.get(Block, selection.block_id)
        assert block is not None
        assert block.source_csv_filename == "second.csv"
        assert block.metrics_json == '{"attempt":2}'
        audit = db.exec(select(ClassicSessionSelectionAudit)).one()
        assert audit.reason_code == "first_valid_attempt"


def test_researcher_selection_updates_block_and_appends_audit(engine) -> None:
    _seed(engine)
    persistence = SQLModelClassicPersistence(engine)
    attempts = []
    for number, digest in ((1, "a" * 64), (2, "b" * 64)):
        attempt = persistence.create_attempt(
            participant_id="P20",
            visit_ordinal=1,
            workload_level="MEDIUM",
            scenario_name="military_aviation/medium_workload.txt",
            artifact_root=f"P20/visit-1/MEDIUM/{number}",
        )
        persistence.finalize_attempt(
            attempt.id,
            task_validity="valid",
            physiology_quality="good",
            source_csv_filename=f"attempt-{number}.csv",
            source_csv_sha256=digest,
            metrics={"attempt": number},
            hrv={"quality": "good"},
        )
        attempts.append(attempt)

    persistence.select_attempt(attempts[1].id, reason_code="researcher_qc_review")

    with Session(engine) as db:
        selection = db.exec(select(ClassicSessionSelection)).one()
        block = db.get(Block, selection.block_id)
        audits = db.exec(
            select(ClassicSessionSelectionAudit).order_by(ClassicSessionSelectionAudit.id)
        ).all()
        assert selection.attempt_id == attempts[1].id
        assert block is not None and block.metrics_json == '{"attempt":2}'
        assert [audit.reason_code for audit in audits] == [
            "first_valid_attempt",
            "researcher_qc_review",
        ]
        assert audits[1].previous_attempt_id == attempts[0].id


def test_selecting_classic_attempt_replaces_legacy_provenance_and_invalidates_fit(
    engine,
) -> None:
    _seed(engine)
    persistence = SQLModelClassicPersistence(engine)
    attempt = persistence.create_attempt(
        participant_id="P20",
        visit_ordinal=1,
        workload_level="HIGH",
        scenario_name="military_aviation/high_workload.txt",
        scenario_sha256="c" * 64,
        openmatb_source_sha256="d" * 64,
        artifact_root="classic-over-legacy",
    )
    with Session(engine) as db:
        visit = db.exec(select(Visit)).one()
        legacy = Block(
            visit_id=visit.id,
            workload_level="HIGH",
            source_csv_filename="legacy.csv",
            source_csv_sha256="1" * 64,
            metrics_json='{"legacy":true}',
        )
        db.add(legacy)
        db.flush()
        db.add(
            BlockProvenance(
                block_id=legacy.id,
                manifest_filename="legacy.manifest.json",
                manifest_sha256="2" * 64,
                manifest_json='{"manifest_version":"legacy"}',
                validation_status="ok",
            )
        )
        db.add(
            DepdfFit(
                participant_id="P20",
                visit_id=visit.id,
                mwl_source="raw_tlx",
                g0=1.0,
                p0=2.0,
                tau0=3.0,
                hcf_value=4.0,
                hcf_source="test",
                criteria_version=1,
                per_level_json="{}",
            )
        )
        stored = db.get(ClassicSessionAttempt, attempt.id)
        assert stored is not None
        stored.status = "COMPLETE"
        stored.task_validity = "valid"
        stored.source_csv_filename = "openmatb-session.csv"
        stored.source_csv_sha256 = "3" * 64
        stored.metrics_json = '{"classic":true}'
        db.add(stored)
        db.commit()

    persistence.select_attempt(attempt.id, reason_code="replace_legacy_source")

    with Session(engine) as db:
        block = db.exec(select(Block)).one()
        provenance = db.exec(select(BlockProvenance)).one()
        assert block.source_csv_filename == "openmatb-session.csv"
        assert block.metrics_json == '{"classic":true}'
        assert provenance.block_id == block.id
        assert provenance.validation_status == "classic_session_verified"
        payload = json.loads(provenance.manifest_json or "{}")
        assert payload["classic_session_id"] == attempt.id
        assert payload["scenario"]["sha256"] == "c" * 64
        assert db.exec(select(DepdfFit)).first() is None


def test_artifact_inventory_is_registered_once_and_remains_immutable(engine) -> None:
    _seed(engine)
    persistence = SQLModelClassicPersistence(engine)
    attempt = persistence.create_attempt(
        participant_id="P20",
        visit_ordinal=1,
        workload_level="HIGH",
        scenario_name="military_aviation/high_workload.txt",
        artifact_root="P20/visit-1/HIGH/first",
    )
    persistence.finalize_attempt(
        attempt.id,
        task_validity="valid",
        physiology_quality="good",
        source_csv_filename="openmatb-session.csv",
        source_csv_sha256="c" * 64,
        metrics={"tracking": {"in_target_pct": 81.0}},
        hrv={"quality": "good"},
    )
    inventory = [
        {
            "kind": "report_en",
            "relative_path": "report.en.md",
            "sha256": "d" * 64,
            "size_bytes": 42,
        },
        {
            "kind": "rr_csv",
            "relative_path": "rr-intervals.csv",
            "sha256": "e" * 64,
            "size_bytes": 84,
        },
    ]

    stored = persistence.register_artifacts(attempt.id, inventory)

    assert [artifact.relative_path for artifact in stored] == [
        "report.en.md",
        "rr-intervals.csv",
    ]
    with Session(engine) as db:
        assert len(db.exec(select(ClassicSessionArtifact)).all()) == 2
    with pytest.raises(ClassicPersistenceError, match="artifacts_immutable"):
        persistence.register_artifacts(attempt.id, inventory)


def test_terminal_metadata_artifacts_and_selection_commit_atomically(engine) -> None:
    _seed(engine)
    persistence = SQLModelClassicPersistence(engine)
    attempt = persistence.create_attempt(
        participant_id="P20",
        visit_ordinal=1,
        workload_level="LOW",
        scenario_name="military_aviation/low_workload.txt",
        artifact_root="atomic-attempt",
    )
    duplicate_inventory = [
        {
            "kind": "session",
            "relative_path": "session.json",
            "sha256": "a" * 64,
            "size_bytes": 10,
        },
        {
            "kind": "duplicate",
            "relative_path": "session.json",
            "sha256": "b" * 64,
            "size_bytes": 20,
        },
    ]

    with pytest.raises(ClassicPersistenceError, match="duplicate_artifact_path"):
        persistence.finalize_attempt_with_artifacts(
            attempt.id,
            task_validity="valid",
            physiology_quality="good",
            source_csv_filename="openmatb-session.csv",
            source_csv_sha256="c" * 64,
            metrics={"n_rows": 1},
            hrv={"phases": {}},
            inventory=duplicate_inventory,
        )

    with Session(engine) as db:
        unchanged = db.get(ClassicSessionAttempt, attempt.id)
        assert unchanged is not None and unchanged.status == "PREPARED"
        assert db.exec(select(ClassicSessionArtifact)).first() is None
        assert db.exec(select(ClassicSessionSelection)).first() is None


def test_interrupted_metadata_and_artifacts_commit_together(engine) -> None:
    _seed(engine)
    persistence = SQLModelClassicPersistence(engine)
    attempt = persistence.create_attempt(
        participant_id="P20",
        visit_ordinal=1,
        workload_level="MEDIUM",
        scenario_name="military_aviation/medium_workload.txt",
        artifact_root="atomic-interrupted",
    )

    stored = persistence.terminate_attempt_with_artifacts(
        attempt.id,
        status="INTERRUPTED",
        reason_code="backend_process_restart",
        task_validity="invalid",
        physiology_quality="insufficient_data",
        source_csv_filename="openmatb-session.csv",
        source_csv_sha256="d" * 64,
        metrics={"n_rows": 0},
        hrv={"phases": {}},
        inventory=[
            {
                "kind": "session",
                "relative_path": "session.json",
                "sha256": "e" * 64,
                "size_bytes": 10,
            }
        ],
    )

    assert stored.status == "INTERRUPTED"
    assert [item.relative_path for item in persistence.list_artifacts(attempt.id)] == [
        "session.json"
    ]
