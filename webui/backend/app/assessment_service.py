"""Transactional lifecycle and source links. Callers own commit/rollback."""
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import inspect, text
from sqlmodel import select
from .assessment_models import AssessmentOccasion, AssessmentAttempt, AssessmentSourceLink, now
from .models import Participant, Visit


def get_attempt(db, identity):
    row = db.get(AssessmentAttempt, identity)
    if row is None:
        raise HTTPException(404, 'assessment attempt not found')
    return row


def create_occasion(db, body):
    if db.get(Participant, body.participant_id) is None:
        raise HTTPException(404, 'participant not found')
    from app.astra_roster import require_active
    require_active(db, body.participant_id)
    visit = db.get(Visit, body.visit_id)
    if visit is None or visit.participant_id != body.participant_id:
        raise HTTPException(422, 'occasion requires an assigned participant visit')
    if body.accompanying_occasion_id:
        other = db.get(AssessmentOccasion, body.accompanying_occasion_id)
        if (other is None or other.participant_id != body.participant_id or other.visit_id != body.visit_id
                or not body.collection_group_id or other.collection_group_id != body.collection_group_id
                or body.instrument != 'physiology'):
            raise HTTPException(422, 'accompanying physiology requires the same participant, visit and collection group')
    row = AssessmentOccasion(**body.model_dump())
    db.add(row)
    db.flush()
    return row


def create_attempt(db, occasion_id, body, *, repeat_of=None, reason=None):
    from .purpose_service import declare_acquisition
    occasion = db.get(AssessmentOccasion, occasion_id)
    if occasion is None:
        raise HTTPException(404, 'assessment occasion not found')
    from app.astra_roster import require_active
    require_active(db, occasion.participant_id)
    if occasion.visit_id is None or occasion.phase is None:
        raise HTTPException(422, 'Create a new assigned occasion before acquiring; historical context remains unknown')
    context = None
    if body.execution_purpose == 'study':
        from .study_admission import for_occasion
        from .study_registry import lock_registry
        lock_registry(db)
        context = for_occasion(db, occasion_id)
    rows = db.exec(select(AssessmentAttempt).where(AssessmentAttempt.occasion_id == occasion_id)).all()
    if rows and not repeat_of:
        raise HTTPException(409, {'code': 'explicit_repeat_required', 'attempt_ids': [r.id for r in rows]})
    if repeat_of and any(r.acquisition_state in {'created', 'started'} for r in rows):
        raise HTTPException(409, 'finish or interrupt the active attempt before repeating')
    if repeat_of:
        prior = get_attempt(db, repeat_of)
        if prior.occasion_id != occasion_id or prior.acquisition_state not in {'finished', 'interrupted', 'unknown'}:
            raise HTTPException(409, 'finish or interrupt the prior attempt before repeating')
    if context and repeat_of:
        policy = context['repeat_policy']
        cause = prior.interruption_category if prior.acquisition_state == 'interrupted' else 'intentional_repeat'
        if len(rows) >= policy['max_attempts'] or (cause or 'unknown') not in policy['permitted_causes']:
            raise HTTPException(409, dict(code='study_repeat_not_permitted', message='The frozen repeat cause or attempt limit does not permit this repeat.'))
    target_id = body.target_attempt_id
    if occasion.instrument == 'questionnaire' and not target_id:
        raise HTTPException(422, 'questionnaire requires exact target_attempt_id')
    if target_id:
        target = get_attempt(db, target_id)
        target_occasion = db.get(AssessmentOccasion, target.occasion_id)
        if context:
            from .study_registry_models import StudyAssignment
            assignment = db.get(StudyAssignment, context['assignment_id'])
            if target.occasion_id != json.loads(assignment.occasions_json).get(context['target_key']):
                raise HTTPException(422, 'Questionnaire target differs from the exact frozen assigned task.')
        if (occasion.instrument != 'questionnaire' or target_occasion.instrument == 'questionnaire'
                or (target_occasion.participant_id, target_occasion.visit_id) != (occasion.participant_id, occasion.visit_id)):
            raise HTTPException(422, 'questionnaire target must be a task attempt in the same participant visit')
    row = AssessmentAttempt(occasion_id=occasion_id, ordinal=max([r.ordinal for r in rows], default=0) + 1,
        execution_purpose=body.execution_purpose, repeat_of=repeat_of, repeat_reason=reason, target_attempt_id=target_id)
    declare_acquisition(db, row, purpose=body.execution_purpose)
    return row


def transition(db, identity, state, category=None, *, native_session_id=None):
    if state == 'started':
        from .study_registry import lock_registry
        lock_registry(db)
    row = get_attempt(db, identity)
    if state == 'started' and row.execution_purpose == 'study':
        from .study_admission import resolve_assignment, require_prerequisites
        occasion = db.get(AssessmentOccasion, row.occasion_id)
        context = resolve_assignment(db, attempt_id=identity, instrument=occasion.instrument, participant_id=occasion.participant_id, visit_id=occasion.visit_id, purpose='study')
        require_prerequisites(db, identity, context)
    if row.acquisition_state == state and (state != 'interrupted' or row.interruption_category == category):
        return row
    allowed = {'started': {'created'}, 'finished': {'started'}, 'interrupted': {'created', 'started'}}
    if row.acquisition_state not in allowed[state]:
        raise HTTPException(409, {'code': 'invalid_attempt_transition', 'state': row.acquisition_state})
    if state == 'started' and row.execution_purpose == 'study':
        if context['instrument'] == 'openmatb':
            from .study_preflight import require_held_launch
            if native_session_id is None:
                require_held_launch(context)
            else:
                from .assessment_adapters import source_attempt
                if source_attempt(db, 'openmatb_suite_session', native_session_id).id != row.id:
                    raise HTTPException(409, 'Native release must bind this exact attempt.')
        from .study_preparation import freeze_preparation_admission
        freeze_preparation_admission(db, row, context)
    if state in {'finished', 'interrupted'}:
        from .station_resources import finish
        finish(db, row.id, uncertain=state == 'interrupted' and category == 'unknown')
    row.acquisition_state = state
    if state == 'started':
        row.started_at = now()
    else:
        row.finished_at = now()
        row.interruption_category = category
    db.add(row)
    db.flush()
    if state in {'finished', 'interrupted'}:
        from .crew_exports import enqueue
        enqueue(db, row)
    return row


def source_links(db, identity):
    return db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.attempt_id == identity)).all()


def attempt_view(db, row):
    from .study_preparation import practice_context
    from .study_registry_models import StudyPreparationAdmission
    admission = db.get(StudyPreparationAdmission, row.id)
    db.refresh(row)
    from .assessment_adapters import receipt_facets
    context = None
    if row.execution_purpose == 'study':
        from .study_admission import for_occasion
        try: context = for_occasion(db, row.occasion_id)
        except HTTPException: pass
    return {**row.model_dump(mode='json'), 'assignment_context': context, 'sources': [x.model_dump() for x in source_links(db, row.id)],
        'preparation_admission': admission.model_dump(mode='json') if admission else None,
        'preparation_context': practice_context(db, row.id) if row.execution_purpose == 'practice' else None,
        'receipt': receipt_facets(db, row)}


def raw_view(db, identity):
    row = get_attempt(db, identity)
    records = []
    tables = set(inspect(db.connection()).get_table_names())
    from .assessment_adapters import SOURCE_INSTRUMENTS
    for link in source_links(db, identity):
        if link.source_table not in SOURCE_INSTRUMENTS or link.source_table not in tables:
            continue
        source = db.execute(text(f'SELECT * FROM "{link.source_table}" WHERE id=:id'), {'id': link.source_id}).mappings().first()
        if source:
            records.append({'link': link.model_dump(), 'record': dict(source)})
    return {'attempt': attempt_view(db, row), 'records': records, 'record': records[0]['record'] if records else None}


def payload_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def prepare_result(db, identity, *, instrument, participant_id, visit_id, purpose, payload):
    row = get_attempt(db, identity)
    occasion = db.get(AssessmentOccasion, row.occasion_id)
    if (occasion.instrument != instrument or occasion.participant_id != participant_id
            or (visit_id is not None and occasion.visit_id != visit_id) or row.execution_purpose != purpose):
        raise HTTPException(422, 'attempt does not match acquisition context or declared purpose')
    from .study_admission import resolve_assignment
    context = resolve_assignment(db, attempt_id=identity, instrument=instrument, participant_id=participant_id, visit_id=visit_id, purpose=purpose, require_started=True)
    from .study_preparation import practice_context
    preparation = practice_context(db, identity, validate=True) if purpose == 'practice' else None
    if preparation and payload.get('payload', payload).get('locale') != preparation['locale']:
        raise HTTPException(422, 'Practice language differs from the frozen preparation.')
    if context:
        submitted = payload.get('payload', payload)
        if submitted.get('locale') != context['locale'] or submitted.get('fast_mode', False):
            raise HTTPException(422, 'Payload language/configuration differs from the frozen assignment.')
    digest = payload_hash(payload)
    if row.final_payload_sha256:
        if row.final_payload_sha256 != digest:
            raise HTTPException(409, {'code': 'final_payload_conflict', 'attempt_id': row.id,
                                     'repeat_url': f'/assessments/attempts/{row.id}/repeat'})
        return row, True
    if row.acquisition_state not in {'started', 'finished'}:
        raise HTTPException(409, 'start this attempt before acquisition; repeat interrupted attempts')
    return row, False


def save_result(db, attempt, source, payload):
    source.purpose_provenance_id = attempt.purpose_provenance_id
    source.attempt_id = attempt.id
    db.add(source)
    db.flush()
    db.add(AssessmentSourceLink(attempt_id=attempt.id, source_table=source.__tablename__, source_id=str(source.id),
                               purpose_provenance_id=attempt.purpose_provenance_id))
    attempt.final_payload_sha256 = payload_hash(payload)
    attempt.raw_saving = 'saved'
    attempt.processing = 'complete'
    transition(db, attempt.id, 'finished')
    db.flush()


def occasion_history(db, identity):
    from .assessment_models import AssessmentOccasionClassification
    occasion = db.get(AssessmentOccasion, identity)
    if occasion is None:
        raise HTTPException(404, 'assessment occasion not found')
    history = []
    for row in db.exec(select(AssessmentOccasionClassification).where(
            AssessmentOccasionClassification.occasion_id == identity).order_by(AssessmentOccasionClassification.id)).all():
        item = row.model_dump(mode='json')
        item['supporting_references'] = json.loads(item.pop('supporting_references_json'))
        history.append(item)
    return {'occasion_id': identity, 'history': history, 'current': history[-1] if history else None}


def classify_occasion(db, identity, body):
    from .assessment_models import AssessmentOccasionClassification
    occasion_history(db, identity)
    occasion = db.get(AssessmentOccasion, identity)
    if occasion.origin not in {'legacy', 'legacy_compat'}:
        raise HTTPException(422, 'retrospective association requires historical/legacy context')
    visit = db.get(Visit, body.visit_id)
    if visit is None or visit.participant_id != occasion.participant_id:
        raise HTTPException(422, 'reviewed visit must belong to the original participant')
    if body.reviewer.startswith(('system:', 'local:')):
        raise HTTPException(422, 'named human reviewer required')
    row = AssessmentOccasionClassification(occasion_id=identity,
        **body.model_dump(exclude={'supporting_references'}),
        supporting_references_json=json.dumps(body.supporting_references, allow_nan=False))
    db.add(row)
    db.flush()


def bind_new_source(db, attempt_id, source, *, purpose):
    """Bind a transient optional source to the declaration made before acquisition.

    Runtime adapters call declare_acquisition(..., attempt_id=...) after the study
    admission layer chooses an exact attempt. This never reclassifies observations.
    """
    from .assessment_adapters import SOURCE_INSTRUMENTS
    attempt = get_attempt(db, attempt_id)
    occasion = db.get(AssessmentOccasion, attempt.occasion_id)
    instrument = SOURCE_INSTRUMENTS.get(source.__tablename__)
    if instrument is None or occasion.instrument != instrument:
        raise ValueError('attempt instrument does not match source')
    if attempt.execution_purpose != purpose or attempt.acquisition_state not in {'created', 'started'}:
        raise ValueError('attempt purpose/state does not admit a new source')
    if getattr(source, 'participant_id', None) != occasion.participant_id:
        raise ValueError('attempt participant does not match source')
    if getattr(source, 'visit_id', occasion.visit_id) != occasion.visit_id:
        raise ValueError('attempt visit does not match source')
    if source_links(db, attempt_id):
        raise ValueError('attempt already has an acquisition source; explicitly repeat it')
    source.purpose_provenance_id = attempt.purpose_provenance_id
    if hasattr(source, 'attempt_id'):
        source.attempt_id = attempt.id
    db.add(source)
    db.flush()
    db.add(AssessmentSourceLink(attempt_id=attempt.id, source_table=source.__tablename__, source_id=str(source.id),
                              purpose_provenance_id=attempt.purpose_provenance_id))
    db.flush()
    return attempt.purpose_provenance_id
