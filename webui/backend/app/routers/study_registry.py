"""Local researcher authoring, immutable version history and assignment entry routes."""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from app.db import get_session
from app import study_registry as service
from app.study_registry_schemas import DraftPayload, FreezeRequest, Attestation, AssignmentRequest, AmendmentRequest, SelectionRequest
from app.study_registry_models import StudyDraft, StudyVersion, StudyAssignment, StudyAmendment, StudyRecoveryInterval

router = APIRouter(prefix='/study', tags=['study registry'])


@router.get('/templates/{kind}')
def template(kind: str): return service.template(kind)


@router.get('/bindings')
def bindings(db: Session = Depends(get_session)):
    from app.study_bindings import binding_options
    return binding_options(db)


@router.get('/drafts')
def drafts(db: Session = Depends(get_session)): return db.exec(select(StudyDraft).order_by(StudyDraft.created_at)).all()


@router.post('/drafts', status_code=201)
def create(body: DraftPayload, db: Session = Depends(get_session)):
    row = service.create_draft(db, body.model_dump()); db.commit(); db.refresh(row); return row


@router.get('/drafts/{identity}')
def draft(identity: str, db: Session = Depends(get_session)): return service._draft(db, identity)


@router.put('/drafts/{identity}')
def edit(identity: str, body: DraftPayload, db: Session = Depends(get_session)):
    row = service.update_draft(db, identity, body.model_dump()); db.commit(); db.refresh(row); return row


@router.post('/drafts/{identity}/validate')
def validate(identity: str, db: Session = Depends(get_session)): return dict(issues=service.validate(db, identity))


@router.post('/drafts/{identity}/rehearse', status_code=201)
def rehearse(identity: str, db: Session = Depends(get_session)):
    row = service.rehearse(db, identity); db.commit(); db.refresh(row); return row


@router.post('/drafts/{identity}/freeze', status_code=201)
def freeze(identity: str, body: FreezeRequest, db: Session = Depends(get_session)):
    row = service.freeze(db, identity, body.model_dump()); db.commit(); return service.version_view(db, row.id)


@router.get('/versions')
def versions(db: Session = Depends(get_session)):
    return dict(active_version_id=service.active_version(db), versions=[service.version_view(db, v.id) for v in db.exec(select(StudyVersion).order_by(StudyVersion.created_at)).all()])


@router.get('/versions/{identity}')
def version(identity: str, db: Session = Depends(get_session)): return service.version_view(db, identity)


@router.post('/versions/{identity}/clone', status_code=201)
def clone(identity: str, db: Session = Depends(get_session)):
    view = service.version_view(db, identity)
    study, analysis = view['study'], view['analysis']
    study.update(version_id=None, analysis_plan_id=None); analysis.update(version_id=None, study_version_id=None)
    row = service.create_draft(db, dict(study=study, analysis=analysis)); db.commit(); db.refresh(row); return row


@router.post('/versions/{identity}/activate', status_code=201)
def activate(identity: str, body: Attestation, db: Session = Depends(get_session)):
    row = service.activate(db, identity, **body.model_dump()); db.commit(); db.refresh(row); return row


@router.post('/versions/{identity}/assign', status_code=201)
def assign(identity: str, body: AssignmentRequest, db: Session = Depends(get_session)):
    row = service.assign(db, identity, **body.model_dump()); db.commit(); db.refresh(row); return row


@router.post('/versions/{identity}/amend', status_code=201)
def amend(identity: str, body: AmendmentRequest, db: Session = Depends(get_session)):
    rows = service.amend(db, identity, body.assignment_ids, actor=body.actor, reason=body.reason); db.commit()
    for row in rows: db.refresh(row)
    return rows


@router.get('/assignments')
def assignments(participant_id: str | None = None, db: Session = Depends(get_session)):
    query = select(StudyAssignment)
    if participant_id: query = query.where(StudyAssignment.participant_id == participant_id)
    return [{**a.model_dump(), 'current': service.assignment_is_current(db, a), 'started': service.assignment_started(db, a)} for a in db.exec(query).all()]


@router.get('/assignments/{identity}')
def assignment(identity: str, db: Session = Depends(get_session)):
    from app.assessment_models import AssessmentAttempt
    from app.assessment_service import attempt_view
    row = db.get(StudyAssignment, identity)
    if row is None: raise HTTPException(404, 'assignment not found')
    occasions = json.loads(row.occasions_json)
    return dict(assignment=row, current=service.assignment_is_current(db, row), started=service.assignment_started(db, row),
        version=service.version_view(db, row.version_id), occasions=occasions,
        attempts={key: [attempt_view(db, a) for a in db.exec(select(AssessmentAttempt).where(AssessmentAttempt.occasion_id == value)).all()] for key, value in occasions.items()},
        recovery_intervals=db.exec(select(StudyRecoveryInterval).where(StudyRecoveryInterval.assignment_id == identity)).all(),
        amendments=db.exec(select(StudyAmendment).where(StudyAmendment.prior_assignment_id == identity)).all())


@router.post('/attempts/{identity}/prerequisites', status_code=201)
def selections(identity: str, body: SelectionRequest, db: Session = Depends(get_session)):
    from app.study_admission import select_prerequisites
    row = select_prerequisites(db, identity, body.selections); db.commit(); db.refresh(row); return row


@router.post('/assignments/{identity}/recovery/{key}/start', status_code=201)
def recovery_start(identity: str, key: str, body: Attestation, anchor_attempt_id: str, db: Session = Depends(get_session)):
    from app.assessment_models import AssessmentAttempt
    from app.study_admission import resolve_assignment
    service.lock_registry(db)
    service.named(body.actor)
    row = db.get(StudyAssignment, identity)
    if row is None or not service.assignment_is_current(db, row): raise HTTPException(409, 'Current assignment required.')
    spec = json.loads(service.get_version(db, row.version_id).study_json)
    interval = next((i for i in spec['recovery_intervals'] if i['key'] == key), None)
    anchor = db.get(AssessmentAttempt, anchor_attempt_id)
    if not interval or anchor is None or anchor.occasion_id != json.loads(row.occasions_json)[interval['anchor_key']] or anchor.acquisition_state != 'finished':
        raise HTTPException(422, 'Select the completed exact recovery anchor attempt.')
    anchor_spec = next(o for o in spec['occasions'] if o['key'] == interval['anchor_key'])
    resolve_assignment(db, attempt_id=anchor.id, instrument=anchor_spec['instrument'], participant_id=row.participant_id, visit_id=row.visit_id, purpose='study')
    prior = db.get(StudyRecoveryInterval, (identity, key))
    if prior:
        if prior.anchor_attempt_id != anchor.id: raise HTTPException(409, 'Recovery anchor is already recorded.')
        return prior
    recorded = StudyRecoveryInterval(assignment_id=identity, interval_key=key, anchor_attempt_id=anchor.id, actor=body.actor, reason=body.reason)
    db.add(recorded); db.commit(); db.refresh(recorded); return recorded


@router.post('/assignments/{identity}/recovery/{key}/finish')
def recovery_finish(identity: str, key: str, body: Attestation, db: Session = Depends(get_session)):
    from datetime import datetime, timezone
    service.lock_registry(db)
    service.named(body.actor)
    row = db.get(StudyRecoveryInterval, (identity, key))
    assignment = db.get(StudyAssignment, identity)
    if row is None or assignment is None: raise HTTPException(409, 'Start the authored recovery interval first.')
    spec = json.loads(service.get_version(db, assignment.version_id).study_json)
    interval = next(i for i in spec['recovery_intervals'] if i['key'] == key)
    now = datetime.now(timezone.utc)
    if (now - row.started_at.replace(tzinfo=timezone.utc)).total_seconds() < interval['duration_seconds']: raise HTTPException(409, 'Authored recovery duration has not elapsed.')
    if row.ended_at is None:
        row.ended_at = now; row.finish_actor = body.actor; row.finish_reason = body.reason
    db.add(row); db.commit(); db.refresh(row); return row
