"""Flat copies use synthetic evidence and isolated directories only."""
import asyncio
import csv
import json
from datetime import date, datetime, timezone

import pytest
from sqlmodel import Session, select

from app import crew_exports as exports, station_resources as resources
from app.assessment_models import AssessmentAttempt, AssessmentOccasion, AssessmentSourceLink
from app.models import Participant, ParticipantRoster, PvtAssessment, Visit


@pytest.fixture
def ledger(engine, tmp_path, monkeypatch):
    monkeypatch.setenv("MATB_CREW_EXPORT_ROOT", str(tmp_path / "exports"))
    with Session(engine) as db:
        db.add(Participant(id="P01", enrollment_date=date(2026, 10, 5)))
        db.flush()
        db.add(ParticipantRoster(participant_id="P01", callsign="CUELLAR", mission="ASTRA-1"))
        visit = Visit(participant_id="P01", visit_ordinal=9, scheduled_day=3)
        db.add(visit)
        db.flush()
        occasion = AssessmentOccasion(participant_id="P01", visit_id=visit.id, instrument="pvt", origin="synthetic_test")
        db.add(occasion)
        db.flush()
        at = datetime(2026, 10, 8, 4, 30, tzinfo=timezone.utc)
        attempt = AssessmentAttempt(occasion_id=occasion.id, ordinal=1, execution_purpose="study",
            acquisition_state="started", started_at=at)
        db.add(attempt)
        db.flush()
        source = PvtAssessment(participant_id="P01", visit_id=visit.id, attempt_id=attempt.id,
            kss_score=3, administered_at=at.isoformat(), duration_ms=600000,
            raw_trials_json=json.dumps([{"rt_ms": 243, "false_start": False}]),
            metrics_json=json.dumps({"mean_rt_ms": 243, "lapses": 0}))
        db.add(source)
        db.flush()
        db.add(AssessmentSourceLink(attempt_id=attempt.id, source_table="pvt_assessment", source_id=str(source.id)))
        db.commit()
        yield db, attempt, tmp_path / "exports"


def complete(db, attempt):
    from app.assessment_service import transition
    transition(db, attempt.id, "finished")
    db.commit()


def test_flat_csv_has_callsign_bogota_day_and_raw_trials_without_json_blobs(ledger):
    db, attempt, root = ledger
    complete(db, attempt)
    relative = exports.export_attempt(db, attempt.id)
    assert relative.startswith("CUELLAR/2026-10-07_DM3/CUELLAR_20261007T233000")
    path = root / relative
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert {row["callsign"] for row in rows} == {"CUELLAR"}
    assert {row["planned_date"] for row in rows} == {"2026-10-07"}
    assert any(row["field"] == "raw_trials[0].rt_ms" and row["value"] == "243" for row in rows)
    assert any(row["field"] == "kss_score" and row["value"] == "3" for row in rows)
    original = path.read_bytes()
    assert exports.export_attempt(db, attempt.id) == relative
    assert path.read_bytes() == original
    assert not list(root.rglob("*.tmp"))


def test_durable_job_exports_only_after_commit_and_never_during_acquisition(ledger):
    from app.assessment_service import transition
    from app.station_worker import execute_internal
    db, attempt, root = ledger
    transition(db, attempt.id, "finished")
    assert db.exec(select(resources.StationJob)).one().kind == "crew_export"
    assert not root.exists()
    db.rollback()
    assert not db.exec(select(resources.StationJob)).all()
    complete(db, attempt)
    state = resources.lock(db)
    state.reservation_json = json.dumps({"owner": "assignment:synthetic"})
    state.lanes_json = json.dumps({"browser": {"owner": "assignment:synthetic"}})
    db.add(state)
    db.commit()
    assert resources.claim_job(db) is None
    state.lanes_json = "{}"
    db.add(state)
    db.commit()
    job = resources.claim_job(db)
    assert job.kind == "crew_export"
    db.commit()
    asyncio.run(execute_internal(db.get_bind(), job))
    db.refresh(job)
    assert job.status == "complete"
    assert len(list(root.rglob("*.csv"))) == 1


def test_no_practice_created_or_legacy_exports_and_all_callsign_day_directories(ledger):
    db, attempt, root = ledger
    assert exports.export_attempt(db, attempt.id) is None
    attempt.acquisition_state = "finished"
    attempt.execution_purpose = "practice"
    db.add(attempt)
    db.flush()
    assert exports.export_attempt(db, attempt.id) is None
    attempt.execution_purpose = "study"
    occasion = db.get(AssessmentOccasion, attempt.occasion_id)
    visit = db.get(Visit, occasion.visit_id)
    visit.visit_ordinal = 1
    db.add(visit)
    db.flush()
    assert exports.export_attempt(db, attempt.id) is None
    exports.prepare_directories()
    assert {p.name for p in root.iterdir()} == exports.CALLSIGNS
    assert {p.name for p in (root / "WHITE").iterdir()} == {
        "2026-10-07_DM3", "2026-10-11_DM7", "2026-10-15_DM11", "2026-10-20_POST"}
    assert not list(root.rglob("*.csv"))


def test_atomic_failure_preserves_existing_csv_and_original_evidence(ledger, monkeypatch):
    db, attempt, root = ledger
    complete(db, attempt)
    path = root / exports.export_attempt(db, attempt.id)
    original = path.read_bytes()
    def failed_source(*_):
        yield "pvt_assessment", "1", "raw_trials[0].rt_ms", 300
        raise OSError("synthetic unavailable evidence")
    monkeypatch.setattr(exports, "_source_rows", failed_source)
    with pytest.raises(OSError):
        exports.export_attempt(db, attempt.id)
    assert path.read_bytes() == original
    assert not list(root.rglob("*.tmp"))
    assert db.exec(select(PvtAssessment)).one().raw_trials_json == '[{"rt_ms": 243, "false_start": false}]'


def test_native_csv_is_flat_and_cannot_read_outside_its_session(ledger, tmp_path):
    from app.openmatb_models import OpenMatbBlockAttempt, OpenMatbSuiteSession
    db, _, root = ledger
    visit = db.exec(select(Visit)).one()
    occasion = AssessmentOccasion(participant_id="P01", visit_id=visit.id, instrument="openmatb", origin="synthetic_test")
    db.add(occasion)
    db.flush()
    attempt = AssessmentAttempt(occasion_id=occasion.id, ordinal=1, execution_purpose="study",
        acquisition_state="finished", started_at=datetime(2026, 10, 7, 14, tzinfo=timezone.utc))
    db.add(attempt)
    folder = tmp_path / "native-session"
    folder.mkdir()
    raw = folder / "native.csv"
    raw.write_text("time;task;value\n1;TRACK;0.25\n", encoding="utf-8")
    suite = OpenMatbSuiteSession(id="native-test", participant_id="P01", visit_id=visit.id, visit_ordinal=9,
        preset_id="test", preset_version="1", preset_sha256="a", instruction_protocol_id="test",
        instruction_version="1", instruction_sha256="b", block_order_json='["LOW"]', scenario_paths_json="[]",
        controller_lease_hash="never-export-lease", participant_token_hash="never-export-token", artifact_root=str(folder))
    db.add(suite)
    db.flush()
    block = OpenMatbBlockAttempt(id="native-block", session_id=suite.id, block_index=0, profile="LOW",
        task_status="completed", artifact_status="saved", session_csv=str(raw))
    db.add(block)
    db.flush()
    for table, identity in (("openmatb_suite_session", suite.id), ("openmatb_block_attempt", block.id)):
        db.add(AssessmentSourceLink(attempt_id=attempt.id, source_table=table, source_id=identity))
    db.commit()
    path = root / exports.export_attempt(db, attempt.id)
    content = path.read_text(encoding="utf-8-sig")
    assert "native_csv[1][2],0.25" in content
    assert "never-export" not in content and str(folder) not in content
    outside = tmp_path / "outside.csv"
    outside.write_text("private\n", encoding="utf-8")
    block.session_csv = str(outside)
    db.add(block)
    db.commit()
    with pytest.raises(ValueError, match="outside"):
        exports.export_attempt(db, attempt.id)
    assert path.read_text(encoding="utf-8-sig") == content
    assert raw.read_text(encoding="utf-8") == "time;task;value\n1;TRACK;0.25\n"


def test_mission_events_ratings_and_deferred_metrics_are_flat(ledger, tmp_path):
    from app.simulation_models import SimulationSession
    db, _, root = ledger
    visit = db.exec(select(Visit)).one()
    occasion = AssessmentOccasion(participant_id="P01", visit_id=visit.id, instrument="suas", origin="synthetic_test")
    db.add(occasion)
    db.flush()
    attempt = AssessmentAttempt(occasion_id=occasion.id, ordinal=1, execution_purpose="study",
        acquisition_state="started", started_at=datetime(2026, 10, 7, 14, tzinfo=timezone.utc))
    db.add(attempt)
    db.flush()
    folder = tmp_path / "mission"
    folder.mkdir()
    (folder / "events.jsonl").write_text('{"kind":"command","payload":{"rt_ms":321,"access_token":"never-export"}}\n', encoding="utf-8")
    (folder / "questionnaires.json").write_text('{"rtlx":42}', encoding="utf-8")
    mission = SimulationSession(id="synthetic-mission", participant_id="P01", visit_id=visit.id,
        scenario_id="test", scenario_sha256="a", manifest_json="{}", locale="es", lifecycle="FINISHED", artifact_root=str(folder))
    db.add(mission)
    db.flush()
    db.add(AssessmentSourceLink(attempt_id=attempt.id, source_table="simulation_session", source_id=mission.id))
    complete(db, attempt)
    path = root / exports.export_attempt(db, attempt.id)
    content = path.read_text(encoding="utf-8-sig")
    assert "events[0].payload.rt_ms,321" in content and "questionnaires.rtlx,42" in content
    assert "metrics.json.available,False" in content
    assert "never-export" not in content
    (folder / "metrics.json").write_text('{"score":0.8}', encoding="utf-8")
    exports.export_attempt(db, attempt.id)
    assert "metrics.score,0.8" in path.read_text(encoding="utf-8-sig")
    assert exports._cells("-0.25") == "-0.25"
    assert exports._cells("=1+1") == "'=1+1"


def test_cancelled_preparation_does_not_invent_an_acquisition_start(ledger):
    from app.assessment_service import transition
    db, attempt, root = ledger
    attempt.acquisition_state = "created"
    attempt.started_at = None
    db.add(attempt)
    db.flush()
    transition(db, attempt.id, "interrupted", "participant_stop")
    db.commit()
    with (root / exports.export_attempt(db, attempt.id)).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert all(row["started_at"] == "" and row["acquisition_state"] == "interrupted" for row in rows)
