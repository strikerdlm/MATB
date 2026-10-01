from datetime import datetime, timezone
import asyncio
import json
import pytest
from fastapi import HTTPException
from sqlmodel import Session, select
from app import astra_roster, astra_deployment
from app.models import Participant, ParticipantRoster, Visit
from app.openmatb_models import OpenMatbSuiteSession
from app.openmatb_runtime import OpenMatbRuntimeError
from app.openmatb_schemas import CreateOpenMatbSession
from app.routers.participants import remove_participant, restore_participant, list_participants
from tests.test_openmatb_runtime import _manager, _seed_visit


def test_astra_roster_has_five_seven_and_eight_unacquired_visits(engine):
    with Session(engine) as db:
        astra_roster.initialize(db)
        astra_roster.initialize(db)
        people = astra_roster.dashboard(db)['participants']
        assert [p['callsign'] for p in people if p['mission'] == 'ASTRA-1'] == ['CUELLAR','ICEMAN','COLORADO','WHITE','PIRATA']
        assert [p['callsign'] for p in people if p['mission'] == 'ASTRA-2'] == ['BART','CHUCKY','VOLCANO','K-FIR','Irving','Midas','Meteoro']
        assert len(db.exec(select(Participant)).all()) == 12
        assert len(db.exec(select(Visit)).all()) == 96
        assert all(len(p['visits']) == 8 and all(v['actual_date'] is None and v['completed_blocks'] == 0 for v in p['visits']) for p in people)
        assert people[-1]['time_slot'] == '15:45–17:15'
        assert people[-1]['visits'][-1]['planned_date'].isoformat() == '2026-11-05'
        assert people[0]['visits'][1]['planned_date'].isoformat() == '2026-10-06'
        assert all(p['unit'] is None and p['age_band'] is None for p in people if p['callsign'] in {'K-FIR', 'Irving', 'Midas', 'Meteoro'})
        assert len({tuple(p['block_order']) for p in people}) == 6


def test_removal_is_reversible_and_bootstrap_does_not_readd(engine):
    with Session(engine) as db:
        astra_roster.initialize(db)
        original = db.get(Participant, 'P01').model_dump()
        remove_participant('P01', db)
        astra_roster.initialize(db)
        assert len(list_participants(session=db)) == 11
        assert db.get(Participant, 'P01').model_dump() == original
        assert len(db.exec(select(Visit).where(Visit.participant_id == 'P01')).all()) == 8
        restore_participant('P01', db)
        assert len(list_participants(session=db)) == 12
        assert db.get(ParticipantRoster, 'P01').callsign == 'CUELLAR'


def test_callsign_display_preserves_legacy_database_and_prevents_duplicates(engine):
    from app.routers.participants import create_participant
    from app.schemas import ParticipantCreate
    from datetime import date

    with Session(engine) as db:
        astra_roster.initialize(db)
        for old, new in astra_roster.CALLSIGN_UPDATES.items():
            row = db.exec(select(ParticipantRoster).where(ParticipantRoster.callsign == new)).one()
            row.callsign = old
            db.add(row)
        db.commit()
        remove_participant('P12', db)
        # Compare every stored table, including visits, sessions and results.
        connection = db.connection().connection.driver_connection
        before = list(connection.iterdump())
        astra_roster.initialize(db)
        people = astra_roster.dashboard(db, include_archived=True)['participants']
        assert [(p['id'], p['callsign']) for p in people[-4:]] == [
            ('P09', 'K-FIR'), ('P10', 'Irving'), ('P11', 'Midas'), ('P12', 'Meteoro')]
        assert people[-1]['archived']
        assert [p['callsign'] for p in list_participants(include_archived=True, session=db)][-4:] == [
            'K-FIR', 'Irving', 'Midas', 'Meteoro']
        assert list(connection.iterdump()) == before
        for callsign in ('K-FIR', 'irving', 'MIDAS', 'Meteoro', 'Alfa 1', 'ALFA-4'):
            with pytest.raises(HTTPException) as error:
                astra_roster.add_person(db, callsign=callsign, mission='ASTRA-2')
            assert error.value.status_code == 409
        with pytest.raises(HTTPException) as error:
            create_participant(ParticipantCreate(id='P99', callsign='Irving', enrollment_date=date.today()), db)
        assert error.value.status_code == 409
        db.rollback()


def test_new_member_does_not_reuse_removed_identity(engine):
    with Session(engine) as db:
        astra_roster.initialize(db)
        remove_participant('P01', db)
        new = astra_roster.add_person(db, callsign='NUEVO', mission='ASTRA-1')
        assert new.id == 'P13'
        with pytest.raises(HTTPException):
            astra_roster.add_person(db, callsign=' cuellar ', mission='ASTRA-2')


def test_pending_session_can_be_recovered_but_not_duplicated(engine, tmp_path):
    _seed_visit(engine)
    manager = _manager(engine, tmp_path)
    request = CreateOpenMatbSession(participant_id='P01', visit_ordinal=1, execution_purpose='practice')
    prepared = asyncio.run(manager.create_session(request))
    manager.acknowledge_instructions(prepared.session.id, prepared.participant_token)
    assert manager.active_session().id == prepared.session.id
    with pytest.raises(OpenMatbRuntimeError, match='openmatb_active_session'):
        asyncio.run(manager.create_session(request))
    recovered = asyncio.run(manager.recover_pending_session(prepared.session.id))
    assert recovered.session.lifecycle == 'READY'
    assert recovered.controller_lease != prepared.controller_lease
    with pytest.raises(OpenMatbRuntimeError, match='invalid_lease'):
        asyncio.run(manager.abort(prepared.session.id, prepared.controller_lease, 'old_tab'))
    asyncio.run(manager.abort(recovered.session.id, recovered.controller_lease, 'operator_abort'))
    assert manager.active_session() is None
    assert asyncio.run(manager.create_session(request)).session.id != prepared.session.id


def test_active_or_acquired_sessions_cannot_be_reclaimed_or_participant_removed(engine, tmp_path):
    _seed_visit(engine)
    manager = _manager(engine, tmp_path)
    prepared = asyncio.run(manager.create_session(CreateOpenMatbSession(participant_id='P01', visit_ordinal=1, execution_purpose='practice')))
    with Session(engine) as db:
        with pytest.raises(HTTPException): remove_participant('P01', db)
        row = db.get(OpenMatbSuiteSession, prepared.session.id)
        row.lifecycle = 'READY'
        row.started_at = datetime.now(timezone.utc)
        db.add(row); db.commit()
    with pytest.raises(OpenMatbRuntimeError, match='openmatb_recovery_not_pending'):
        asyncio.run(manager.recover_pending_session(prepared.session.id))


def test_astra_protocol_materializes_real_assignments_without_results(engine, tmp_path):
    manager = _manager(engine, tmp_path)
    with Session(engine) as db:
        astra_roster.initialize(db)
        from app.study_registry import install_registry_guards
        install_registry_guards(engine)
        from app.components import is_component_active
        if not is_component_active('matb-openmatb'):
            with pytest.raises(HTTPException) as rejected:
                astra_deployment.configure(db, manager, 'Investigadora de prueba')
            assert rejected.value.status_code == 409
            assert 'OpenMATB' in rejected.value.detail
            assert not astra_deployment.status(db)['active']
            return
        current = astra_deployment.configure(db, manager, 'Investigadora de prueba')
        assert current['active']
        assert astra_deployment.configure(db, manager, 'Investigadora de prueba') == current
        first = astra_deployment.assign_visit(db, 'P01', 8)
        assert astra_deployment.assign_visit(db, 'P01', 8).id == first.id
        assert len(json.loads(first.occasions_json)) == 6
        assert first.arm == 'ORDER-1'
        from app.assessment_models import AssessmentAttempt
        assert not db.exec(select(AssessmentAttempt)).all()
        from app.study_registry import version_view
        view = version_view(db, current['version_id'])
        assert [v['code'] for v in view['study']['visits']] == [f'V{i}' for i in range(8)]
        assert len(view['study']['recovery_intervals']) == 16
    preset = next(p for p in manager.list_presets() if p.preset_id == astra_deployment.PRESET_ID)
    assert preset.profiles['PRACTICE'].duration_seconds == 300
    assert preset.profiles['PRACTICE'].difficulty == 0.1
    assert all(preset.profiles[level].duration_seconds == 900 for level in ('LOW','MEDIUM','HIGH'))


def test_astra_practice_uses_v7_label_without_changing_legacy_protocol(engine, tmp_path):
    manager = _manager(engine, tmp_path)
    with Session(engine) as db:
        astra_roster.initialize(db)
    prepared = asyncio.run(manager.create_session(CreateOpenMatbSession(participant_id='P01', visit_ordinal=8, execution_purpose='practice')))
    assert prepared.session.visit_code == 'V7'
    with Session(engine) as db:
        asyncio.run(manager.abort(prepared.session.id, prepared.controller_lease, 'operator_abort'))
        remove_participant('P01', db)
    with pytest.raises(HTTPException):
        asyncio.run(manager.create_session(CreateOpenMatbSession(participant_id='P01', visit_ordinal=8, execution_purpose='practice')))
