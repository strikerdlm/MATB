"""Frozen local authoring registry. All mutations are transactional; callers commit."""
import json
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine, select
from .study_registry_models import (StudyWorkspace, StudyDraft, StudyVersion, StudyRehearsal,
    StudyActivation, StudyAssignment, StudyAmendment)
from .study_registry_schemas import DraftPayload
from .assessment_service import payload_hash
from .study_protocol import selected_protocol


def lock_registry(db):
    # Serialize applicability decisions with starts on SQLite, including first activation.
    db.execute(text('INSERT OR IGNORE INTO study_registry_lock (id) VALUES (1)'))


def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def named(actor):
    if not actor.strip() or actor.startswith(('system:', 'local:')):
        raise HTTPException(422, 'A named researcher attestation is required.')


def template(kind):
    from .study_bindings import browser_binding
    if kind not in {'longitudinal', 'pre-post-recovery', 'repeated-block'}:
        raise HTTPException(404, 'template not found')
    protocol = selected_protocol()
    visits = [dict(ordinal=v.ordinal, code=v.code, scheduled_day=v.scheduled_day) for v in protocol.visits]
    keys = ['pre', 'post', 'recovery'] if kind == 'pre-post-recovery' else ['block1', 'block2'] if kind == 'repeated-block' else ['baseline']
    occasions = [dict(key=key if v['ordinal'] == 1 else f"{key}_v{v['ordinal']}", visit_ordinal=v['ordinal'],
        instrument='pvt', phase=key, order=i + 1, condition_by_arm={'A': 'baseline'}, locale='es-419',
        config=browser_binding('pvt')) for v in (visits if kind == 'longitudinal' else visits[:1]) for i, key in enumerate(keys)]
    return DraftPayload.model_validate(dict(study=dict(study_id='researcher-study', title=f'{kind} — SYNTHETIC DRAFT',
        template_family=protocol.protocol_id, synthetic=True, enabled_instruments=['pvt'], visits=visits,
        arms=['A'], assignment_method='explicit_researcher_selection', occasions=occasions,
        recovery_intervals=[], rules=dict(preparation='', repeat='', interruption='')),
        analysis=dict(unit='participant', outcomes=[dict(key='primary', metric='pvt.median_rt_ms', units='ms', occasion_keys=[occasions[0]['key']], summary='individual')],
        contrasts=[], rules=dict(exclusions='', denominators='', qualification='', pooling='', historical_unknowns='exclude')))).model_dump()


def _draft(db, identity):
    row = db.get(StudyDraft, identity)
    if row is None: raise HTTPException(404, 'draft not found')
    return row


def create_draft(db, payload):
    lock_registry(db)
    normalized = DraftPayload.model_validate(payload).model_dump()
    from .study_bindings import implementation_binding
    from .study_analysis_bundle import calculation_binding, dependency_versions
    normalized['analysis']['calculation_sha256'] = calculation_binding()
    normalized['analysis']['calculator_dependencies'] = dependency_versions(set(normalized['study']['enabled_instruments']))
    normalized['study']['implementation_sha256'] = {key: implementation_binding(key) for key in normalized['study']['enabled_instruments']}
    row = StudyDraft(payload_json=canonical(normalized), sha256=payload_hash(normalized))
    db.add(row); db.flush()
    return row


def update_draft(db, identity, payload):
    lock_registry(db)
    row = _draft(db, identity)
    if row.frozen_version_id: raise HTTPException(409, 'Frozen draft: clone a version to author an amendment.')
    normalized = DraftPayload.model_validate(payload).model_dump()
    from .study_bindings import implementation_binding
    from .study_analysis_bundle import calculation_binding, dependency_versions
    normalized['analysis']['calculation_sha256'] = calculation_binding()
    normalized['analysis']['calculator_dependencies'] = dependency_versions(set(normalized['study']['enabled_instruments']))
    normalized['study']['implementation_sha256'] = {key: implementation_binding(key) for key in normalized['study']['enabled_instruments']}
    row.payload_json = canonical(normalized); row.sha256 = payload_hash(normalized)
    db.add(row); db.flush()
    return row


def validate(db, identity):
    from .study_bindings import binding_issues
    payload = DraftPayload.model_validate_json(_draft(db, identity).payload_json)
    study, analysis = payload.study, payload.analysis
    from .study_policies import policy_issues
    issues = policy_issues(study, analysis)
    from .study_analysis_bundle import calculation_binding, dependency_versions
    if analysis.calculation_sha256 != calculation_binding() or analysis.calculator_dependencies != dependency_versions(set(study.enabled_instruments)):
        issues.append(dict(path='analysis.calculation_sha256',message='Save draft to refresh the exact installed calculator/dependency binding before approval.'))
    def issue(path, message): issues.append(dict(path=path, message=message))
    for group, rules in [('study', study.rules), ('analysis', analysis.rules)]:
        for key, value in rules.model_dump().items():
            if not value.strip(): issue(f'{group}.rules.{key}', 'Researcher-authored rule required; no scientific threshold is supplied by the template.')
    protocol = selected_protocol()
    if study.template_family != protocol.protocol_id: issue('study.template_family', 'Wrong deployment template family.')
    if study.version_id or study.analysis_plan_id or analysis.version_id or analysis.study_version_id:
        issue('version_id', 'Draft references are allocated by freeze, never supplied by the client.')
    visit_ordinals = [v.ordinal for v in study.visits]
    if len(set(visit_ordinals)) != len(visit_ordinals): issue('study.visits', 'Visit ordinals must be unique.')
    if len(set(study.arms)) != len(study.arms) or any(not a for a in study.arms): issue('study.arms', 'Arms must be nonblank and unique.')
    keys = {o.key: o for o in study.occasions}
    if len(keys) != len(study.occasions): issue('study.occasions', 'Occasion keys must be unique.')
    if set(study.enabled_instruments) != {o.instrument for o in study.occasions}: issue('study.enabled_instruments', 'Enabled instruments must exactly match scheduled occasions.')
    from .study_bindings import implementation_binding
    if study.implementation_sha256 != {key: implementation_binding(key) for key in study.enabled_instruments}:
        issue('study.implementation_sha256', 'Installed instruction/scoring implementation changed. Save, review and rehearse a new draft fingerprint.')
    orders = set()
    for i, occasion in enumerate(study.occasions):
        path = f'study.occasions.{i}'
        if occasion.visit_ordinal not in visit_ordinals: issue(path + '.visit_ordinal', 'Unknown scheduled visit.')
        if (occasion.visit_ordinal, occasion.order) in orders: issue(path + '.order', 'Order must be unique within a visit.')
        orders.add((occasion.visit_ordinal, occasion.order))
        if set(occasion.condition_by_arm) != set(study.arms): issue(path + '.condition_by_arm', 'Assign a condition for every arm.')
        if occasion.instrument == 'suas' and not any(keys.get(k) and keys[k].instrument == 'pvt' for k in occasion.prerequisite_keys):
            issue(path + '.prerequisite_keys', 'Mission requires an explicitly selected study PVT prerequisite.')
        if occasion.instrument == 'openmatb' and sum(o.instrument == 'questionnaire' and o.target_key == occasion.key for o in study.occasions) != 1:
            issue(path, 'Schedule exactly one workload questionnaire targeting this native occasion.')
        for message in binding_issues(db, occasion): issue(path + '.config', message)
        for key in occasion.prerequisite_keys:
            prior = keys.get(key)
            if prior is None or prior.visit_ordinal != occasion.visit_ordinal or prior.order >= occasion.order:
                issue(path + '.prerequisite_keys', 'Prerequisites must reference earlier occasions in this visit.')
        if occasion.instrument == 'questionnaire':
            target = keys.get(occasion.target_key)
            if target is None or target.instrument != 'openmatb':
                issue(path + '.target_key', 'The implemented workload questionnaire requires an OpenMATB target.')
            elif (any(o.visit_ordinal == target.visit_ordinal and target.order < o.order < occasion.order
                      and not (o.instrument == 'physiology' and o.accompanying_key == target.key
                               and o.collection_group == target.collection_group and o.collection_group)
                      for o in study.occasions)
                  or set(occasion.prerequisite_keys) - {target.key}
                  or any(r.before_key == occasion.key for r in study.recovery_intervals)):
                issue(path, 'Native ratings must be immediate after their target (declared H10 accompaniment allowed); only the exact target may be a questionnaire prerequisite. Delayed questionnaires are unsupported.')
        if occasion.accompanying_key:
            target = keys.get(occasion.accompanying_key)
            if (occasion.instrument != 'physiology' or target is None or target.instrument not in {'openmatb','liftoff','suas'}
                    or target.order >= occasion.order or not occasion.collection_group or target.collection_group != occasion.collection_group):
                issue(path + '.accompanying_key', 'H10 accompaniment requires an earlier native, Liftoff or mission occasion in the same explicit collection group.')
        if occasion.target_key:
            target = keys.get(occasion.target_key)
            if occasion.instrument != 'questionnaire' or target is None or target.order >= occasion.order or target.locale != occasion.locale:
                issue(path + '.target_key', 'Questionnaire must follow its target and use the same frozen language.')
        if occasion.target_key or occasion.accompanying_key:
            for key in filter(None, [occasion.target_key, occasion.accompanying_key]):
                target = keys.get(key)
                if target is None or target.visit_ordinal != occasion.visit_ordinal:
                    issue(path, 'Target/accompaniment must reference an occasion in this visit.')
    if len({i.key for i in study.recovery_intervals}) != len(study.recovery_intervals): issue('study.recovery_intervals', 'Interval keys must be unique.')
    for i, interval in enumerate(study.recovery_intervals):
        anchor, before = keys.get(interval.anchor_key), keys.get(interval.before_key)
        if not anchor or not before or anchor.visit_ordinal != before.visit_ordinal or anchor.order >= before.order:
            issue(f'study.recovery_intervals.{i}', 'Recovery requires an earlier anchor and later assessment in the same visit.')
    outcome_keys = {o.key for o in analysis.outcomes}
    if len(outcome_keys) != len(analysis.outcomes): issue('analysis.outcomes', 'Outcome keys must be unique.')
    from .study_analysis_catalog import issues as descriptive_issues
    issues.extend(descriptive_issues(study, analysis))
    for i, outcome in enumerate(analysis.outcomes):
        if any(key not in keys for key in outcome.occasion_keys): issue(f'analysis.outcomes.{i}.occasion_keys', 'Unknown occasion reference.')
    for i, contrast in enumerate(analysis.contrasts):
        if contrast.left_outcome not in outcome_keys or contrast.right_outcome not in outcome_keys:
            issue(f'analysis.contrasts.{i}', 'Unknown outcome reference.')
    return issues


def rehearse(db, identity):
    """Run the actual materialization and attempt lifecycle in a disposable database."""
    from .models import Participant, Visit
    from .assessment_service import create_attempt, transition
    from .assessment_schemas import AttemptIn
    from datetime import date
    draft = _draft(db, identity)
    issues = validate(db, identity)
    if issues: raise HTTPException(422, dict(code='study_validation_failed', issues=issues))
    payload = json.loads(draft.payload_json)
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    counts = dict(assignments=0, occasions=0, attempts=0)
    try:
        with Session(engine) as isolated:
            # Rehearsal versions are confined to this database, never approved in the workspace.
            version = _freeze_row(draft, actor='SYNTHETIC REHEARSAL', reason='Isolated service exercise', rehearsal_id='synthetic')
            isolated.add(version); isolated.flush()
            _bind_workspace(isolated, version)
            isolated.add(StudyActivation(version_id=version.id, actor='SYNTHETIC REHEARSAL', reason='ephemeral'))
            isolated.add(Participant(id='SYNTHETIC', enrollment_date=date(2000, 1, 1))); isolated.flush()
            for v in payload['study']['visits']:
                visit = Visit(participant_id='SYNTHETIC', visit_ordinal=v['ordinal'], scheduled_day=v['scheduled_day'])
                isolated.add(visit); isolated.flush()
                assignment = assign(isolated, version.id, 'SYNTHETIC', visit.id, payload['study']['arms'][0], actor='SYNTHETIC REHEARSAL')
                counts['assignments'] += 1
                occasion_ids = json.loads(assignment.occasions_json)
                for scheduled in sorted(payload['study']['occasions'], key=lambda o: o['order']):
                    if scheduled['key'] not in occasion_ids: continue
                    occasion_id = occasion_ids[scheduled['key']]
                    # Lifecycle exercise is deliberately practice; rehearsal cannot yield study evidence.
                    from .assessment_models import AssessmentOccasion
                    occasion = isolated.get(AssessmentOccasion, occasion_id)
                    occasion_spec = next(o for o in payload['study']['occasions'] if o['key'] == next(k for k, value in json.loads(assignment.occasions_json).items() if value == occasion_id))
                    target = None
                    if occasion_spec['target_key']:
                        from .assessment_models import AssessmentAttempt
                        target = isolated.exec(select(AssessmentAttempt).where(AssessmentAttempt.occasion_id == json.loads(assignment.occasions_json)[occasion_spec['target_key']])).one().id
                    attempt = create_attempt(isolated, occasion_id, AttemptIn(execution_purpose='practice', target_attempt_id=target))
                    transition(isolated, attempt.id, 'started'); transition(isolated, attempt.id, 'finished')
                    counts['occasions'] += 1; counts['attempts'] += 1
            isolated.rollback()
    finally: engine.dispose()
    row = StudyRehearsal(draft_id=draft.id, draft_sha256=draft.sha256,
        result_json=canonical(dict(isolation='ephemeral_database', synthetic=True, hardware_evidence=False, **counts)))
    db.add(row); db.flush()
    return row


def _freeze_row(draft, *, actor, reason, rehearsal_id):
    study_id, analysis_id = str(uuid4()), str(uuid4())
    payload = json.loads(draft.payload_json)
    study, analysis = payload['study'], payload['analysis']
    study.update(version_id=study_id, analysis_plan_id=analysis_id)
    analysis.update(version_id=analysis_id, study_version_id=study_id)
    return StudyVersion(id=study_id, analysis_plan_id=analysis_id, study_id=study['study_id'], template_family=study['template_family'],
        study_json=canonical(study), analysis_json=canonical(analysis), study_sha256=payload_hash(study), analysis_sha256=payload_hash(analysis),
        draft_sha256=draft.sha256, rehearsal_id=rehearsal_id, actor=actor, reason=reason)


def _bind_workspace(db, version):
    from .study_models import StudyMetadata
    protocol = selected_protocol()
    metadata = db.get(StudyMetadata, 1)
    if metadata and (metadata.protocol_id, metadata.schedule_sha256) != (protocol.protocol_id, protocol.schedule_sha256):
        raise HTTPException(409, 'study_protocol_mismatch')
    workspace = db.get(StudyWorkspace, 1)
    expected = (version.study_id, version.template_family, protocol.protocol_id, protocol.schedule_sha256)
    if workspace:
        actual = (workspace.study_id, workspace.template_family, workspace.deployment_protocol_id, workspace.deployment_schedule_sha256)
        if expected != actual: raise HTTPException(409, 'study_workspace_mismatch')
    else:
        db.add(StudyWorkspace(study_id=expected[0], template_family=expected[1], deployment_protocol_id=expected[2], deployment_schedule_sha256=expected[3])); db.flush()


def freeze(db, identity, body):
    lock_registry(db)
    draft = _draft(db, identity); named(body['actor'])
    if not body['reason'].strip(): raise HTTPException(422, 'Attestation reason required.')
    if draft.frozen_version_id: raise HTTPException(409, 'Draft already frozen.')
    issues = validate(db, identity)
    if issues: raise HTTPException(422, dict(code='study_validation_failed', issues=issues))
    rehearsal = db.get(StudyRehearsal, body['rehearsal_id'])
    if body['sha256'] != draft.sha256 or rehearsal is None or rehearsal.draft_id != draft.id or rehearsal.draft_sha256 != draft.sha256:
        raise HTTPException(409, 'Rehearsal and attestation must match the current draft fingerprint. Rehearse the edited draft.')
    if json.loads(draft.payload_json)['study']['synthetic']: raise HTTPException(422, 'Synthetic templates cannot be scientifically approved. Author and explicitly classify a real draft.')
    version = _freeze_row(draft, actor=body['actor'], reason=body['reason'], rehearsal_id=rehearsal.id)
    _bind_workspace(db, version)
    db.add(version); draft.frozen_version_id = version.id; db.add(draft); db.flush()
    return version


def get_version(db, identity):
    row = db.get(StudyVersion, identity)
    if row is None: raise HTTPException(404, 'frozen study version not found')
    return row


def version_view(db, identity):
    row = get_version(db, identity)
    return {**row.model_dump(mode='json', exclude={'study_json', 'analysis_json'}), 'study': json.loads(row.study_json), 'analysis': json.loads(row.analysis_json)}


def activate(db, identity, *, actor, reason):
    lock_registry(db)
    named(actor); version = get_version(db, identity); _bind_workspace(db, version)
    row = StudyActivation(version_id=identity, actor=actor, reason=reason)
    db.add(row); db.flush(); return row


def active_version(db):
    row = db.exec(select(StudyActivation).order_by(StudyActivation.id.desc())).first()
    return row.version_id if row else None


def assignment_is_current(db, row):
    return db.exec(select(StudyAmendment).where(StudyAmendment.prior_assignment_id == row.id)).first() is None


def assignment_started(db, row):
    from .assessment_models import AssessmentAttempt
    return any(a.started_at is not None for a in db.exec(select(AssessmentAttempt).where(
        AssessmentAttempt.occasion_id.in_(list(json.loads(row.occasions_json).values())))).all())


def assign(db, identity, participant_id, visit_id, arm, *, actor, replacing=None):
    lock_registry(db)
    from .models import Visit
    from .assessment_service import create_occasion
    from .assessment_schemas import OccasionIn
    named(actor); version = get_version(db, identity); _bind_workspace(db, version)
    if active_version(db) != identity: raise HTTPException(409, 'Explicitly activate this frozen version before assigning collection.')
    visit = db.get(Visit, visit_id)
    if not visit or visit.participant_id != participant_id: raise HTTPException(422, 'Assignment requires this participant’s planned visit.')
    study = json.loads(version.study_json)
    planned = next((v for v in study['visits'] if v['ordinal'] == visit.visit_ordinal), None)
    if not planned or planned['scheduled_day'] != visit.scheduled_day: raise HTTPException(422, 'Visit schedule differs from the frozen version.')
    if arm not in study['arms']: raise HTTPException(422, 'Select a frozen assignment arm.')
    current = [a for a in db.exec(select(StudyAssignment).where(StudyAssignment.visit_id == visit_id)).all() if assignment_is_current(db, a)]
    if current and (len(current) != 1 or current[0].id != replacing): raise HTTPException(409, 'Visit already assigned. Use an explicit future amendment.')
    row = StudyAssignment(version_id=identity, participant_id=participant_id, visit_id=visit_id, arm=arm, occasions_json='{}', actor=actor)
    occasions = {}
    for spec in sorted(study['occasions'], key=lambda s: s['order']):
        if spec['visit_ordinal'] != visit.visit_ordinal: continue
        occasion = create_occasion(db, OccasionIn(participant_id=participant_id, visit_id=visit_id, instrument=spec['instrument'],
            phase=spec['phase'], order=spec['order'], condition=spec['condition_by_arm'][arm], version_ref=identity,
            collection_group_id=f"{row.id}:{spec['collection_group']}" if spec['collection_group'] else None,
            accompanying_occasion_id=occasions.get(spec['accompanying_key'])))
        occasions[spec['key']] = occasion.id
    row.occasions_json = canonical(occasions); db.add(row); db.flush(); return row


def amend(db, identity, assignment_ids, *, actor, reason):
    lock_registry(db)
    named(actor)
    if not reason.strip(): raise HTTPException(422, 'Amendment reason required.')
    if len(set(assignment_ids)) != len(assignment_ids): raise HTTPException(422, 'Select each assignment once.')
    priors = []
    for key in assignment_ids:
        row = db.get(StudyAssignment, key)
        if row is None or not assignment_is_current(db, row): raise HTTPException(409, 'Assignment is absent or already amended.')
        if assignment_started(db, row): raise HTTPException(409, 'Started visits remain pinned to their original frozen version.')
        priors.append(row)
    result = []
    for prior in priors:
        replacement = assign(db, identity, prior.participant_id, prior.visit_id, prior.arm, actor=actor, replacing=prior.id)
        old, new = version_view(db, prior.version_id), version_view(db, identity)
        diff = {key: {'before': old[key], 'after': new[key]} for key in ('study', 'analysis') if old[key] != new[key]}
        db.add(StudyAmendment(prior_assignment_id=prior.id, replacement_assignment_id=replacement.id, actor=actor, reason=reason, diff_json=canonical(diff)))
        db.flush(); result.append(replacement)
    return result


def install_registry_guards(engine):
    with engine.begin() as conn:
        conn.execute(text("CREATE TRIGGER IF NOT EXISTS frozen_study_draft_update BEFORE UPDATE ON study_draft WHEN OLD.frozen_version_id IS NOT NULL BEGIN SELECT RAISE(ABORT, 'immutable frozen draft'); END"))
        conn.execute(text("CREATE TRIGGER IF NOT EXISTS frozen_study_draft_delete BEFORE DELETE ON study_draft WHEN OLD.frozen_version_id IS NOT NULL BEGIN SELECT RAISE(ABORT, 'immutable frozen draft'); END"))
        conn.execute(text("CREATE TRIGGER IF NOT EXISTS immutable_recovery_identity BEFORE UPDATE ON study_recovery_interval WHEN OLD.ended_at IS NOT NULL OR NEW.assignment_id != OLD.assignment_id OR NEW.interval_key != OLD.interval_key OR NEW.anchor_attempt_id != OLD.anchor_attempt_id OR NEW.started_at != OLD.started_at OR NEW.actor != OLD.actor OR NEW.reason != OLD.reason BEGIN SELECT RAISE(ABORT, 'immutable recovery record'); END"))
        conn.execute(text("CREATE TRIGGER IF NOT EXISTS immutable_recovery_delete BEFORE DELETE ON study_recovery_interval BEGIN SELECT RAISE(ABORT, 'immutable recovery record'); END"))
        for table in ('study_version', 'study_rehearsal', 'study_validation', 'study_native_rating', 'study_activation', 'study_assignment', 'study_amendment', 'study_attempt_selection'):
            for operation in ('UPDATE', 'DELETE'):
                conn.execute(text(f'CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, \'immutable study record\'); END'))
