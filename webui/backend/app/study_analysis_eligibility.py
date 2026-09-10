"""Separate source, purpose, preparation, timing and human qualification criteria."""
import json
from sqlmodel import select
from app.hcf_derivations import fingerprint
from app.study_analysis_rules import named, purpose_criterion
from app.study_registry_models import StudyPreparationAdmission, StudyPreparation, StudyPreparationEvent


def qualification_criterion(items, kind, capture, selected_id=None):
    candidates=[i for i in items if i['record']['kind']==kind and (selected_id is None or i['record']['id']==selected_id)]
    if len(candidates)!=1:
        return dict(passed=False,reason='Select exactly one linked report of this kind.',evidence=candidates)
    item=candidates[0]; record=item['record']; binding=item['binding']
    manifest=json.loads(capture['manifest_json'])
    context=record.get('context') or {}
    passed=(not record.get('revocations') and record.get('assessment',{}).get('status')=='PASS'
            and named(record.get('reviewer')) and named(binding.get('reviewer'))
            and bool(binding.get('rationale')) and binding.get('context_source')=='reviewer_attestation'
            and binding.get('context')==context and binding.get('capture_manifest_sha256')==capture['manifest_sha256']
            and context.get('software_versions',{}).get('acquisition_commit')==manifest.get('source_commit')
            and context.get('presentation',{}).get('profile_id')==manifest.get('profile_id'))
    return dict(passed=bool(passed),reason='Requires a passing, context-bound named report without revocation; external human reports retain their stated claim boundary.',evidence=item)


def preparation_criterion(db, attempt, assignment_id, version_id, occasion_key, config):
    admission=db.get(StudyPreparationAdmission,attempt.id)
    if admission is None: return dict(passed=False,reason='No original preparation admission evidence.',evidence=None)
    snapshot=json.loads(admission.snapshot_json); evidence=[]; valid=True
    for item in snapshot['requirements']:
        prep=db.get(StudyPreparation,item['preparation_id'])
        if prep is None: valid=False; continue
        events=db.exec(select(StudyPreparationEvent).where(StudyPreparationEvent.id.in_([e['id'] for e in item['event_frontier']]))).all()
        by_id={e.id:e for e in events}
        valid=valid and prep.identity_sha256==item['identity_sha256'] and prep.config_sha256==item['config_sha256']
        for expected in item['event_frontier']:
            event=by_id.get(expected['id'])
            import hashlib
            valid=valid and event is not None and hashlib.sha256(event.payload_json.encode()).hexdigest()==expected['payload_sha256']
        valid=valid and all(identity in by_id and by_id[identity].passed for identity in item['decision_event_ids'])
        evidence.append(dict(preparation=prep.model_dump(mode='json'),events=[e.model_dump(mode='json') for e in sorted(events,key=lambda e:e.id)]))
    valid=valid and fingerprint(snapshot)==admission.snapshot_sha256 and snapshot['attempt_id']==attempt.id and snapshot['assignment_id']==assignment_id and snapshot['version_id']==version_id and snapshot['occasion_key']==occasion_key and snapshot['config_sha256']==fingerprint(config)
    return dict(passed=bool(valid),reason='Original admitted decision and exact event frontier; subsequent preparation does not replace it.',evidence=dict(admission=admission.model_dump(mode='json'),records=evidence))


def evaluate(db, attempt, *, source, results, policy, historical_allowed, assignment_id, version_id, occasion_key, config, repeat_policy, interruption_policy, qualification_ids):
    from app.purpose_service import provenance_view
    provenance=provenance_view(db,attempt.purpose_provenance_id) if attempt.purpose_provenance_id else None
    criteria={'purpose':purpose_criterion(provenance,historical_allowed)}
    criteria['source']=dict(passed=bool(source and source.get('verified')),reason='Exact raw source and scoring identity; independent of qualification.',evidence=source and {k:source.get(k) for k in ('attempt_id','verified','run','selected_metrics')})
    criteria['preparation']=preparation_criterion(db,attempt,assignment_id,version_id,occasion_key,config)
    items=[]
    if source and source.get('capture'):
        from app.evidence_qualification import linked
        items=linked(db,source['capture']['id'])['items']
    for key,kind in [('physical','physical_timing'),('human','human_calibration')]:
        criteria[key]=qualification_criterion(items,kind,source['capture'],qualification_ids.get(kind)) if source and source.get('capture') else dict(passed=False,reason='No context-bound qualification evidence for this source.',evidence=None)
    criteria['protocol']=dict(passed=bool(results) and all(r.get('protocol_valid',False) for r in results.values()),reason='Existing instrument validity calculations only.',evidence=results)
    interrupted=attempt.interruption_category is not None or attempt.acquisition_state=='interrupted'
    criteria['interruption']=dict(passed=not interrupted or interruption_policy['available_outcomes']=='retain_available',reason=interruption_policy['rationale'],evidence=dict(category=attempt.interruption_category,state=attempt.acquisition_state))
    repeat_ok=attempt.ordinal<=repeat_policy['max_attempts']
    if attempt.repeat_of:
        from app.assessment_models import AssessmentAttempt
        prior=db.get(AssessmentAttempt,attempt.repeat_of)
        cause='intentional_repeat' if prior and prior.acquisition_state=='finished' else prior.interruption_category if prior else None
        repeat_ok=repeat_ok and cause in repeat_policy['permitted_causes']
    criteria['repeat']=dict(passed=bool(repeat_ok),reason=repeat_policy['rationale'],evidence=dict(ordinal=attempt.ordinal,repeat_of=attempt.repeat_of,reason=attempt.repeat_reason))
    required={'purpose','repeat','interruption'}
    for key,field,permission in [('source','source_requirement','complete_verified'),('preparation','participant_preparation_requirement','prepared'),('physical','physical_requirement','qualified'),('human','human_calibration_requirement','calibrated'),('protocol','protocol_requirement','valid')]:
        if policy[field]==permission: required.add(key)
    for key,c in criteria.items():
        c['required']=key in required
        c['href']=f'/assessments/attempts/{attempt.id}' if key not in {'physical','human'} else '/evidence/qualifications'
    return criteria, all(c['passed'] for c in criteria.values() if c['required'])
