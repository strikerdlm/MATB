"""Measured preparation uses actual persisted observations, never self-attested passes."""
import json
import pytest
from fastapi import HTTPException
from sqlmodel import Session
from tests.test_study_registry import seed, authored


def prepared_assignment(db, *, later=False):
    from app.study_registry import create_draft, rehearse, freeze, activate, assign
    payload = json.loads(authored(db).payload_json)
    requirement = payload['study']['preparation_policy'][0]
    requirement.update(demonstration_required=True, acknowledgement_required=True,
        comprehension=[dict(id='understanding-v1', metric='comprehension.correct_fraction', comparator='eq', threshold=1, rationale='Software fixture criterion')],
        practice=[dict(id='practice-v1', metric='pvt.median_rt_ms', comparator='lte', threshold=400, rationale='Software fixture criterion')])
    if later: requirement['placement'] = 'prescribed_later'
    draft = create_draft(db, payload); rehearsal = rehearse(db, draft.id)
    version = freeze(db, draft.id, dict(actor='Dr Fixture', reason='Software fixture only', sha256=draft.sha256, rehearsal_id=rehearsal.id))
    activate(db, version.id, actor='Dr Fixture', reason='Fixture'); return assign(db, version.id, 'R01', 1, 'A', actor='Dr Fixture')


def test_stages_practice_failures_and_repeats_are_retained(engine):
    from app.study_preparation import begin, record_stage, preparation_view, finish_practice, begin_practice
    from app.assessment_service import transition
    from app.routers.pvt import ingest_pvt, PvtAssessmentIn
    with Session(engine) as db:
        seed(db); assignment = prepared_assignment(db)
        run = begin(db, assignment.id, 'pre')
        assert preparation_view(db, run.id)['next_action'] == 'demonstration'
        with pytest.raises(HTTPException): record_stage(db, run.id, 'acknowledgement', {})
        record_stage(db, run.id, 'demonstration', {})
        record_stage(db, run.id, 'acknowledgement', {})
        record_stage(db, run.id, 'comprehension', {'response': 'wrong'})
        assert preparation_view(db, run.id)['next_action'] == 'comprehension'
        record_stage(db, run.id, 'comprehension', {'response': 'SPACE'})
        assert preparation_view(db, run.id)['next_action'] == 'practice'
        with pytest.raises(HTTPException): record_stage(db, run.id, 'practice', {'passed': True})
        for rt in [600, 300]:
            attempt = begin_practice(db, run.id)
            transition(db, attempt.id, 'started')
            body = PvtAssessmentIn(participant_id='R01', visit_ordinal=1, execution_purpose='practice', attempt_id=attempt.id,
                administered_at='2026-09-10T12:00:00Z', duration_ms=12000, fast_mode=True, kss_score=3, locale='es-419',
                trials=[dict(index=0, wait_ms=2000, stimulus_at_ms=2000, response_at_ms=2000+rt, rt_ms=rt, outcome='lapse' if rt >= 500 else 'response')])
            ingest_pvt(body, db)
            finish_practice(db, run.id, attempt.id)
        view = preparation_view(db, run.id)
        assert view['next_action'] == 'ready'
        assert [e['passed'] for e in view['events'] if e['stage']=='practice'] == [False, True]
        assert len([e for e in view['events'] if e['stage']=='comprehension']) == 2
        assert view['events'][-1]['observations']['pvt.median_rt_ms'] == 300
        assert view['events'][-1]['duration_seconds'] == 12


def test_gate_requires_exact_version_mapping_and_completed_measurement(engine):
    from app.study_preparation import begin, preparation_view, require_preparation
    from app.study_admission import for_occasion
    with Session(engine) as db:
        seed(db); assignment = prepared_assignment(db)
        context = for_occasion(db, json.loads(assignment.occasions_json)['pre'])
        with pytest.raises(HTTPException) as error: require_preparation(db, context)
        assert error.value.detail['code'] == 'study_preparation_required'
        run = begin(db, assignment.id, 'pre')
        assert preparation_view(db, run.id)['presentation']['input_mapping'] == 'space'
        from app.study_preparation import resolve_presentation
        changed = {**context, 'config': {**context['config'], 'input_mapping':'mouse'}}
        with pytest.raises(HTTPException): resolve_presentation(db, changed)


def test_exposure_preserves_unknown_historical_times(engine):
    from app.study_preparation import exposure_history
    from app.assessment_models import AssessmentOccasion, AssessmentAttempt
    with Session(engine) as db:
        seed(db)
        occasion = AssessmentOccasion(participant_id='R01', instrument='pvt', origin='legacy')
        db.add(occasion); db.flush()
        db.add(AssessmentAttempt(occasion_id=occasion.id, ordinal=1, execution_purpose='practice', created_at=None, acquisition_state='unknown')); db.flush()
        row = exposure_history(db, 'R01')[0]
        assert row['duration_seconds'] is None and row['started_at'] is None
        assert row['version_id'] is None and row['config_sha256'] is None
        from app.assessment_service import attempt_view
        historical = db.get(AssessmentAttempt, row['attempt_id'])
        assert attempt_view(db, historical)['preparation_admission'] is None


@pytest.mark.anyio
@pytest.mark.parametrize("ordinary_path", ["create", "persisted_start"])
async def test_native_preflight_retains_runtime_identity_and_blocks_release_until_exact_comprehension(engine, tmp_path, monkeypatch, ordinary_path):
    import asyncio
    from types import SimpleNamespace
    from tests.test_openmatb_runtime import _manager
    from tests.test_study_acquisition import assigned, native_binding
    from app.openmatb_schemas import CreateOpenMatbSession
    from app.openmatb_models import OpenMatbSuiteSession, OpenMatbBlockAttempt
    from app.assessment_models import AssessmentAttempt
    from app.study_registry_models import StudyNativePreflight
    from app.study_preparation import begin, bind_native_presentation, record_stage, preparation_view
    from sqlmodel import select
    manager = _manager(engine, tmp_path)
    monkeypatch.setattr(manager, 'readiness', lambda: SimpleNamespace(ready=True))
    monkeypatch.setattr(manager, 'schedule_evidence_processing', lambda: None)
    def policies(payload):
        payload['study']['preparation_policy'][0].update(acknowledgement_required=True,
            comprehension=[dict(id='native-recognition-v1',rationale='Software-only fixture',metric='comprehension.correct_fraction',comparator='eq',threshold=1)])
    with Session(engine) as db:
        assignment, attempts = assigned(db,'openmatb',native_binding(db),modify=policies,start=False)
        run = begin(db,assignment,'task');run_id=run.id;db.commit()
    snapshot = dict(schema_version='native-preflight-v1', enabled_tasks=['communications'], controller=None, issues=[],
        mapping={'communications':{'keys':{'validateresponse':'ENTER'},'owncallsign':'ABC123'}},sha256='fixture-snapshot')
    process_commands=[]
    class Process:
        def __init__(self,csv):
            self.pid=23456;self.returncode=None;self.stdout=asyncio.StreamReader();self.stderr=asyncio.StreamReader();self.done=asyncio.Event();self.stdin=self
            self.stdout.feed_data((json.dumps(dict(event='ready',session_csv=str(csv),preflight=snapshot))+'\n').encode())
        def write(self,data):
            command=json.loads(data);process_commands.append(command)
            if command['command']=='release_preflight': self.stdout.feed_data(b'{"event":"preflight_released"}\n')
            if command['command']=='abort': self.terminate()
        async def drain(self): pass
        async def wait(self): await self.done.wait();return self.returncode
        def terminate(self):
            if self.returncode is None:self.returncode=0;self.stdout.feed_eof();self.stderr.feed_eof();self.done.set()
        kill=terminate
    async def spawn(*command,**kwargs):
        assert kwargs['env']['MATB_PREPARATION_HOLD']=='1'
        csv=__import__('pathlib').Path(command[command.index('--session-dir')+1])/'1.csv'
        process=Process(csv)
        if hasattr(__import__('os'),'killpg'):monkeypatch.setattr('app.openmatb_runtime.os.killpg',lambda *_:process.terminate())
        return process
    monkeypatch.setattr('app.openmatb_runtime.asyncio.create_subprocess_exec',spawn)
    monkeypatch.setattr('app.openmatb_runtime._WindowsJob',lambda _:None)
    prepared=await manager.create_session(CreateOpenMatbSession(participant_id='P01',visit_ordinal=1,execution_purpose='study',attempt_id=attempts[0],preparation_only=True,visual_profile_id='matb-fac-modern',visual_profile_version='1.0.0'))
    held=await manager.start_block(prepared.session.id,prepared.controller_lease,preparation_only=True)
    assert held.lifecycle=='PREFLIGHT_HELD' and held.started_at is None
    with Session(engine) as db:
        assert db.get(AssessmentAttempt,attempts[0]).acquisition_state=='created'
        assert not db.exec(select(OpenMatbBlockAttempt)).all()
        retained=db.get(StudyNativePreflight,held.id)
        original_csv=retained.session_csv;original_block=retained.block_instance_id
        bind_native_presentation(db,run_id,held.id);db.commit()
    with pytest.raises(HTTPException): await manager.start_block(held.id,prepared.controller_lease)
    assert process_commands==[]
    with Session(engine) as db:
        record_stage(db,run_id,'acknowledgement',{})
        record_stage(db,run_id,'comprehension',{'comm-validateresponse':'ENTER','callsign':'WRONG'})
        assert preparation_view(db,run_id)['next_action']=='comprehension'
        record_stage(db,run_id,'comprehension',{'comm-validateresponse':'ENTER','callsign':'ABC123'});db.commit()
    # Software fixture for a prior prepared source / a persisted ordinary READY source.
    # Matching competence is already ready; a new callsign still requires its own hold.
    with Session(engine) as db:
        from app.study_preparation import require_preparation, assignment_context
        require_preparation(db, assignment_context(db, assignment, 'task'))
        suite = db.get(OpenMatbSuiteSession, held.id)
        suite.lifecycle = 'COMPLETE' if ordinary_path == 'create' else 'READY'
        selected = db.get(AssessmentAttempt, attempts[0])
        selected.acquisition_state = 'finished' if ordinary_path == 'create' else 'started'
        db.add(suite); db.add(selected); db.flush()
        ordinary_attempt_id = selected.id
        if ordinary_path == 'create':
            from app.assessment_service import create_attempt, transition
            from app.assessment_schemas import AttemptIn
            repeated = create_attempt(db, selected.occasion_id, AttemptIn(execution_purpose='study'),
                repeat_of=selected.id, reason='Explicit software regression repeat after matching preparation')
            # Persisted old caller state: new code must not admit this ordinary source.
            repeated.acquisition_state = 'started'; db.add(repeated); db.flush()
            ordinary_attempt_id = repeated.id
        db.commit()
    with pytest.raises(HTTPException) as bypass:
        if ordinary_path == 'create':
            await manager.create_session(CreateOpenMatbSession(participant_id='P01', visit_ordinal=1,
                execution_purpose='study', attempt_id=ordinary_attempt_id, visual_profile_id='matb-fac-modern', visual_profile_version='1.0.0'))
        else:
            await manager.start_block(held.id, prepared.controller_lease)
    assert bypass.value.detail['code'] == 'study_native_preflight_required'
    assert bypass.value.detail['assignment_url'] == f'/study/participant?assignment={assignment}'
    assert process_commands == []
    with Session(engine) as db:
        suite = db.get(OpenMatbSuiteSession, held.id); suite.lifecycle = 'PREFLIGHT_HELD'
        if ordinary_path == 'create':
            repeated = db.get(AssessmentAttempt, ordinary_attempt_id); repeated.acquisition_state = 'interrupted'; db.add(repeated)
        selected = db.get(AssessmentAttempt, attempts[0]); selected.acquisition_state = 'created'
        db.add(suite); db.add(selected); db.commit()
    with Session(engine) as db:
        from app.assessment_service import transition
        from app.study_registry_models import StudyPreparationAdmission
        with pytest.raises(HTTPException) as direct_start:
            transition(db, attempts[0], 'started')
        assert direct_start.value.detail['code'] == 'study_native_preflight_required'
        assert db.get(StudyPreparationAdmission, attempts[0]) is None
    running=await manager.start_block(held.id,prepared.controller_lease)
    assert running.lifecycle=='RUNNING'
    assert process_commands==[dict(command='release_preflight',snapshot_sha256='fixture-snapshot')]
    with Session(engine) as db:
        block=db.get(OpenMatbBlockAttempt,original_block)
        assert block.session_csv==original_csv
        assert db.get(AssessmentAttempt,attempts[0]).acquisition_state=='started'
        admission = json.loads(db.get(StudyPreparationAdmission, attempts[0]).snapshot_json)
        assert admission['requirements'][0]['preparation_id'] == run_id
        assert any(event['stage'] == 'native_presentation' for event in admission['requirements'][0]['event_frontier'])
    await manager.abort(held.id,prepared.controller_lease,'operator_abort')


def test_preparation_mutations_cannot_follow_mapping_change_but_history_remains_readable(engine, monkeypatch):
    from app.study_preparation import begin, record_stage, preparation_view, practice_context
    from app import study_bindings
    with Session(engine) as db:
        seed(db); assignment=prepared_assignment(db); run=begin(db,assignment.id,'pre')
        monkeypatch.setattr(study_bindings,'implementation_binding',lambda _: 'different-implementation')
        with pytest.raises(HTTPException): record_stage(db,run.id,'demonstration',{})
        assert preparation_view(db,run.id)['presentation']['implementation_sha256'] != 'different-implementation'


def test_preparation_evidence_is_immutable_and_disabled_items_are_not_accepted(engine):
    from app.study_preparation import begin, record_stage
    from sqlalchemy import text
    with Session(engine) as db:
        seed(db); assignment=prepared_assignment(db);run=begin(db,assignment.id,'pre')
        record_stage(db,run.id,'demonstration',{});record_stage(db,run.id,'acknowledgement',{})
        with pytest.raises(HTTPException):record_stage(db,run.id,'comprehension',{'response':'SPACE','disabled-track':'yes'})
        db.commit()
    with engine.begin() as conn:
        with pytest.raises(Exception,match='immutable'): conn.execute(text('DELETE FROM study_preparation_event'))


def test_prior_practice_reuse_is_explicit_exact_and_never_later_training(engine):
    from app.study_preparation import begin, record_stage, begin_practice, finish_practice, reuse_practice, preparation_view
    from app.assessment_service import transition
    from app.routers.pvt import ingest_pvt, PvtAssessmentIn
    with Session(engine) as db:
        seed(db); assignment = prepared_assignment(db)
        original = begin(db, assignment.id, 'pre')
        def understand(run):
            record_stage(db, run.id, 'demonstration', {})
            record_stage(db, run.id, 'acknowledgement', {})
            record_stage(db, run.id, 'comprehension', {'response':'SPACE'})
        understand(original)
        attempt = begin_practice(db, original.id); transition(db, attempt.id, 'started')
        ingest_pvt(PvtAssessmentIn(participant_id='R01', visit_ordinal=1, execution_purpose='practice', attempt_id=attempt.id,
            administered_at='2026-09-10T12:00:00Z', duration_ms=12000, fast_mode=True, kss_score=3, locale='es-419',
            trials=[dict(index=0,wait_ms=2000,stimulus_at_ms=2000,response_at_ms=2300,rt_ms=300,outcome='response')]), db)
        evidence = finish_practice(db, original.id, attempt.id)
        current = begin(db, assignment.id, 'pre'); understand(current)
        assert preparation_view(db,current.id)['next_action'] == 'practice'
        reuse_practice(db,current.id,evidence.id,'Dr Fixture','Same frozen criterion and mapping; no additional practice prescribed')
        view = preparation_view(db,current.id)
        assert view['next_action']=='ready'
        assert view['practice_attempt_ids']==[]
        assert view['events'][-1]['reused_from_event_id']==evidence.id
        assert view['events'][-1]['attempt_id']==attempt.id
        with pytest.raises(HTTPException): reuse_practice(db,current.id,evidence.id,'Dr Fixture','repeat')


def test_native_practice_grades_reconciled_exact_source_and_retains_failed_exposure(engine,tmp_path,monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from tests.test_openmatb_runtime import _manager
    from tests.test_study_acquisition import assigned,native_binding
    from app.study_preparation import begin,begin_practice,finish_practice,preparation_view,exposure_history
    from app.assessment_service import transition
    from app.openmatb_schemas import CreateOpenMatbSession
    from app.openmatb_models import OpenMatbSuiteSession
    from app.study_preflight import retain_snapshot
    from app.evidence_service import ingest_evidence,run_derivation
    from matb_integration.evidence.reference import synthetic_capture
    from matb_integration.evidence.writer import EvidenceWriter
    manager=_manager(engine,tmp_path)
    def policy(payload):
        payload['study']['preparation_policy'][0]['practice']=[dict(id='actual-hit-rate',rationale='Software-only fixture',metric='sysmon.hit_rate',comparator='eq',threshold=1)]
    with Session(engine) as db:
        assignment,_=assigned(db,'openmatb',native_binding(db),modify=policy,start=False)
        preparation=begin(db,assignment,'task'); run_id=preparation.id;db.commit()
        from app.study_preparation import require_preflight_practice, assignment_context
        with pytest.raises(HTTPException): require_preflight_practice(db, assignment_context(db,assignment,'task'))
    for succeeds in [False,True]:
        with Session(engine) as db:
            attempt=begin_practice(db,run_id);transition(db,attempt.id,'started');attempt_id=attempt.id;db.commit()
        prepared=asyncio.run(manager.create_session(CreateOpenMatbSession(participant_id='P01',visit_ordinal=1,execution_purpose='practice',attempt_id=attempt_id,visual_profile_id='matb-fac-modern',visual_profile_version='1.0.0')))
        with Session(engine) as db:
            suite=db.get(OpenMatbSuiteSession,prepared.session.id)
            block=manager.records.begin(db,suite,'PRACTICE')
            snapshot=dict(enabled_tasks=['sysmon'],mapping={'sysmon':{'lights':{'1':{'key':'F5'}},'scales':{}}},controller=None,issues=[] if succeeds else ['required_controller_unavailable'],sha256='fixture')
            retain_snapshot(db,suite,SimpleNamespace(block_instance_id=block.id,session_csv=tmp_path/'original.csv',preflight_snapshot=snapshot))
            suite.lifecycle='COMPLETE' if succeeds else 'FAILED';block.task_status='completed' if succeeds else 'failed';block.evidence_status='complete'
            db.add(suite);db.add(block);db.commit()
            if succeeds:
                original=EvidenceWriter.__init__
                def bound(writer,stem,session_id,context,identity):
                    original(writer,stem,session_id,context,{**identity,'block_instance_id':block.id,'parent_session_id':suite.id})
                with monkeypatch.context() as patch:
                    patch.setattr(EvidenceWriter,'__init__',bound)
                    capture,_=ingest_evidence(db,synthetic_capture(tmp_path/'evidence',tasks=('sysmon',),purpose='practice'))
                run_derivation(db,capture)
                block.capture_id=capture;db.add(block);db.commit()
            event=finish_practice(db,run_id,attempt_id);db.commit()
            assert event.passed is succeeds
            if succeeds:
                payload=json.loads(event.payload_json)
                assert payload['observations']['sysmon.hit_rate']==1
                assert payload['source_evidence']['capture_id']==capture
                assert payload['source_evidence']['metric_ids']
    with Session(engine) as db:
        assert preparation_view(db,run_id)['next_action']=='resolve_mapping'
        require_preflight_practice(db, assignment_context(db,assignment,'task'))
        history=[row for row in exposure_history(db,'P01') if row['preparation_id']==run_id]
        assert [row['competence'] for row in history]==[False,True]
        assert history[1]['repeat_of']==history[0]['attempt_id']


def test_stopped_preparation_cannot_be_resumed_as_competence(engine):
    from app.study_preparation import begin,stop_preparation,preparation_view,record_stage
    with Session(engine) as db:
        seed(db);assignment=prepared_assignment(db);run=begin(db,assignment.id,'pre')
        record_stage(db,run.id,'demonstration',{})
        stop_preparation(db,run.id)
        assert preparation_view(db,run.id)['next_action']=='stopped'
        with pytest.raises(HTTPException):record_stage(db,run.id,'acknowledgement',{})
        repeated=begin(db,assignment.id,'pre')
        assert repeated.id!=run.id and preparation_view(db,repeated.id)['next_action']=='demonstration'


def test_later_native_practice_is_rejected_before_freeze_but_recognition_supported(engine,tmp_path):
    from tests.test_openmatb_runtime import _manager
    from tests.test_study_acquisition import assigned,native_binding
    from app.study_registry_models import StudyVersion
    from sqlmodel import select
    _manager(engine,tmp_path)
    def later_native(payload):
        payload['study']['preparation_policy'][0].update(placement='prescribed_later',practice=[dict(id='later-native',rationale='Fixture',metric='sysmon.hit_rate',comparator='gte',threshold=0)])
    with Session(engine) as db:
        with pytest.raises(HTTPException) as rejected: assigned(db,'openmatb',native_binding(db),modify=later_native,start=False)
        assert 'before baseline' in str(rejected.value.detail)
        assert not db.exec(select(StudyVersion)).all()
        def recognition(payload):
            payload['study']['preparation_policy'][0].update(placement='prescribed_later',comprehension=[dict(id='recognition',rationale='Fixture',metric='comprehension.correct_fraction',comparator='eq',threshold=1)])
        assignment,_=assigned(db,'openmatb',native_binding(db),modify=recognition,start=False)
        assert assignment


def test_later_browser_practice_can_be_frozen(engine):
    with Session(engine) as db:
        seed(db)
        assert prepared_assignment(db,later=True).id


@pytest.fixture(params=[False, True], ids=['normal-clock', 'equal-clock-reverse-ids'])
def preparation_clock(request):
    from datetime import datetime, timezone
    from itertools import count
    from sqlalchemy import event
    from app.study_registry_models import StudyPreparationEvent
    counter = count(1)
    def tie(mapper, connection, target):
        target.created_at = datetime(2026, 10, 3, tzinfo=timezone.utc)
        target.id = f'00000000-0000-0000-0000-{999999 - next(counter):012d}'
    if request.param:
        event.listen(StudyPreparationEvent, 'before_insert', tie)
    yield request.param
    if request.param:
        event.remove(StudyPreparationEvent, 'before_insert', tie)


def test_measurement_admission_freezes_exact_preparation_frontier_across_later_restart(engine, preparation_clock):
    from app.study_registry_models import StudyPreparationAdmission
    from app.study_preparation import begin, record_stage, begin_practice, finish_practice, stop_preparation, required_preparation
    from app.assessment_service import create_attempt, transition, attempt_view
    from app.assessment_schemas import AttemptIn
    from app.routers.pvt import ingest_pvt, PvtAssessmentIn
    from app.study_admission import for_occasion
    from sqlalchemy import text
    with Session(engine) as db:
        seed(db); assignment = prepared_assignment(db, later=True)
        occasion_id = json.loads(assignment.occasions_json)['pre']
        measurement = create_attempt(db, occasion_id, AttemptIn(execution_purpose='study'))
        with pytest.raises(HTTPException): transition(db, measurement.id, 'started')
        assert db.get(StudyPreparationAdmission, measurement.id) is None
        def qualify():
            run = begin(db, assignment.id, 'pre')
            for stage, response in [('demonstration', {}), ('acknowledgement', {}), ('comprehension', {'response':'SPACE'})]:
                record_stage(db, run.id, stage, response)
            practice = begin_practice(db, run.id); transition(db, practice.id, 'started')
            ingest_pvt(PvtAssessmentIn(participant_id='R01', visit_ordinal=1, execution_purpose='practice', attempt_id=practice.id,
                administered_at='2026-09-10T12:00:00Z', duration_ms=12000, fast_mode=True, kss_score=3, locale='es-419',
                trials=[dict(index=0, wait_ms=2000, stimulus_at_ms=2000, response_at_ms=2300, rt_ms=300, outcome='response')]), db)
            decision = finish_practice(db, run.id, practice.id)
            return run, decision
        original, decision = qualify()
        transition(db, measurement.id, 'started'); db.commit()
        admitted = db.get(StudyPreparationAdmission, measurement.id)
        original_json, original_hash = admitted.snapshot_json, admitted.snapshot_sha256
        snapshot = json.loads(original_json)
        evidence = snapshot['requirements'][0]
        assert evidence['preparation_id'] == original.id and decision.id in evidence['decision_event_ids']
        assert evidence['identity_sha256'] == original.identity_sha256
        assert [event['stage'] for event in evidence['event_frontier']] == ['demonstration','acknowledgement','comprehension','practice']
        stop_preparation(db, original.id)
        replacement, _ = qualify(); db.commit()
        assert required_preparation(db, for_occasion(db, occasion_id))[0]['preparation_id'] == replacement.id
        transition(db, measurement.id, 'started')
        reopened = attempt_view(db, measurement)
        assert reopened['preparation_admission']['snapshot_json'] == original_json
        assert reopened['preparation_admission']['snapshot_sha256'] == original_hash
        assert reopened['receipt']['preparation'] == 'prepared'
        with pytest.raises(Exception, match='immutable'):
            db.execute(text('UPDATE study_preparation_admission SET snapshot_sha256=:value WHERE attempt_id=:id'), {'value':'changed','id':measurement.id})
        db.rollback()


def test_new_event_sequence_preserves_legacy_payload_and_survives_reload(engine, preparation_clock):
    from app.study_registry_models import StudyPreparationEvent
    from app.study_preparation import begin, record_stage, _events
    with Session(engine) as db:
        seed(db); assignment = prepared_assignment(db, later=True)
        run = begin(db, assignment.id, 'pre')
        # An existing ledger entry has no ordinal; preserve it byte-for-byte.
        legacy = StudyPreparationEvent(preparation_id=run.id, stage='demonstration',
            passed=True, payload_json='{"responses":{},"criteria":[]}')
        db.add(legacy); db.flush()
        legacy_id, legacy_payload, legacy_time = legacy.id, legacy.payload_json, legacy.created_at
        acknowledgement = record_stage(db, run.id, 'acknowledgement', {})
        comprehension = record_stage(db, run.id, 'comprehension', {'response': 'SPACE'})
        expected = [legacy.id, acknowledgement.id, comprehension.id]
        run_id = run.id
        db.commit()
    with Session(engine) as db:
        events = _events(db, run_id)
        assert [item.id for item in events] == expected
        assert [json.loads(item.payload_json).get('event_sequence') for item in events] == [None, 2, 3]
        old = db.get(StudyPreparationEvent, legacy_id)
        assert (old.payload_json, old.created_at) == (legacy_payload, legacy_time)
