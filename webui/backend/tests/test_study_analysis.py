"""Frozen descriptive contract regressions, using isolated synthetic evidence only."""
import pytest
from app.study_analysis_rules import purpose_criterion, select_attempt, compare_configurations, aggregate


def history(initial='unknown', current='study', actor='Researcher'):
    first=dict(classification=initial,purpose='practice' if initial=='explicit' else 'study',actor='local:acquisition-request')
    last=dict(classification='retrospective',purpose=current,actor=actor,reason='Reviewed original records')
    return dict(history=[first,last],current=last)


def test_unknown_requires_named_history_and_plan_permission():
    assert not purpose_criterion(history(), False)['passed']
    assert purpose_criterion(history(), True)['passed']
    assert not purpose_criterion(history(actor='system:migration'), True)['passed']
    assert not purpose_criterion(history(initial='explicit'), True)['passed']
    assert not purpose_criterion(None, True)['passed']


def test_selection_is_prespecified_and_never_latest_fallback():
    attempts=[dict(id='a',ordinal=1,acquisition_state='finished'),dict(id='b',ordinal=2,acquisition_state='finished')]
    assert select_attempt(attempts,'explicit',None) is None
    assert select_attempt(attempts,'first_finished',None)['id']=='a'
    assert select_attempt(attempts,'latest_finished',None)['id']=='b'
    with pytest.raises(ValueError): select_attempt(attempts,'explicit','absent')


def test_unknown_config_is_not_equal_and_review_must_be_named():
    values=[dict(task='x',instructions=None),dict(task='x',instructions=None)]
    assert not compare_configurations(values,'identical_only',None)['passed']
    assert not compare_configurations(values,'explicit_review',dict(actor='system:migration',rationale='same',reference='record'))['passed']
    assert compare_configurations(values,'explicit_review',dict(actor='Dr Example',rationale='Declared comparison',reference='local-review:1'))['passed']


def test_aggregation_keeps_missing_denominator_and_paired_contrast():
    plan=dict(unit='participant',outcomes=[dict(key='before',summary='mean',occasion_keys=['a']),dict(key='after',summary='mean',occasion_keys=['b'])],contrasts=[dict(key='change',left_outcome='after',right_outcome='before',operation='difference')])
    rows=[dict(participant_id='p1',visit_id=1,attempt_id='1',occasion_key='a',denominator=True,values={'before':2}),dict(participant_id='p1',visit_id=1,attempt_id='2',occasion_key='b',denominator=True,values={'after':5}),dict(participant_id='p2',visit_id=1,attempt_id=None,occasion_key='b',denominator=True,values={})]
    result=aggregate(plan,rows,'exclude_outcome')
    assert result['outcomes']['after']['denominator']==2
    assert result['outcomes']['after']['observed']==1
    assert result['contrasts']['change']['values']=={'p1':3}
    assert result['contrasts']['change']['denominator']==2
    assert rows[-1]['values']=={}


@pytest.mark.parametrize('status',['FAIL','NOT_TESTED','PASS'])
def test_qualification_checks_actual_report_status_and_binding(status):
    from app.study_analysis_eligibility import qualification_criterion
    import json
    context=dict(software_versions=dict(acquisition_commit='commit'),presentation=dict(profile_id='profile'))
    capture=dict(manifest_sha256='sha',manifest_json=json.dumps(dict(source_commit='commit',profile_id='profile')))
    item=dict(record=dict(id='r',kind='physical_timing',assessment=dict(status=status),context=context,reviewer='Dr Reviewer',revocations=[]),binding=dict(context=context,capture_manifest_sha256='sha',context_source='reviewer_attestation',reviewer='Dr Binder',rationale='Exact station'))
    assert qualification_criterion([item],'physical_timing',capture)['passed']==(status=='PASS')
    item['record']['revocations']=[dict(reason='Withdrawn')]
    assert not qualification_criterion([item],'physical_timing',capture)['passed']
    item['record']['revocations']=[]; item['binding']['capture_manifest_sha256']='other'
    assert not qualification_criterion([item],'physical_timing',capture)['passed']


def test_execution_freezes_raw_values_denominators_and_survives_classification(engine,tmp_path):
    import json
    import zipfile
    from sqlmodel import Session
    from sqlalchemy import text
    from app.study_registry import activate,assign
    from app.assessment_service import create_attempt,transition
    from app.assessment_schemas import AttemptIn
    from app.routers.pvt import PvtAssessmentIn,ingest_pvt
    from app import study_analysis
    from app.study_analysis_models import StudyAnalysisArtifact
    from app.routers.study_analysis import export
    from app.purpose_service import classify_retrospectively
    from tests.test_study_registry import seed,frozen
    with Session(engine) as db:
        seed(db); version=frozen(db); activate(db,version.id,actor='Dr Example',reason='Synthetic test')
        assignment=assign(db,version.id,'R01',1,'A',actor='Dr Example'); occasion=json.loads(assignment.occasions_json)['pre']
        attempt=create_attempt(db,occasion,AttemptIn(execution_purpose='study')); transition(db,attempt.id,'started')
        ingest_pvt(PvtAssessmentIn(participant_id='R01',visit_ordinal=1,execution_purpose='study',attempt_id=attempt.id,kss_score=4,administered_at='2026-09-10T12:00:00Z',duration_ms=12000,locale='es-419',trials=[dict(index=0,wait_ms=2000,stimulus_at_ms=2000,response_at_ms=2300,rt_ms=300,outcome='response')]),db)
        request=dict(version_id=version.id,attempts={occasion:attempt.id},actor='Dr Example',reason='Synthetic descriptive run')
        preview=study_analysis.preview(db,request)
        assert len(preview['rows'])==3
        assert preview['rows'][0]['criteria']
        execution=study_analysis.execute(db,request); db.commit()
        original=execution.result_json
        assert json.loads(original)['outcomes']['primary']['values']=={'R01':300}
        classify_retrospectively(db,attempt.purpose_provenance_id,purpose='practice',reviewer='Dr Correction',reason='Review'); db.commit()
        reopened=study_analysis.read(db,execution.id)
        assert reopened['current_applicability']['changed']
        assert db.get(type(execution),execution.id).result_json==original
        with pytest.raises(Exception,match='immutable'):
            db.execute(text('UPDATE study_analysis_execution SET result_json=\'{}\''))
        db.rollback()
        archive=export(execution.id,db).body
        import io
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle: bundle.extractall(tmp_path/'bundle')
        # In-process verification still uses pinned artifact bytes and raw recalculation.
        import importlib.util
        spec=importlib.util.spec_from_file_location('offline_verify',tmp_path/'bundle/verify.py'); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        assert module.verify(tmp_path/'bundle')['status']=='reproduced'
        import os,subprocess,venv
        venv.EnvBuilder(with_pip=True,system_site_packages=False).create(tmp_path/'replay-venv')
        python=tmp_path/('replay-venv/Scripts/python.exe' if os.name=='nt' else 'replay-venv/bin/python'); clean_env={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','PYTHONHOME','VIRTUAL_ENV'}}
        installed=subprocess.run([str(python),'-I','-m','pip','install','--no-index','--find-links','wheels','-r','requirements.lock'],cwd=tmp_path/'bundle',env=clean_env,capture_output=True,text=True)
        assert installed.returncode==0,installed.stdout+installed.stderr
        replay=subprocess.run([str(python),'-I','verify.py','.'],cwd=tmp_path/'bundle',env=clean_env,capture_output=True,text=True)
        assert replay.returncode==0,replay.stdout+replay.stderr
        (tmp_path/'bundle/offline-proof.json').write_text(replay.stdout)

        assert (tmp_path/'bundle/figure.svg').read_text()==json.loads(original)['figure']


def test_hcf_growth_preserves_old_values_and_fingerprint(engine):
    from sqlmodel import Session
    from app.hcf_derivations import derive
    import json
    references=[dict(participant_id=f'p{i}',attempt_id=f'a{i}',screen_id=str(i),raw_sha256=str(i),scoring_sha256=str(i),scores={'simple_rt':{'valid':True,'median_ms':value}}) for i,value in enumerate([200,300,400])]
    with Session(engine) as db:
        old=derive(db,references); original=old.snapshot_json
        assert derive(db,list(reversed(references))).id==old.id
        new=derive(db,[*references,dict(participant_id='p3',attempt_id='a3',screen_id='3',raw_sha256='3',scoring_sha256='3',scores={'simple_rt':{'valid':True,'median_ms':900}})])
        assert new.id!=old.id and db.get(type(old),old.id).snapshot_json==original
        assert json.loads(new.snapshot_json)['values']['p0']['value']!=json.loads(original)['values']['p0']['value']
        with pytest.raises(ValueError,match='exactly one'): derive(db,[*references,references[0]])


@pytest.mark.parametrize('denominator,expected',[('assigned',False),('finished',True)])
def test_historical_archive_mapping_preserves_identity_and_unknown_configuration(engine,denominator,expected):
    import json
    from sqlmodel import Session
    from app.models import PvtAssessment,ArchivedAssessment
    from app.assessment_adapters import attach_source
    from app.assessment_models import AssessmentOccasionClassification
    from app.purpose_service import historical_association_identity,classify_retrospectively
    from app.study_registry import create_draft,rehearse,freeze
    from app import study_analysis
    from tests.test_study_registry import seed,authored
    with Session(engine) as db:
        seed(db); payload=json.loads(authored(db).payload_json)
        payload['analysis']['rules']['historical_unknowns']='reviewed_classification_required'
        payload['analysis']['eligibility_policy'].update(incomplete_denominator=denominator,configuration_pooling='explicit_review',pooling_review='Review historic configuration unknowns',pooling_attestation=dict(actor='Dr Reviewer',rationale='Historical descriptive comparison, unknown presentation retained',reference='local-review:historic'))
        draft=create_draft(db,payload); rehearsal=rehearse(db,draft.id)
        version=freeze(db,draft.id,dict(actor='Dr Reviewer',reason='Historical analysis plan',sha256=draft.sha256,rehearsal_id=rehearsal.id))
        raw=PvtAssessment(id=77,participant_id='R01',visit_id=1,kss_score=3,administered_at='2025-01-01T00:00:00Z',duration_ms=12000,protocol_valid=False,pvt_version=2,raw_trials_json=json.dumps([dict(index=0,wait_ms=2000,stimulus_at_ms=2000,response_at_ms=2300,rt_ms=300,outcome='response')]),metrics_json='{}',timing_evidence_json='{}')
        archive=ArchivedAssessment(experiment_id='pvt',participant_id='R01',original_id=77,snapshot_json=raw.model_dump_json(),reason='Preserved earlier acquisition')
        db.add(archive);db.flush()
        archive.purpose_provenance_id=historical_association_identity(db,source_table='archived_assessment',source_id=archive.id,purpose='study',snapshot=archive.model_dump(mode='json'));db.add(archive);db.flush()
        attempt=attach_source(db,'archived_assessment',archive.model_dump(mode='json'),historical=True)
        attempt.acquisition_state='finished';db.add(attempt);db.flush()
        classify_retrospectively(db,attempt.purpose_provenance_id,purpose='study',reviewer='Dr Historian',reason='Original unknown intent reviewed')
        db.add(AssessmentOccasionClassification(occasion_id=attempt.occasion_id,visit_id=1,phase='pre',order=1,condition='baseline',version_ref=version.id,reviewer='Dr Historian',reason='Retrospective association for this analysis'))
        # Original integer reused by a different stored source must never replace the archive.
        raw.raw_trials_json=raw.raw_trials_json.replace('2300','2900').replace('300,','900,').replace('"response"','"lapse"');db.add(raw);db.flush()
        preview=study_analysis.preview(db,dict(version_id=version.id,attempts={attempt.occasion_id:attempt.id}))
        row=preview['rows'][0]
        assert row['historical'] and row['assignment'] is None and row['configuration'] is None
        assert row['criteria']['purpose']['passed']
        assert row['criteria']['preparation']['passed'] is False
        assert row['denominator'] is expected
        assert row['eligible'] is expected
        assert row['source']['records'][0]['link']['source_table']=='archived_assessment'
        assert row['calculations']['primary']['value']==300


def test_integrated_independent_instruments_and_prespecified_condition_difference(engine):
    import json
    from sqlmodel import Session
    from tests.test_study_registry import seed,authored
    from app.study_registry import create_draft,rehearse,freeze,activate,assign
    from app.study_bindings import browser_binding
    from app.assessment_service import create_attempt,transition
    from app.assessment_schemas import AttemptIn
    from app.routers.pvt import PvtAssessmentIn,ingest_pvt
    from app.routers.screen import ingest_screen
    from tests.test_screen_endpoint import _payload
    from app.study_analysis import preview,execute
    with Session(engine) as db:
        seed(db); payload=json.loads(authored(db).payload_json)
        payload['study']['enabled_instruments']=['pvt','screen']
        payload['study']['occasions'][1]['condition_by_arm']={'A':'post-load'}
        payload['study']['occasions'][2].update(instrument='screen',config=browser_binding('screen'))
        payload['analysis']['outcomes']=[dict(key='before',metric='pvt.median_rt_ms',units='ms',occasion_keys=['pre'],summary='individual'),dict(key='after',metric='pvt.median_rt_ms',units='ms',occasion_keys=['post'],summary='individual'),dict(key='screen',metric='screen.simple_rt',units='ms',occasion_keys=['recovery'],summary='individual')]
        payload['analysis']['contrasts']=[dict(key='change',left_outcome='after',right_outcome='before',operation='difference')]
        draft=create_draft(db,payload); rehearsal=rehearse(db,draft.id); version=freeze(db,draft.id,dict(actor='Dr Example',reason='Independent instrument fixture',sha256=draft.sha256,rehearsal_id=rehearsal.id))
        activate(db,version.id,actor='Dr Example',reason='Fixture');assignment=assign(db,version.id,'R01',1,'A',actor='Dr Example'); occasions=json.loads(assignment.occasions_json); selections={}
        for key,rt in [('pre',300),('post',400),('recovery',320)]:
            attempt=create_attempt(db,occasions[key],AttemptIn(execution_purpose='study'));transition(db,attempt.id,'started');selections[occasions[key]]=attempt.id
            if key=='recovery': ingest_screen(participant_id='R01',payload={**_payload(simple=rt),'locale':'es-419'},overwrite=False,attempt_id=attempt.id,execution_purpose='study',session=db)
            else: ingest_pvt(PvtAssessmentIn(participant_id='R01',visit_ordinal=1,execution_purpose='study',attempt_id=attempt.id,kss_score=3,administered_at='2026-09-10T00:00:00Z',duration_ms=12000,locale='es-419',trials=[dict(index=0,wait_ms=2000,stimulus_at_ms=2000,response_at_ms=2000+rt,rt_ms=rt,outcome='response')]),db)
        request=dict(version_id=version.id,attempts=selections,actor='Dr Example',reason='Independent outcomes')
        viewed=preview(db,request)
        assert viewed['comparisons']['contrast:change']['passed']
        assert all(c['passed'] for c in viewed['comparisons'].values())
        result=json.loads(execute(db,request).result_json)
        assert result['contrasts']['change']['values']=={'R01':100}
        assert result['outcomes']['screen']['observed']==1
        assert result['inferential_tests']==[] and result['automatic_model'] is None


def test_complete_case_excludes_a_unit_missing_one_pooled_occasion():
    plan=dict(unit='participant',outcomes=[dict(key='response',summary='mean',occasion_keys=['a','b'])],contrasts=[])
    rows=[dict(participant_id='p',visit_id=1,attempt_id='1',occasion_key='a',denominator=True,values={'response':3}),dict(participant_id='p',visit_id=1,attempt_id=None,occasion_key='b',denominator=True,values={})]
    result=aggregate(plan,rows,'complete_case')
    assert result['outcomes']['response']['denominator']==1
    assert result['outcomes']['response']['observed']==0


def test_frozen_job_input_does_not_reselect_after_later_changes(engine,monkeypatch):
    from sqlmodel import Session
    from tests.test_study_registry import seed,frozen
    from app.study_registry import activate,assign
    from app.study_analysis import freeze_input,execute_frozen
    from app.hcf_derivations import fingerprint
    import json
    with Session(engine) as db:
        seed(db);version=frozen(db);activate(db,version.id,actor='Dr Example',reason='Fixture');assign(db,version.id,'R01',1,'A',actor='Dr Example')
        request=dict(version_id=version.id,actor='Dr Example',reason='Queue fixed denominator',attempts={})
        frozen_input=freeze_input(db,request); original=frozen_input.snapshot_json
        from app.assessment_service import create_attempt
        from app.assessment_schemas import AttemptIn
        occasion=json.loads(original)['rows'][0]['occasion_id']
        create_attempt(db,occasion,AttemptIn(execution_purpose='study'))
        result=execute_frozen(db,frozen_input.id)
        assert json.loads(result.snapshot_json)['rows'][0]['attempts']==[]
        assert json.loads(result.snapshot_json)['frozen_input_id']==frozen_input.id
        assert frozen_input.snapshot_json==original
        assert json.loads(result.result_json)['outcomes']['primary']['denominator']==1
        from fastapi import HTTPException
        import app.study_analysis_bundle as bundle
        monkeypatch.setattr(bundle,'dependency_versions',lambda instruments: {})
        with pytest.raises(HTTPException,match='dependency') as changed:
            execute_frozen(db,frozen_input.id)
        assert changed.value.status_code==409
        assert frozen_input.snapshot_json==original
