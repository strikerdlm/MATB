"""Prospective assignment admission. Historical associations never grant collection authority."""
import json
from fastapi import HTTPException
from sqlmodel import select
from .study_registry_models import StudyAssignment, StudyAttemptSelection, StudyRecoveryInterval
from .assessment_models import AssessmentOccasion, AssessmentAttempt
from .study_registry import get_version, assignment_is_current, _bind_workspace, canonical


def _required(message='Select an active assigned assessment before study collection.'):
    raise HTTPException(409, dict(code='study_assignment_required', message=message, assignment_url='/study/assignments'))


def for_occasion(db, occasion_id):
    occasion = db.get(AssessmentOccasion, occasion_id)
    if occasion is None: _required()
    rows = db.exec(select(StudyAssignment).where(StudyAssignment.visit_id == occasion.visit_id)).all()
    for assignment in rows:
        for key, identity in json.loads(assignment.occasions_json).items():
            if identity != occasion_id: continue
            if not assignment_is_current(db, assignment): _required('This assignment was amended. Select its replacement; the old attempt remains historical.')
            version = get_version(db, assignment.version_id); _bind_workspace(db, version)
            study = json.loads(version.study_json)
            spec = next(o for o in study['occasions'] if o['key'] == key)
            if (occasion.version_ref, occasion.participant_id, occasion.visit_id, occasion.instrument, occasion.condition) != (
                version.id, assignment.participant_id, assignment.visit_id, spec['instrument'], spec['condition_by_arm'][assignment.arm]):
                _required('Assignment context does not match its immutable occasion.')
            return dict(assignment_id=assignment.id, version_id=version.id, analysis_plan_id=version.analysis_plan_id,
                study_sha256=version.study_sha256, analysis_sha256=version.analysis_sha256, implementation_sha256=study['implementation_sha256'][spec['instrument']],
                participant_id=assignment.participant_id, visit_id=assignment.visit_id, arm=assignment.arm,
                occasion_key=key, occasion_id=occasion_id, **spec, rules=study['rules'],
                recovery_intervals=study['recovery_intervals'], preparation_policy=[p for p in study['preparation_policy'] if p['occasion_key'] in json.loads(assignment.occasions_json)], repeat_policy=study['repeat_policy'], interruption_policy=study['interruption_policy'], analysis_gate='not_implemented', preparation_gate='not_implemented', resource_gate='not_implemented')
    _required()


def resolve_assignment(db, *, attempt_id, instrument, participant_id, visit_id=None, purpose, config=None, require_started=False):
    if purpose != 'study': return None
    if not attempt_id: _required()
    attempt = db.get(AssessmentAttempt, attempt_id)
    if attempt is None: _required()
    context = for_occasion(db, attempt.occasion_id)
    from .purpose_service import provenance_view
    # Task1's current recorded purpose governs admission and prerequisites.
    history = provenance_view(db, attempt.purpose_provenance_id)
    current = history['current']
    if (attempt.execution_purpose != 'study' or current['purpose'] != 'study'
            or context['instrument'] != instrument or context['participant_id'] != participant_id
            or (visit_id is not None and context['visit_id'] != visit_id)):
        _required('Attempt participant, visit, instrument or current purpose differs from the assignment.')
    from .study_bindings import binding_issues, implementation_binding
    from .study_registry_schemas import OccasionSpec
    issues = binding_issues(db, OccasionSpec.model_validate({key: context[key] for key in OccasionSpec.model_fields}))
    if implementation_binding(instrument) != context['implementation_sha256']: issues.append('Installed instruction/control/scoring source fingerprint changed.')
    if issues: raise HTTPException(409, dict(code='study_binding_unavailable', message='The installed instrument differs from the frozen binding.', issues=issues, assignment_url='/study/assignments'))
    if require_started and attempt.acquisition_state not in {'started', 'finished'}: _required('Start the exact assigned attempt before saving or launching acquisition.')
    if config is not None and config != context['config']: _required('Configuration differs from the frozen assigned binding.')
    return context


def select_prerequisites(db, attempt_id, selections):
    from .study_registry import lock_registry
    lock_registry(db)
    attempt = db.get(AssessmentAttempt, attempt_id)
    if attempt is None: _required()
    if attempt.acquisition_state != 'created': raise HTTPException(409, 'Prerequisite selection is frozen when the attempt starts.')
    context = for_occasion(db, attempt.occasion_id)
    if set(selections) != set(context['prerequisite_keys']): raise HTTPException(422, 'Select an exact attempt for every authored prerequisite.')
    assignment = db.get(StudyAssignment, context['assignment_id'])
    occasion_ids = json.loads(assignment.occasions_json)
    for key, identity in selections.items():
        target = db.get(AssessmentAttempt, identity)
        if target is None or target.occasion_id != occasion_ids[key]: raise HTTPException(422, 'Prerequisite attempt belongs to another assigned occasion.')
    prior = db.get(StudyAttemptSelection, attempt_id)
    payload = canonical(selections)
    if prior:
        if prior.selections_json != payload: raise HTTPException(409, 'Selection is immutable. Create an explicit new attempt to change it.')
        return prior
    row = StudyAttemptSelection(attempt_id=attempt_id, selections_json=payload); db.add(row); db.flush(); return row


def require_prerequisites(db, attempt_id, context):
    from .experiment_catalog import require_study_pvt
    from .study_policies import require_preparation
    require_preparation(context)
    selection = db.get(StudyAttemptSelection, attempt_id)
    selected = json.loads(selection.selections_json) if selection else {}
    if set(selected) != set(context['prerequisite_keys']): _required('Select the exact prerequisite attempts on the assignment page.')
    for key, identity in selected.items():
        attempt = db.get(AssessmentAttempt, identity)
        occasion = db.get(AssessmentOccasion, attempt.occasion_id)
        resolve_assignment(db, attempt_id=identity, instrument=occasion.instrument, participant_id=context['participant_id'], visit_id=context['visit_id'], purpose='study')
        if attempt.acquisition_state != 'finished': _required('Complete the selected prerequisite attempt first.')
        if occasion.instrument == 'pvt': require_study_pvt(db, context['visit_id'], attempt_id=identity)
    for interval in context['recovery_intervals']:
        if interval['before_key'] != context['occasion_key']: continue
        recorded = db.get(StudyRecoveryInterval, (context['assignment_id'], interval['key']))
        if not recorded or not recorded.ended_at: _required('Complete the authored recovery interval before this assessment.')


def guard_source(db, row, *, require_started=True):
    """Gate resume/start of pre-existing runtime sources too; legacy study is read-only."""
    from .assessment_adapters import source_attempt, SOURCE_INSTRUMENTS
    if getattr(row, 'execution_purpose', 'study') != 'study': return None
    try: attempt = source_attempt(db, row.__tablename__, str(row.id))
    except HTTPException: _required()
    return resolve_assignment(db, attempt_id=attempt.id, instrument=SOURCE_INSTRUMENTS[row.__tablename__], participant_id=row.participant_id,
        visit_id=getattr(row, 'visit_id', None), purpose='study', require_started=require_started)


def sync_runtime_attempt(db, source, *, state, cause='unknown'):
    """Only assigned sources receive known live transitions; legacy timestamps stay unknown."""
    from .assessment_adapters import source_attempt
    from .assessment_service import transition
    try:
        attempt = source_attempt(db, source.__tablename__, str(source.id))
        for_occasion(db, attempt.occasion_id)
    except HTTPException: return
    if attempt.acquisition_state in {'finished', 'interrupted'}: return
    if state == 'started' and attempt.acquisition_state == 'created': transition(db, attempt.id, state)
    elif state == 'finished' and attempt.acquisition_state == 'started': transition(db, attempt.id, state)
    elif state == 'interrupted': transition(db, attempt.id, state, cause)
