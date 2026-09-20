"""Synthetic end-to-end ledger flow through actual routes and station jobs."""
import asyncio
import json
import time
import httpx
from fastapi import FastAPI
from sqlmodel import Session, SQLModel, select


def test_note_preview_infer_export_preserves_evidence(engine,monkeypatch,tmp_path):
    from app.routers.inference import router
    from app.db import get_session
    from app import inference_service, station_resources
    from app.station_worker import execute_internal
    from app.evidence_models import EvidenceCapture,EvidenceArtifact,EvidenceRun,EvidenceMetric
    from matb_integration.inference.contracts import ProviderAttempt,sha256,canonical_bytes
    from matb_integration.inference.client import JevProvider
    from matb_integration.inference.replay import verify_inference_bundle
    from matb_integration.automation.engine import AdaptiveAutomationEngine
    def forbidden_action(*args,**kwargs):
        raise AssertionError('semantic inference invoked authoritative automation')
    monkeypatch.setattr(AdaptiveAutomationEngine,'evaluate',forbidden_action)
    monkeypatch.setattr(AdaptiveAutomationEngine,'apply',forbidden_action)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(EvidenceCapture(id='c',manifest_sha256='a'*64,artifact_fingerprint='b'*64,
            session_id='s',block_instance_id='b',condition='LOW',execution_purpose='practice',
            completion='complete',manifest_json='{}'))
        db.commit()
        db.add(EvidenceArtifact(capture_id='c',role='events',content=b'original',sha256=sha256(b'original')))
        db.add(EvidenceRun(id='er',capture_id='c',version='1',status='complete',fingerprint='c'*64,result_json='{}'))
        db.commit()
    def scientific_snapshot():
        with Session(engine) as db:
            return [[r.model_dump() for r in db.exec(select(model)).all()] for model in
                (EvidenceCapture,EvidenceArtifact,EvidenceRun,EvidenceMetric)]
    before=scientific_snapshot()
    calls=[]
    async def fake(self,payload):
        calls.append(payload)
        return ProviderAttempt(attempt_id='remote-attempt',outcome='received',status=200,
            started_at_ns='1',finished_at_ns='2',raw_response=canonical_bytes({'model':'jev-1.13.0','answers':{
            'reported_task_tradeoff':{'type':'noul','noul':0.1},
            'reported_instruction_difficulty':{'type':'noul','noul':0.2},
            'automation_belief':{'type':'choice','choice':'not_stated','confidence':0.8,
              'probabilities':{'expected_active':0.0,'expected_inactive':0.0,'conflicting':0.0,'not_stated':1.0}}}}))
    monkeypatch.setattr(JevProvider,'evaluate',fake)
    monkeypatch.setattr(inference_service,'remote_enabled',lambda:True)
    app=FastAPI();app.include_router(router)
    def session():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_session]=session
    async def process(identity):
        with Session(engine,expire_on_commit=False) as db:
            job=station_resources.claim_job(db,identity);db.commit()
        assert job is not None
        await execute_internal(engine,job)
    async def flow():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            response=await client.post('/inference/annotations',json={'annotation_id':'n','capture_id':'c',
                'source_event_ids':[],'language':'en','author_role':'researcher','source_kind':'synthetic',
                'original_text':'The panel was visible.','created_at_ns':'9007199254740993'})
            assert response.status_code==201,response.text
            notes=await client.get('/inference/annotations?capture_id=c')
            assert notes.status_code==200
            assert notes.json()['items'][0]['annotation_id']=='n'
            assert (await client.get('/inference/annotations?capture_id=other')).json()['items']==[]
            queued=(await client.post('/inference/previews',json={'capture_id':'c','evidence_run_id':'er','annotation_id':'n'})).json()
            await process(queued['job_id'])
            preview=(await client.get('/inference/previews/'+queued['id'])).json()
            now=time.time_ns()
            request={'preview_id':preview['id'],'preview_hash':preview['preview_hash'],'question_pack_id':'matb-debrief-v1',
                'authorization':{'provider_id':'jev_ai_pro','purpose':'retrospective_annotation',
                'payload_hash':preview['lineage']['payload_hash'],'approved_by':'rater','approved_at_ns':str(now-1000000),
                'expires_at_ns':str(now+10**12),'revoked':False,'redaction_reviewed':True,
                'protocol_authorization':'synthetic-protocol','data_processing_authorization':'synthetic-only'}}
            queued=(await client.post('/inference/runs',json=request)).json()
            duplicate=(await client.post('/inference/runs',json=request)).json()
            assert duplicate['id']==queued['id']
            await process(queued['job_id'])
            viewed=(await client.get('/inference/runs/'+queued['id']+'?reviewer=rater&include_answers=true')).json()
            assert viewed['status']=='valid',viewed
            history=(await client.get('/inference/runs?capture_id=c&limit=1')).json()
            assert history['items'][0]['id']==queued['id']
            assert history['items'][0]['result_json'] is None
            assert (await client.get('/inference/runs?capture_id=other')).json()['items']==[]
            assert (await client.get('/inference/runs?capture_id=c&limit=101')).status_code==422
            review_url='/inference/runs/'+queued['id']+'/reviews'
            assert (await client.get(review_url)).status_code==422
            assert (await client.get(review_url+'?reviewer=reader')).status_code==200
            contaminated=await client.post(review_url,json={'reviewer':'reader','activity':'blinded_reference',
                'labels_json':'{"reported_task_tradeoff":"unmentioned","automation_belief":"not_stated","reported_instruction_difficulty":"unmentioned"}'})
            assert contaminated.status_code==409
            exported=await client.get('/inference/runs/'+queued['id']+'/export?reviewer=rater')
            assert exported.status_code==200,exported.text if exported.status_code!=200 else ''
            path=tmp_path/'inference.zip';path.write_bytes(exported.content)
            replayed=verify_inference_bundle(str(path))
            assert replayed['result']['outcome']=='valid'
            assert replayed['provenance']['annotations'][0]['annotation_id']=='n'
            assert replayed['provenance']['approval']['payload_hash']==request['authorization']['payload_hash']
            assert any(r['activity']=='export_exposure' for r in replayed['provenance']['audit'])
            retry=(await client.post('/inference/runs/'+queued['id']+'/retry',json=request)).json()
            revoked=await client.post('/inference/runs/'+retry['id']+'/revoke',json={'reviewer':'rater','reason':'withdraw synthetic approval'})
            assert revoked.status_code==200,revoked.text
            assert revoked.json()['prevented_dispatch'] is True
            assert (await client.get('/inference/runs/'+retry['id'])).json()['status']=='blocked'
            with Session(engine,expire_on_commit=False) as db:
                assert station_resources.claim_job(db,retry['job_id']) is None
    asyncio.run(flow())
    assert len(calls)==1
    assert scientific_snapshot()==before
