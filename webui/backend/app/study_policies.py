"""Prespecified, bounded policy contracts. Evidence and analysis engines are later tasks."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

Cause = Literal['intentional_repeat','withdrawal','operator_stop','hardware_failure','software_failure','planned_interruption','unknown','participant_stop','technical_failure','lost_connection','other']
Selection = Literal['explicit','first_finished','latest_finished']

class Criterion(Strict):
    id: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    metric: str
    comparator: Literal['gte','lte','eq']
    threshold: float = Field(allow_inf_nan=False)

class PreparationRequirement(Strict):
    # The occasion key resolves its instrument and exact configuration within this immutable version.
    occasion_key: str
    placement: Literal['before_baseline','prescribed_later']
    demonstration_required: bool
    acknowledgement_required: bool
    comprehension: list[Criterion]
    practice: list[Criterion]
    rationale: str = Field(min_length=1)

class RepeatPolicy(Strict):
    permitted_causes: list[Cause]
    max_attempts: int = Field(ge=1)
    selection: Selection
    rationale: str = Field(min_length=1)

class InterruptionPolicy(Strict):
    available_outcomes: Literal['retain_available','exclude_attempt']
    rationale: str = Field(min_length=1)

class EligibilityPolicy(Strict):
    repeat_selection: Selection
    incomplete_denominator: Literal['assigned','started','finished']
    missing_handling: Literal['exclude_outcome','complete_case']
    source_requirement: Literal['complete_verified','report_status']
    physical_requirement: Literal['qualified','report_status']
    human_calibration_requirement: Literal['calibrated','report_status']
    participant_preparation_requirement: Literal['prepared','report_status']
    protocol_requirement: Literal['valid','report_status']
    configuration_pooling: Literal['identical_only','explicit_review']
    pooling_review: str | None
    hcf_enabled: bool
    hcf_screen_keys: list[str]
    hcf_attempt_selection: Selection
    rationale: str = Field(min_length=1)

# These are existing instrument observations, not invented competence criteria.
PRACTICE_METRICS = {
    'pvt': {'pvt.median_rt_ms','pvt.lapses'},
    'screen': {'screen.simple_rt'},
    'openmatb': {'sysmon.hit_rate','track.rmse_deviation'},
}

def policy_issues(study, analysis):
    issues=[]
    def issue(path,message): issues.append(dict(path=path,message=message))
    if study.preparation_policy is None: issue('study.preparation_policy','Affirmatively author preparation requirements for every occasion; no pass threshold is supplied.')
    else:
        keys={o.key:o for o in study.occasions}
        if len(study.preparation_policy)!=len(keys) or {p.occasion_key for p in study.preparation_policy}!=set(keys):
            issue('study.preparation_policy','Specify preparation once for each frozen occasion.')
        for p in study.preparation_policy:
            occasion=keys.get(p.occasion_key)
            if not occasion: continue
            for c in p.comprehension:
                if c.metric!='comprehension.correct_fraction' or not 0<=c.threshold<=1: issue('study.preparation_policy','Comprehension supports correct_fraction with a researcher-entered threshold from 0 to 1.')
            for c in p.practice:
                if c.metric not in PRACTICE_METRICS.get(occasion.instrument,set()): issue('study.preparation_policy',f'Unsupported practice observation metric for {occasion.instrument}: {c.metric}')
            criteria=p.comprehension+p.practice
            if len({c.id for c in criteria})!=len(criteria): issue('study.preparation_policy','Criterion identities must be unique within the requirement.')
    if study.repeat_policy is None: issue('study.repeat_policy','Choose permitted repeat causes, a maximum attempt count and selection policy.')
    if study.interruption_policy is None: issue('study.interruption_policy','Choose available-outcome handling; actual interruption categories remain separately recorded.')
    policy=analysis.eligibility_policy
    if policy is None: issue('analysis.eligibility_policy','Prespecify eligibility, incomplete denominator, missing handling, pooling and HCF selection.')
    else:
        if study.repeat_policy and policy.repeat_selection!=study.repeat_policy.selection: issue('analysis.eligibility_policy.repeat_selection','Study and analysis attempt-selection policies must agree.')
        if policy.configuration_pooling=='explicit_review' and not (policy.pooling_review or '').strip(): issue('analysis.eligibility_policy.pooling_review','An explicit reviewed pooling rationale and review reference is required.')
        keys={o.key:o for o in study.occasions}
        if policy.hcf_enabled != bool(policy.hcf_screen_keys): issue('analysis.eligibility_policy.hcf_screen_keys','Enabled HCF requires designated screen occasions; disabled HCF must have none.')
        if len(set(policy.hcf_screen_keys))!=len(policy.hcf_screen_keys) or any(key not in keys or keys[key].instrument!='screen' for key in policy.hcf_screen_keys): issue('analysis.eligibility_policy.hcf_screen_keys','Designate unique screen occasions. HCF selects exactly one eligible attempt per participant.')
    return issues


def require_preparation(context):
    from fastapi import HTTPException
    # Task4 must replace this hook with measured evidence evaluation. No prose interpretation.
    requirements=context['preparation_policy']
    required=[p for p in requirements if (p['placement']=='before_baseline' or p['occasion_key']==context['occasion_key']) and
              (p['demonstration_required'] or p['acknowledgement_required'] or p['comprehension'] or p['practice'])]
    if required:
        raise HTTPException(409,dict(code='study_preparation_engine_pending',message='This version requires measured preparation. Preparation evaluation is not implemented yet.',occasion_keys=[p['occasion_key'] for p in required],assignment_url='/study/assignments'))
