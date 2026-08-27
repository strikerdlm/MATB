from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.classic_models import (
    ClassicSessionArtifact,
    ClassicSessionAttempt,
    ClassicSessionSelection,
    ClassicSessionSelectionAudit,
)
from app.models import Participant, Visit


def test_multiple_classic_attempts_are_preserved_for_one_workload_cell(engine) -> None:
    with Session(engine) as db:
        db.add(Participant(id="P10", enrollment_date=date(2026, 8, 23)))
        db.add(Visit(participant_id="P10", visit_ordinal=1, scheduled_day=0))
        db.commit()
        visit = db.exec(select(Visit).where(Visit.participant_id == "P10")).one()

        db.add(
            ClassicSessionAttempt(
                id="attempt-1",
                visit_id=visit.id,
                workload_level="LOW",
                attempt_number=1,
                scenario_name="military_aviation/low_workload.txt",
                artifact_root="P10/visit-1/LOW/attempt-1",
            )
        )
        db.add(
            ClassicSessionAttempt(
                id="attempt-2",
                visit_id=visit.id,
                workload_level="LOW",
                attempt_number=2,
                scenario_name="military_aviation/low_workload.txt",
                artifact_root="P10/visit-1/LOW/attempt-2",
            )
        )
        db.commit()

        attempts = db.exec(select(ClassicSessionAttempt)).all()
        assert [attempt.id for attempt in attempts] == ["attempt-1", "attempt-2"]


def test_selection_and_artifacts_link_to_attempt_without_replacing_it(engine) -> None:
    with Session(engine) as db:
        db.add(Participant(id="P11", enrollment_date=date(2026, 8, 23)))
        db.add(Visit(participant_id="P11", visit_ordinal=1, scheduled_day=0))
        db.commit()
        visit = db.exec(select(Visit).where(Visit.participant_id == "P11")).one()
        db.add(
            ClassicSessionAttempt(
                id="attempt-selected",
                visit_id=visit.id,
                workload_level="MEDIUM",
                attempt_number=1,
                scenario_name="military_aviation/medium_workload.txt",
                artifact_root="P11/visit-1/MEDIUM/attempt-selected",
                status="COMPLETE",
                task_validity="valid",
                physiology_quality="partial",
            )
        )
        db.add(
            ClassicSessionSelection(
                visit_id=visit.id,
                workload_level="MEDIUM",
                attempt_id="attempt-selected",
            )
        )
        db.add(
            ClassicSessionSelectionAudit(
                visit_id=visit.id,
                workload_level="MEDIUM",
                previous_attempt_id=None,
                new_attempt_id="attempt-selected",
                reason_code="first_valid_attempt",
            )
        )
        db.add(
            ClassicSessionArtifact(
                session_id="attempt-selected",
                kind="report_en",
                relative_path="report.en.md",
                sha256="a" * 64,
                size_bytes=42,
            )
        )
        db.commit()

        selected = db.exec(select(ClassicSessionSelection)).one()
        assert selected.attempt_id == "attempt-selected"
        assert db.exec(select(ClassicSessionSelectionAudit)).one().reason_code == "first_valid_attempt"
        assert db.exec(select(ClassicSessionArtifact)).one().relative_path == "report.en.md"


def test_attempt_number_is_unique_within_visit_and_workload(engine) -> None:
    with Session(engine) as db:
        db.add(Participant(id="P12", enrollment_date=date(2026, 8, 23)))
        db.add(Visit(participant_id="P12", visit_ordinal=1, scheduled_day=0))
        db.commit()
        visit = db.exec(select(Visit).where(Visit.participant_id == "P12")).one()
        for session_id in ("attempt-a", "attempt-b"):
            db.add(
                ClassicSessionAttempt(
                    id=session_id,
                    visit_id=visit.id,
                    workload_level="HIGH",
                    attempt_number=1,
                    scenario_name="military_aviation/high_workload.txt",
                    artifact_root=f"P12/visit-1/HIGH/{session_id}",
                )
            )
        with pytest.raises(IntegrityError):
            db.commit()
