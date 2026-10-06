"""One bounded durable worker, drained without cancelling compute threads."""
import asyncio
import json
from sqlmodel import Session
from app import station_resources as resources


async def execute_internal(engine,job):
    payload=json.loads(job.payload_json)
    try:
        if job.kind=='semantic_review':
            from app.inference_service import execute_semantic_job, fail_semantic_job
            try:
                await execute_semantic_job(engine,job)
            except Exception:
                fail_semantic_job(engine,job)
                raise RuntimeError('semantic_review_failed') from None
        elif job.kind=='native_evidence':
            # Manager provides its existing source authority; durable attempt remains queued on restart.
            from app.station_worker import MANAGERS
            manager=MANAGERS.get(str(engine.url))
            if manager is None: raise RuntimeError('Native evidence manager unavailable')
            await asyncio.to_thread(manager.records.process,payload['attempt_id'])
        elif job.kind=='mission_finalize':
            from app.station_mission import finalize
            await asyncio.to_thread(finalize,engine,payload)
        elif job.kind=='crew_export':
            from app.crew_exports import run_export
            await asyncio.to_thread(run_export,engine,payload['attempt_id'])
        elif job.kind=='hcf_refresh':
            def refresh():
                from app.hcf_refresh import refresh_fit_hcf
                with Session(engine, expire_on_commit=False) as db: refresh_fit_hcf(db)
            await asyncio.to_thread(refresh)
        else: raise ValueError('Unsupported durable job kind: '+job.kind)
        with Session(engine, expire_on_commit=False) as db: resources.finish_job(db,job.id);db.commit()
    except Exception as exc:
        with Session(engine, expire_on_commit=False) as db: resources.finish_job(db,job.id,error=type(exc).__name__+': '+str(exc));db.commit()


MANAGERS={}


class StationWorker:
    def __init__(self,engine,app,*,application=None):
        from app.station_http import StationWorkMiddleware
        from fastapi.middleware.asyncexitstack import AsyncExitStackMiddleware
        # Replay bypasses admission middleware, but still needs FastAPI's
        # request file lifecycle just like a request dispatched by FastAPI.
        app=AsyncExitStackMiddleware(app)
        if application is not None:
            from starlette.middleware.exceptions import ExceptionMiddleware
            app=ExceptionMiddleware(app,handlers=application.exception_handlers)
        self.engine=engine;self.middleware=StationWorkMiddleware(app);self.middleware.application=application;self.closing=False;self.task=None

    def start(self): self.task=asyncio.create_task(self.run())

    async def run(self):
        while not self.closing:
            with Session(self.engine, expire_on_commit=False) as db: job=resources.claim_job(db);db.commit()
            if job: await self.middleware.execute(self.engine,job)
            else: await asyncio.sleep(.2)

    async def shutdown(self):
        self.closing=True
        if self.task:
            done,_=await asyncio.wait({self.task},timeout=30)
            if not done: raise RuntimeError('Heavy worker still active; backend owner lease retained until process exit.')
            self.task.result()
        with Session(self.engine) as db:
            if resources.running(db):
                raise RuntimeError("Heavy work termination is unconfirmed; retain backend owner lease until process exit.")
