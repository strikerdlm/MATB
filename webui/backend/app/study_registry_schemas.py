"""V1 constrained researcher-authored study and descriptive analysis contracts."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class VisitSpec(Strict):
    ordinal: int = Field(ge=1, le=16)
    code: str = Field(min_length=1)
    scheduled_day: int = Field(ge=0)


class OccasionSpec(Strict):
    key: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')
    visit_ordinal: int = Field(ge=1, le=16)
    instrument: Literal['pvt', 'screen', 'openmatb', 'liftoff', 'suas', 'physiology', 'questionnaire']
    phase: str = Field(min_length=1)
    order: int = Field(ge=1)
    condition_by_arm: dict[str, str]
    locale: Literal['en', 'es-419']
    config: dict
    prerequisite_keys: list[str] = Field(default_factory=list)
    target_key: str | None = None
    collection_group: str | None = None
    accompanying_key: str | None = None


class RecoverySpec(Strict):
    key: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')
    anchor_key: str
    before_key: str
    duration_seconds: int = Field(gt=0)


class StudyRules(Strict):
    preparation: str
    repeat: str
    interruption: str


from .study_policies import PreparationRequirement, RepeatPolicy, InterruptionPolicy, EligibilityPolicy


class StudySpecV1(Strict):
    schema_version: Literal['StudySpecV1'] = 'StudySpecV1'
    version_id: str | None = None
    analysis_plan_id: str | None = None
    study_id: str = Field(pattern=r'^[a-z][a-z0-9-]{2,63}$')
    title: str = Field(min_length=1)
    template_family: Literal['astra-2026', 'matb-longitudinal-6-visit-v1']
    synthetic: bool
    enabled_instruments: list[str]
    implementation_sha256: dict[str, str] = Field(default_factory=dict)
    visits: list[VisitSpec] = Field(min_length=1)
    arms: list[str] = Field(min_length=1)
    assignment_method: Literal['explicit_researcher_selection']
    occasions: list[OccasionSpec] = Field(min_length=1)
    recovery_intervals: list[RecoverySpec] = Field(default_factory=list)
    rules: StudyRules
    preparation_policy: list[PreparationRequirement] | None = None
    repeat_policy: RepeatPolicy | None = None
    interruption_policy: InterruptionPolicy | None = None


class OutcomeSpec(Strict):
    key: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')
    metric: str
    units: str | None = None
    source_keys: list[str] = Field(default_factory=list)
    source_summary: Literal['individual', 'mean', 'median'] = 'individual'
    occasion_keys: list[str] = Field(min_length=1)
    summary: Literal['mean', 'median', 'individual']


class ContrastSpec(Strict):
    key: str
    left_outcome: str
    right_outcome: str
    operation: Literal['difference']


class AnalysisRules(Strict):
    exclusions: str
    denominators: str
    qualification: str
    pooling: str
    historical_unknowns: Literal['exclude', 'reviewed_classification_required']


class AnalysisPlanV1(Strict):
    schema_version: Literal['AnalysisPlanV1'] = 'AnalysisPlanV1'
    version_id: str | None = None
    study_version_id: str | None = None
    calculation_sha256: str | None = None
    calculator_dependencies: dict[str,str] = Field(default_factory=dict)
    unit: Literal['participant', 'visit', 'attempt']
    outcomes: list[OutcomeSpec] = Field(min_length=1)
    contrasts: list[ContrastSpec] = Field(default_factory=list)
    rules: AnalysisRules
    eligibility_policy: EligibilityPolicy | None = None


class DraftPayload(Strict):
    study: StudySpecV1
    analysis: AnalysisPlanV1


class Attestation(Strict):
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class FreezeRequest(Attestation):
    sha256: str
    rehearsal_id: str


class AssignmentRequest(Strict):
    participant_id: str
    visit_id: int
    arm: str
    actor: str = Field(min_length=1)


class AmendmentRequest(Attestation):
    assignment_ids: list[str] = Field(min_length=1)


class SelectionRequest(Strict):
    selections: dict[str, str]
