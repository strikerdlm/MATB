"""Preparation commands reference immutable server assignments and exact attempts."""
from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select
from app.db import get_session
from app import study_preparation as service
from app.study_registry_models import StudyPreparation

router = APIRouter(prefix='/study', tags=['preparation'])


class StageResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    stage: Literal['demonstration', 'acknowledgement', 'comprehension']
    responses: dict[str, str] = Field(default_factory=dict)


class PracticeSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    attempt_id: str


@router.get('/assignments/{identity}/preparation')
def requirements(identity: str, db: Session = Depends(get_session)):
    from app.study_registry_models import StudyAssignment
    from fastapi import HTTPException
    import json
    assignment = db.get(StudyAssignment, identity)
    if not assignment: raise HTTPException(404, 'Assignment not found.')
    keys = json.loads(assignment.occasions_json)
    return dict(requirements={key: service.required_preparation(db, service.assignment_context(db, identity, key)) for key in keys},
        preparations=[service.preparation_view(db, r.id) for r in db.exec(select(StudyPreparation).where(StudyPreparation.assignment_id == identity)).all()])


@router.post('/assignments/{identity}/preparation/{key}', status_code=201)
def begin(identity: str, key: str, db: Session = Depends(get_session)):
    row = service.begin(db, identity, key); db.commit(); return service.preparation_view(db, row.id)


@router.get('/preparation/{identity}')
def view(identity: str, db: Session = Depends(get_session)):
    return service.preparation_view(db, identity)


@router.post('/preparation/{identity}/stages', status_code=201)
def stage(identity: str, body: StageResponse, db: Session = Depends(get_session)):
    service.record_stage(db, identity, body.stage, body.responses); db.commit(); return service.preparation_view(db, identity)


@router.post('/preparation/{identity}/practice', status_code=201)
def practice(identity: str, db: Session = Depends(get_session)):
    from app.assessment_service import attempt_view
    row = service.begin_practice(db, identity); db.commit(); return attempt_view(db, row)


@router.post('/preparation/{identity}/grade')
def grade(identity: str, body: PracticeSelection, db: Session = Depends(get_session)):
    service.finish_practice(db, identity, body.attempt_id); db.commit(); return service.preparation_view(db, identity)


@router.get('/participants/{identity}/exposure')
def exposures(identity: str, db: Session = Depends(get_session)):
    return service.exposure_history(db, identity)


class NativePresentation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    session_id: str


@router.post('/preparation/{identity}/native-presentation')
def native_presentation(identity: str, body: NativePresentation, db: Session = Depends(get_session)):
    service.bind_native_presentation(db, identity, body.session_id); db.commit(); return service.preparation_view(db, identity)


class PracticeReuse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: str
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)


@router.get('/preparation/{identity}/reusable-practice')
def reusable(identity: str, db: Session = Depends(get_session)):
    return service.reusable_practice(db, identity)


@router.post('/preparation/{identity}/reuse-practice', status_code=201)
def reuse(identity: str, body: PracticeReuse, db: Session = Depends(get_session)):
    service.reuse_practice(db, identity, body.event_id, body.actor, body.reason)
    db.commit(); return service.preparation_view(db, identity)


@router.post('/preparation/{identity}/stop')
def stop(identity: str, db: Session = Depends(get_session)):
    service.stop_preparation(db, identity); db.commit(); return service.preparation_view(db, identity)
