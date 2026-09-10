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
                              visit_id=suite.visit_id, purpose='study', require_started=not suite.lifecycle.startswith('PREFLIGHT_'))


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


def finish_block(db, block, outcome, *, cause="unknown"):
    from .assessment_service import transition
    try: task = source_attempt(db, 'openmatb_block_attempt', block.id)
    except HTTPException: return
    try: for_occasion(db, task.occasion_id)
    except HTTPException: return
    if task.acquisition_state in {'created', 'started'}:
        transition(db, task.id, 'finished' if outcome == 'completed' and task.acquisition_state == 'started' else 'interrupted',
                   None if outcome == 'completed' else cause)

    if outcome != 'completed':
        try: rating = source_attempt(db, 'openmatb_block_attempt', block.id, 'ratings')
        except HTTPException: return
        if rating.acquisition_state in {'created', 'started'}:
            transition(db, rating.id, 'interrupted', cause)


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


def submit_assigned_ratings(db, suite, block, request):
    """Save only the explicitly bound questionnaire; repeats get independent raw sources."""
    from hashlib import sha256
    from pathlib import Path
    from .assessment_service import transition
    from .study_registry import canonical, lock_registry
    from .study_registry_models import StudyNativeRating
    from .study_admission import select_prerequisites
    lock_registry(db)
    context = native_context(db, suite)
    task = source_attempt(db, 'openmatb_block_attempt', block.id)
    if task.acquisition_state != 'finished':
        raise HTTPException(409, 'Finish the exact native task before its questionnaire.')
    rating = (db.get(AssessmentAttempt, request.questionnaire_attempt_id) if request.questionnaire_attempt_id
              else source_attempt(db, 'openmatb_block_attempt', block.id, 'ratings'))
    if rating is None or rating.target_attempt_id != task.id:
        raise HTTPException(409, 'Select a questionnaire attempt targeting this exact native task.')
    rating_context = resolve_assignment(db, attempt_id=rating.id, instrument='questionnaire',
        participant_id=suite.participant_id, visit_id=suite.visit_id, purpose='study')
    if rating_context['target_key'] != context['occasion_key']:
        raise HTTPException(409, 'Questionnaire target differs from this native task.')
    payload = canonical({'nasa_tlx': request.nasa_tlx, 'bedford': request.bedford})
    saved = db.get(StudyNativeRating, rating.id)
    if saved:
        if saved.payload_json != payload:
            from .openmatb_runtime import OpenMatbRuntimeError
            raise OpenMatbRuntimeError('openmatb_scale_already_saved')
        return False
    if rating.acquisition_state not in {'created', 'started'}:
        raise HTTPException(409, 'Select a created questionnaire attempt; interrupted attempts remain interrupted.')
    if rating_context['prerequisite_keys'] and rating.acquisition_state == 'created':
        select_prerequisites(db, rating.id, {context['occasion_key']: task.id})
    if rating.acquisition_state == 'created': transition(db, rating.id, 'started')
    else:
        from .study_admission import require_prerequisites
        require_prerequisites(db, rating.id, rating_context)
    record = StudyNativeRating(id=rating.id, target_attempt_id=task.id, session_id=suite.id,
        block_instance_id=block.id, payload_json=payload, payload_sha256=sha256(payload.encode()).hexdigest())
    db.add(record)
    db.add(AssessmentSourceLink(attempt_id=rating.id, source_table='study_native_rating', source_id=rating.id,
        purpose_provenance_id=rating.purpose_provenance_id))
    rating.raw_saving = 'saved'; rating.ratings = 'saved'; transition(db, rating.id, 'finished')
    score = dict(instrument_version='MATB-FAC-WORKLOAD-1.0', occasion_id=context['occasion_id'],
        questionnaire_attempt_id=rating.id, target_attempt_id=task.id, block_instance_id=block.id,
        condition=block.profile, locale=suite.locale, nasa_tlx=request.nasa_tlx,
        rtlx_mean_0_100=sum(request.nasa_tlx.values()) / 6, bedford=request.bedford,
        bedford_status='exploratory_translation_not_locally_validated')
    scores = json.loads(suite.scores_json)
    first = context['occasion_id'] not in scores
    scores[context['occasion_id'] if first else rating.id] = score
    directory = Path(suite.artifact_root) / 'scales'
    (directory / 'ratings').mkdir(parents=True, exist_ok=True)
    _write_rating_artifact(directory / 'ratings' / f'{rating.id}.json', canonical(score) + '\n')
    if first:
        _write_rating_artifact(directory / f"{context['occasion_id']}.json", canonical(score) + '\n')
    # The original block projection is written only by its original questionnaire.
    original = source_attempt(db, 'openmatb_block_attempt', block.id, 'ratings')
    if original.id == rating.id:
        from .study_registry_models import now
        block.ratings_json = payload; block.ratings_saved_at = now(); db.add(block)
    suite.scores_json = canonical(scores)
    if suite.lifecycle == 'AWAITING_SCALE':
        from .study_registry_models import now
        suite.current_block_index += 1; suite.active_block_instance_id = None
        suite.lifecycle = 'COMPLETE'; suite.finished_at = now()
    db.add(suite)
    return True


def _write_rating_artifact(path, content):
    # The caller holds the registry's SQLite write lock. Preserve an existing
    # artifact, including an identical file left by a failed database commit.
    if path.exists():
        if path.read_bytes() != content.encode('utf-8'):
            raise HTTPException(409, 'Existing rating artifact differs; preserve it for review before retrying.')
        return
    from matb_integration.recording.artifacts import write_json_artifact
    write_json_artifact(path, content, serializer=lambda value: value)
