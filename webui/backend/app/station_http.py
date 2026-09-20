"""Heavy request admission before multipart parsing; durable bounded replay queue."""
import asyncio
import base64
import json
import re
from pathlib import Path
from fastapi import HTTPException
from sqlmodel import Session
from starlette.responses import JSONResponse
from app import station_resources as resources
from app.db import get_engine

# Explicit workload inventory; read-only metadata, markers, stop and raw closure stay available.
HEAVY = [
    ('GET',r'/inference/runs/[^/]+/export'),
    ('POST',r'/ingest(?:/evidence)?'),
    ('POST',r'/analysis/(?:run|bayes/run|liftoff/run)'),
    ('POST',r'/evidence/captures/[^/]+/reconcile'),
    ('POST',r'/evidence/analysis-inputs'),
    ('GET',r'/evidence/captures/[^/]+/export'),
    ('POST',r'/exports/research-bundle'),('GET',r'/exports/research-context'),
    ('GET',r'/screen'),('GET',r'/fits'),
    ('POST',r'/study/analyses(?:/preview|/inputs|/inputs/[^/]+/execute)?'),
    ('GET',r'/study/analyses/[^/]+/export'),
    ('POST',r'/study/analyses/[^/]+/refresh'),
    ('GET',r'/physiology/captures/[^/]+/(?:bundle|analysis)'),
    ('POST',r'/liftoff/sessions/[^/]+/physiology/(?:analyze|retry)'),
    ('GET',r'/liftoff/sessions/[^/]+/bundle'),
    ('POST',r'/liftoff/sessions/[^/]+/(?:seal|physiology-link(?:/retry)?)'),
    ('GET',r'/simulation/sessions/[^/]+/(?:bundle|debrief)'),
    ('POST',r'/geography/(?:preparations|captures/[^/]+)'),
    ('POST',r'/experiments/compile'),
]


def is_heavy(method,path):
    return any(method==verb and re.fullmatch(pattern,path) for verb,pattern in HEAVY)


def artifact_root(engine):
    path=Path(engine.url.database or '.')
    # Restored job response files live in the recorded relocation inventory.
    if (path.parent / 'relocation.json').is_file():
        import json
        mappings=json.loads((path.parent / 'relocation.json').read_text(encoding='utf-8'))
        match=next((r for r in mappings['roots'] if r['original'].replace('\\','/').endswith('/station-job-artifacts')),None)
        if match: return path.parent / match['logical']
    return path.parent / 'station-job-artifacts'


class StationWorkMiddleware:
    def __init__(self,app):
        self.app=app

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':
            await self.app(scope,receive,send);return
        engine=get_engine()
        heavy=is_heavy(scope['method'],scope['path'])
        if scope['method']=='POST' and re.fullmatch(r'/study/preparation/[^/]+/grade',scope['path']):
            from app.study_registry_models import StudyPreparation
            with Session(engine) as db:
                preparation=db.get(StudyPreparation,scope['path'].split('/')[-2])
                heavy=bool(preparation and preparation.instrument=='openmatb')
        if not heavy:
            await self.app(scope,receive,send);return
        try:
            # No body bytes are consumed before reservation/size admission.
            with Session(engine, expire_on_commit=False) as db:
                state=resources.lock(db)
                busy=bool(json.loads(state.reservation_json) or json.loads(state.lanes_json) or state.maintenance or resources.running(db))
                if busy and (scope['path'].startswith('/ingest') or scope['path'].endswith('/physiology-link')):
                    resources.blocked('station_upload_deferred','Large uploads are refused before spooling during acquisition; retry after explicit visit close.')
                # Own capacity before accepting a large idle multipart body.
                if (scope['path'].startswith('/ingest') or scope['path'].endswith('/physiology-link')):
                    job=resources.enqueue(db,'inline_upload',dict(path=scope['path'],nonce=resources.now()))
                    job=resources.claim_job(db,job.id)
                    db.commit()
                    if job is None: resources.blocked('station_busy','Station admission changed; retry upload.')
                    identity=job.id
                else: identity=None
            if identity:
                error=None
                async def tracked(message):
                    nonlocal error
                    if message['type']=='http.response.start' and message['status']>=400: error='HTTP '+str(message['status'])
                    await send(message)
                try: await self.app(scope,receive,tracked)
                except asyncio.CancelledError:
                    with Session(engine) as db:
                        resources.lock(db);row=db.get(resources.StationJob,identity);row.status='uncertain';row.error='Upload processing await interrupted';db.add(row);db.commit()
                    raise
                except BaseException as exc:
                    error=type(exc).__name__;raise
                finally:
                    if not asyncio.current_task().cancelling():
                        with Session(engine, expire_on_commit=False) as db: resources.finish_job(db,identity,error=error);db.commit()
                return
            body=bytearray()
            while True:
                message=await receive()
                if message['type']=='http.disconnect': return
                body.extend(message.get('body',b''))
                if len(body)>resources.MAX_PAYLOAD//2: raise HTTPException(413,dict(code='station_queue_payload_too_large',message='Deferred request body exceeds 64 KiB.'))
                if not message.get('more_body',False): break
            payload=dict(method=scope['method'],path=scope['path'],query=scope.get('query_string',b'').decode(),
                         headers=[(k.decode('latin1'),v.decode('latin1')) for k,v in scope.get('headers',[]) if k.lower() not in {b'authorization',b'cookie'}],
                         body=base64.b64encode(body).decode())
            with Session(engine, expire_on_commit=False) as db:
                if scope['path'] in {'/study/analyses','/study/analyses/inputs','/study/analyses/preview'}:
                    from app.study_analysis import deferred_selection
                    payload['selection_cutoff']=deferred_selection(db,json.loads(body))
                job=resources.enqueue(db,'http',payload)
                identity=job.id
                claimed=resources.claim_job(db,identity)
                db.commit()
            if claimed:
                await self.execute(engine,claimed,send=send,original_scope=scope)
            else:
                await JSONResponse(dict(job_id=identity,status='queued',station_url='/station',next_action='Close the visit when collection and recordings are complete.'),status_code=202,headers={'X-MATB-Station-Job':identity})(scope,receive,send)
        except HTTPException as exc:
            await JSONResponse({'detail':exc.detail},status_code=exc.status_code)(scope,receive,send)

    async def execute(self,engine,job,*,send=None,original_scope=None):
        try:
            return await self._execute(engine,job,send=send,original_scope=original_scope)
        except asyncio.CancelledError:
            with Session(engine) as db:
                resources.lock(db);row=db.get(resources.StationJob,job.id)
                row.status='uncertain';row.error='Interrupted await; actual worker termination not established';db.add(row);db.commit()
            raise
        except Exception as exc:
            with Session(engine) as db:
                resources.finish_job(db,job.id,error=type(exc).__name__+': '+str(exc));db.commit()
            if send: raise

    async def _execute(self,engine,job,*,send=None,original_scope=None):
        payload=json.loads(job.payload_json)
        if job.kind!='http':
            from app.station_worker import execute_internal
            return await execute_internal(engine,job)
        body=base64.b64decode(payload['body']); consumed=False
        scope=dict(original_scope or dict(type='http',asgi={'version':'3.0'},http_version='1.1',scheme='http',server=('testserver',80),client=('127.0.0.1',0),root_path=''))
        if getattr(self,'application',None) is not None: scope['app']=self.application
        scope.update(method=payload['method'],path=payload['path'],raw_path=payload['path'].encode(),query_string=payload['query'].encode(),headers=[(k.encode('latin1'),v.encode('latin1')) for k,v in payload['headers']],station_selection_cutoff=payload.get('selection_cutoff'))
        response_status=500;response_headers=[];size=0
        root=artifact_root(engine);root.mkdir(parents=True,exist_ok=True)
        result_path=root/(job.id+'.response')
        async def receive():
            nonlocal consumed
            if not consumed:
                consumed=True;return dict(type='http.request',body=body,more_body=False)
            # StreamingResponse monitors disconnect concurrently with response streaming.
            await asyncio.Future()
        with result_path.open('wb') as result:
            async def capture(message):
                nonlocal response_status,response_headers,size
                if message['type']=='http.response.start':
                    response_status=message['status'];response_headers=[(k.decode('latin1'),v.decode('latin1')) for k,v in message.get('headers',[])]
                elif message['type']=='http.response.body':
                    data=message.get('body',b'');size+=len(data)
                    if size>128*1024*1024: raise ValueError('Station result exceeds 128 MiB artifact limit')
                    result.write(data)
                if send: await send(message)
            error=None
            try:
                await self.app(scope,receive,capture)
                # Existing detached jobs retain station ownership until actual termination.
                if payload['path']=='/analysis/bayes/run':
                    from app.routers.analysis import _BAYES_THREADS
                    while any(t.is_alive() for t in list(_BAYES_THREADS.values())): await asyncio.sleep(.1)
                if payload['path']=='/geography/preparations':
                    from app.routers.geography import JOBS
                    while any(v['status'] in {'queued','running'} for v in JOBS.values()): await asyncio.sleep(.1)
                if response_status>=400: error='HTTP '+str(response_status)
            except asyncio.CancelledError:
                # Cancelling an await is not proof the underlying thread stopped.
                with Session(engine, expire_on_commit=False) as db:
                    resources.lock(db);current=db.get(resources.StationJob,job.id);current.status='uncertain';current.error='Worker await interrupted; backend retains ownership';db.add(current);db.commit()
                raise
            except Exception as exc:
                error=type(exc).__name__+': '+str(exc)
                if send: raise
            finally:
                if not asyncio.current_task().cancelling():
                    with Session(engine, expire_on_commit=False) as db:
                        resources.finish_job(db,job.id,error=error,result=dict(path=str(result_path),status=response_status,headers=response_headers,bytes=size,source_cutoff=payload.get('selection_cutoff',{}).get('at')));db.commit()
