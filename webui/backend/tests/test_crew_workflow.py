"""Synthetic, isolated ledger tests; never write to the station database."""
import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlmodel import Session, select

from app import crew_workflow as crew, study_registry as registry
from app.assessment_models import AssessmentAttempt
from app.models import ParticipantRoster
from app.study_registry_models import StudyAssignment
from tests.test_openmatb_runtime import _manager


@pytest.fixture(autouse=True)
def crew_components():
    from app.components import is_component_active

    if not all(is_component_active(name) for name in ("matb-openmatb", "matb-suas")):
        pytest.skip("Requires OpenMATB and sUAS; exercised by full-component tests")


@pytest.fixture
def station(engine, tmp_path):
    runtime = _manager(engine, tmp_path)
    with Session(engine) as db:
        result = crew.configure(db, runtime, actor="Investigadora de prueba", reason="Prueba aislada del inicio simplificado solicitado por la tripulación.")
        db.commit()
        yield db, runtime, result


def test_configuration_has_callsigns_no_polar_and_is_idempotent(station):
    db, runtime, result = station
    assert [p["callsign"] for p in crew.roster(db, "openmatb")["participants"]] == list(crew.CALLSIGNS)
    study = json.loads(registry.get_version(db, result["version_id"]).study_json)
    assert set(study["enabled_instruments"]) == {"openmatb", "questionnaire", "pvt", "screen", "suas"}
    assert all(not p["acknowledgement_required"] and not p["practice"] for p in study["preparation_policy"])
    assert not db.exec(select(AssessmentAttempt)).all()
    assert crew.configure(db, runtime, actor="Investigadora de prueba", reason="Comprobación idempotente de la misma configuración.")["changed"] is False


def test_prepare_reuses_attempt_and_assignment_for_double_click(station):
    db, _, _ = station
    first = crew.prepare(db, "CUELLAR", "screen")
    second = crew.prepare(db, "CUELLAR", "screen")
    assert first["action"] == "launch"
    assert first["attempt_id"] == second["attempt_id"]
    assert first["session_number"] == 1
    assert len(db.exec(select(StudyAssignment)).all()) == 1
    assert len(db.exec(select(AssessmentAttempt)).all()) == 1


def test_suas_opens_exact_visit_pvt_before_mission(station):
    db, _, _ = station
    result = crew.prepare(db, "ICEMAN", "suas")
    pvt = crew.prepare(db, "ICEMAN", "pvt")
    assert result["activity"] == "pvt"
    assert result["attempt_id"] == pvt["attempt_id"]
    assert result["visit_id"] == pvt["visit_id"]
    assert crew.progress(db, "ICEMAN", "suas")[0]["completed_sessions"] == 0
    attempt = db.get(AssessmentAttempt, pvt["attempt_id"])
    attempt.acquisition_state = "interrupted"
    attempt.interruption_category = "unknown"
    db.add(attempt)
    db.flush()
    assert crew.progress(db, "ICEMAN", "suas")[0]["state"] == "interrupted"
    assert crew.prepare(db, "ICEMAN", "suas", retry=True)["attempt_id"] != attempt.id


def test_daily_limit_uses_bogota_midnight_and_keeps_other_activities_available(station):
    db, _, _ = station
    completed = datetime(2026, 10, 7, 4, 59, tzinfo=timezone.utc)
    result = crew.prepare(db, "WHITE", "screen", now=completed)
    attempt = db.get(AssessmentAttempt, result["attempt_id"])
    # A synthetic completed acquisition models a real source adapter's terminal event.
    attempt.acquisition_state = "finished"
    attempt.started_at = completed
    attempt.finished_at = completed
    db.add(attempt)
    db.flush()
    blocked = crew.prepare(db, "WHITE", "screen", now=completed)
    assert blocked["action"] == "done_today"
    assert blocked["session_number"] == 2
    assert crew.prepare(db, "WHITE", "pvt", now=completed)["action"] == "launch"
    next_day = datetime(2026, 10, 7, 5, 0, tzinfo=timezone.utc)
    next_session = crew.prepare(db, "WHITE", "screen", now=next_day)
    assert next_session["action"] == "launch"
    assert next_session["session_number"] == 2
    assert next_session["attempt_id"] != attempt.id


def test_interrupted_attempt_requires_recorded_retry_and_never_skips_session(station):
    db, _, _ = station
    first = crew.prepare(db, "PIRATA", "pvt")
    attempt = db.get(AssessmentAttempt, first["attempt_id"])
    attempt.acquisition_state = "interrupted"
    attempt.interruption_category = "unknown"
    db.add(attempt)
    db.flush()
    assert crew.prepare(db, "PIRATA", "pvt")["action"] == "retry_required"
    retry = crew.prepare(db, "PIRATA", "pvt", retry=True)
    assert retry["session_number"] == 1
    replacement = db.get(AssessmentAttempt, retry["attempt_id"])
    assert replacement.repeat_of == attempt.id
    assert attempt.acquisition_state == "interrupted"


def test_invalid_callsign_and_instrument_do_not_create_records(station):
    db, _, _ = station
    for callsign, instrument in (("P01", "pvt"), ("CUELLAR", "physiology")):
        with pytest.raises(HTTPException) as error:
            crew.prepare(db, callsign, instrument)
        assert error.value.status_code == 422
    assert not db.exec(select(AssessmentAttempt)).all()


def test_browser_admission_needs_no_preparation_form_and_refuses_duplicate_owner(station):
    from app.routers.assessments import start
    db, _, _ = station
    prepared = crew.prepare(db, "COLORADO", "pvt")
    db.commit()
    result = start(prepared["attempt_id"], db)
    assert result["acquisition_state"] == "started"
    assert result["preparation_admission"] is not None
    with pytest.raises(HTTPException) as error:
        start(prepared["attempt_id"], db)
    assert error.value.detail["code"] == "browser_already_acquiring"


def test_browser_retry_releases_only_interrupted_owner_and_idle_switch_needs_no_form(station):
    from app.routers.assessments import start, interrupt
    from app.assessment_schemas import InterruptIn
    from app import station_resources
    from app.assessment_service import transition
    db, runtime, _ = station
    first = crew.prepare(db, "CUELLAR", "pvt")
    start(first["attempt_id"], db)
    with pytest.raises(HTTPException) as busy:
        crew.prepare(db, "WHITE", "screen")
    assert busy.value.detail["code"] == "crew_station_busy"
    interrupt(first["attempt_id"], InterruptIn(category="unknown"), db)
    assert station_resources.snapshot(db)["reservation"]["uncertain"]
    repeated = crew.prepare(db, "CUELLAR", "pvt", retry=True)
    start(repeated["attempt_id"], db)
    transition(db, repeated["attempt_id"], "finished")
    db.commit()
    assert not station_resources.snapshot(db)["acquisitions"]
    other = crew.prepare(db, "WHITE", "screen")
    start(other["attempt_id"], db)
    assert station_resources.snapshot(db)["reservation"]["participant"] == other["participant_id"]


def test_native_blocks_and_ratings_stay_pending_with_real_elapsed_rest(station):
    from app.assessment_service import create_attempt
    from app.assessment_schemas import AttemptIn
    from app.study_registry_models import StudyRecoveryInterval
    db, _, _ = station
    now = datetime(2026, 10, 6, 17, 0, tzinfo=timezone.utc)
    prepared = crew.prepare(db, "CUELLAR", "openmatb", now=now)
    task = db.get(AssessmentAttempt, prepared["attempt_id"])
    task.acquisition_state = "finished"
    task.finished_at = now
    db.add(task)
    db.flush()
    public, state = crew.progress(db, "CUELLAR", "openmatb", now=now)
    assert public["completed_sessions"] == 0
    assert state["pending"]["instrument"] == "questionnaire"
    occasion_id = json.loads(state["assignment"].occasions_json)[state["pending"]["key"]]
    ratings = create_attempt(db, occasion_id, AttemptIn(execution_purpose="study", target_attempt_id=task.id))
    ratings.acquisition_state = "finished"
    ratings.finished_at = now
    ratings.raw_saving = "saved"
    db.add(ratings)
    db.flush()
    rest = crew.prepare(db, "CUELLAR", "openmatb", now=now)
    assert rest["action"] == "rest" and rest["remaining_seconds"] == 180
    assert rest["completed_sessions"] == 0
    from datetime import timedelta
    next_block = crew.prepare(db, "CUELLAR", "openmatb", now=now + timedelta(seconds=180))
    assert next_block["action"] == "launch"
    assert next_block["session_number"] == 1
    recorded = db.exec(select(StudyRecoveryInterval)).one()
    assert recorded.ended_at is not None
    assert recorded.anchor_attempt_id == ratings.id


def test_configuration_preserves_existing_identity_and_adds_only_missing_crew(engine, tmp_path):
    from datetime import date
    from app.models import Participant
    runtime = _manager(engine, tmp_path)
    with Session(engine) as db:
        for identity, callsign in (("P01", "CUELLAR"), ("P02", "COLORADO"), ("P03", "ICEMAN"), ("P04", "PIRATA"), ("P99", "P99")):
            db.add(Participant(id=identity, enrollment_date=date(2026, 10, 1)))
            db.flush()
            db.add(ParticipantRoster(participant_id=identity, callsign=callsign))
        db.commit()
        crew.configure(db, runtime, actor="Investigadora de prueba", reason="Conservar identidades previas durante configuración de prueba.")
        assert db.get(ParticipantRoster, "P03").callsign == "ICEMAN"
        assert db.get(ParticipantRoster, "P04").callsign == "PIRATA"
        assert db.get(ParticipantRoster, "P99").callsign == "P99"
        assert len(db.exec(select(ParticipantRoster)).all()) == 6
        assert crew.progress(db, "WHITE", "pvt")[0]["participant_id"] not in {"P01", "P02", "P03", "P04", "P99"}


def test_terminal_legacy_native_source_does_not_block_or_rewrite_history(station):
    import asyncio
    from app.assessment_adapters import source_attempt
    from app.openmatb_models import OpenMatbSuiteSession
    from app.openmatb_schemas import CreateOpenMatbSession
    db, runtime, _ = station
    prepared = asyncio.run(runtime.create_session(CreateOpenMatbSession(
        participant_id="P01", visit_ordinal=1, execution_purpose="practice")))
    native = db.get(OpenMatbSuiteSession, prepared.session.id)
    attempt = source_attempt(db, "openmatb_suite_session", native.id)
    attempt.acquisition_state = "started"
    native.lifecycle = "COMPLETE"
    db.add(attempt)
    db.add(native)
    db.commit()
    assert crew._has_live_attempt(db) is False
    assert crew.configure(db, runtime, actor="Investigadora de prueba", reason="Conservar historial nativo antiguo sin adquisición activa.")["changed"] is False
    assert db.get(AssessmentAttempt, attempt.id).acquisition_state == "started"
    native.lifecycle = "READY"
    db.add(native)
    db.flush()
    assert crew._has_live_attempt(db) is True


def test_native_creation_binds_the_crew_attempt_and_waits_only_for_hardware_preflight(station):
    import asyncio
    from app.openmatb_schemas import CreateOpenMatbSession
    db, runtime, _ = station
    selected = crew.prepare(db, "CUELLAR", "openmatb")
    db.commit()
    config = selected["config"]
    created = asyncio.run(runtime.create_session(CreateOpenMatbSession(
        preparation_only=True, attempt_id=selected["attempt_id"], execution_purpose="study",
        participant_id=selected["participant_id"], visit_ordinal=selected["visit_ordinal"],
        preset_id=config["preset"]["id"], preset_version=config["preset"]["version"],
        instruction_protocol_id=config["instructions"]["id"], instruction_version=config["instructions"]["version"],
        visual_profile_id=config["visual"]["id"], visual_profile_version=config["visual"]["version"], display_index=0)))
    assert created.session.lifecycle == "PREFLIGHT_READY"
    assert created.session.participant_id == selected["participant_id"]
    again = crew.prepare(db, "CUELLAR", "openmatb")
    assert again["session_id"] == created.session.id
    assert again["attempt_id"] == selected["attempt_id"]
    db.commit()
    asyncio.run(runtime.abort(created.session.id, created.controller_lease, "operator_abort"))
