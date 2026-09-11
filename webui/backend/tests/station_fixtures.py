"""Explicit researcher closure and actual queue execution for non-lifespan clients."""
from sqlmodel import Session
from app import station_resources as station
from app.station_worker import StationWorker
from app.main import app


async def close_and_drain(engine):
    with Session(engine) as db:
        station.close_visit(db,actor='Dr Fixture',reason='All collection complete; run deferred derivations')
        db.commit()
    worker=StationWorker(engine,app.router,application=app)
    for _ in range(station.MAX_QUEUE+1):
        with Session(engine,expire_on_commit=False) as db:
            job=station.claim_job(db);db.commit()
        if job is None:return
        await worker.middleware.execute(engine,job)
        with Session(engine) as db:
            final=db.get(station.StationJob,job.id)
            assert final.status=='complete',final.error
    raise AssertionError('Queue did not drain within bounded fixture limit')
