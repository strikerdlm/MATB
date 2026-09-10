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

class PoolingAttestation(Strict):
    actor: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    reference: str = Field(min_length=1)


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
    pooling_attestation: PoolingAttestation | None = None
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
            if occasion.instrument == 'openmatb' and p.placement == 'prescribed_later' and p.practice:
                issue('study.preparation_policy', 'This adapter must complete native practice derivation before baseline. Move native practice before baseline; later native recognition/comprehension may remain prescribed. / Este adaptador debe evaluar la práctica nativa antes de la línea base. Mueva la práctica nativa antes de la línea base; puede conservar el reconocimiento/comprensión posterior prescrito.')
            for c in p.practice:
                if c.metric not in PRACTICE_METRICS.get(occasion.instrument,set()): issue('study.preparation_policy',f'Unsupported practice observation metric for {occasion.instrument}: {c.metric}')
            if occasion.instrument == 'openmatb' and p.placement == 'before_baseline' and any([p.demonstration_required,p.acknowledgement_required,p.comprehension,p.practice]):
                prior_native = [other for other in study.preparation_policy if other.occasion_key != p.occasion_key
                    and other.placement == 'before_baseline' and other.occasion_key in keys
                    and keys[other.occasion_key].instrument == 'openmatb' and keys[other.occasion_key].visit_ordinal == occasion.visit_ordinal
                    and keys[other.occasion_key].order < occasion.order
                    and any([other.demonstration_required,other.acknowledgement_required,other.comprehension,other.practice])]
                if prior_native: issue('study.preparation_policy','Only one native runtime can be held before baseline. Explicitly prescribe later preparation for subsequent native occasions with run-specific callsign recognition.')
            criteria=p.comprehension+p.practice
            if len({c.id for c in criteria})!=len(criteria): issue('study.preparation_policy','Criterion identities must be unique within the requirement.')
    if study.repeat_policy is None: issue('study.repeat_policy','Choose permitted repeat causes, a maximum attempt count and selection policy.')
    if study.interruption_policy is None: issue('study.interruption_policy','Choose available-outcome handling; actual interruption categories remain separately recorded.')
    policy=analysis.eligibility_policy
    if policy is None: issue('analysis.eligibility_policy','Prespecify eligibility, incomplete denominator, missing handling, pooling and HCF selection.')
    else:
        if study.repeat_policy and policy.repeat_selection!=study.repeat_policy.selection: issue('analysis.eligibility_policy.repeat_selection','Study and analysis attempt-selection policies must agree.')
        if policy.configuration_pooling=='explicit_review' and not (policy.pooling_review or '').strip(): issue('analysis.eligibility_policy.pooling_review','An explicit reviewed pooling rationale and review reference is required.')
        if policy.configuration_pooling=='explicit_review':
            from .study_analysis_rules import named
            if policy.pooling_attestation is None or not named(policy.pooling_attestation.actor): issue('analysis.eligibility_policy.pooling_attestation','A named pooling actor, rationale and review reference must be frozen.')
        keys={o.key:o for o in study.occasions}
        if policy.hcf_enabled != bool(policy.hcf_screen_keys): issue('analysis.eligibility_policy.hcf_screen_keys','Enabled HCF requires designated screen occasions; disabled HCF must have none.')
        if len(set(policy.hcf_screen_keys))!=len(policy.hcf_screen_keys) or any(key not in keys or keys[key].instrument!='screen' for key in policy.hcf_screen_keys): issue('analysis.eligibility_policy.hcf_screen_keys','Designate unique screen occasions. HCF selects exactly one eligible attempt per participant.')
    return issues


def require_preparation(db, context):
    from .study_preparation import require_preparation as measured_preparation
    return measured_preparation(db, context)
