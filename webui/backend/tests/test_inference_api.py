import asyncio
import httpx
from fastapi import FastAPI


def test_api_has_small_allowlisted_surface_and_rejects_bad_body(engine):
    from app.routers.inference import router
    from app.db import get_session
    from sqlmodel import Session, SQLModel
    SQLModel.metadata.create_all(engine)
    app=FastAPI()
    app.include_router(router)
    def session():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_session]=session
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            for path in ('/inference/annotations','/inference/previews','/inference/runs',
                         '/inference/runs/missing/reviews','/inference/runs/missing/retry'):
                response=await client.post(path,json={'provider_url':'https://example.com'})
                assert response.status_code == 422
            for path in ('/inference/previews/missing','/inference/runs/missing'):
                assert (await client.get(path)).status_code == 404
            response=await client.post('/inference/annotations',content=b'x'*40000)
            assert response.status_code == 413
    asyncio.run(check())


def test_retry_checks_all_attempts_not_only_selected_prior():
    import time
    import pytest
    from app.routers.inference import check_retry
    from app.inference_models import InferenceRun
    from fastapi import HTTPException
    older=InferenceRun(id='old',input_identity='x',preview_id='p',authorization_id='a',status='valid')
    newer=InferenceRun(id='new',input_identity='x',preview_id='p',authorization_id='a',status='throttled',
        result_json='{"earliest_retry_ns":"'+str(time.time_ns()+10**12)+'"}')
    with pytest.raises(HTTPException): check_retry([older,newer])
    newer.status='sending'
    newer.result_json=None
    with pytest.raises(HTTPException): check_retry([older,newer])


def test_only_export_is_heavy():
    from app.station_http import is_heavy
    assert is_heavy('GET','/inference/runs/r/export')
    assert not is_heavy('POST','/inference/runs')
    assert not is_heavy('POST','/inference/previews')


def test_model_exposure_prevents_later_blinded_label(engine):
    from app.routers.inference import router
    from app.inference_models import InferenceRun
    from app.db import get_session
    from sqlmodel import Session, SQLModel
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(InferenceRun(id='r',input_identity='x',preview_id='p',authorization_id='a',status='valid',result_json='{"answers_json":"{}"}'))
        db.add(InferenceRun(id='r2',input_identity='x',attempt_number=2,preview_id='p',authorization_id='a',status='valid',result_json='{"answers_json":"{}"}'))
        db.commit()
    app=FastAPI()
    app.include_router(router)
    def session():
        with Session(engine) as db: yield db
    app.dependency_overrides[get_session]=session
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            hidden=(await client.get('/inference/runs/r')).json()
            assert hidden.get('result_json') is None
            shown=await client.get('/inference/runs/r?reviewer=rater&include_answers=true')
            assert shown.json()['result_json'] is not None
            contaminated=await client.post('/inference/runs/r/reviews',json={'reviewer':'rater','activity':'blinded_reference','labels_json':'{}'})
            assert contaminated.status_code==409
            replicate=await client.post('/inference/runs/r2/reviews',json={'reviewer':'rater','activity':'blinded_reference','labels_json':'{}'})
            assert replicate.status_code==409
            assert (await client.get('/inference/runs/r/export')).status_code==422
    asyncio.run(check())
