from tests.study_policy_fixtures import fixture_policies
"""Frozen authoring and prospective assignment contracts (core and auto)."""
from datetime import date
import json
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, select
from app.models import Participant, Visit


def authored(db):
    from app.study_registry import create_draft, template
    payload = template('pre-post-recovery')
    payload['study']['rules'] = dict(preparation='Researcher instruction review', repeat='Explicit repeats retained', interruption='Record cause; retain data')
    payload['analysis']['rules'] = dict(exclusions='Exclude interrupted attempts', denominators='All assigned participants', qualification='Describe timing evidence', pooling='Separate every version', historical_unknowns='exclude')
    payload['study']['synthetic'] = False
    return create_draft(db, fixture_policies(payload))


def frozen(db):
    from app.study_registry import rehearse, freeze
    draft = authored(db)
    rehearsal = rehearse(db, draft.id)
    return freeze(db, draft.id, dict(actor='Dr Example', reason='Reviewed scientific rules', sha256=draft.sha256, rehearsal_id=rehearsal.id))


def seed(db):
    db.add(Participant(id='R01', enrollment_date=date(2026, 9, 10)))
    db.flush()
    db.add(Visit(participant_id='R01', visit_ordinal=1, scheduled_day=0)); db.commit()


def test_draft_rehearsal_freeze_and_immutability(engine):
    from app.study_registry import rehearse, freeze, update_draft, version_view, install_registry_guards
    from app.study_registry_models import StudyRehearsal
    with Session(engine) as db:
        seed(db)
        draft = authored(db)
        before = len(db.exec(select(Participant)).all())
        rehearsal = rehearse(db, draft.id)
        assert len(db.exec(select(Participant)).all()) == before
        assert json.loads(rehearsal.result_json)['isolation'] == 'ephemeral_database'
        changed = json.loads(draft.payload_json); changed['study']['title'] = 'Changed'
        update_draft(db, draft.id, changed)
        with pytest.raises(HTTPException) as exc:
            freeze(db, draft.id, dict(actor='Dr Example', reason='Reviewed', sha256=draft.sha256, rehearsal_id=rehearsal.id))
        assert exc.value.status_code == 409
        rehearsal = rehearse(db, draft.id)
        version = freeze(db, draft.id, dict(actor='Dr Example', reason='Reviewed', sha256=draft.sha256, rehearsal_id=rehearsal.id))
        assert version_view(db, version.id)['study_sha256']
        with pytest.raises(HTTPException): update_draft(db, draft.id, changed)
        db.commit()
    install_registry_guards(engine)
    with engine.begin() as conn:
        with pytest.raises(Exception, match='immutable'): conn.execute(text('UPDATE study_version SET study_json=\'{}\''))


def test_validation_missing_rules_bad_references_and_synthetic(engine):
    from app.study_registry import create_draft, template, validate, rehearse, freeze
    with Session(engine) as db:
        draft = create_draft(db, template('repeated-block'))
        issues = validate(db, draft.id)
        assert any('rules' in issue['path'] for issue in issues)
        draft = authored(db)
        payload = json.loads(draft.payload_json)
        payload['analysis']['outcomes'][0]['occasion_keys'] = ['absent']
        broken = create_draft(db, payload)
        assert any('occasion_keys' in issue['path'] for issue in validate(db, broken.id))
        payload['analysis']['outcomes'][0]['occasion_keys'] = ['pre']
        payload['study']['synthetic'] = True
        synthetic = create_draft(db, payload)
        rehearsal = rehearse(db, synthetic.id)
        with pytest.raises(HTTPException): freeze(db, synthetic.id, dict(actor='Dr Example', reason='Reviewed', sha256=synthetic.sha256, rehearsal_id=rehearsal.id))


def test_explicit_amendment_rejects_stale_and_preserves_started_visit(engine):
    from app.study_registry import activate, assign, amend
    from app.study_admission import resolve_assignment
    from app.assessment_service import create_attempt, transition
    from app.assessment_schemas import AttemptIn
    with Session(engine) as db:
        seed(db)
        first = frozen(db); activate(db, first.id, actor='Dr Example', reason='Begin')
        assignment = assign(db, first.id, 'R01', 1, 'A', actor='Dr Example')
        occasion = json.loads(assignment.occasions_json)['pre']
        stale = create_attempt(db, occasion, AttemptIn(execution_purpose='study'))
        second = frozen(db); activate(db, second.id, actor='Dr Example', reason='Amend')
        amended = amend(db, second.id, [assignment.id], actor='Dr Example', reason='Updated instructions')
        with pytest.raises(HTTPException): transition(db, stale.id, 'started')
        with pytest.raises(HTTPException): resolve_assignment(db, attempt_id=stale.id, instrument='pvt', participant_id='R01', visit_id=1, purpose='study')
        current = amended[0]
        attempt = create_attempt(db, json.loads(current.occasions_json)['pre'], AttemptIn(execution_purpose='study'))
        transition(db, attempt.id, 'started')
        with pytest.raises(HTTPException): amend(db, first.id, [current.id], actor='Dr Example', reason='Wrong')
        assert resolve_assignment(db, attempt_id=attempt.id, instrument='pvt', participant_id='R01', visit_id=1, purpose='study')['version_id'] == second.id


def test_local_metadata_and_wrong_workspace_never_admit(engine):
    from app.study_registry import activate
    from app.study_registry_models import StudyWorkspace
    from app.study_admission import resolve_assignment
    from app.assessment_service import create_occasion, create_attempt
    from app.assessment_schemas import OccasionIn, AttemptIn
    with Session(engine) as db:
        seed(db); version = frozen(db)
        local = create_occasion(db, OccasionIn(participant_id='R01', visit_id=1, instrument='pvt', phase='pre', order=1, version_ref=version.id))
        with pytest.raises(HTTPException): create_attempt(db, local.id, AttemptIn(execution_purpose='study'))
        practice = create_attempt(db, local.id, AttemptIn(execution_purpose='practice'))
        assert resolve_assignment(db, attempt_id=practice.id, instrument='pvt', participant_id='R01', visit_id=1, purpose='practice') is None
        workspace = db.get(StudyWorkspace, 1); workspace.study_id = 'other'; db.add(workspace); db.flush()
        with pytest.raises(HTTPException): activate(db, version.id, actor='Dr Example', reason='Wrong workspace')


def test_recovery_interval_requires_exact_finished_anchor_and_actual_elapsed_time(engine):
    from datetime import timedelta
    from app.study_registry import update_draft, rehearse, freeze, activate, assign
    from app.assessment_service import create_attempt, transition
    from app.assessment_schemas import AttemptIn
    from app.routers.study_registry import recovery_start, recovery_finish
    from app.study_registry_schemas import Attestation
    from app.study_registry_models import StudyRecoveryInterval
    with Session(engine) as db:
        seed(db); draft=authored(db); payload=json.loads(draft.payload_json)
        payload['study']['recovery_intervals']=[dict(key='rest',anchor_key='post',before_key='recovery',duration_seconds=60)]
        update_draft(db,draft.id,payload); r=rehearse(db,draft.id)
        version=freeze(db,draft.id,dict(actor='Dr Example',reason='Authored rest duration',sha256=draft.sha256,rehearsal_id=r.id))
        activate(db,version.id,actor='Dr Example',reason='Begin'); assignment=assign(db,version.id,'R01',1,'A',actor='Dr Example')
        occasions=json.loads(assignment.occasions_json)
        post=create_attempt(db,occasions['post'],AttemptIn(execution_purpose='study'))
        recovery=create_attempt(db,occasions['recovery'],AttemptIn(execution_purpose='study'))
        body=Attestation(actor='Dr Administrator',reason='Observed interval')
        with pytest.raises(HTTPException): recovery_start(assignment.id,'rest',body,post.id,db)
        transition(db,post.id,'started');transition(db,post.id,'finished')
        with pytest.raises(HTTPException): transition(db,recovery.id,'started')
        recorded=recovery_start(assignment.id,'rest',body,post.id,db)
        with pytest.raises(HTTPException): recovery_finish(assignment.id,'rest',body,db)
        recorded.started_at-=timedelta(seconds=61);db.add(recorded);db.commit()
        ended=recovery_finish(assignment.id,'rest',body,db)
        assert ended.ended_at > ended.started_at
        assert ended.finish_actor=='Dr Administrator' and ended.finish_reason=='Observed interval'
        transition(db,recovery.id,'started')
        assert db.get(StudyRecoveryInterval,(assignment.id,'rest')).anchor_attempt_id==post.id


def test_rejects_unsupported_questionnaire_and_impossible_accompaniment(engine):
    from app.study_registry import create_draft, validate
    with Session(engine) as db:
        payload=json.loads(authored(db).payload_json)
        pvt=payload['study']['occasions'][0]
        payload['study']['occasions'].append({**pvt,'key':'ratings','instrument':'questionnaire','order':4,'target_key':'pre','config':dict(binding_id='MATB-FAC-WORKLOAD-1.0',input_mapping='browser-ratings',scoring='rtlx-mean-bedford')})
        payload['study']['enabled_instruments'].append('questionnaire')
        assert any('OpenMATB target' in i['message'] for i in validate(db,create_draft(db,payload).id))
        payload['study']['occasions']=payload['study']['occasions'][:-1]
        payload['study']['enabled_instruments']=['pvt']
        payload['study']['occasions'][0]['accompanying_key']='post'
        assert any('accompaniment' in i['message'].lower() for i in validate(db,create_draft(db,payload).id))


def test_active_authored_schedule_drives_new_enrollment(client,engine):
    from app.study_registry import update_draft,rehearse,freeze,activate
    with Session(engine) as db:
        draft=authored(db);payload=json.loads(draft.payload_json)
        payload['study']['visits']=[dict(ordinal=1,code='BASE',scheduled_day=0),dict(ordinal=2,code='FOLLOW',scheduled_day=9)]
        update_draft(db,draft.id,payload);r=rehearse(db,draft.id)
        v=freeze(db,draft.id,dict(actor='Dr Example',reason='Authored schedule',sha256=draft.sha256,rehearsal_id=r.id));activate(db,v.id,actor='Dr Example',reason='Begin');db.commit()
    response=client.post('/participants',json=dict(id='P09',enrollment_date='2026-09-10'))
    assert response.status_code==201,response.text
    visits=client.get('/participants/P09/visits').json()
    assert [(v['visit_ordinal'],v['scheduled_day']) for v in visits]==[(1,0),(2,9)]


def test_binding_catalog_does_not_offer_disabled_optional_components(engine,monkeypatch):
    from app import components
    from app.study_bindings import binding_options
    monkeypatch.setattr(components,'is_component_active',lambda identity: False)
    with Session(engine) as db:
        options=binding_options(db)
        assert set(options)=={'pvt','screen'}


def test_required_preparation_fails_closed_and_repeat_limits_are_enforced(engine):
    from app.study_registry import create_draft, rehearse,freeze,activate,assign,validate
    from app.assessment_service import create_attempt,transition
    from app.assessment_schemas import AttemptIn
    with Session(engine) as db:
        seed(db);payload=json.loads(authored(db).payload_json)
        payload['study']['preparation_policy'][0]['acknowledgement_required']=True
        draft=create_draft(db,payload);r=rehearse(db,draft.id)
        v=freeze(db,draft.id,dict(actor='Dr Test',reason='Required acknowledgement',sha256=draft.sha256,rehearsal_id=r.id));activate(db,v.id,actor='Dr Test',reason='Test');a=assign(db,v.id,'R01',1,'A',actor='Dr Test')
        task=create_attempt(db,json.loads(a.occasions_json)['pre'],AttemptIn(execution_purpose='study'))
        with pytest.raises(HTTPException) as exc: transition(db,task.id,'started')
        assert exc.value.detail['code']=='study_preparation_engine_pending'
        payload['study']['preparation_policy'][0]['practice']=[dict(id='guess',rationale='Unsupported metric test',metric='invented.pass',comparator='gte',threshold=7)]
        assert any('Unsupported practice observation' in i['message'] for i in validate(db,create_draft(db,payload).id))


def test_authored_repeat_limit_rejects_second_attempt(engine):
    from app.study_registry import create_draft,rehearse,freeze,activate,assign
    from app.assessment_service import create_attempt,transition
    from app.assessment_schemas import AttemptIn
    with Session(engine) as db:
        seed(db);payload=json.loads(authored(db).payload_json);payload['study']['repeat_policy']['max_attempts']=1
        draft=create_draft(db,payload);r=rehearse(db,draft.id);v=freeze(db,draft.id,dict(actor='Dr Test',reason='One attempt',sha256=draft.sha256,rehearsal_id=r.id));activate(db,v.id,actor='Dr Test',reason='Test');a=assign(db,v.id,'R01',1,'A',actor='Dr Test')
        task=create_attempt(db,json.loads(a.occasions_json)['pre'],AttemptIn(execution_purpose='study'));transition(db,task.id,'started');transition(db,task.id,'finished')
        with pytest.raises(HTTPException) as exc: create_attempt(db,task.occasion_id,AttemptIn(execution_purpose='study'),repeat_of=task.id,reason='Try again')
        assert exc.value.detail['code']=='study_repeat_not_permitted'


def test_public_browser_study_saves_reject_unassigned_and_amended_context(client,engine):
    from tests.test_experiment_safety import full_pvt
    from tests.test_screen_endpoint import _payload
    from app.study_registry import activate,assign,amend
    from app.assessment_service import create_attempt
    from app.assessment_schemas import AttemptIn
    client.post('/participants',json=dict(id='P01',enrollment_date='2026-09-10'))
    for path,body in [('/pvt',full_pvt()),('/screen',dict(execution_purpose='study',participant_id='P01',payload=_payload()))]:
        response=client.post(path,json=body)
        assert response.status_code==409,response.text
        assert response.json()['detail']['code']=='study_assignment_required'
    with Session(engine) as db:
        v=frozen(db);activate(db,v.id,actor='Dr Test',reason='Begin');a=assign(db,v.id,'P01',1,'A',actor='Dr Test')
        task=create_attempt(db,json.loads(a.occasions_json)['pre'],AttemptIn(execution_purpose='study'));identity=task.id
        updated=frozen(db);activate(db,updated.id,actor='Dr Test',reason='New version');amend(db,updated.id,[a.id],actor='Dr Test',reason='Future assignment');db.commit()
    response=client.post('/pvt',json=full_pvt(attempt_id=identity,locale='es-419'))
    assert response.status_code==409 and response.json()['detail']['code']=='study_assignment_required'


def test_frozen_browser_binding_rejects_changed_installed_stimulus(engine,monkeypatch):
    from app.study_registry import activate,assign
    from app.assessment_service import create_attempt,transition
    from app.assessment_schemas import AttemptIn
    from app import study_bindings
    with Session(engine) as db:
        seed(db);v=frozen(db);activate(db,v.id,actor='Dr Test',reason='Begin');a=assign(db,v.id,'R01',1,'A',actor='Dr Test')
        task=create_attempt(db,json.loads(a.occasions_json)['pre'],AttemptIn(execution_purpose='study'))
        original=study_bindings.browser_binding
        monkeypatch.setattr(study_bindings,'browser_binding',lambda key:{**original(key),'sha256':'changed-source'})
        with pytest.raises(HTTPException) as exc: transition(db,task.id,'started')
        assert exc.value.detail['code']=='study_binding_unavailable'


def test_browser_fingerprint_tracks_shared_copy_and_server_scoring(tmp_path,monkeypatch):
    from app import study_bindings
    monkeypatch.setattr(study_bindings,'_ROOT',tmp_path)
    copy=tmp_path/'webui/frontend/src/lib/i18n.tsx';copy.parent.mkdir(parents=True);copy.write_bytes(b'participant instructions A')
    scoring=tmp_path/'webui/backend/app/routers/pvt.py';scoring.parent.mkdir(parents=True);scoring.write_bytes(b'scoring A')
    first=study_bindings.browser_binding('pvt')['sha256']
    copy.write_bytes(b'participant instructions B')
    second=study_bindings.browser_binding('pvt')['sha256']
    scoring.write_bytes(b'scoring B')
    assert len({first,second,study_bindings.browser_binding('pvt')['sha256']})==3
