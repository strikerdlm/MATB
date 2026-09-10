from tests.study_policy_fixtures import fixture_policies
"""Assigned acquisitions preserve immutable context through source-specific adapters."""
import asyncio
import json
from datetime import date
from pathlib import Path
import pytest
from fastapi import HTTPException
from sqlmodel import Session, select
from app.models import Participant, Visit
from app.assessment_models import AssessmentAttempt, AssessmentOccasion


def assigned(db, instrument, config, *, participant='P01', locale='es-419', keys=None):
    from app.study_registry import create_draft, template, rehearse, freeze, activate, assign
    from app.assessment_service import create_attempt, transition
    from app.assessment_schemas import AttemptIn
    from app.components import is_component_active
    component = {'openmatb':'matb-openmatb','physiology':'matb-physiology','liftoff':'matb-liftoff'}.get(instrument)
    if component and not is_component_active(component): pytest.skip('Assigned optional acquisition requires its auto profile component.')
    if db.get(Participant, participant) is None:
        db.add(Participant(id=participant,enrollment_date=date(2026,9,10)));db.flush()
        db.add(Visit(participant_id=participant,visit_ordinal=1,scheduled_day=0));db.flush()
    visit=db.exec(select(Visit).where(Visit.participant_id==participant,Visit.visit_ordinal==1)).first()
    if visit is None:
        visit=Visit(participant_id=participant,visit_ordinal=1,scheduled_day=0);db.add(visit);db.flush()
    payload=template('pre-post-recovery')
    original=payload['study']['occasions'][0]
    occasions=[]
    for index,key in enumerate(keys or ['task']):
        item={**original,'key':key,'instrument':instrument,'phase':key,'order':index*2+1,'config':config,'locale':locale,'condition_by_arm':{'A':'HIGH'}}
        occasions.append(item)
        if instrument=='openmatb': occasions.append({**original,'key':key+'_rating','instrument':'questionnaire','phase':'ratings','order':index*2+2,'target_key':key,'locale':locale,'config':{'binding_id':'MATB-FAC-WORKLOAD-1.0','input_mapping':'browser-ratings','scoring':'rtlx-mean-bedford'}})
    payload['study'].update(synthetic=False,occasions=occasions,enabled_instruments=list({o['instrument'] for o in occasions}),rules=dict(preparation='Researcher reviewed control knowledge',repeat='Retain all explicit repeats',interruption='Record actual cause'))
    payload['analysis']['outcomes'][0].update(metric={'openmatb':'openmatb.performance','physiology':'physiology.raw','liftoff':'liftoff.performance','pvt':'pvt.median_rt_ms','screen':'screen.hcf'}[instrument],occasion_keys=[occasions[0]['key']])
    payload['analysis']['rules'].update(exclusions='Retain all observations',denominators='All assigned visits',qualification='Report timing and hardware evidence',pooling='Separate versions')
    draft=create_draft(db,fixture_policies(payload));rehearsal=rehearse(db,draft.id);version=freeze(db,draft.id,dict(actor='Dr Test',reason='Authored fixture rules',sha256=draft.sha256,rehearsal_id=rehearsal.id));activate(db,version.id,actor='Dr Test',reason='Fixture collection')
    assignment=assign(db,version.id,participant,visit.id,'A',actor='Dr Test')
    result=[]
    for key in keys or ['task']:
        a=create_attempt(db,json.loads(assignment.occasions_json)[key],AttemptIn(execution_purpose='study'));transition(db,a.id,'started');result.append(a.id)
    db.commit()
    return assignment.id,result


def native_binding(db):
    from app.study_bindings import binding_options
    from app.components import is_component_active
    if not is_component_active('matb-openmatb'): pytest.skip('Assigned native acquisition requires its auto profile component.')
    options=binding_options(db)['openmatb']
    return dict(preset=next(v for v in options['presets'] if v['id']=='matb-fac-standard'),instructions=next(v for v in options['instructions'] if v['id']=='matb-fac-es-419'),visual=next(v for v in options['visuals'] if v['id']=='matb-fac-modern'),input_mapping='openmatb-default',scenario_generator='published-preset-v1',scoring='openmatb-current')


def test_native_repeated_condition_child_ratings_and_evidence_identity(engine,tmp_path):
    from tests.test_openmatb_runtime import _manager
    from app.openmatb_schemas import CreateOpenMatbSession,WorkloadScaleRequest
    from app.openmatb_models import OpenMatbSuiteSession
    from app.assessment_adapters import source_attempt
    manager=_manager(engine,tmp_path)
    with Session(engine) as db:
        assignment,attempt_ids=assigned(db,'openmatb',native_binding(db),keys=['high1','high2'])
    files=[]
    for index,attempt_id in enumerate(attempt_ids):
        prepared=asyncio.run(manager.create_session(CreateOpenMatbSession(execution_purpose='study',participant_id='P01',visit_ordinal=1,attempt_id=attempt_id,visual_profile_id='matb-fac-modern',visual_profile_version='1.0.0')))
        assert prepared.session.block_order==['HIGH']
        from tests.test_openmatb_records import sealed_attempt
        block_id,capture_id,raw_events=sealed_attempt((manager,prepared),engine,terminal=False,profile='HIGH',purpose='study')
        with Session(engine) as db:
            suite=db.get(OpenMatbSuiteSession,prepared.session.id)
            assert source_attempt(db,'openmatb_block_attempt',block_id).id==attempt_id
            suite.lifecycle='AWAITING_SCALE';db.add(suite);db.commit()
            assert db.get(AssessmentAttempt,attempt_id).acquisition_state=='finished'
            occasion_id=db.get(AssessmentAttempt,attempt_id).occasion_id
            assert list(json.loads(suite.scenario_paths_json))==[occasion_id]
        scores={key:40+index*5 for key in ['mental_demand','physical_demand','temporal_demand','performance','effort','frustration']}
        manager.submit_scale(prepared.session.id,prepared.participant_token,WorkloadScaleRequest(block_instance_id=block_id,nasa_tlx=scores,bedford=3))
        path=Path(manager.artifact_root)/prepared.session.id/'scales'/f'{occasion_id}.json';files.append(path)
        assert path.exists()
        with Session(engine) as db:
            rating=source_attempt(db,'openmatb_block_attempt',block_id,'ratings')
            assert rating.target_attempt_id==attempt_id and rating.acquisition_state=='finished'
            assert db.get(AssessmentOccasion,rating.occasion_id).version_ref
        manager.records.process(block_id)
        receipt=manager.receipt(prepared.session.id)['attempts'][0]
        assert receipt['legacy_import_status']=='inapplicable_assigned_occasion'
        assert receipt['capture_id']==capture_id and receipt['evidence_status']=='processed'
        from app.evidence_models import EvidenceArtifact
        with Session(engine) as db:
            assert source_attempt(db,'evidence_capture',capture_id).id==attempt_id
            artifact=db.exec(select(EvidenceArtifact).where(EvidenceArtifact.capture_id==capture_id,EvidenceArtifact.role=='events')).one()
            assert artifact.content==raw_events
    assert files[0].read_bytes()!=files[1].read_bytes()


def test_h10_supported_binding_assignment_and_current_purpose(engine):
    from app.study_bindings import binding_options
    from app.study_admission import resolve_assignment
    from app.purpose_service import classify_retrospectively
    with Session(engine) as db:
        if 'physiology' not in binding_options(db): pytest.skip('Assigned H10 acquisition runs in auto profile.')
        config=binding_options(db)['physiology'][0]
        assignment,attempts=assigned(db,'physiology',config)
        assert resolve_assignment(db,attempt_id=attempts[0],instrument='physiology',participant_id='P01',purpose='study',config=config)
        with pytest.raises(HTTPException):resolve_assignment(db,attempt_id=attempts[0],instrument='physiology',participant_id='P01',purpose='study',config={**config,'input_mapping':'unresolved-device'})
        attempt=db.get(AssessmentAttempt,attempts[0]);classify_retrospectively(db,attempt.purpose_provenance_id,purpose='practice',reviewer='Dr Test',reason='Correction')
        with pytest.raises(HTTPException):resolve_assignment(db,attempt_id=attempts[0],instrument='physiology',participant_id='P01',purpose='study',config=config)


def test_h10_actual_completion_and_restart_follow_assigned_attempt(engine,tmp_path):
    from app.physiology_runtime import PolarCaptureManager
    from matb_integration.physiology.transport import SimulatedPolarTransport
    from app.study_bindings import binding_options
    from app.assessment_adapters import source_attempt
    from app.components import is_component_active
    if not is_component_active('matb-physiology'): pytest.skip('Assigned H10 acquisition runs in auto profile.')
    async def exercise():
        transport=SimulatedPolarTransport(); manager=PolarCaptureManager(engine=engine,artifact_root=tmp_path,transport=transport)
        await manager.startup()
        token,_=(await manager.scan(.25))[0];await manager.connect(token)
        with Session(engine) as db:
            config=binding_options(db)['physiology'][0]
            _,identities=assigned(db,'physiology',config,keys=['baseline','second'])
        for index,identity in enumerate(identities):
            with Session(engine) as db: occasion=db.get(AssessmentAttempt,identity).occasion_id
            capture,lease=manager.create_capture(participant_id='P01',session_kind='generic',session_id=occasion,settings=config['settings'],execution_purpose='study',attempt_id=identity)
            await manager.start_capture(capture.capture_id,lease)
            if index==0:
                transport.emit_hr(bytes.fromhex('16 3c 00 04')); await asyncio.sleep(.02)
                await manager.stop_capture(capture.capture_id,lease)
            else: await manager.shutdown()
            with Session(engine) as db:
                attempt=source_attempt(db,'polar_capture',capture.capture_id)
                assert attempt.id==identity
                assert attempt.acquisition_state==('finished' if index==0 else 'interrupted')
                assert attempt.finished_at is not None
    asyncio.run(exercise())


def test_native_interrupted_repeat_retains_distinct_rating_target(engine,tmp_path):
    from tests.test_openmatb_runtime import _manager
    from app.openmatb_schemas import CreateOpenMatbSession
    from app.openmatb_models import OpenMatbSuiteSession
    from app.assessment_service import create_attempt,transition
    from app.assessment_schemas import AttemptIn
    from app.assessment_adapters import source_attempt
    manager=_manager(engine,tmp_path)
    with Session(engine) as db: _,ids=assigned(db,'openmatb',native_binding(db))
    first=asyncio.run(manager.create_session(CreateOpenMatbSession(execution_purpose='study',participant_id='P01',visit_ordinal=1,attempt_id=ids[0],visual_profile_id='matb-fac-modern',visual_profile_version='1.0.0')))
    with Session(engine) as db:
        suite=db.get(OpenMatbSuiteSession,first.session.id);block=manager.records.begin(db,suite,'HIGH');db.commit();block_id=block.id
    # Durable startup recovery records unknown interruption, never a successful task.
    manager.records.recover()
    with Session(engine) as db:
        task=source_attempt(db,'openmatb_block_attempt',block_id)
        assert task.id==ids[0] and task.acquisition_state=='interrupted'
        previous_rating=source_attempt(db,'openmatb_block_attempt',block_id,'ratings')
        assert previous_rating.acquisition_state=='interrupted'
        repeated=create_attempt(db,task.occasion_id,AttemptIn(execution_purpose='study'),repeat_of=task.id,reason='Interrupted source retained');transition(db,repeated.id,'started');db.commit();repeat_id=repeated.id
        suite=db.get(OpenMatbSuiteSession,first.session.id);suite.lifecycle='INTERRUPTED';db.add(suite);db.commit()
    second=asyncio.run(manager.create_session(CreateOpenMatbSession(execution_purpose='study',participant_id='P01',visit_ordinal=1,attempt_id=repeat_id,visual_profile_id='matb-fac-modern',visual_profile_version='1.0.0')))
    with Session(engine) as db:
        suite=db.get(OpenMatbSuiteSession,second.session.id);block=manager.records.begin(db,suite,'HIGH');db.commit()
        assert source_attempt(db,'openmatb_block_attempt',block.id,'ratings').target_attempt_id==repeat_id


@pytest.mark.anyio
@pytest.mark.skipif(not __import__('app.components', fromlist=['is_component_active']).is_component_active('matb-liftoff'), reason='Assigned Liftoff integration runs under auto.')
async def test_liftoff_launch_uses_frozen_prerequisite_instead_of_legacy_grid(liftoff_client,engine,tmp_path):
    from app.components import is_component_active
    if not is_component_active('matb-liftoff'): pytest.skip('Optional Liftoff acquisition runs under auto.')
    from tests.test_liftoff_endpoints import create_payload
    from tests.test_openmatb_runtime import _manager
    from app.study_registry import template,create_draft,rehearse,freeze,activate,assign
    from app.assessment_service import create_attempt,transition
    from app.assessment_schemas import AttemptIn
    from app.study_admission import select_prerequisites
    from app.openmatb_schemas import CreateOpenMatbSession
    from app.openmatb_models import OpenMatbSuiteSession
    from app.models import Block
    client,manager=liftoff_client;manager.receiver.inject_valid_packets(20)
    native=_manager(engine,tmp_path/'native')
    body=create_payload()
    with Session(engine) as db:
        payload=template('pre-post-recovery');original=payload['study']['occasions'][0]
        native_spec={**original,'key':'native','instrument':'openmatb','config':native_binding(db),'condition_by_arm':{'A':'HIGH'}}
        rating={**original,'key':'rating','instrument':'questionnaire','order':2,'target_key':'native','config':dict(binding_id='MATB-FAC-WORKLOAD-1.0',input_mapping='browser-ratings',scoring='rtlx-mean-bedford')}
        flight={**original,'key':'flight','instrument':'liftoff','order':3,'prerequisite_keys':['native'],'config':dict(binding_id='liftoff-telemetry-all-v1',input_mapping='liftoff-telemetry-all-v1',configuration=body['configuration'],scoring='liftoff-current')}
        payload['study'].update(synthetic=False,occasions=[native_spec,rating,flight],enabled_instruments=['openmatb','questionnaire','liftoff'],rules=dict(preparation='Fixture',repeat='Fixture',interruption='Fixture'))
        payload['analysis']['outcomes'][0].update(metric='liftoff.performance',occasion_keys=['flight']);payload['analysis']['rules'].update(exclusions='Fixture',denominators='Fixture',qualification='Fixture',pooling='Fixture')
        draft=create_draft(db,fixture_policies(payload));r=rehearse(db,draft.id);v=freeze(db,draft.id,dict(actor='Dr Fixture',reason='Exact prerequisite fixture',sha256=draft.sha256,rehearsal_id=r.id));activate(db,v.id,actor='Dr Fixture',reason='Fixture');a=assign(db,v.id,'P01',1,'A',actor='Dr Fixture');occasions=json.loads(a.occasions_json)
        task=create_attempt(db,occasions['native'],AttemptIn(execution_purpose='study'));transition(db,task.id,'started');db.commit();task_id=task.id
    prepared=await native.create_session(CreateOpenMatbSession(execution_purpose='study',participant_id='P01',visit_ordinal=1,attempt_id=task_id,visual_profile_id='matb-fac-modern',visual_profile_version='1.0.0'))
    with Session(engine) as db:
        suite=db.get(OpenMatbSuiteSession,prepared.session.id);native.records.begin(db,suite,'HIGH');native.records.finish(db,suite,outcome='completed',csv=None);suite.lifecycle='FAILED';db.add(suite)
        # Genuine legacy grid is separate historical evidence and cannot satisfy the selected source.
        for index,level in enumerate(['LOW','MEDIUM','HIGH']): db.add(Block(visit_id=1,workload_level=level,source_csv_filename=level+'.csv',source_csv_sha256=str(index)*64,metrics_json='{}'))
        flight=create_attempt(db,occasions['flight'],AttemptIn(execution_purpose='study'));select_prerequisites(db,flight.id,{'native':task_id});transition(db,flight.id,'started');body['attempt_id']=flight.id;db.commit()
    # The legacy task_sequence is LIFTOFF_MATB; it must not suppress the frozen native prerequisite either.
    response=await client.post('/liftoff/sessions',json=body)
    assert response.status_code==409,response.text
    assert response.json()['detail']['code']=='assigned_matb_first'


@pytest.mark.anyio
@pytest.mark.skipif(not __import__('app.components', fromlist=['is_component_active']).is_component_active('matb-liftoff'), reason='Assigned Liftoff integration runs under auto.')
async def test_liftoff_launch_does_not_invent_legacy_prerequisite(liftoff_client,engine):
    from app.components import is_component_active
    if not is_component_active('matb-liftoff'): pytest.skip('Optional Liftoff acquisition runs under auto.')
    from tests.test_liftoff_endpoints import create_payload
    from tests.study_fixtures import liftoff_payload
    client,manager=liftoff_client;manager.receiver.inject_valid_packets(20)
    from app.study_models import StudyParticipantContext
    with Session(engine) as db:
        db.add(Participant(id='P02',enrollment_date=date(2026,9,10)));db.flush()
        db.add(Visit(participant_id='P02',visit_ordinal=1,scheduled_day=0))
        db.add(StudyParticipantContext(participant_id='P02',protocol_id='astra-2026',task_sequence='MATB_LIFTOFF',prior_fpv_hours=0,gaming_hours_per_week=0));db.commit()
    body=liftoff_payload(manager,{**create_payload(),'participant_id':'P02'})
    response=await client.post('/liftoff/sessions',json=body)
    assert response.status_code==201,response.text
