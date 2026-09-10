"""Strict requests; frozen assignment validation is added by the study layer."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class OccasionIn(Strict):
    participant_id: str = Field(min_length=1)
    visit_id: int
    instrument: Literal['pvt', 'screen', 'openmatb', 'liftoff', 'suas', 'physiology', 'questionnaire']
    phase: str = Field(min_length=1)
    order: int = Field(ge=1)
    condition: str | None = None
    version_ref: str | None = None
    origin: Literal['local'] = 'local'
    collection_group_id: str | None = None
    accompanying_occasion_id: str | None = None


class AttemptIn(Strict):
    execution_purpose: Literal['study', 'practice']
    target_attempt_id: str | None = None


class RepeatIn(AttemptIn):
    reason: str = Field(min_length=1)


class InterruptIn(Strict):
    category: Literal['operator_stop', 'participant_stop', 'technical_failure', 'lost_connection', 'other']


class OccasionClassificationIn(Strict):
    visit_id: int
    phase: str = Field(min_length=1)
    order: int = Field(ge=1)
    condition: str | None = None
    version_ref: str | None = None
    reviewer: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    supporting_references: list[str] = Field(default_factory=list)
