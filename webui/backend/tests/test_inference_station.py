import asyncio
import json
import pytest
from sqlmodel import Session, SQLModel
from app import station_resources as resources


@pytest.mark.parametrize('field,value', [('reservation_json','{"owner":"visit"}'),
    ('lanes_json','{"h10":{"held":false}}'),('lanes_json','{"native":{"held":true}}'),
    ('maintenance',True),('reservation_json','{"uncertain":true}')])
def test_semantic_work_cannot_claim_protected_station(engine, field, value):
    from app.inference_service import enqueue_preview
    with Session(engine) as db:
        state=resources.lock(db)
        setattr(state,field,value)
        db.add(state)
        db.flush()
        job=enqueue_preview(db, 'capture', 'run', 'note', 'matb-debrief-v1')
        db.commit()
        assert resources.claim_job(db,job.id) is None


def test_disabled_persisted_job_is_blocked_without_provider(engine, monkeypatch):
    from app.inference_service import execute_semantic_job
    from app.inference_models import InferenceRun
    SQLModel.metadata.create_all(engine)
    monkeypatch.setenv('MATB_JEV_MODE','off')
    with Session(engine) as db:
        run=InferenceRun(id='r', input_identity='x', preview_id='p', authorization_id='a')
        db.add(run)
        job=resources.enqueue(db,'semantic_review',dict(operation='evaluate',run_id='r'))
        db.commit()
        job=resources.claim_job(db,job.id)
        db.commit()
        asyncio.run(execute_semantic_job(engine,job))
        db.expire_all()
        assert db.get(InferenceRun,'r').status == 'blocked'


def test_cancelled_queued_run_is_recoverable(engine):
    from app.inference_service import recover_inference
    from app.inference_models import InferenceRun
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        job=resources.enqueue(db,'semantic_review',dict(operation='evaluate',run_id='r'))
        db.add(InferenceRun(id='r',input_identity='x',preview_id='p',authorization_id='a',job_id=job.id))
        db.commit()
        resources.cancel_job(db,job.id)
        db.commit()
    recover_inference(engine)
    with Session(engine) as db:
        assert db.get(InferenceRun,'r').status == 'cancelled'


def test_internal_exception_preserves_unknown_and_sanitizes_job(engine,monkeypatch):
    from app import inference_service
    from app.inference_models import InferenceRun
    from app.station_worker import execute_internal
    SQLModel.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        db.add(InferenceRun(id='r',input_identity='x',preview_id='p',authorization_id='a',status='sending'))
        job=resources.enqueue(db,'semantic_review',dict(operation='evaluate',run_id='r'))
        db.commit();job=resources.claim_job(db,job.id);db.commit()
    async def broken(*args):raise RuntimeError('PRIVATE-NARRATIVE')
    monkeypatch.setattr(inference_service,'execute_semantic_job',broken)
    asyncio.run(execute_internal(engine,job))
    with Session(engine) as db:
        assert db.get(InferenceRun,'r').status=='outcome_unknown'
        assert 'PRIVATE-NARRATIVE' not in db.get(resources.StationJob,job.id).error
