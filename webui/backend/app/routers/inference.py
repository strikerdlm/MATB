"""Bounded optional Console API; existing app security middleware remains in force."""
import json
import time
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field, ValidationError
from sqlmodel import Session, select
from sqlalchemy import String, cast, func
from app.db import get_session
from app import inference_service as service, station_resources as resources
from app.inference_models import InferenceRun, InferenceArtifact, InferenceReview, InferenceAnnotation
from matb_integration.inference.contracts import FrozenContract, Identifier, Digest, Nanoseconds, ReviewAnnotationV1, InferenceInputV1
from matb_integration.inference.privacy import validate_egress, EgressError

router=APIRouter(prefix='/inference',tags=['experimental-semantic-review'])


class PreviewRequest(FrozenContract):
    capture_id: Identifier
    evidence_run_id: Identifier
    annotation_id: Identifier
    pack_id: Literal['matb-debrief-v1'] = 'matb-debrief-v1'


class Authorization(FrozenContract):
    provider_id: Literal['jev_ai_pro']
    purpose: Literal['retrospective_annotation']
    payload_hash: Digest
    approved_by: Identifier
    approved_at_ns: Nanoseconds
    expires_at_ns: Nanoseconds
    revoked: Literal[False]
    redaction_reviewed: Literal[True]
    protocol_authorization: Identifier
    data_processing_authorization: Identifier


class RunRequest(FrozenContract):
    preview_id: Identifier
    preview_hash: Digest
    question_pack_id: Literal['matb-debrief-v1']
    authorization: Authorization


class ReviewRequest(FrozenContract):
    reviewer: Identifier
    activity: Literal['blinded_reference','adjudication']
    labels_json: str = Field(min_length=2,max_length=4000)
    elapsed_seconds: float | None = Field(default=None,ge=0,le=86400)


class RevocationRequest(FrozenContract):
    reviewer: Identifier
    reason: str = Field(min_length=1, max_length=500)


async def body(request, model):
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>32768:
            raise HTTPException(413,detail={'code':'inference_body_too_large'})
    try:
        return model.model_validate_json(bytes(raw))
    except ValidationError:
        raise HTTPException(422,detail={'code':'inference_request_invalid'}) from None


def checked(fn,*args):
    try:
        return fn(*args)
    except (service.InferenceError,EgressError,ValueError):
        raise HTTPException(409,detail={'code':'inference_request_rejected'}) from None


@router.post('/annotations',status_code=201)
async def annotations(request: Request,db: Session=Depends(get_session)):
    note=await body(request,ReviewAnnotationV1)
    row=checked(service.create_annotation,db,note)
    db.commit()
    return {'id':row.id,'hash':row.content_hash}


@router.get('/annotations')
def annotation_history(capture_id: str=Query(...,max_length=200), offset: int=Query(0,ge=0),
        limit: int=Query(20,ge=1,le=100), db: Session=Depends(get_session)):
    rows=db.exec(select(InferenceAnnotation).where(InferenceAnnotation.capture_id==capture_id)
        .order_by(InferenceAnnotation.id).offset(offset).limit(limit+1)).all()
    items=[]
    for row in rows[:limit]:
        note=ReviewAnnotationV1.model_validate_json(row.content_json)
        if service.sha256(note)!=row.content_hash:
            raise HTTPException(409,detail={'code':'annotation_integrity'})
        items.append(note.model_dump(mode='json'))
    return {'items':items,'next_offset':offset+limit if len(rows)>limit else None}


@router.get('/runs')
def run_history(capture_id: str=Query(...,max_length=200), offset: int=Query(0,ge=0),
        limit: int=Query(20,ge=1,le=100), db: Session=Depends(get_session)):
    rows=db.exec(select(InferenceRun).join(InferenceArtifact,InferenceRun.preview_id==InferenceArtifact.id)
        .where(InferenceArtifact.role=='input',func.json_extract(cast(InferenceArtifact.content,String),'$.capture_id')==capture_id)
        .order_by(InferenceRun.input_identity,InferenceRun.attempt_number).offset(offset).limit(limit+1)).all()
    items=[]
    for row in rows[:limit]:
        service.sync_queued_status(db,row)
        items.append(row.model_dump()|{'result_json':None})
    db.commit()
    return {'items':items,'next_offset':offset+limit if len(rows)>limit else None}


@router.get('/annotations/{identity}')
def annotation_detail(identity: str,db: Session=Depends(get_session)):
    row=db.get(InferenceAnnotation,identity)
    if row is None:
        raise HTTPException(404,detail={'code':'annotation_missing'})
    value=ReviewAnnotationV1.model_validate_json(row.content_json)
    if service.sha256(value)!=row.content_hash:
        raise HTTPException(409,detail={'code':'annotation_integrity'})
    return value.model_dump(mode='json')


@router.post('/previews',status_code=202)
async def previews(request: Request,db: Session=Depends(get_session)):
    value=await body(request,PreviewRequest)
    job=checked(service.enqueue_preview,db,value.capture_id,value.evidence_run_id,value.annotation_id,value.pack_id)
    db.commit()
    return {'id':job.id,'job_id':job.id,'status':job.status}


@router.get('/previews/{identity}')
def preview(identity: str,db: Session=Depends(get_session)):
    row=db.get(InferenceArtifact,identity)
    if row is None:
        job=db.get(resources.StationJob,identity)
        if job is None or job.kind!='semantic_review':
            raise HTTPException(404,detail={'code':'preview_missing'})
        return {'id':identity,'status':job.status,'job_id':job.id,
            'error_code':'preview_unavailable' if job.status in {'failed','cancelled'} else None}
    row=checked(service.read_artifact,db,identity,'input')
    value=InferenceInputV1.model_validate_json(row.content)
    return {'id':identity,'status':'ready','preview_hash':row.sha256,
        'payload':value.outbound_bytes.decode('utf-8'),
        'lineage':value.model_dump(mode='json',exclude={'outbound_bytes'})}


def check_retry(attempts):
    if any(item.status in {'queued','sending'} for item in attempts):
        raise HTTPException(409,detail={'code':'attempt_still_active'})
    for item in attempts:
        retry=json.loads(item.result_json).get('earliest_retry_ns') if item.result_json else None
        if retry and time.time_ns()<int(retry):
            raise HTTPException(409,detail={'code':'retry_too_early'})


def create_run(db,value,prior=None):
    resources.lock(db)  # Serialize duplicate-click and replicate identities.
    frozen_row=checked(service.read_artifact,db,value.preview_id,'input')
    if frozen_row.sha256!=value.preview_hash:
        raise HTTPException(409,detail={'code':'preview_changed'})
    frozen=InferenceInputV1.model_validate_json(frozen_row.content)
    reviewed=InferenceInputV1(**(frozen.model_dump()|{'redaction_status':'reviewed'}))
    checked(validate_egress,reviewed,value.authorization.model_dump(),frozen.provider_id)
    prior_runs=db.exec(select(InferenceRun).where(InferenceRun.input_identity==frozen.input_identity)).all()
    for item in prior_runs:
        service.sync_queued_status(db,item)
    if prior is None and prior_runs:
        existing=min(prior_runs,key=lambda item:item.attempt_number)
        return {'id':existing.id,'job_id':existing.job_id,'status':existing.status}
    if prior and (prior.input_identity!=frozen.input_identity or prior.status in {'queued','sending'}):
        raise HTTPException(409,detail={'code':'retry_identity_or_state'})
    if prior:
        check_retry(prior_runs)
    identity=str(uuid4())
    approval=service.artifact(db,identity,'authorization',value.authorization.model_dump_json().encode())
    run=InferenceRun(id=identity,input_identity=frozen.input_identity,preview_id=value.preview_id,
        authorization_id=approval.id,attempt_number=max((r.attempt_number for r in prior_runs),default=0)+1,
        prior_attempt_id=prior.id if prior else None)
    db.add(run)
    db.flush()
    service.audit(db,run.id,'authorization',{'artifact_id':approval.id},value.authorization.approved_by)
    job=resources.enqueue(db,'semantic_review',{'operation':'evaluate','run_id':identity})
    run.job_id=job.id
    db.add(run)
    db.commit()
    return {'id':identity,'job_id':job.id,'status':run.status}


@router.post('/runs',status_code=202)
async def runs(request: Request,db: Session=Depends(get_session)):
    return create_run(db,await body(request,RunRequest))


@router.get('/runs/{identity}')
def run(identity: str,reviewer: str=Query('',max_length=200),include_answers: bool=False,db: Session=Depends(get_session)):
    row=db.get(InferenceRun,identity)
    if row is None:
        raise HTTPException(404,detail={'code':'inference_run_missing'})
    service.sync_queued_status(db,row)
    db.commit()
    db.refresh(row)
    if include_answers:
        if not reviewer.strip():
            raise HTTPException(422,detail={'code':'named_reviewer_required'})
        resources.lock(db)
        service.audit(db,identity,'model_exposure',{},reviewer)
        db.commit()
        db.refresh(row)
    # Other raters' labels and model answers remain absent from metadata reads.
    data=row.model_dump()
    # Transport diagnostics are not semantic answers and may be shown while blinded.
    result=json.loads(row.result_json) if row.result_json else {}
    data['error_code']=result.get('error_code')
    if data['error_code'] is None:
        latest=db.exec(select(InferenceReview).where(InferenceReview.owner_id==identity,
            InferenceReview.activity=='status').order_by(InferenceReview.created_at_ns.desc()).limit(1)).first()
        if latest:
            data['error_code']=json.loads(latest.content_json).get('code')
    data['earliest_retry_ns']=result.get('earliest_retry_ns')
    if not include_answers:
        data['result_json']=None
    return data


@router.post('/runs/{identity}/revoke')
async def revoke(identity: str,request: Request,db: Session=Depends(get_session)):
    value=await body(request,RevocationRequest)
    if not value.reviewer.strip() or not value.reason.strip():
        raise HTTPException(422,detail={'code':'revocation_invalid'})
    resources.lock(db)
    row=db.get(InferenceRun,identity)
    if row is None:
        raise HTTPException(404,detail={'code':'inference_run_missing'})
    service.audit(db,row.authorization_id,'revocation',{'reason':value.reason,'run_id':identity},value.reviewer)
    prevented=row.status=='queued'
    if prevented:
        if row.job_id:
            resources.cancel_job(db,row.job_id)
        service.set_status(db,row,'blocked',code='approval_revoked')
    db.commit()
    return {'id':identity,'status':row.status,'prevented_dispatch':prevented,
        'notice':'approval_revoked' if prevented else 'delivery_may_have_occurred'}


@router.get('/runs/{identity}/reviews')
def review_history(identity: str,reviewer: str=Query(...,min_length=1,max_length=200),
        offset: int=Query(0,ge=0),limit: int=Query(20,ge=1,le=100),db: Session=Depends(get_session)):
    if not reviewer.strip():
        raise HTTPException(422,detail={'code':'named_reviewer_required'})
    resources.lock(db)
    row=db.get(InferenceRun,identity)
    if row is None:
        raise HTTPException(404,detail={'code':'inference_run_missing'})
    service.audit(db,identity,'review_exposure',{},reviewer)
    rows=db.exec(select(InferenceReview).join(InferenceRun,InferenceReview.owner_id==InferenceRun.id)
        .where(InferenceRun.input_identity==row.input_identity,
            InferenceReview.activity.in_(['blinded_reference','adjudication']))
        .order_by(InferenceReview.created_at_ns,InferenceReview.id).offset(offset).limit(limit+1)).all()
    db.commit()
    return {'items':[r.model_dump() for r in rows[:limit]],'next_offset':offset+limit if len(rows)>limit else None}


@router.post('/runs/{identity}/retry',status_code=202)
async def retry(identity: str,request: Request,db: Session=Depends(get_session)):
    value=await body(request,RunRequest)
    prior=db.get(InferenceRun,identity)
    if prior is None:
        raise HTTPException(404,detail={'code':'inference_run_missing'})
    return create_run(db,value,prior)


@router.post('/runs/{identity}/reviews',status_code=201)
async def reviews(identity: str,request: Request,db: Session=Depends(get_session)):
    value=await body(request,ReviewRequest)
    if not value.reviewer.strip():
        raise HTTPException(422,detail={'code':'named_reviewer_required'})
    if db.get(InferenceRun,identity) is None:
        raise HTTPException(404,detail={'code':'inference_run_missing'})
    resources.lock(db)
    if value.activity=='blinded_reference':
        current=db.get(InferenceRun,identity)
        exposed=db.exec(select(InferenceReview).join(InferenceRun,InferenceReview.owner_id==InferenceRun.id).where(
            InferenceRun.input_identity==current.input_identity,
            InferenceReview.reviewer==value.reviewer,
            InferenceReview.activity.in_(['model_exposure','export_exposure','review_exposure','adjudication','blinded_reference']))).first()
        if exposed:
            raise HTTPException(409,detail={'code':'independent_label_not_available'})
    try:
        labels=json.loads(value.labels_json)
        allowed = {
            'reported_task_tradeoff': {'present', 'explicit_absence', 'unmentioned', 'insufficient_evidence'},
            'reported_instruction_difficulty': {'present', 'explicit_absence', 'unmentioned', 'insufficient_evidence'},
            'automation_belief': {'expected_active', 'expected_inactive', 'conflicting', 'not_stated', 'insufficient_evidence'},
        }
        if not isinstance(labels, dict) or set(labels) != set(allowed):
            raise ValueError('incomplete labels')
        if any(not isinstance(labels[key], str) or labels[key] not in options for key, options in allowed.items()):
            raise ValueError('invalid label')
        service.canonical_bytes(labels)
    except (ValueError,TypeError):
        raise HTTPException(422,detail={'code':'review_labels_invalid'}) from None
    row=service.audit(db,identity,value.activity,labels,value.reviewer)
    if value.elapsed_seconds is not None:
        service.audit(db,identity,'coding_timing',{'review_id':row.id,'activity':value.activity,
            'elapsed_seconds':value.elapsed_seconds,'method':'browser_monotonic_self_started_v1'},value.reviewer)
    db.commit()
    return {'id':row.id,'activity':row.activity}


@router.get('/runs/{identity}/export')
def export(identity: str,reviewer: str=Query(...,min_length=1,max_length=200),db: Session=Depends(get_session)):
    from app.inference_service import export_bundle
    if not reviewer.strip():
        raise HTTPException(422,detail={'code':'named_reviewer_required'})
    resources.lock(db)
    service.audit(db,identity,'export_exposure',{},reviewer)
    content=checked(export_bundle,db,identity)
    db.commit()
    return Response(content,media_type='application/zip',headers={'Content-Disposition':'attachment; filename="inference.zip"'})
