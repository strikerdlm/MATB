"""Version-bound preparation from responses and persisted instrument observations.

All criteria are supplied by the frozen researcher protocol. Administrative
acknowledgement and demonstration never stand in for observed performance.
"""
import hashlib
import json
import math
from fastapi import HTTPException
from sqlmodel import select
from .assessment_models import AssessmentAttempt, AssessmentOccasion
from .study_registry_models import StudyAssignment, StudyPreparation, StudyPreparationEvent, StudyPreparationPractice
from .study_registry import canonical, lock_registry


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def fail(message, code='study_preparation_required'):
    raise HTTPException(409, dict(code=code, message=message, preparation_url='/study/participant'))


def assignment_context(db, assignment_id, key):
    from .study_admission import for_occasion
    assignment = db.get(StudyAssignment, assignment_id)
    if not assignment or key not in json.loads(assignment.occasions_json):
        raise HTTPException(404, 'Assigned preparation requirement not found.')
    return for_occasion(db, json.loads(assignment.occasions_json)[key])


PREPARATION_SOURCES = (
    'webui/backend/app/study_preparation.py', 'webui/backend/app/study_preflight.py',
    'webui/backend/app/study_native_practice.py', 'webui/backend/app/study_policies.py',
    'webui/backend/app/routers/study_preparation.py',
    'webui/backend/app/assessment_service.py', 'webui/backend/app/study_admission.py',
    'webui/frontend/src/components/study/StudyParticipant.tsx',
    'openmatb/core/preflight.py', 'matb_integration/evidence/reconcile.py',
    'matb_integration/evidence/contracts.py',
)


def preparation_implementation():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    files = {path: hashlib.sha256((root/path).read_bytes()).hexdigest()
             for path in PREPARATION_SOURCES if (root/path).is_file()}
    return dict(version='measured-preparation-v1', source_files=files, sha256=digest(files))


def resolve_presentation(db, context):
    from .study_bindings import binding_issues, implementation_binding
    from .study_registry_schemas import OccasionSpec
    issues = binding_issues(db, OccasionSpec.model_validate({key: context[key] for key in OccasionSpec.model_fields}))
    if issues or implementation_binding(context['instrument']) != context['implementation_sha256']:
        fail('Restore the frozen instrument version and supported response mapping.', 'study_binding_unavailable')
    instrument, locale = context['instrument'], context['locale']
    en = locale == 'en'
    items = []
    if instrument == 'pvt':
        items = [dict(id='response', task='pvt', text='Press SPACE or the response area when the counter appears; wait while it is absent.' if en else 'Pulse ESPACIO o el área de respuesta cuando aparezca el contador; espere mientras esté ausente.',
                      question='Which key responds to the counter?' if en else '¿Qué tecla responde al contador?', answer='SPACE')]
    elif instrument == 'screen':
        items = [dict(id=key, task=key, text=text, question=question, answer=answer) for key, text, question, answer in (
            ('simple_rt', 'Respond to the stimulus using SPACE.' if en else 'Responda al estímulo con ESPACIO.', 'Response key?' if en else '¿Tecla de respuesta?', 'SPACE'),
            ('choice_rt', 'Use LEFT ARROW for left and RIGHT ARROW for right.' if en else 'Use FLECHA IZQUIERDA para izquierda y FLECHA DERECHA para derecha.', 'Key for the left arrow?' if en else '¿Tecla para la flecha izquierda?', 'ARROWLEFT'),
            ('nback', 'Press SPACE when the displayed item matches the item two positions back.' if en else 'Pulse ESPACIO cuando el elemento coincida con el de dos posiciones atrás.', 'Key for a match?' if en else '¿Tecla para una coincidencia?', 'SPACE'),
            ('tracking', 'Follow the target with the configured pointer.' if en else 'Siga el objetivo con el puntero configurado.', 'Use the pointer?' if en else '¿Usa el puntero?', 'YES' if en else 'SI'))]
    elif instrument == 'openmatb':
        items = []  # The actual assigned runtime presentation is a later immutable event, never guessed.
    else:
        items = [dict(id='instrument', task=instrument, text='Review the instrument instructions before continuing.' if en else 'Revise las instrucciones del instrumento antes de continuar.', question='Instrument?' if en else '¿Instrumento?', answer=instrument.upper())]
    return dict(locale=locale, instrument=instrument, input_mapping=context['config']['input_mapping'],
                enabled_tasks=[item['task'] for item in items], items=items,
                config=context['config'], implementation_sha256=context['implementation_sha256'], preparation_implementation=preparation_implementation())


def _identity(context, presentation, requirement):
    return digest(dict(version_id=context['version_id'], presentation=presentation, requirement=requirement))


def begin(db, assignment_id, key):
    lock_registry(db)
    context = assignment_context(db, assignment_id, key)
    requirement = next(p for p in context['preparation_policy'] if p['occasion_key'] == key)
    # Never insert additional training into an already opened measurement visit.
    started = db.exec(select(AssessmentAttempt).join(AssessmentOccasion).where(
        AssessmentOccasion.visit_id == context['visit_id'], AssessmentAttempt.execution_purpose == 'study',
        AssessmentAttempt.started_at.is_not(None))).first()
    if started and requirement['placement'] != 'prescribed_later':
        fail('Preparation belongs before measurement. Use the frozen prescribed-later requirement or a new visit.')
    presentation = resolve_presentation(db, context)
    row = StudyPreparation(assignment_id=assignment_id, participant_id=context['participant_id'],
        version_id=context['version_id'], occasion_key=key, instrument=context['instrument'],
        identity_sha256=_identity(context, presentation, requirement), config_sha256=digest(context['config']),
        presentation_json=canonical(presentation), requirement_json=canonical(requirement))
    db.add(row); db.flush(); return row


def _run(db, identity):
    row = db.get(StudyPreparation, identity)
    if row is None: raise HTTPException(404, 'Preparation not found.')
    context = assignment_context(db, row.assignment_id, row.occasion_key)
    presentation = resolve_presentation(db, context)
    requirement = next(p for p in context['preparation_policy'] if p['occasion_key'] == row.occasion_key)
    if _identity(context, presentation, requirement) != row.identity_sha256:
        fail('Preparation presentation/version changed. Start preparation for the current binding.')
    if requirement['placement'] == 'before_baseline':
        started = db.exec(select(AssessmentAttempt).join(AssessmentOccasion).where(
            AssessmentOccasion.visit_id == context['visit_id'], AssessmentAttempt.execution_purpose == 'study',
            AssessmentAttempt.started_at.is_not(None))).first()
        if started: fail('Additional preparation after measurement starts must be explicitly prescribed by the frozen protocol.')
    return row


def _events(db, identity):
    events = db.exec(select(StudyPreparationEvent).where(StudyPreparationEvent.preparation_id == identity).order_by(StudyPreparationEvent.created_at, StudyPreparationEvent.id)).all()
    # Legacy events retain their historical order. New append ordinals survive
    # clock ties/regressions, reloads and backup without rewriting observed times.
    return sorted(events, key=lambda event: json.loads(event.payload_json).get('event_sequence', 0))


def _append_event(db, event):
    # All callers hold lock_registry, serializing the per-preparation append.
    events = _events(db, event.preparation_id)
    payload = json.loads(event.payload_json)
    payload['event_sequence'] = len(events) + 1
    event.payload_json = canonical(payload)
    db.add(event); db.flush(); return event


def _next(row, events):
    requirement = json.loads(row.requirement_json)
    if any(event.stage == 'stopped' for event in events): return 'stopped'
    if row.instrument == 'openmatb':
        if requirement['practice'] and not any(e.stage == 'practice' and e.passed for e in events): return 'practice'
        if not any(e.stage == 'native_presentation' and e.passed for e in events): return 'resolve_mapping'
    for stage, required in [('demonstration', requirement['demonstration_required']), ('acknowledgement', requirement['acknowledgement_required']),
                            ('comprehension', bool(requirement['comprehension'])), ('practice', bool(requirement['practice']))]:
        if required and not any(e.stage == stage and e.passed for e in events): return stage
    return 'ready'


def preparation_view(db, identity):
    row = db.get(StudyPreparation, identity)
    if not row: raise HTTPException(404, 'Preparation not found.')
    events = _events(db, identity)
    presented = json.loads(row.presentation_json)
    runtime = next((e for e in events if e.stage == 'native_presentation' and e.passed), None)
    if runtime: presented.update(json.loads(runtime.payload_json)['presentation'])
    return {**row.model_dump(mode='json'), 'presentation': presented,
            'requirement': json.loads(row.requirement_json), 'next_action': _next(row, events),
            'events': [{**e.model_dump(mode='json'), **json.loads(e.payload_json)} for e in events],
            'practice_attempt_ids': [p.attempt_id for p in db.exec(select(StudyPreparationPractice).where(StudyPreparationPractice.preparation_id == identity)).all()]}


def _grade(criteria, observations):
    outcomes = []
    for criterion in criteria:
        observed = observations.get(criterion['metric'])
        valid = isinstance(observed, (float, int)) and not isinstance(observed, bool) and math.isfinite(observed)
        passed = valid and {'gte': lambda: observed >= criterion['threshold'], 'lte': lambda: observed <= criterion['threshold'], 'eq': lambda: observed == criterion['threshold']}[criterion['comparator']]()
        outcomes.append(dict(criterion=criterion, observed=observed, passed=bool(passed)))
    return outcomes


def record_stage(db, identity, stage, responses):
    lock_registry(db); row = _run(db, identity)
    if stage not in {'demonstration', 'acknowledgement', 'comprehension'}:
        fail('Practice competence requires actual persisted instrument observations.')
    if _next(row, _events(db, identity)) != stage: fail('Complete the current preparation stage first.')
    outcomes = []
    if stage == 'comprehension':
        items = preparation_view(db, identity)['presentation']['items']
        if not items or set(responses) != {item['id'] for item in items}: raise HTTPException(422, 'Respond to each enabled task item exactly once.')
        observations = {'comprehension.correct_fraction': sum(str(responses[i['id']]).strip().upper() == i['answer'] for i in items) / len(items)}
        outcomes = _grade(json.loads(row.requirement_json)['comprehension'], observations)
    event = StudyPreparationEvent(preparation_id=identity, stage=stage, passed=all(o['passed'] for o in outcomes),
        payload_json=canonical(dict(responses=responses, criteria=outcomes)))
    return _append_event(db, event)


def begin_practice(db, identity):
    from .assessment_service import create_occasion, create_attempt
    from .assessment_schemas import OccasionIn, AttemptIn
    lock_registry(db); row = _run(db, identity)
    if _next(row, _events(db, identity)) != 'practice': fail('Complete understanding before practice, or use the standalone practice catalog.')
    context = assignment_context(db, row.assignment_id, row.occasion_key)
    existing = db.exec(select(StudyPreparationPractice).where(StudyPreparationPractice.preparation_id == identity)).all()
    for item in existing:
        attempt = db.get(AssessmentAttempt, item.attempt_id)
        if attempt.acquisition_state in {'created', 'started'}: return attempt
    if existing:
        prior_link = sorted(existing, key=lambda item:item.created_at)[-1]
        prior = db.get(AssessmentAttempt, prior_link.attempt_id)
        if not any(e.stage == 'practice' and e.attempt_id == prior.id for e in _events(db, identity)):
            fail('Evaluate the completed practice observations before repeating.')
        attempt = create_attempt(db, prior.occasion_id, AttemptIn(execution_purpose='practice'), repeat_of=prior.id, reason='Explicit preparation repeat after recorded unsuccessful practice')
    else:
        occasion = create_occasion(db, OccasionIn(participant_id=row.participant_id, visit_id=context['visit_id'],
            instrument=row.instrument, phase='preparation', order=1, version_ref=row.version_id))
        attempt = create_attempt(db, occasion.id, AttemptIn(execution_purpose='practice'))
    db.add(StudyPreparationPractice(attempt_id=attempt.id, preparation_id=identity)); db.flush(); return attempt


def practice_context(db, attempt_id, *, validate=False):
    link = db.get(StudyPreparationPractice, attempt_id)
    if not link: return None
    row = _run(db, link.preparation_id) if validate else db.get(StudyPreparation, link.preparation_id)
    if validate: context = assignment_context(db, row.assignment_id, row.occasion_key)
    else:
        from .study_registry import get_version
        assignment = db.get(StudyAssignment, row.assignment_id)
        study = json.loads(get_version(db, row.version_id).study_json)
        spec = next(o for o in study['occasions'] if o['key'] == row.occasion_key)
        context = dict(**spec, assignment_id=row.assignment_id, version_id=row.version_id, participant_id=row.participant_id,
            visit_id=assignment.visit_id, occasion_id=json.loads(assignment.occasions_json)[row.occasion_key],
            assigned_visit=next(v for v in study['visits'] if v['ordinal'] == spec['visit_ordinal']))
    return {**context, 'preparation_id': row.id}


def finish_practice(db, identity, attempt_id):
    from .models import PracticeResult
    lock_registry(db); row = _run(db, identity)
    link = db.get(StudyPreparationPractice, attempt_id)
    if not link or link.preparation_id != identity: fail('Select the exact practice attempt created for this preparation.')
    prior = next((e for e in _events(db, identity) if e.stage == 'practice' and e.attempt_id == attempt_id), None)
    if prior: return prior
    attempt = db.get(AssessmentAttempt, attempt_id)
    if row.instrument != 'openmatb' and attempt.acquisition_state not in {'finished', 'interrupted'}: fail('Finish or record interruption of this practice before grading.')
    source = db.exec(select(PracticeResult).where(PracticeResult.attempt_id == attempt_id)).first()
    observations, duration, source_hash, source_evidence = {}, None, None, None
    if row.instrument == 'openmatb':
        from .study_native_practice import observe_practice
        observations, duration, source_evidence, source = observe_practice(db, row, attempt)
        source_hash = digest(source_evidence) if source_evidence else None
    elif source:
        payload, result = json.loads(source.payload_json), json.loads(source.result_json)
        if payload.get('locale') != json.loads(row.presentation_json)['locale']: fail('Practice language differs from the preparation presentation.')
        source_hash = digest(dict(payload=payload, result=result))
        if row.instrument == 'pvt' and payload.get('trials'):
            observations = {f'pvt.{key}': result['metrics'].get(key) for key in ['median_rt_ms', 'lapses']}
            duration = result['duration_ms'] / 1000
        elif row.instrument == 'screen' and payload.get('simple_rt', {}).get('trials'): observations = {'screen.simple_rt': result['scores'].get('simple_rt', {}).get('median_ms')}
    outcomes = _grade(json.loads(row.requirement_json)['practice'], observations)
    passed = attempt.acquisition_state == 'finished' and bool(source) and all(o['passed'] for o in outcomes)
    event = StudyPreparationEvent(preparation_id=identity, stage='practice', attempt_id=attempt_id,
        passed=passed, duration_seconds=duration, payload_json=canonical(dict(observations=observations, criteria=outcomes,
        practice_configuration=dict(fast_mode=payload.get('fast_mode', False), locale=payload.get('locale'), duration_ms=payload.get('duration_ms')) if source and row.instrument in {'pvt','screen'} else None,
        source_table=(source.__tablename__ if row.instrument == 'openmatb' else 'practiceresult') if source else None, source_id=source.id if source else None, source_sha256=source_hash, source_evidence=source_evidence, outcome=attempt.acquisition_state)))
    return _append_event(db, event)


def required_preparation(db, context, *, native_session_id=None):
    """Only this assigned visit's prescribed boundary; never every future visit."""
    results = []
    for requirement in context['preparation_policy']:
        if requirement['placement'] == 'prescribed_later' and requirement['occasion_key'] != context['occasion_key']: continue
        if not any([requirement['demonstration_required'], requirement['acknowledgement_required'], requirement['comprehension'], requirement['practice']]): continue
        target = assignment_context(db, context['assignment_id'], requirement['occasion_key'])
        try:
            identity = _identity(target, resolve_presentation(db, target), requirement)
        except HTTPException as exc:
            results.append(dict(occasion_key=requirement['occasion_key'], state='blocked', reason=exc.detail)); continue
        candidates = db.exec(select(StudyPreparation).where(StudyPreparation.assignment_id == context['assignment_id'], StudyPreparation.identity_sha256 == identity)).all()
        # Later training is an additional exposure in this exact assignment.
        if requirement['placement'] == 'prescribed_later': candidates = [r for r in candidates if r.assignment_id == context['assignment_id']]
        def usable(candidate):
            events = _events(db, candidate.id)
            if _next(candidate, events) != 'ready': return False
            if candidate.instrument == 'openmatb':
                from sqlalchemy import text
                native = next((e for e in events if e.stage == 'native_presentation' and e.passed), None)
                session_id = json.loads(native.payload_json)['session_id'] if native else None
                if native_session_id and requirement['occasion_key'] == context['occasion_key'] and session_id != native_session_id:
                    return False
                lifecycle = db.execute(text('SELECT lifecycle FROM openmatb_suite_session WHERE id=:id'), {'id':session_id}).scalar_one_or_none()
                if lifecycle not in {'PREFLIGHT_HELD','RUNNING','PAUSED','AWAITING_SCALE','COMPLETE'}: return False
            return True
        ready = next((r for r in candidates if usable(r)), None)
        results.append(dict(occasion_key=requirement['occasion_key'], state='prepared' if ready else 'required', preparation_id=ready.id if ready else None))
    return results


def require_preparation(db, context, *, native_session_id=None):
    selected = required_preparation(db, context, native_session_id=native_session_id)
    missing = [r for r in selected if r['state'] != 'prepared']
    if missing:
        raise HTTPException(409, dict(code='study_preparation_required', message='Complete the frozen preparation requirements before acquisition.', requirements=missing,
                                     preparation_url=f"/study/participant?assignment={context['assignment_id']}"))

    return selected


def freeze_preparation_admission(db, attempt, context):
    """Called in the locked created→started transaction, after acquisition guards."""
    from .study_registry_models import StudyPreparationAdmission
    from .assessment_models import AssessmentSourceLink
    if db.get(StudyPreparationAdmission, attempt.id): return
    native_source = db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.attempt_id == attempt.id,
        AssessmentSourceLink.source_table == 'openmatb_suite_session')).first() if context['instrument'] == 'openmatb' else None
    selected = require_preparation(db, context, native_session_id=native_source.source_id if native_source else None)
    requirements = []
    for decision in selected:
        preparation = db.get(StudyPreparation, decision['preparation_id'])
        events = _events(db, preparation.id)
        policy = json.loads(preparation.requirement_json)
        stages = [stage for stage, required in [('demonstration', policy['demonstration_required']),
            ('acknowledgement', policy['acknowledgement_required']), ('comprehension', policy['comprehension']),
            ('practice', policy['practice']), ('native_presentation', preparation.instrument == 'openmatb')] if required]
        accepted = [next(event.id for event in events if event.stage == stage and event.passed) for stage in stages]
        requirements.append(dict(occasion_key=decision['occasion_key'], preparation_id=preparation.id,
            identity_sha256=preparation.identity_sha256, config_sha256=preparation.config_sha256,
            decision_event_ids=accepted, event_frontier=[dict(id=event.id, stage=event.stage, passed=event.passed,
                attempt_id=event.attempt_id, payload_sha256=hashlib.sha256(event.payload_json.encode()).hexdigest(),
                created_at=event.created_at.isoformat()) for event in events]))
    snapshot = dict(schema_version='preparation-admission-v1', attempt_id=attempt.id,
        assignment_id=context['assignment_id'], version_id=context['version_id'], study_sha256=context['study_sha256'],
        occasion_key=context['occasion_key'], config_sha256=digest(context['config']), requirements=requirements)
    db.add(StudyPreparationAdmission(attempt_id=attempt.id, assignment_id=context['assignment_id'],
        snapshot_json=canonical(snapshot), snapshot_sha256=digest(snapshot)))
    db.flush()


def exposure_history(db, participant_id):
    rows = db.exec(select(AssessmentAttempt, AssessmentOccasion).join(AssessmentOccasion).where(AssessmentOccasion.participant_id == participant_id)).all()
    history = []
    for attempt, occasion in rows:
        link = db.get(StudyPreparationPractice, attempt.id)
        preparation = db.get(StudyPreparation, link.preparation_id) if link else None
        event = next((e for e in _events(db, preparation.id) if e.attempt_id == attempt.id and e.stage == 'practice'), None) if preparation else None
        duration = event.duration_seconds if event else None
        if duration is None and occasion.instrument == 'pvt':
            from .models import PracticeResult, PvtAssessment
            source = db.exec(select(PracticeResult).where(PracticeResult.attempt_id == attempt.id)).first()
            if source:
                duration_ms = json.loads(source.result_json).get('duration_ms')
                duration = duration_ms / 1000 if isinstance(duration_ms, (int, float)) else None
            else:
                source = db.exec(select(PvtAssessment).where(PvtAssessment.attempt_id == attempt.id)).first()
                if source: duration = source.duration_ms / 1000
        from .purpose_service import provenance_view
        current = provenance_view(db, attempt.purpose_provenance_id)['current'] if attempt.purpose_provenance_id else None
        history.append(dict(purpose_provenance_id=attempt.purpose_provenance_id, purpose_origin=current['classification'] if current else 'unknown', attempt_id=attempt.id, participant_id=participant_id, instrument=occasion.instrument,
            purpose=current['purpose'] if current and current['classification'] != 'unknown' else 'unknown', execution_purpose=attempt.execution_purpose, version_id=preparation.version_id if preparation else occasion.version_ref,
            config_sha256=preparation.config_sha256 if preparation else None, preparation_id=preparation.id if preparation else None,
            started_at=attempt.started_at, finished_at=attempt.finished_at, duration_seconds=duration, ordinal=attempt.ordinal,
            repeat_of=attempt.repeat_of, outcome=attempt.acquisition_state, competence=event.passed if event else None))
    return history


def bind_native_presentation(db, identity, session_id):
    from .study_preflight import presentation, stable_mapping, snapshot_for_attempt
    from .study_registry_models import StudyNativePreflight
    from .openmatb_models import OpenMatbSuiteSession
    lock_registry(db); row = _run(db, identity)
    if row.instrument != 'openmatb': fail('Native preparation required.')
    context = assignment_context(db, row.assignment_id, row.occasion_key)
    suite = db.get(OpenMatbSuiteSession, session_id)
    snapshot = db.get(StudyNativePreflight, session_id)
    if not suite or suite.lifecycle != 'PREFLIGHT_HELD' or not snapshot: fail('Open the actual assigned native preflight first.')
    attempt = db.get(AssessmentAttempt, snapshot.attempt_id)
    if attempt.occasion_id != context['occasion_id']: fail('Preflight belongs to a different assigned occasion.')
    value = json.loads(snapshot.snapshot_json)
    if value['issues']:
        event = StudyPreparationEvent(preparation_id=identity, stage='native_preflight_failure', passed=False,
            payload_json=canonical(dict(session_id=session_id, snapshot=value, recovery='Stop the held runtime, resolve the controller/mapping, and explicitly repeat preparation.')))
        return _append_event(db, event)
    existing = next((e for e in _events(db, identity) if e.stage == 'native_presentation'), None)
    if existing:
        if json.loads(existing.payload_json)['session_id'] != session_id: fail('This preparation belongs to a different runtime. Start new preparation explicitly.')
        return existing
    for practice in [e for e in _events(db, identity) if e.stage == 'practice' and e.passed]:
        observed = snapshot_for_attempt(db, practice.attempt_id)
        if not observed or stable_mapping(json.loads(observed.snapshot_json)) != stable_mapping(value):
            fail('Practice controller/mapping differs from the actual assigned runtime. Repeat preparation with the required controller.')
    presented = presentation(value, context['locale'])
    from sqlalchemy import text
    binding = context['config']['instructions']
    content = json.loads(db.execute(text('SELECT content_json FROM openmatb_instruction_protocol WHERE protocol_id=:id AND version=:version'), binding).scalar_one())
    presented['source_instruction_content'] = content
    presented['source_instruction_sha256'] = binding['sha256']
    presented['resolved_task_instructions'] = {task: (('Use the joystick x/y axes to keep the cursor in the target.' if context['locale'] == 'en' else 'Use los ejes x/y del joystick para mantener el cursor en el objetivo.') if task == 'track' else content['task_instructions'].get({'communications':'COMM'}.get(task, task.upper()), '')) for task in value['enabled_tasks']}
    event = StudyPreparationEvent(preparation_id=identity, stage='native_presentation', passed=True,
        payload_json=canonical(dict(session_id=session_id, native_attempt_id=attempt.id, session_csv=snapshot.session_csv,
            presentation=presented, presentation_sha256=digest(presented))))
    return _append_event(db, event)


def _practice_compatible(current, prior):
    current_content, prior_content = json.loads(current.presentation_json), json.loads(prior.presentation_json)
    return (current.participant_id == prior.participant_id and current.version_id == prior.version_id
        and current.instrument == prior.instrument and current.config_sha256 == prior.config_sha256
        and current_content == prior_content
        and json.loads(current.requirement_json)['practice'] == json.loads(prior.requirement_json)['practice'])


def reusable_practice(db, identity):
    row = _run(db, identity)
    if json.loads(row.requirement_json)['placement'] == 'prescribed_later': return []
    candidates = db.exec(select(StudyPreparation).where(StudyPreparation.participant_id == row.participant_id,
        StudyPreparation.id != identity)).all()
    return [dict(event_id=e.id, preparation_id=prior.id, attempt_id=e.attempt_id, criteria=json.loads(e.payload_json)['criteria'])
        for prior in candidates if _practice_compatible(row, prior)
        for e in _events(db, prior.id) if e.stage == 'practice' and e.passed
        and not json.loads(e.payload_json).get('reused_from_event_id')]


def reuse_practice(db, identity, event_id, actor, reason):
    lock_registry(db); row = _run(db, identity)
    if not actor.strip() or not reason.strip(): raise HTTPException(422, 'Researcher and reuse reason are required.')
    if _next(row, _events(db, identity)) != 'practice': fail('Select prior competence only at the practice stage.')
    if not any(item['event_id'] == event_id for item in reusable_practice(db, identity)):
        fail('Prior practice must match this participant, frozen version, configuration, language and criterion. Prescribed later training requires a new exposure.')
    original = db.get(StudyPreparationEvent, event_id)
    payload = json.loads(original.payload_json)
    payload.update(reused_from_event_id=original.id, reused_from_preparation_id=original.preparation_id, actor=actor, reason=reason)
    event = StudyPreparationEvent(preparation_id=identity, stage='practice', attempt_id=original.attempt_id,
        passed=True, duration_seconds=None, payload_json=canonical(payload))
    return _append_event(db, event)


def stop_preparation(db, identity):
    lock_registry(db); row = _run(db, identity)
    existing = next((event for event in _events(db, identity) if event.stage == 'stopped'), None)
    if existing: return existing
    event = StudyPreparationEvent(preparation_id=row.id, stage='stopped', passed=None,
        payload_json=canonical(dict(reason='Participant or operator stopped preparation; prior responses and exposure retained.')))
    return _append_event(db, event)


def require_preflight_practice(db, context):
    """Finish/grade prescribed practice before acquiring the sole native device owner."""
    requirement = next(item for item in context['preparation_policy'] if item['occasion_key'] == context['occasion_key'])
    if not requirement['practice']: return
    identity = _identity(context, resolve_presentation(db, context), requirement)
    runs = db.exec(select(StudyPreparation).where(StudyPreparation.assignment_id == context['assignment_id'],
        StudyPreparation.occasion_key == context['occasion_key'], StudyPreparation.identity_sha256 == identity)).all()
    if not any(_next(run, _events(db, run.id)) == 'resolve_mapping' for run in runs):
        fail('Complete and grade the prescribed native practice before opening the assigned runtime. Stop a prior held runtime before explicit new preparation.')
