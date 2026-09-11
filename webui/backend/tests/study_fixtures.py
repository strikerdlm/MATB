"""Explicit real-registry fixtures for pre-assignment endpoint regression cases.

No admission helper is patched. Every supplied study attempt belongs to a validated,
rehearsed, named/frozen, activated version and materialized assignment.
"""
from tests.study_policy_fixtures import fixture_policies
from copy import deepcopy


def provision_browser(client, participant='P01'):
    cache=getattr(client,'study_fixture_assignments',{})
    if participant in cache:return cache[participant]
    template=client.get('/study/templates/longitudinal').json()
    bindings=client.get('/study/bindings').json()
    visits=client.get(f'/participants/{participant}/visits').json()
    if not isinstance(visits,list):return {}
    occasions=[]
    original=template['study']['occasions'][0]
    for visit in visits:
        ordinal=visit['visit_ordinal']
        for instrument,count in [('pvt',4),('screen',3), *([('physiology',1)] if 'physiology' in bindings else [])]:
            for index in range(count):
                config=bindings[instrument][0] if instrument!='questionnaire' else dict(binding_id='MATB-FAC-WORKLOAD-1.0',input_mapping='browser-ratings',scoring='rtlx-mean-bedford')
                occasions.append({**original,'key':f'{instrument}_v{ordinal}_{index+1}','visit_ordinal':ordinal,'instrument':instrument,'phase':'baseline','order':len(occasions)+1,'config':config,'condition_by_arm':{'A':'rest'},'target_key':f'pvt_v{ordinal}_1' if instrument=='questionnaire' else None})
    template['study'].update(synthetic=False,title='Explicit endpoint regression fixture',occasions=occasions,enabled_instruments=sorted({o['instrument'] for o in occasions}),rules=dict(preparation='Review the fixed instructions',repeat='Retain explicit reasoned repeats',interruption='Record actual cause'))
    template['analysis']['outcomes'][0]['occasion_keys']=['pvt_v1_1']
    template['analysis']['rules'].update(exclusions='Report all retained observations',denominators='All assigned participants',qualification='Report timing evidence',pooling='Keep version strata separate')
    def post(path,body):
        response=client.post(path,json=body);assert response.status_code in {200,201},response.text;return response.json()
    draft=post('/study/drafts',fixture_policies(template));rehearsal=post(f"/study/drafts/{draft['id']}/rehearse",{})
    frozen=post(f"/study/drafts/{draft['id']}/freeze",dict(actor='Dr Regression',reason='Authored fixture rules',sha256=draft['sha256'],rehearsal_id=rehearsal['id']))
    post(f"/study/versions/{frozen['id']}/activate",dict(actor='Dr Regression',reason='Fixture collection'))
    result={}
    for visit in visits:
        row=post(f"/study/versions/{frozen['id']}/assign",dict(actor='Dr Regression',participant_id=participant,visit_id=visit['id'],arm='A'))
        import json
        result[visit['id']]=json.loads(row['occasions_json'])
    cache[participant]=result;client.study_fixture_assignments=cache
    return result


def assigned_occasion(client,instrument='pvt',*,participant='P01',visit_id=None,order=None,**_context):
    if instrument == 'questionnaire':
        # Generic questionnaire lifecycle contract, outside scientific assignment.
        visit_id=visit_id or client.get(f'/participants/{participant}/visits').json()[0]['id']
        response=client.post('/assessments/occasions',json=dict(participant_id=participant,visit_id=visit_id,instrument='questionnaire',phase='practice',order=1))
        assert response.status_code==201,response.text
        return response.json()
    if instrument == 'physiology':
        from app.components import is_component_active
        if not is_component_active('matb-physiology'):
            import pytest
            pytest.skip('Assigned H10 integration runs in the auto component profile.')
    assigned=provision_browser(client,participant)
    visit_id=visit_id or next(iter(assigned))
    candidates=[value for key,value in assigned[visit_id].items() if key.startswith(instrument+'_')]
    if order: identity=candidates[order-1]
    else:
        identity=next((value for value in candidates if not client.get(f'/assessments/occasions/{value}/attempts').json()),candidates[0])
    return client.get(f'/assessments/occasions/{identity}').json()


def study_post(client,path,*,json,**kwargs):
    """Provide the missing prospective context in old PVT/screen scoring tests."""
    body=deepcopy(json)
    if body.get('execution_purpose')=='study' and not body.get('attempt_id') and body.get('participant_id'):
        participant=body['participant_id']
        exists=client.get(f'/participants/{participant}/visits')
        if exists.status_code==200:
            visits=exists.json();ordinal=body.get('visit_ordinal',1)
            visit=next((v for v in visits if v['visit_ordinal']==ordinal),None)
            if visit:
                instrument='pvt' if path=='/pvt' else 'screen'
                occasion=assigned_occasion(client,instrument,participant=participant,visit_id=visit['id'],order=1)
                attempts=client.get(f"/assessments/occasions/{occasion['id']}/attempts").json()
                if attempts:a=attempts[0]
                else:
                    response=client.post(f"/assessments/occasions/{occasion['id']}/attempts",json={'execution_purpose':'study'});assert response.status_code==201,response.text;a=response.json()
                    response=client.post(f"/assessments/attempts/{a['id']}/start");assert response.status_code==200,response.text
                body['attempt_id']=a['id']
    if body.get('execution_purpose')=='study':
        (body['payload'] if path=='/screen' else body).setdefault('locale','es-419')
    return client.post(path,json=body,**kwargs)


def native_request(engine, **body):
    from sqlmodel import Session
    from app.openmatb_schemas import CreateOpenMatbSession
    from tests.test_study_acquisition import assigned, native_binding
    from app.study_bindings import binding_options
    with Session(engine) as db:
        config=native_binding(db)
        if body.get('visual_theme'):
            visual_id=body.pop('visual_theme')
            config['visual']=next(v for v in binding_options(db)['openmatb']['visuals'] if v['id']==visual_id)
        _,ids=assigned(db,'openmatb',config)
    return CreateOpenMatbSession(**{**body,'attempt_id':ids[0],'visual_profile_id':config['visual']['id'],'visual_profile_version':config['visual']['version']})


def liftoff_payload(manager, body):
    from sqlmodel import Session
    from tests.test_study_acquisition import assigned
    with Session(manager.persistence.engine) as db:
        config=dict(binding_id='liftoff-telemetry-all-v1',input_mapping='liftoff-telemetry-all-v1',configuration=body['configuration'],scoring='liftoff-current')
        _,ids=assigned(db,'liftoff',config,participant=body['participant_id'])
    return {**body,'attempt_id':ids[0]}


def h10_arguments(engine, **body):
    from sqlmodel import Session
    from app.assessment_models import AssessmentAttempt
    from tests.test_study_acquisition import assigned
    config=dict(binding_id='polar-h10-pmd-v1',input_mapping='rr-ecg-acc',settings=body['settings'],scoring='raw-streams')
    with Session(engine) as db:
        _,ids=assigned(db,'physiology',config)
        occasion=db.get(AssessmentAttempt,ids[0]).occasion_id
    return {**body,'execution_purpose':'study','attempt_id':ids[0],'session_id':occasion}


def mission_request(engine, **body):
    cached=getattr(engine,'_test_mission_request',None)
    if cached is not None:return cached
    from pathlib import Path
    from sqlmodel import Session, select
    from app.models import Visit
    from app.study_registry import template,create_draft,rehearse,freeze,activate,assign
    from app.study_bindings import browser_binding
    from app.assessment_service import create_attempt,transition
    from app.assessment_schemas import AttemptIn
    from app.study_admission import select_prerequisites
    from app.simulation_schemas import CreateSimulationSession
    from matb_integration.suas.scenarios.loader import load_scenario
    from matb_integration.suas.scenarios.profiles import block_order_for_participant
    from tests.test_experiment_safety import full_pvt
    from app.routers.pvt import ingest_pvt,PvtAssessmentIn
    import json
    with Session(engine) as db:
        visit=db.exec(select(Visit).where(Visit.participant_id==body.get('participant_id','P01'),Visit.visit_ordinal==body.get('visit_ordinal',1))).one()
        payload=template('pre-post-recovery');original=payload['study']['occasions'][0]
        scenario_id=body.get('scenario_id','reference_area_search')
        loaded=load_scenario(Path(__file__).resolve().parents[3]/'scenarios'/'suas'/f'{scenario_id}.yaml')
        order='_'.join(v.value for v in block_order_for_participant(visit.participant_id))
        locale='en' if body.get('locale','en')=='en' else 'es-419'
        pvt={**original,'key':'pvt','visit_ordinal':visit.visit_ordinal,'locale':locale,'config':browser_binding('pvt')}
        mission={**original,'key':'mission','visit_ordinal':visit.visit_ordinal,'instrument':'suas','phase':'mission','order':2,'locale':locale,'prerequisite_keys':['pvt'],'condition_by_arm':{'A':order},'config':dict(binding_id='suas-protocol-v1',scenario=dict(id=scenario_id,sha256=loaded.sha256),presentation=body.get('presentation'),input_mapping='suas-default',scoring='suas-current',practice_included=True)}
        payload['study'].update(synthetic=False,occasions=[pvt,mission],enabled_instruments=['pvt','suas'],rules=dict(preparation='Review mission controls',repeat='Explicit retained repeats',interruption='Record actual cause'))
        payload['analysis']['outcomes'][0]['occasion_keys']=['pvt'];payload['analysis']['rules'].update(exclusions='Keep all evidence',denominators='All assigned participants',qualification='Report timing evidence',pooling='Separate versions')
        draft=create_draft(db,fixture_policies(payload));r=rehearse(db,draft.id);v=freeze(db,draft.id,dict(actor='Dr Regression',reason='Authored fixture',sha256=draft.sha256,rehearsal_id=r.id));activate(db,v.id,actor='Dr Regression',reason='Test collection');a=assign(db,v.id,visit.participant_id,visit.id,'A',actor='Dr Regression');occasions=json.loads(a.occasions_json)
        p=create_attempt(db,occasions['pvt'],AttemptIn(execution_purpose='study'));transition(db,p.id,'started');db.commit()
        ingest_pvt(PvtAssessmentIn.model_validate(full_pvt(attempt_id=p.id,participant_id=visit.participant_id,visit_ordinal=visit.visit_ordinal,locale=locale)),db)
        task=create_attempt(db,occasions['mission'],AttemptIn(execution_purpose='study'));select_prerequisites(db,task.id,{'pvt':p.id});transition(db,task.id,'started');db.commit();identity=task.id
    request=CreateSimulationSession(**{**body,'execution_purpose':'study','attempt_id':identity})
    engine._test_mission_request=request
    return request
