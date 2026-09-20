"""Local semantic ledger adapter. Never mutates scientific evidence rows."""
import json
import os
import time
from uuid import uuid4
from sqlmodel import Session, select
from matb_integration.inference.contracts import InferenceInputV1, ReviewAnnotationV1, canonical_bytes, sha256
from matb_integration.inference.projection import project_review
from matb_integration.inference.question_packs import load_question_pack
from .evidence_models import EvidenceArtifact, EvidenceCapture, EvidenceMetric, EvidenceRecord, EvidenceRun
from .inference_models import InferenceAnnotation, InferenceArtifact, InferenceRun, InferenceReview


class InferenceError(ValueError):
    """Bounded local diagnostic code, safe for ordinary logs."""


def create_annotation(db: Session, annotation: ReviewAnnotationV1):
    if db.get(EvidenceCapture, annotation.capture_id) is None:
        raise InferenceError('capture_missing')
    events = set(db.exec(select(EvidenceRecord.event_id).where(
        EvidenceRecord.capture_id == annotation.capture_id)).all())
    if not set(annotation.source_event_ids).issubset(events):
        raise InferenceError('cross_capture_event')
    if annotation.supersedes_annotation_id:
        prior = db.get(InferenceAnnotation, annotation.supersedes_annotation_id)
        if prior is None or prior.capture_id != annotation.capture_id:
            raise InferenceError('annotation_parent_missing')
    existing = db.get(InferenceAnnotation, annotation.annotation_id)
    if existing:
        if existing.content_hash != sha256(annotation):
            raise InferenceError('annotation_immutable')
        return existing
    row = InferenceAnnotation(id=annotation.annotation_id, capture_id=annotation.capture_id,
        content_json=annotation.model_dump_json(), content_hash=sha256(annotation))
    db.add(row)
    db.flush()
    return row


def resolve_input(db: Session, capture_id: str, run_id: str, annotation_id: str, pack_id: str):
    if run_id == 'latest':
        raise InferenceError('frozen_run_required')
    capture = db.get(EvidenceCapture, capture_id)
    run = db.get(EvidenceRun, run_id)
    note = db.get(InferenceAnnotation, annotation_id)
    if capture is None or run is None or run.capture_id != capture_id or not run.fingerprint or not run.result_json or run.status in {'pending', 'failed'}:
        raise InferenceError('source_run_unavailable')
    if note is None or note.capture_id != capture_id:
        raise InferenceError('annotation_unavailable')
    annotation = ReviewAnnotationV1.model_validate_json(note.content_json)
    if sha256(annotation) != note.content_hash:
        raise InferenceError('annotation_integrity')
    artifacts = db.exec(select(EvidenceArtifact).where(EvidenceArtifact.capture_id == capture_id)).all()
    if not artifacts or any(sha256(a.content) != a.sha256 for a in artifacts):
        raise InferenceError('artifact_integrity')
    metrics = db.exec(select(EvidenceMetric).where(EvidenceMetric.run_id == run_id)).all()
    source = dict(capture_id=capture_id, evidence_run_id=run_id,
        reconciliation_fingerprint=run.fingerprint, source_artifact_hashes=[a.sha256 for a in artifacts],
        event_ids=db.exec(select(EvidenceRecord.event_id).where(EvidenceRecord.capture_id == capture_id)).all(),
        quality_snapshot=dict(execution_purpose=capture.execution_purpose,
            metrics=[dict(id=m.id, key=m.key, eligible=m.eligible, status=m.status) for m in metrics]),
        exclusions=[dict(field=m.key, reason=m.status, eligible=False) for m in metrics if not m.eligible])
    return project_review(source, annotation, load_question_pack(pack_id))


def artifact(db, owner, role, content, identity=None):
    row = InferenceArtifact(id=identity or str(uuid4()), owner_id=owner, role=role,
        content=content, sha256=sha256(content))
    db.add(row)
    db.flush()
    return row


def read_artifact(db, identity, role):
    row = db.get(InferenceArtifact, identity)
    if row is None or row.role != role or sha256(row.content) != row.sha256:
        raise InferenceError('inference_artifact_integrity')
    return row


def audit(db, owner, activity, content, reviewer='system'):
    row = InferenceReview(id=str(uuid4()), owner_id=owner, activity=activity,
        reviewer=reviewer, created_at_ns=str(time.time_ns()), content_json=canonical_bytes(content).decode())
    db.add(row)
    db.flush()
    return row


def enqueue_preview(db, capture_id, run_id, annotation_id, pack_id):
    from .station_resources import enqueue
    return enqueue(db, 'semantic_review', dict(operation='project', capture_id=capture_id,
        evidence_run_id=run_id, annotation_id=annotation_id, pack_id=pack_id))


def set_status(db, run, status, **details):
    run.status = status
    db.add(run)
    audit(db, run.id, 'status', dict(status=status, **details))


def remote_enabled():
    from .components import is_component_active
    return (is_component_active('matb-semantic-review') and
        os.getenv('MATB_ENABLE_SEMANTIC_REVIEW') == '1' and
        os.getenv('MATB_JEV_MODE', 'off') == 'post_session_remote')


async def execute_semantic_job(engine, job):
    from . import station_resources as resources
    from matb_integration.inference.privacy import validate_egress, EgressError
    from matb_integration.inference.client import JevProvider
    from matb_integration.inference.response_validation import validate_response
    payload = json.loads(job.payload_json)
    with Session(engine) as db:
        resources.lock(db)  # Serialize the approval check with local revocation.
        owner = db.get(resources.StationJob, job.id)
        state = db.get(resources.StationState, 1)
        if owner is None or owner.status != 'running' or state is None or state.maintenance or json.loads(state.reservation_json) or json.loads(state.lanes_json):
            raise InferenceError('station_not_admitted')
        if resources.running(db).id != job.id:
            raise InferenceError('station_owner_mismatch')
        if payload['operation'] == 'project':
            value = resolve_input(db, payload['capture_id'], payload['evidence_run_id'], payload['annotation_id'], payload['pack_id'])
            artifact(db, job.id, 'input', value.model_dump_json().encode(), identity=job.id)
            db.commit()
            return
        if payload['operation'] != 'evaluate':
            raise InferenceError('unsupported_operation')
        run = db.get(InferenceRun, payload['run_id'])
        if run is None or run.status != 'queued':
            raise InferenceError('attempt_not_queued')
        if not remote_enabled():
            set_status(db, run, 'blocked', code='provider_disabled')
            db.commit()
            return
        try:
            frozen = InferenceInputV1.model_validate_json(read_artifact(db, run.preview_id, 'input').content)
            current = resolve_input(db, frozen.capture_id, frozen.evidence_run_id, frozen.annotation_id, frozen.question_pack_id)
            if current.input_identity != frozen.input_identity:
                raise InferenceError('frozen_input_changed')
            authorization = json.loads(read_artifact(db, run.authorization_id, 'authorization').content)
            revoked = db.exec(select(InferenceReview).where(InferenceReview.owner_id == run.authorization_id,
                InferenceReview.activity == 'revocation')).first()
            if revoked:
                authorization['revoked'] = True
            reviewed = InferenceInputV1(**(frozen.model_dump() | {'redaction_status': 'reviewed'}))
            validate_egress(reviewed, authorization, frozen.provider_id)
        except (InferenceError, EgressError, ValueError):
            set_status(db, run, 'blocked', code='input_or_egress_rejected')
            db.commit()
            return
        set_status(db, run, 'sending')
        db.commit()
        run_id = run.id
    # No database session or derivation lock spans provider I/O.
    attempt = await JevProvider().evaluate(json.loads(frozen.outbound_bytes))
    result = validate_response(json.loads(frozen.outbound_bytes), attempt)
    with Session(engine) as db:
        run = db.get(InferenceRun, run_id)
        owner = db.get(resources.StationJob, job.id)
        artifact(db, run.id, 'provider_attempt', attempt.model_dump_json().encode())
        artifact(db, run.id, 'response', attempt.raw_response)
        if owner is None or owner.status != 'running' or run.status != 'sending':
            set_status(db, run, 'late', code='cancelled_or_lost_ownership')
            artifact(db, run.id, 'late_result', result.model_dump_json().encode())
        else:
            run.result_json = result.model_dump_json()
            set_status(db, run, result.outcome)
        db.commit()


def recover_inference(engine):
    from .station_resources import StationJob
    with Session(engine) as db:
        for run in db.exec(select(InferenceRun).where(InferenceRun.status.in_(['sending','queued']))).all():
            if run.status=='sending':
                set_status(db, run, 'outcome_unknown', code='backend_restart')
            else:
                job=db.get(StationJob,run.job_id) if run.job_id else None
                if job is None or job.status in {'cancelled','failed','complete'}:
                    set_status(db,run,'cancelled' if job and job.status=='cancelled' else 'blocked',code='job_terminated')
        db.commit()


def sync_queued_status(db, run):
    from .station_resources import StationJob
    if run.status!='queued': return
    job=db.get(StationJob,run.job_id) if run.job_id else None
    if job is None or job.status in {'cancelled','failed','complete'}:
        set_status(db,run,'cancelled' if job and job.status=='cancelled' else 'blocked',code='job_terminated')


def fail_semantic_job(engine,job):
    payload=json.loads(job.payload_json)
    if payload.get('operation')!='evaluate': return
    with Session(engine) as db:
        run=db.get(InferenceRun,payload.get('run_id'))
        if run and run.status in {'sending','queued'}:
            set_status(db,run,'outcome_unknown' if run.status=='sending' else 'blocked',code='local_execution_failure')
        db.commit()


def export_bundle(db, identity):
    from matb_integration.inference.contracts import ProviderAttempt
    from matb_integration.inference.replay import build_bundle
    run=db.get(InferenceRun,identity)
    if run is None:
        raise InferenceError('run_missing')
    value=InferenceInputV1.model_validate_json(read_artifact(db,run.preview_id,'input').content)
    row=db.exec(select(InferenceArtifact).where(InferenceArtifact.owner_id==identity,
        InferenceArtifact.role=='provider_attempt')).first()
    if row is None or sha256(row.content)!=row.sha256:
        raise InferenceError('attempt_unavailable')
    attempt=ProviderAttempt.model_validate_json(row.content)
    chain=[]
    annotation_id=value.annotation_id
    while annotation_id:
        if len(chain)>=100 or any(n['annotation_id']==annotation_id for n in chain):
            raise InferenceError('annotation_chain_invalid')
        note=db.get(InferenceAnnotation,annotation_id)
        if note is None:
            raise InferenceError('annotation_unavailable')
        parsed=ReviewAnnotationV1.model_validate_json(note.content_json)
        if sha256(parsed)!=note.content_hash or parsed.capture_id!=value.capture_id:
            raise InferenceError('annotation_integrity')
        chain.append(parsed.model_dump(mode='json'))
        annotation_id=parsed.supersedes_annotation_id
    approval=read_artifact(db,run.authorization_id,'authorization')
    siblings=db.exec(select(InferenceRun).where(InferenceRun.input_identity==run.input_identity)).all()
    owners=[r.id for r in siblings]+[r.authorization_id for r in siblings]
    history=db.exec(select(InferenceReview).where(InferenceReview.owner_id.in_(owners))
        .order_by(InferenceReview.created_at_ns,InferenceReview.id).limit(2001)).all()
    if len(history)>2000:
        raise InferenceError('audit_export_limit')
    audit_rows=[r.model_dump() for r in history]
    reviews=[r for r in audit_rows if r['activity'] in {'blinded_reference','adjudication','status'}]
    provenance={'annotations':chain,'approval':json.loads(approval.content),'approval_json':approval.content.decode('utf-8'),
        'approval_hash':approval.sha256,'approval_id':approval.id,'run_id':run.id,
        'input_identity':run.input_identity,'audit':audit_rows}
    return build_bundle(value,attempt,reviews,disposition=run.status,provenance=provenance)
