"""Atomic software station protection, independent of optional instruments."""
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from sqlmodel import Session


def test_competing_starts_and_whole_visit(tmp_path):
    from sqlmodel import create_engine, SQLModel
    engine=create_engine("sqlite:///"+str(tmp_path/"station.db"),connect_args={"check_same_thread":False})
    SQLModel.metadata.create_all(engine)
    from app.station_resources import admit, finish, snapshot, close_visit
    def start(key):
        try:
            with Session(engine) as db:
                admit(db, key, instrument='pvt', owner='assignment:A', participant='P01', visit=1)
                db.commit()
            return key
        except HTTPException:
            return None
    with ThreadPoolExecutor(2) as pool:
        winners=list(pool.map(start,['a','b']))
    assert sum(v is not None for v in winners)==1
    with Session(engine) as db:
        finish(db,next(v for v in winners if v));db.commit()
        assert snapshot(db)['reservation']['owner']=='assignment:A'
        close_visit(db,actor='Dr Test',reason='Visit explicitly closed');db.commit()
        assert snapshot(db)['reservation'] is None


def test_declared_h10_pair_and_wrong_participant(engine):
    from app.station_resources import admit
    with Session(engine) as db:
        admit(db,'matb',instrument='openmatb',owner='assignment:A',participant='P01',visit=1,occasion_key='task',group='paired')
        db.commit()
        with pytest.raises(HTTPException):
            admit(db,'h10',instrument='physiology',owner='assignment:A',participant='P02',visit=1,occasion_key='h10',group='paired',accompanying='task')
        db.rollback()
        admit(db,'h10',instrument='physiology',owner='assignment:A',participant='P01',visit=1,occasion_key='h10',group='paired',accompanying='task');db.commit()
        with pytest.raises(HTTPException):
            admit(db,'another',instrument='pvt',owner='assignment:A',participant='P01',visit=1)


def test_queue_bounds_failure_cancel_and_recovery(engine):
    from app.station_resources import admit, enqueue, claim_job, finish_job, cancel_job, recover, snapshot, recover_idle, MAX_QUEUE
    with Session(engine) as db:
        admit(db,'browser',instrument='pvt',owner='assignment:A',participant='P01',visit=1);db.commit()
        first=enqueue(db,'test',{'id':0});db.commit()
        assert enqueue(db,'test',{'id':0}).id==first.id
        for index in range(1,MAX_QUEUE): enqueue(db,'test',{'id':index})
        db.commit()
        with pytest.raises(HTTPException): enqueue(db,'test',{'id':'overflow'})
        db.rollback()
        assert claim_job(db) is None
        cancel_job(db,first.id);db.commit()
    recover(engine)
    with Session(engine) as db:
        assert snapshot(db)['reservation']['uncertain']
        recover_idle(db,actor='Dr Test',reason='Browser closed; physical station checked',native_pids=[]);db.commit()
        job=claim_job(db);db.commit()
        assert job is not None
        with pytest.raises(HTTPException): admit(db,'new',instrument='screen',owner='standalone:new')
        db.rollback()
        assert cancel_job(db,job.id).status=='cancelling'
        db.commit()
        assert claim_job(db) is None
        finish_job(db,job.id,error='Worker failed');db.commit()
        assert claim_job(db) is not None


@pytest.mark.anyio
async def test_http_heavy_inventory_defers_before_handlers_and_stop_remains_available(engine,monkeypatch):
    import httpx
    from fastapi import FastAPI
    from app.station_http import StationWorkMiddleware, HEAVY
    from app.station_resources import admit,finish,close_visit
    calls=[]
    app=FastAPI()
    @app.post('/analysis/run')
    async def heavy(): calls.append('heavy');return {'result':'done'}
    @app.post('/physiology/captures/capture/stop')
    async def stop(): calls.append('stop');return {'stopped':True}
    app.add_middleware(StationWorkMiddleware)
    with Session(engine) as db:
        admit(db,'pvt',instrument='pvt',owner='assignment:A',participant='P01',visit=1)
        finish(db,'pvt');db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
        response=await client.post('/analysis/run')
        assert response.status_code==202 and not calls
        assert (await client.post('/physiology/captures/capture/stop')).status_code==200
        assert calls==['stop']
    with Session(engine) as db: close_visit(db,actor='Dr Test',reason='Ratings and recovery complete');db.commit()
    from app.station_worker import StationWorker
    worker=StationWorker(engine,app.router);worker.start()
    import asyncio
    for _ in range(30):
        if calls==['stop','heavy']: break
        await asyncio.sleep(.02)
    await worker.shutdown()
    assert calls==['stop','heavy']
    with Session(engine) as db:
        from app.station_resources import StationJob
        job=db.get(StationJob,response.json()['job_id'])
        assert job.status=='complete'
        assert json.loads(job.result_json)['status']==200


@pytest.mark.anyio
async def test_reserved_upload_is_rejected_without_consuming_body(engine):
    from app.station_http import StationWorkMiddleware
    from app.station_resources import admit
    with Session(engine) as db: admit(db,'browser',instrument='screen',owner='standalone:browser');db.commit()
    consumed=False;messages=[]
    async def receive():
        nonlocal consumed
        consumed=True
        raise AssertionError('Upload was consumed before admission')
    async def send(message): messages.append(message)
    async def endpoint(*args): raise AssertionError('Upload handler ran')
    await StationWorkMiddleware(endpoint)({'type':'http','method':'POST','path':'/ingest/evidence','headers':[]},receive,send)
    assert not consumed and messages[0]['status']==409


def test_held_runtime_has_same_visit_and_blocks_heavy_work(engine):
    from app.station_resources import admit,enqueue,claim_job,finish,snapshot
    with Session(engine) as db:
        admit(db,'native',instrument='openmatb',owner='assignment:A',participant='P01',visit=1,held=True)
        db.commit()
        assert snapshot(db)['reservation'] is None
        job=enqueue(db,'test',{});db.commit()
        assert claim_job(db,job.id) is None
        with pytest.raises(HTTPException): admit(db,'wrong',instrument='pvt',owner='assignment:B',participant='P02',visit=1)
        db.rollback()
        admit(db,'baseline',instrument='pvt',owner='assignment:A',participant='P01',visit=1);db.commit()
        with pytest.raises(HTTPException): admit(db,'native',instrument='openmatb',owner='assignment:A',participant='P01',visit=1)
        db.rollback()
        finish(db,'baseline');db.commit()
        admit(db,'native',instrument='openmatb',owner='assignment:A',participant='P01',visit=1);db.commit()


def test_native_pid_prevents_false_idle_recovery(engine,monkeypatch):
    from app.station_resources import admit,recover,recover_idle
    from app import native_process_guard
    with Session(engine) as db: admit(db,'native',instrument='openmatb',owner='standalone:native',pid=424242);db.commit()
    recover(engine)
    monkeypatch.setattr(native_process_guard,'process_alive',lambda pid:pid==424242)
    with Session(engine) as db:
        with pytest.raises(HTTPException,match='alive'): recover_idle(db,actor='Dr Test',reason='Checked',native_pids=[])


def test_browser_start_cannot_duplicate_and_finish_retains_visit(client):
    from tests.test_assessments import occasion,attempt
    from tests.test_pvt_endpoint import _enroll
    _enroll(client)
    selected=attempt(client,occasion(client))
    assert client.post('/assessments/attempts/'+selected['id']+'/start').status_code==409
    assert client.post('/assessments/attempts/'+selected['id']+'/finish').status_code==200
    assert client.get('/station').json()['reservation'] is not None


@pytest.mark.anyio
async def test_owner_lease_precedes_schema_and_migration_writes(engine,monkeypatch):
    from app import main
    from app.routers import analysis
    calls=[]
    def deny(*args): calls.append('lease');raise RuntimeError('second backend')
    monkeypatch.setattr(analysis,'acquire_backend_instance_lease',deny)
    monkeypatch.setattr(main,'init_db',lambda **kwargs:calls.append('schema'))
    with pytest.raises(RuntimeError,match='second backend'):
        async with main.lifespan(main.app): pass
    assert calls==['lease']


def test_initializing_preflight_blocks_baseline_until_same_runtime_is_held(engine):
    from app.station_resources import admit
    with Session(engine) as db:
        admit(db,'native',instrument='openmatb',owner='assignment:A',held=True,initializing=True);db.commit()
        with pytest.raises(HTTPException): admit(db,'baseline',instrument='pvt',owner='assignment:A')
        db.rollback()
        admit(db,'native',instrument='openmatb',owner='assignment:A',held=True);db.commit()
        admit(db,'baseline',instrument='pvt',owner='assignment:A');db.commit()



def test_deferred_analysis_records_metadata_cutoff_without_raw_calculation(engine,monkeypatch):
    from app import study_analysis
    from app.study_registry import activate,assign
    from tests.test_study_registry import seed,frozen
    from app.models import Participant,Visit
    from datetime import date
    with Session(engine) as db:
        seed(db);version=frozen(db);activate(db,version.id,actor='Dr Test',reason='Fixture')
        assign(db,version.id,'R01',1,'A',actor='Dr Test');db.commit()
        request=dict(version_id=version.id,attempts={},actor='Dr Test',reason='Explicit deferred selection')
        def forbidden(*args,**kwargs): raise AssertionError('Raw decoding occurred during queue acceptance')
        with monkeypatch.context() as patch:
            patch.setattr(study_analysis,'read_source',forbidden)
            patch.setattr(study_analysis,'calculate',forbidden)
            cutoff=study_analysis.deferred_selection(db,request)
        db.add(Participant(id='R02',enrollment_date=date(2026,9,10)));db.flush()
        visit=Visit(participant_id='R02',visit_ordinal=1,scheduled_day=0);db.add(visit);db.flush()
        assign(db,version.id,'R02',visit.id,'A',actor='Dr Test');db.commit()
        deferred=study_analysis.preview(db,{**request,'_selection_cutoff':cutoff})
        current=study_analysis.preview(db,request)
        assert len(deferred['rows'])==3 and len(current['rows'])==6
        assert {row['participant_id'] for row in deferred['rows']}=={'R01'}
        assert cutoff['at'] and 'eligibility' in cutoff['semantics']


@pytest.mark.anyio
async def test_actual_thread_cancellation_request_keeps_station_owned(engine):
    import asyncio
    import threading
    import httpx
    from fastapi import FastAPI
    from app.station_http import StationWorkMiddleware
    from app.station_resources import cancel_job,admit,snapshot
    begun=threading.Event();release=threading.Event();ended=threading.Event()
    app=FastAPI()
    @app.post('/analysis/run')
    async def work():
        def compute(): begun.set();release.wait(5);ended.set();return {'done':True}
        return await asyncio.to_thread(compute)
    app.add_middleware(StationWorkMiddleware)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
        request=asyncio.create_task(client.post('/analysis/run'))
        for _ in range(100):
            if begun.is_set():break
            await asyncio.sleep(.01)
        assert begun.is_set()
        with Session(engine) as db:
            job=snapshot(db)['jobs'][0]
            assert cancel_job(db,job['id']).status=='cancelling';db.commit()
            with pytest.raises(HTTPException):admit(db,'browser',instrument='pvt',owner='standalone:browser')
            db.rollback()
        assert not ended.is_set()
        release.set();assert (await request).status_code==200
        assert ended.is_set()
        with Session(engine) as db:
            assert not snapshot(db)['jobs']
            admit(db,'browser',instrument='pvt',owner='standalone:browser');db.commit()


@pytest.mark.anyio
@pytest.mark.parametrize('phase', ['collection', 'ratings', 'recovery'])
async def test_all_public_heavy_surfaces_defer_through_whole_visit(engine, monkeypatch, phase):
    """Independent concrete route inventory: no heavy handler may run in any phase."""
    import httpx
    from fastapi import FastAPI
    from app.station_http import StationWorkMiddleware
    from app import station_resources as station, study_analysis
    monkeypatch.setattr(study_analysis, 'deferred_selection', lambda *_args: {'at': 'fixture-cutoff'})
    downstream = FastAPI()
    @downstream.api_route('/{path:path}', methods=['GET', 'POST'])
    async def must_not_execute(path: str):
        raise AssertionError('Protected heavy handler executed: ' + path)
    application = StationWorkMiddleware(downstream)
    with Session(engine) as db:
        station.admit(db, 'matrix-pvt', instrument='pvt', owner='assignment:matrix', participant='P01', visit=1)
        if phase != 'collection':
            station.finish(db, 'matrix-pvt')
        db.commit()
    routes = [
        ('POST', '/analysis/run'), ('POST', '/analysis/bayes/run'),
        ('POST', '/analysis/liftoff/run'), ('POST', '/evidence/captures/x/reconcile'),
        ('POST', '/evidence/analysis-inputs'), ('GET', '/evidence/captures/x/export'),
        ('POST', '/exports/research-bundle'), ('GET', '/exports/research-context'),
        ('GET', '/screen'), ('GET', '/fits'), ('POST', '/study/analyses'),
        ('POST', '/study/analyses/preview'), ('POST', '/study/analyses/inputs'),
        ('POST', '/study/analyses/inputs/x/execute'), ('GET', '/study/analyses/x/export'),
        ('POST', '/study/analyses/x/refresh'), ('GET', '/physiology/captures/x/bundle'),
        ('GET', '/physiology/captures/x/analysis'), ('GET', '/liftoff/sessions/x/bundle'),
        ('POST', '/liftoff/sessions/x/seal'), ('POST', '/liftoff/sessions/x/physiology-link/retry'),
        ('GET', '/simulation/sessions/x/bundle'), ('GET', '/simulation/sessions/x/debrief'),
        ('POST', '/geography/preparations'), ('POST', '/geography/captures/x'),
        ('POST', '/experiments/compile'),
    ]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://testserver') as client:
        for method, path in routes:
            selection = dict(version_id='fixture', actor='Dr Test', reason='Admission fixture')
            response = await client.request(method, path, json=selection if path in {
                '/study/analyses', '/study/analyses/preview', '/study/analyses/inputs',
            } else {})
            assert response.status_code == 202, (phase, path, response.text)
            with Session(engine) as db:
                station.cancel_job(db, response.json()['job_id'])
                db.commit()
        for path in ['/ingest', '/ingest/evidence', '/liftoff/sessions/x/physiology-link']:
            response = await client.post(path, content=b'unparsed upload')
            assert response.status_code == 409, (phase, path, response.text)
