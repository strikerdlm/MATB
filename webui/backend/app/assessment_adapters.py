"""Additive adapters for installed source tables; never import optional runtimes."""
import json
from sqlalchemy import inspect, text
from sqlmodel import select
from .assessment_models import AssessmentOccasion, AssessmentAttempt, AssessmentSourceLink

SOURCE_INSTRUMENTS = {
    'pvt_assessment': 'pvt', 'screenresult': 'screen', 'practiceresult': None,
    'archived_assessment': None, 'openmatb_suite_session': 'openmatb',
    'openmatb_block_attempt': 'openmatb', 'liftoff_session': 'liftoff',
    'simulation_session': 'suas', 'technical_simulation_session': 'suas',
    'simulation_block': 'suas', 'technical_simulation_block': 'suas', 'polar_capture': 'physiology', 'evidence_capture': 'openmatb',
}


def attach_source(db, table, source, *, historical=True):
    """Associate persisted original identity without editing its sealed contents.

    Historical archive IDs identify the archive, not the potentially reused original
    numeric ID. Unknown times and receipt facts remain unknown.
    """
    existing = db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.source_table == table,
        AssessmentSourceLink.source_id == str(source['id']), AssessmentSourceLink.role == 'acquisition')).first()
    if existing:
        return db.get(AssessmentAttempt, existing.attempt_id)
    if table == 'evidence_capture' and source.get('parent_session_id'):
        native = db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.source_table == 'openmatb_block_attempt',
            AssessmentSourceLink.source_id == source.get('block_instance_id'), AssessmentSourceLink.role == 'acquisition')).first()
        if native:
            original = db.execute(text('SELECT session_id FROM openmatb_block_attempt WHERE id=:id'), {'id': source['block_instance_id']}).first()
            linked = db.get(AssessmentAttempt, native.attempt_id)
            if original and original[0] == source['parent_session_id'] and linked.execution_purpose == source['execution_purpose']:
                db.add(AssessmentSourceLink(attempt_id=linked.id, source_table=table, source_id=str(source['id']), purpose_provenance_id=linked.purpose_provenance_id))
                db.flush()
                return linked
    if table not in SOURCE_INSTRUMENTS:
        return None
    instrument = SOURCE_INSTRUMENTS[table] or source.get('experiment_id')
    if instrument not in {'pvt', 'screen', 'openmatb', 'liftoff', 'suas', 'physiology'}:
        return None
    evidence = source
    if table == 'archived_assessment':
        try:
            evidence = {**json.loads(source['snapshot_json']), 'participant_id': source.get('participant_id')}
        except (ValueError, TypeError):
            evidence = source
    participant = evidence.get('participant_id')
    visit = evidence.get('visit_id')
    # Only recorded foreign keys are used; historical screens never get guessed visits.
    purpose = evidence.get('execution_purpose', 'practice' if table == 'practiceresult' else 'study')
    parent = None
    if table in {'openmatb_block_attempt', 'simulation_block', 'technical_simulation_block'}:
        parent_table = 'openmatb_suite_session' if table == 'openmatb_block_attempt' else 'technical_simulation_session' if table == 'technical_simulation_block' else 'simulation_session'
        parent = db.execute(text(f'SELECT * FROM "{parent_table}" WHERE id=:id'), {'id': source['session_id']}).mappings().first()
        if parent:
            participant, visit = parent.get('participant_id'), parent.get('visit_id')
            purpose = 'practice' if source.get('profile', source.get('block_id')) == 'PRACTICE' else parent.get('execution_purpose', 'study')
    if parent and table == 'simulation_block' and purpose == 'study':
        parent_link = db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.source_table == 'simulation_session', AssessmentSourceLink.source_id == source['session_id'])).first()
        if parent_link:
            from .study_admission import for_occasion
            from fastapi import HTTPException
            assigned_attempt = db.get(AssessmentAttempt, parent_link.attempt_id)
            try: for_occasion(db, assigned_attempt.occasion_id)
            except HTTPException: pass
            else:
                db.add(AssessmentSourceLink(attempt_id=assigned_attempt.id, source_table=table, source_id=str(source['id']), purpose_provenance_id=assigned_attempt.purpose_provenance_id)); db.flush()
                return assigned_attempt
    if participant is not None and db.execute(text('SELECT id FROM participant WHERE id=:id'), {'id': participant}).first() is None:
        participant = None
    if visit is not None and db.execute(text('SELECT id FROM visit WHERE id=:id'), {'id': visit}).first() is None:
        visit = None
    occasion = AssessmentOccasion(participant_id=participant, visit_id=visit, instrument=instrument,
        origin='legacy' if historical else 'legacy_compat', phase=None, order=None)
    db.add(occasion)
    db.flush()
    attempt = AssessmentAttempt(occasion_id=occasion.id, ordinal=1, execution_purpose=purpose,
        purpose_provenance_id=source.get('purpose_provenance_id'), created_at=None,
        acquisition_state='unknown' if historical else 'created')
    if not historical and table in {'openmatb_block_attempt', 'simulation_block', 'technical_simulation_block'}:
        from .purpose_service import declare_acquisition
        declare_acquisition(db, attempt, purpose=purpose)
    else:
        db.add(attempt)
        db.flush()
    if historical and attempt.purpose_provenance_id is None:
        from .purpose_service import historical_association_identity
        attempt.purpose_provenance_id = historical_association_identity(db, source_table=table, source_id=str(source['id']), purpose=purpose, snapshot=source)
        db.add(attempt)
    db.add(AssessmentSourceLink(attempt_id=attempt.id, source_table=table, source_id=str(source['id']),
                              purpose_provenance_id=attempt.purpose_provenance_id))
    db.flush()
    if table == 'openmatb_block_attempt':
        _attach_rating(db, attempt, source, historical=historical)
    return attempt


def sync_sources(db):
    """Discover installed sources idempotently. Used by migration and read adapters."""
    tables = set(inspect(db.connection()).get_table_names())
    for table in SOURCE_INSTRUMENTS:
        if table not in tables:
            continue
        for source in db.execute(text(f'SELECT * FROM "{table}"')).mappings().all():
            attempt = attach_source(db, table, dict(source))
            if attempt and table in {'pvt_assessment', 'screenresult', 'practiceresult'} and 'attempt_id' in source and source['attempt_id'] is None:
                db.execute(text(f'UPDATE "{table}" SET attempt_id=:attempt WHERE id=:id'), {'attempt': attempt.id, 'id': source['id']})


def _attach_rating(db, target, source, *, historical):
    from .purpose_service import declare_acquisition
    task_occasion = db.get(AssessmentOccasion, target.occasion_id)
    occasion = AssessmentOccasion(participant_id=task_occasion.participant_id, visit_id=task_occasion.visit_id,
        instrument='questionnaire', origin=task_occasion.origin)
    db.add(occasion)
    db.flush()
    rating = AssessmentAttempt(occasion_id=occasion.id, ordinal=1, execution_purpose=target.execution_purpose,
        target_attempt_id=target.id, created_at=None, acquisition_state='unknown' if historical else 'created')
    if historical:
        from .purpose_service import historical_association_identity
        rating.purpose_provenance_id = historical_association_identity(db, source_table='assessment_attempt', source_id=rating.id, purpose=rating.execution_purpose, snapshot={'target_attempt_id': target.id, 'source_id': str(source['id']), 'role': 'ratings'})
        db.add(rating)
        db.flush()
    else:
        declare_acquisition(db, rating, purpose=rating.execution_purpose)
    db.add(AssessmentSourceLink(attempt_id=rating.id, source_table='openmatb_block_attempt',
        source_id=str(source['id']), role='ratings', purpose_provenance_id=rating.purpose_provenance_id))
    db.flush()


def source_attempt(db, table, identity, role='acquisition'):
    from fastapi import HTTPException
    if table not in SOURCE_INSTRUMENTS:
        raise HTTPException(404, 'unsupported source table')
    link = db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.source_table == table,
        AssessmentSourceLink.source_id == identity, AssessmentSourceLink.role == role)).first()
    if link is None:
        raise HTTPException(404, 'source association not found')
    return db.get(AssessmentAttempt, link.attempt_id)


def receipt_facets(db, attempt):
    """Read source evidence independently; never infer ratings/processing from finish."""
    facets = {'raw_saving': attempt.raw_saving, 'acquisition': attempt.acquisition_state,
              'ratings': attempt.ratings, 'processing': attempt.processing}
    links = db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.attempt_id == attempt.id)).all()
    for link in links:
        if link.source_table not in SOURCE_INSTRUMENTS:
            continue
        row = db.execute(text(f'SELECT * FROM "{link.source_table}" WHERE id=:id'), {'id': link.source_id}).mappings().first()
        if row is None:
            continue
        if link.source_table == 'openmatb_block_attempt' and link.role == 'ratings':
            # A task's completion/artifacts establish no questionnaire facts.
            if row['ratings_json'] is not None:
                facets.update(raw_saving='saved', ratings='saved',
                              acquisition='finished' if row['ratings_saved_at'] is not None else 'unknown')
        elif link.source_table == 'openmatb_block_attempt':
            facets.update(raw_saving=row['artifact_status'], acquisition=row['task_status'],
                          ratings='saved' if row['ratings_json'] is not None else 'unknown', processing=row['evidence_status'])
        elif link.source_table == 'evidence_capture':
            facets['raw_saving'] = 'saved'
            facets['acquisition'] = row['completion']
            # Derivation runs remain separately selectable in the evidence inspector.
        elif link.source_table == 'polar_capture':
            facets.update(raw_saving=row['artifact_state'], acquisition=row['lifecycle'])
        elif link.source_table in {'simulation_session', 'technical_simulation_session', 'simulation_block', 'technical_simulation_block', 'openmatb_suite_session'}:
            facets['acquisition'] = row['lifecycle']
        elif link.source_table == 'liftoff_session':
            facets['acquisition'] = row['status']
    return facets


def source_identity(db, table, identity, role='acquisition'):
    """Nullable linkage for compatibility views; never reconstruct facts on reads."""
    link = db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.source_table == table,
        AssessmentSourceLink.source_id == str(identity), AssessmentSourceLink.role == role)).first()
    if link is None:
        return {'assessment_attempt_id': None, 'assessment_occasion_id': None}
    attempt = db.get(AssessmentAttempt, link.attempt_id)
    return {'assessment_attempt_id': attempt.id, 'assessment_occasion_id': attempt.occasion_id}
