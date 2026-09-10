"""Explicit occasion and attempt resources; no first/latest selection."""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from app.db import get_session
from app.assessment_models import AssessmentOccasion, AssessmentAttempt
from app.assessment_schemas import OccasionIn, AttemptIn, RepeatIn, InterruptIn
from app import assessment_service as service

router = APIRouter(prefix='/assessments', tags=['assessments'])


@router.post('/occasions', status_code=201)
def create_occasion(body: OccasionIn, db: Session = Depends(get_session)):
    row = service.create_occasion(db, body)
    db.commit()
    db.refresh(row)
    return row


@router.get('/occasions')
def occasions(participant_id: str | None = None, visit_id: int | None = None,
              instrument: str | None = None, db: Session = Depends(get_session)):
    query = select(AssessmentOccasion)
    for field, value in [('participant_id', participant_id), ('visit_id', visit_id), ('instrument', instrument)]:
        if value is not None:
            query = query.where(getattr(AssessmentOccasion, field) == value)
    return db.exec(query.order_by(AssessmentOccasion.order, AssessmentOccasion.id)).all()


@router.get('/occasions/{identity}')
def occasion(identity: str, db: Session = Depends(get_session)):
    row = db.get(AssessmentOccasion, identity)
    if row is None:
        raise HTTPException(404, 'assessment occasion not found')
    return row


@router.get('/occasions/{identity}/attempts')
def attempts(identity: str, db: Session = Depends(get_session)):
    occasion(identity, db)
    return [service.attempt_view(db, row) for row in db.exec(select(AssessmentAttempt).where(
        AssessmentAttempt.occasion_id == identity).order_by(AssessmentAttempt.ordinal)).all()]


@router.post('/occasions/{identity}/attempts', status_code=201)
def create_attempt(identity: str, body: AttemptIn, db: Session = Depends(get_session)):
    row = service.create_attempt(db, identity, body)
    db.commit()
    return service.attempt_view(db, row)


@router.get('/attempts/{identity}')
def attempt(identity: str, db: Session = Depends(get_session)):
    return service.attempt_view(db, service.get_attempt(db, identity))


@router.get('/attempts/{identity}/raw')
def raw(identity: str, db: Session = Depends(get_session)):
    return service.raw_view(db, identity)


@router.post('/attempts/{identity}/repeat', status_code=201)
def repeat(identity: str, body: RepeatIn, db: Session = Depends(get_session)):
    prior = service.get_attempt(db, identity)
    row = service.create_attempt(db, prior.occasion_id, body, repeat_of=identity, reason=body.reason)
    db.commit()
    return service.attempt_view(db, row)


@router.post('/attempts/{identity}/start')
def start(identity: str, db: Session = Depends(get_session)):
    row = service.transition(db, identity, 'started')
    db.commit()
    return service.attempt_view(db, row)


@router.post('/attempts/{identity}/finish')
def finish(identity: str, db: Session = Depends(get_session)):
    row = service.transition(db, identity, 'finished')
    db.commit()
    return service.attempt_view(db, row)


@router.post('/attempts/{identity}/interrupt')
def interrupt(identity: str, body: InterruptIn, db: Session = Depends(get_session)):
    row = service.transition(db, identity, 'interrupted', body.category)
    db.commit()
    return service.attempt_view(db, row)


@router.get('/sources/{table}/{identity}')
def source(table: str, identity: str, role: str = 'acquisition', db: Session = Depends(get_session)):
    from app.assessment_adapters import source_attempt
    return service.attempt_view(db, source_attempt(db, table, identity, role))


from app.assessment_schemas import OccasionClassificationIn


@router.get('/occasions/{identity}/classifications')
def classifications(identity: str, db: Session = Depends(get_session)):
    return service.occasion_history(db, identity)


@router.post('/occasions/{identity}/classifications', status_code=201)
def classify(identity: str, body: OccasionClassificationIn, db: Session = Depends(get_session)):
    service.classify_occasion(db, identity, body)
    db.commit()
    return service.occasion_history(db, identity)
