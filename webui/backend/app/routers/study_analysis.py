"""Researcher-triggered descriptive executions and immutable offline export."""
import io
import zipfile
from fastapi import APIRouter, Depends, Response, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select
from app.db import get_session
from app import study_analysis as service
from app.study_analysis_models import StudyAnalysisExecution, StudyAnalysisArtifact, HcfDerivation

router=APIRouter(prefix='/study/analyses',tags=['study descriptive analysis'])


class ExecutionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version_id: str
    attempts: dict[str,str]=Field(default_factory=dict)
    native_metric_ids: dict[str,list[str]]=Field(default_factory=dict)
    qualification_ids: dict[str,dict[str,str]]=Field(default_factory=dict)
    hcf_attempts: dict[str,str]=Field(default_factory=dict)
    actor: str=Field(min_length=1)
    reason: str=Field(min_length=1)


@router.get('/catalog')
def catalog():
    from app.study_analysis_catalog import CATALOG
    from app.components import is_component_active
    from importlib.util import find_spec
    components={'liftoff':'matb-liftoff','suas':'matb-suas','physiology':'matb-physiology','openmatb':'matb-openmatb','questionnaire':'matb-openmatb'}
    return [dict(metric=metric,instrument=instrument,units=units,available=(instrument not in components or is_component_active(components[instrument])) and (instrument not in {'liftoff','suas'} or find_spec('matb_integration.'+instrument) is not None)) for metric,(instrument,units) in CATALOG.items()]


@router.post('/preview')
def preview(body: ExecutionRequest,request: Request,db: Session=Depends(get_session)):
    return service.preview(db,{**body.model_dump(), **({"_selection_cutoff": request.scope["station_selection_cutoff"]} if request.scope.get("station_selection_cutoff") else {})})


@router.post('',status_code=201)
def execute(body: ExecutionRequest,request: Request,db: Session=Depends(get_session)):
    from app.study_registry import lock_registry
    lock_registry(db)
    row=service.execute(db,{**body.model_dump(), **({"_selection_cutoff": request.scope["station_selection_cutoff"]} if request.scope.get("station_selection_cutoff") else {})}); db.commit()
    return service.read(db,row.id)


@router.get('')
def list_executions(db: Session=Depends(get_session)):
    return [dict(id=r.id,version_id=r.version_id,plan_sha256=r.plan_sha256,data_sha256=r.data_sha256,created_at=r.created_at,actor=r.actor) for r in db.exec(select(StudyAnalysisExecution).order_by(StudyAnalysisExecution.created_at))]


@router.get('/hcf')
def hcf(db: Session=Depends(get_session)):
    import json
    return [dict(id=r.id,created_at=r.created_at,snapshot=json.loads(r.snapshot_json)) for r in db.exec(select(HcfDerivation).order_by(HcfDerivation.created_at))]


@router.post('/inputs',status_code=201)
def freeze_input(body: ExecutionRequest,request: Request,db: Session=Depends(get_session)):
    from app.study_registry import lock_registry
    lock_registry(db); row=service.freeze_input(db,{**body.model_dump(), **({"_selection_cutoff": request.scope["station_selection_cutoff"]} if request.scope.get("station_selection_cutoff") else {})});db.commit()
    return row


@router.post('/inputs/{input_id}/execute',status_code=201)
def execute_input(input_id: str,db: Session=Depends(get_session)):
    from app.study_registry import lock_registry
    lock_registry(db);row=service.execute_frozen(db,input_id);db.commit()
    return service.read(db,row.id)


@router.get('/{identity}')
def read(identity: str,db: Session=Depends(get_session)):
    result=service.read(db,identity,current=False)
    result['current_applicability']=dict(status='pending',changed=None,message='Frozen saved evidence. Request current applicability refresh when the station is idle.')
    return result


@router.post('/{identity}/refresh')
def refresh(identity: str,db: Session=Depends(get_session)):
    return service.read(db,identity)


@router.get('/{identity}/export')
def export(identity: str,db: Session=Depends(get_session)):
    service.read(db,identity,current=False)
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for row in db.exec(select(StudyAnalysisArtifact).where(StudyAnalysisArtifact.execution_id==identity).order_by(StudyAnalysisArtifact.path)):
            archive.writestr(row.path,row.content)
    return Response(output.getvalue(),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="study-analysis-{identity}.zip"'})
