"""Explicit frozen-plan descriptive execution. No legacy inferential entry points."""
import json
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import HTTPException
from sqlmodel import select
from app.assessment_models import AssessmentOccasion, AssessmentAttempt, AssessmentOccasionClassification
from app.study_registry_models import StudyVersion, StudyAssignment
from app.study_registry_schemas import StudySpecV1, AnalysisPlanV1
from app.study_analysis_models import StudyAnalysisExecution, StudyAnalysisArtifact, StudyAnalysisInput
from app.hcf_derivations import canonical, fingerprint, derive
from app.study_analysis_rules import select_attempt, aggregate, compare_configurations, pooling_groups, analysis_unit, named
from app.study_analysis_sources import read_source
from app.study_analysis_eligibility import evaluate
from matb_integration.analysis.study_calculators import calculate


def version(db, identity):
    row=db.get(StudyVersion,identity)
    if row is None: raise HTTPException(404,'Frozen study version not found.')
    study=json.loads(row.study_json); plan=json.loads(row.analysis_json)
    from app.study_analysis_catalog import issues
    problems=issues(StudySpecV1.model_validate(study),AnalysisPlanV1.model_validate(plan))
    from app.study_analysis_bundle import calculation_binding, dependency_versions
    if plan.get('calculation_sha256')!=calculation_binding() or plan.get('calculator_dependencies')!=dependency_versions(set(study['enabled_instruments'])): problems.append(dict(path='calculation_sha256',message='Frozen calculator/dependency identity differs from this installation or was not recorded.'))
    if not plan.get('eligibility_policy'): problems.append(dict(path='eligibility_policy',message='Missing frozen policy.'))
    if problems: raise HTTPException(409,dict(code='frozen_plan_not_executable',issues=problems,message='Preserve this historical plan; freeze a new executable version with its actual new planning date.'))
    return row,study,plan


def resolved_association(spec, visit_id, classification=None):
    """Analysis association only; original occasion and exposure facts stay separate."""
    return dict(
        occasion_key=spec['key'], visit_id=visit_id,
        visit_ordinal=spec['visit_ordinal'], phase=spec['phase'], order=spec['order'],
        classification_id=classification.id if classification else None,
        basis='retrospective_analysis_association' if classification else 'prospective_assignment',
    )


def hcf_occasion_order(row):
    association = row['resolved_association']
    attempt = next(a for a in row['attempts'] if a['id'] == row['attempt_id'])
    return (association['visit_ordinal'], association['order'], attempt['ordinal'], attempt['id'])


def _contexts(db, v, study):
    contexts=[]; assigned=set()
    specs = {spec['key']: spec for spec in study['occasions']}
    from app.study_registry import assignment_is_current
    for assignment in db.exec(select(StudyAssignment).where(StudyAssignment.version_id==v.id).order_by(StudyAssignment.id)):
        if not assignment_is_current(db,assignment): continue
        for key,occasion_id in json.loads(assignment.occasions_json).items():
            assigned.add(occasion_id)
            contexts.append(dict(occasion_id=occasion_id,occasion_key=key,assignment=assignment.model_dump(mode='json'),historical=False,
                resolved_association=resolved_association(specs[key], assignment.visit_id)))
    # Only a named explicit association to this exact frozen version supplies a historical occasion.
    for occasion in db.exec(select(AssessmentOccasion).where(AssessmentOccasion.origin.in_(['legacy','legacy_compat'])).order_by(AssessmentOccasion.id)):
        history=db.exec(select(AssessmentOccasionClassification).where(AssessmentOccasionClassification.occasion_id==occasion.id).order_by(AssessmentOccasionClassification.id)).all()
        if not history or occasion.id in assigned: continue
        current=history[-1]
        matching=[o for o in study['occasions'] if current.version_ref==v.id and o['phase']==current.phase and o['order']==current.order and o['instrument']==occasion.instrument]
        from app.models import Visit
        visit=db.get(Visit,current.visit_id)
        matching=[o for o in matching if visit and o['visit_ordinal']==visit.visit_ordinal]
        if len(matching)==1 and named(current.reviewer) and current.reason:
            contexts.append(dict(occasion_id=occasion.id,occasion_key=matching[0]['key'],assignment=None,historical=True,
                resolved_association=resolved_association(matching[0], current.visit_id, current),
                classification_history=[h.model_dump(mode='json') for h in history]))
    return contexts


def deferred_selection(db, request):
    """Metadata-only selection at queue acceptance; raw decoding waits for station idle."""
    v, study, plan = version(db, request['version_id'])
    contexts = _contexts(db, v, study)
    attempts = {}
    for context in contexts:
        candidates = [a.model_dump(mode='json') for a in db.exec(select(AssessmentAttempt).where(AssessmentAttempt.occasion_id == context['occasion_id']).order_by(AssessmentAttempt.ordinal))]
        attempts[context['occasion_id']] = candidates
    return dict(at=datetime.now(timezone.utc).isoformat(), contexts=contexts, attempts=attempts,
                semantics='Occasion/attempt set frozen on acceptance; eligibility and source availability observed when exclusive execution begins.')


def preview(db, request):
    v,study,plan=version(db,request['version_id']); policy=plan['eligibility_policy']
    specs={o['key']:o for o in study['occasions']}; rows=[]
    cutoff=request.get("_selection_cutoff")
    contexts=cutoff["contexts"] if cutoff else _contexts(db,v,study)
    context_ids={c['occasion_id'] for c in contexts}
    if set(request.get('attempts',{}))-context_ids: raise HTTPException(422,'Attempt selection references an occasion outside this plan.')
    for context in contexts:
        occasion=db.get(AssessmentOccasion,context['occasion_id']); spec=specs[context['occasion_key']]
        attempts=list(db.exec(select(AssessmentAttempt).where(AssessmentAttempt.occasion_id==occasion.id).order_by(AssessmentAttempt.ordinal)))
        all_attempts=cutoff["attempts"][occasion.id] if cutoff else [a.model_dump(mode='json') for a in attempts]
        try: selected=select_attempt(all_attempts,policy['repeat_selection'],request.get('attempts',{}).get(occasion.id))
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
        attempt=next((a for a in attempts if selected and a.id==selected['id']),None)
        denominator=policy['incomplete_denominator']=='assigned' or any(a.started_at or a.acquisition_state in {'started','finished','interrupted'} for a in attempts) if policy['incomplete_denominator']!='finished' else any(a.acquisition_state=='finished' for a in attempts)
        if context['historical'] and policy['incomplete_denominator']=='assigned': denominator=False
        row=dict(**context,participant_id=occasion.participant_id,visit_id=context['resolved_association']['visit_id'],attempt_id=attempt.id if attempt else None,
            instrument=occasion.instrument,attempts=all_attempts,denominator=bool(denominator),values={},criteria={},source=None,calculations={},eligible=False,
            occasion=occasion.model_dump(mode='json'),configuration=None)
        relevant=[o for o in plan['outcomes'] if context['occasion_key'] in o['occasion_keys'] and o['metric']!='screen.hcf']
        if occasion.instrument=='screen' and context['occasion_key'] in policy['hcf_screen_keys'] and not relevant:
            relevant=[dict(key='__hcf_screen',metric='screen.simple_rt')]
        if attempt:
            try:
                source=read_source(db,attempt,occasion.instrument,metric_ids=request.get('native_metric_ids',{}).get(attempt.id,[]))
                results={o['key']:calculate(source,o) for o in relevant}
                # Explicit selected native IDs must cover exactly the declared outcome keys, never an arbitrary available metric.
                if occasion.instrument=='openmatb':
                    expected={o['metric'].split('.',1)[1] for o in relevant}
                    if {m['key'] for m in source['selected_metrics']}!=expected: raise ValueError('Selected native metric IDs must match the exact frozen outcome selectors.')
                row.update(source=source,calculations=results)
            except (ValueError,KeyError,OSError,TypeError,ImportError) as exc:
                row['source_error']=str(exc); results={}; source=None
            criteria,eligible=evaluate(db,attempt,source=source,results=results,policy=policy,
                historical_allowed=plan['rules']['historical_unknowns']=='reviewed_classification_required',
                assignment_id=context['assignment']['id'] if context['assignment'] else None,version_id=v.id,
                occasion_key=spec['key'],config=spec['config'],repeat_policy=study['repeat_policy'],interruption_policy=study['interruption_policy'],qualification_ids=request.get('qualification_ids',{}).get(attempt.id,{}))
            criteria['occasion']=dict(passed=not context['historical'] or plan['rules']['historical_unknowns']=='reviewed_classification_required',required=True,reason='Exact assigned occasion or named historical association permitted by the frozen plan.',evidence=context,href=f'/assessments/occasions/{occasion.id}')
            criteria['denominator_coverage']=dict(passed=bool(denominator),required=True,reason='Historical analysis association does not establish assignment coverage; only the frozen denominator rule is applied.',evidence=dict(rule=policy['incomplete_denominator'],assignment_id=context['assignment']['id'] if context['assignment'] else None),href=f'/assessments/occasions/{occasion.id}')
            eligible=eligible and criteria['occasion']['passed'] and bool(denominator)
            row.update(criteria=criteria,eligible=eligible)
            if source and source.get('capture'):
                from app.evidence_models import EvidenceQualificationArtifact
                import base64
                ids=[c['evidence']['record']['id'] for k,c in criteria.items() if k in {'physical','human'} and isinstance(c.get('evidence'),dict) and 'record' in c['evidence']]
                source['qualification_artifacts']=[dict(qualification_id=a.qualification_id,name=a.name,content_base64=base64.b64encode(a.content).decode()) for a in db.exec(select(EvidenceQualificationArtifact).where(EvidenceQualificationArtifact.qualification_id.in_(ids)).order_by(EvidenceQualificationArtifact.qualification_id,EvidenceQualificationArtifact.name))]
            if eligible:
                row['values']={key:r['value'] for key,r in results.items() if key!='__hcf_screen' and r.get('value') is not None and (occasion.instrument!='openmatb' or r.get('source_eligible'))}
            # Original admitted binding proves resolved configuration; planned configuration alone is not measured exposure.
            if criteria['preparation']['passed']:
                row['configuration']=dict(task=spec['config'],instructions=study['implementation_sha256'].get(occasion.instrument),language=spec['locale'],
                    visual=study['implementation_sha256'].get(occasion.instrument),input=spec['config'].get('input_mapping'),timing=study['implementation_sha256'].get(occasion.instrument),scoring=spec['config'].get('scoring'))
            start=attempt.started_at
            row['planning_chronology']=dict(plan_frozen_at=v.created_at.isoformat(),acquisition_started_at=start.isoformat() if start else None,
                acquired_after_freeze=start.replace(tzinfo=timezone.utc)>=v.created_at.replace(tzinfo=timezone.utc) if start else None,prior_result_inspection='not_established')
        else:
            row['criteria']['selection']=dict(passed=False,required=True,reason='No attempt selected by the frozen rule. Incomplete occasions remain in the declared denominator.',evidence=all_attempts,href=f'/assessments/occasions/{occasion.id}')
        rows.append(row)
    comparisons={}
    for outcome in plan['outcomes']:
        candidates=[r for r in rows if r['occasion_key'] in outcome['occasion_keys'] and r['eligible'] and outcome['key'] in r['values']]
        report=pooling_groups(plan,candidates,policy)
        comparisons[outcome['key']]=report
        for row in candidates:
            if not report['groups'][analysis_unit(plan,row)]['passed']: row['values'].pop(outcome['key'],None)
    # Contrasts also require configuration review across their two outcome sets.
    for contrast in plan['contrasts']:
        outcomes=[o for o in plan['outcomes'] if o['key'] in {contrast['left_outcome'],contrast['right_outcome']}]
        keys={key for o in outcomes for key in o['occasion_keys']}
        comparison=pooling_groups(plan,[r for r in rows if r['occasion_key'] in keys and r['eligible'] and any(o['key'] in r['values'] for o in outcomes)],policy,contrast=True)
        comparisons['contrast:'+contrast['key']]=comparison
    selected_ids={r['attempt_id'] for r in rows if r['attempt_id']}
    for key in ('native_metric_ids','qualification_ids'):
        if set(request.get(key,{}))-selected_ids: raise HTTPException(422,'Evidence selection references an unselected attempt.')
    for kinds in request.get('qualification_ids',{}).values():
        if set(kinds)-{'physical_timing','human_calibration'}: raise HTTPException(422,'Unknown qualification kind.')
    snapshot=dict(schema_version='study-descriptive-input-v1',version=v.model_dump(mode='json'),study=study,plan=plan,rows=rows,comparisons=comparisons,
        selected_attempts=request.get('attempts',{}),qualification_selection=request.get('qualification_ids',{}),hcf_selection=request.get('hcf_attempts',{}),automatic_model=None)
    return snapshot


def freeze_input(db, request):
    """Freeze exact raw/eligibility selection. Caller owns admission gate and transaction.

    This performs source validation and bounded calculator work; schedule/gate this
    operation as heavy work too. Queued execution must use the returned immutable ID.
    """
    if not named(request.get('actor')) or not request.get('reason','').strip(): raise HTTPException(422,'Named researcher and execution reason required.')
    snapshot=preview(db,request)
    identity=fingerprint(dict(snapshot=snapshot,request=request))
    row=db.get(StudyAnalysisInput,identity)
    if row is None:
        row=StudyAnalysisInput(id=identity,version_id=request['version_id'],snapshot_json=canonical(snapshot),request_json=canonical(request),actor=request['actor'],reason=request['reason'])
        db.add(row);db.flush()
    return row


def execute(db, request):
    return execute_frozen(db,freeze_input(db,request).id)


def execute_frozen(db, input_id):
    frozen=db.get(StudyAnalysisInput,input_id)
    if frozen is None: raise HTTPException(404,'Frozen descriptive input not found.')
    snapshot=json.loads(frozen.snapshot_json);request=json.loads(frozen.request_json)
    from app.study_analysis_bundle import calculation_binding, dependency_versions
    if snapshot['plan']['calculation_sha256']!=calculation_binding(): raise HTTPException(409,'Pinned calculator differs; preserve the queued input and restore its implementation.')
    if snapshot['plan']['calculator_dependencies']!=dependency_versions(set(snapshot['study']['enabled_instruments'])): raise HTTPException(409,'Pinned calculator dependency identity differs; preserve the queued input and restore its environment.')
    snapshot['frozen_input_id']=input_id
    plan=snapshot['plan'];policy=plan['eligibility_policy'];rows=snapshot['rows']
    hcf=None
    if not policy['hcf_enabled'] and request.get('hcf_attempts'): raise HTTPException(422,'HCF is disabled by the frozen plan.')
    if policy['hcf_enabled']:
        candidates=[r for r in rows if r['occasion_key'] in policy['hcf_screen_keys'] and r['eligible'] and r['source']]
        if set(request.get('hcf_attempts',{}))-{r['participant_id'] for r in candidates}: raise HTTPException(422,'HCF selection references a participant without eligible designated screens.')
        selected=[]
        for participant in sorted({r['participant_id'] for r in candidates}):
            options=[r for r in candidates if r['participant_id']==participant]
            requested=request.get('hcf_attempts',{}).get(participant)
            if policy['hcf_attempt_selection']=='explicit':
                options=[r for r in options if r['attempt_id']==requested]
            else:
                if requested is not None: raise HTTPException(422,'HCF explicit selection cannot override frozen first/latest rule.')
                options=[r for r in options if next(a for a in r['attempts'] if a['id']==r['attempt_id'])['acquisition_state']=='finished']
                options = sorted(options, key=hcf_occasion_order)
                options=options[:1] if policy['hcf_attempt_selection']=='first_finished' else options[-1:]
            if len(options)!=1: raise HTTPException(422,'Select exactly one designated eligible HCF screen attempt per participant.')
            row=options[0]
            from matb_integration.screen.scoring import score_screen
            scores=score_screen(row['source']['raw'])
            selected.append(dict(participant_id=participant,attempt_id=row['attempt_id'],screen_id=row['source']['screen_id'],raw_sha256=fingerprint(row['source']['raw']),scoring_sha256=fingerprint(scores),scores=scores))
        hcf_rows=[r for r in candidates if r['attempt_id'] in {s['attempt_id'] for s in selected}]
        comparison=compare_configurations([r['configuration'] for r in hcf_rows],policy['configuration_pooling'],policy.get('pooling_attestation'))
        if selected and not comparison['passed']: raise HTTPException(422,'HCF reference cohort configuration pooling is not permitted by the frozen plan.')
        snapshot['hcf_comparison']=comparison
        derived=derive(db,selected,plan_id=plan['version_id']); hcf=dict(id=derived.id,created_at=derived.created_at.isoformat(),snapshot=json.loads(derived.snapshot_json))
        for row in rows:
            estimate=hcf['snapshot']['values'].get(row['participant_id'])
            for outcome in plan['outcomes']:
                if outcome['metric']=='screen.hcf' and row['occasion_key'] in outcome['occasion_keys'] and estimate and row['eligible'] and snapshot['comparisons'][outcome['key']]['passed']:
                    row['values'][outcome['key']]=estimate['value']
    snapshot['hcf']=hcf
    result=aggregate(plan,rows,policy['missing_handling'])
    for contrast in plan['contrasts']:
        item=result['contrasts'][contrast['key']]
        failed={group.rsplit(':',1)[0] for group,report in snapshot['comparisons']['contrast:'+contrast['key']]['groups'].items() if not report['passed']}
        for unit in failed: item['values'].pop(unit,None)
        item['observed']=len(item['values'])
        if failed:
            item['excluded_configuration_units']=sorted(failed)
            item['missing']=sorted(set(item['missing'])|failed)
    from app.study_analysis_bundle import implementation_artifacts, render_figure
    try: files,implementation=implementation_artifacts({r['instrument'] for r in rows if r['source']})
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    snapshot['implementation']=implementation
    identity=str(uuid4()); data_sha=fingerprint(snapshot)
    result['figure']=render_figure(result)
    record=StudyAnalysisExecution(id=identity,version_id=request['version_id'],plan_sha256=snapshot['version']['analysis_sha256'],data_sha256=data_sha,
        implementation_sha256=fingerprint(implementation),request_json=canonical(request),snapshot_json=canonical(snapshot),result_json=canonical(result),actor=request['actor'],reason=request['reason'])
    db.add(record); db.flush()
    files.update({'input.json':canonical(snapshot).encode(),'result.json':canonical(result).encode(),'figure.svg':result['figure'].encode(),
        'execution.json':canonical(record.model_dump(mode='json',exclude={'snapshot_json','result_json'})).encode(),
        'selection.json':canonical(frozen.model_dump(mode='json')).encode()})
    import hashlib
    files['checksums.json']=canonical({name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())}).encode()
    for path,data in files.items(): db.add(StudyAnalysisArtifact(execution_id=identity,path=path,sha256=hashlib.sha256(data).hexdigest(),content=data))
    db.flush(); return record


def read(db,identity,*,current=True):
    row=db.get(StudyAnalysisExecution,identity)
    if row is None: raise HTTPException(404,'Analysis execution not found.')
    result={**row.model_dump(mode='json'),'snapshot':json.loads(row.snapshot_json),'result':json.loads(row.result_json)}
    result.pop('snapshot_json'); result.pop('result_json')
    if current:
        try:
            current_request=json.loads(row.request_json);current_request.pop('_selection_cutoff',None)
            present=preview(db,current_request); old=result['snapshot']
            def comparable(value):
                value=json.loads(canonical({k:v for k,v in value.items() if k not in {'hcf','hcf_comparison','implementation','frozen_input_id'}}))
                for item in value['rows']: item.pop('values',None)
                return value
            result['current_applicability']=dict(changed=fingerprint(comparable(old))!=fingerprint(comparable(present)),snapshot=present)
            readiness={}
            from app.study_admission import for_occasion
            from app.study_policies import require_preparation
            for item in present['rows']:
                if item['assignment']:
                    try: readiness[item['occasion_id']]=dict(status='ready',selected=require_preparation(db,for_occasion(db,item['occasion_id'])))
                    except HTTPException as exc: readiness[item['occasion_id']]=dict(status='not_ready',reason=exc.detail)
            result['current_applicability']['current_preparation_readiness']=readiness
        except HTTPException as exc: result['current_applicability']=dict(changed=True,error=exc.detail)
    return result
