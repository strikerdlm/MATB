"""Native single-occasion execution and exact child-source associations."""
import json
from fastapi import HTTPException
from sqlmodel import select
from .assessment_models import AssessmentAttempt, AssessmentSourceLink
from .assessment_adapters import source_attempt
from .study_admission import resolve_assignment, for_occasion


def native_context(db, suite):
    if suite.execution_purpose != 'study': return None
    attempt = source_attempt(db, 'openmatb_suite_session', suite.id)
    return resolve_assignment(db, attempt_id=attempt.id, instrument='openmatb', participant_id=suite.participant_id,
                              visit_id=suite.visit_id, purpose='study', require_started=True)


def storage_key(db, suite, profile):
    # Path lookup is also used for historical reads after purpose review.
    try:
        task = source_attempt(db, 'openmatb_suite_session', suite.id)
        context = for_occasion(db, task.occasion_id)
        return context['occasion_id']
    except HTTPException:
        return profile


def bind_block(db, suite, block):
    context = native_context(db, suite)
    if not context: return False
    task = source_attempt(db, 'openmatb_suite_session', suite.id)
    # One native source per assigned attempt; a repeat starts another suite/source identity.
    if db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.attempt_id == task.id,
        AssessmentSourceLink.source_table == 'openmatb_block_attempt')).first():
        raise HTTPException(409, 'Repeat the assigned assessment to acquire another native block.')
    db.add(AssessmentSourceLink(attempt_id=task.id, source_table='openmatb_block_attempt', source_id=block.id,
        purpose_provenance_id=task.purpose_provenance_id)); db.flush()
    prepare_rating(db, suite, block, context, task)
    block.legacy_import_status = 'inapplicable_assigned_occasion'
    return True


def finish_block(db, block, outcome):
    from .assessment_service import transition
    try: task = source_attempt(db, 'openmatb_block_attempt', block.id)
    except HTTPException: return
    try: for_occasion(db, task.occasion_id)
    except HTTPException: return
    if task.acquisition_state in {'created', 'started'}:
        transition(db, task.id, 'finished' if outcome == 'completed' and task.acquisition_state == 'started' else 'interrupted',
                   None if outcome == 'completed' else 'unknown')

    if outcome != 'completed':
        try: rating = source_attempt(db, 'openmatb_block_attempt', block.id, 'ratings')
        except HTTPException: return
        if rating.acquisition_state in {'created', 'started'}:
            transition(db, rating.id, 'interrupted', 'unknown')


def prepare_rating(db, suite, block, context, task):
    from .study_registry_models import StudyAssignment
    from .study_registry import get_version
    from .assessment_service import create_attempt
    from .assessment_schemas import AttemptIn
    assignment = db.get(StudyAssignment, context['assignment_id'])
    study = json.loads(get_version(db, context['version_id']).study_json)
    rating_spec = next((o for o in study['occasions'] if o['instrument'] == 'questionnaire' and o['target_key'] == context['occasion_key']), None)
    if rating_spec is None: raise HTTPException(409, 'Frozen native workload questionnaire occasion is required.')
    occasion_id = json.loads(assignment.occasions_json)[rating_spec['key']]
    existing = db.exec(select(AssessmentAttempt).where(AssessmentAttempt.occasion_id == occasion_id).order_by(AssessmentAttempt.ordinal)).all()
    if existing:
        matching = next((a for a in existing if a.target_attempt_id == task.id), None)
        if matching: return matching
        prior = existing[-1]
        rating = create_attempt(db, occasion_id, AttemptIn(execution_purpose='study', target_attempt_id=task.id), repeat_of=prior.id, reason='Ratings for the explicitly repeated target task')
    else: rating = create_attempt(db, occasion_id, AttemptIn(execution_purpose='study', target_attempt_id=task.id))
    db.add(AssessmentSourceLink(attempt_id=rating.id, source_table='openmatb_block_attempt', source_id=block.id,
        role='ratings', purpose_provenance_id=rating.purpose_provenance_id)); db.flush()
    return rating


def save_ratings(db, suite, block):
    from .assessment_service import transition
    context = native_context(db, suite)
    if not context: return
    task = source_attempt(db, 'openmatb_block_attempt', block.id)
    rating = prepare_rating(db, suite, block, context, task)
    if rating.acquisition_state == 'finished': return
    transition(db, rating.id, 'started')
    rating.raw_saving = 'saved'; rating.ratings = 'saved'
    transition(db, rating.id, 'finished')


def selected_task_source(db, suite):
    from .study_registry_models import StudyAttemptSelection
    task = source_attempt(db, 'openmatb_suite_session', suite.id)
    selection = db.get(StudyAttemptSelection, task.id)
    if selection:
        for identity in json.loads(selection.selections_json).values():
            source = db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.attempt_id == identity,
                AssessmentSourceLink.source_table == 'liftoff_session')).first()
            if source: return source.source_id
    return None
