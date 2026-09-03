"""Request/response models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.participant_ids import PARTICIPANT_ID_PATTERN


class ParticipantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=PARTICIPANT_ID_PATTERN)
    enrollment_date: date
    sex: str | None = None
    age_band: str | None = None
    notes: str | None = None


class ParticipantOut(BaseModel):
    # Read legacy rows so the UI can identify and replace incompatible IDs;
    # new rows are constrained by ParticipantCreate above.
    id: str
    enrollment_date: date
    sex: str | None = None
    age_band: str | None = None
    notes: str | None = None


class VisitOut(BaseModel):
    id: int
    participant_id: str
    visit_ordinal: int
    scheduled_day: int
    actual_date: date | None = None
    status: str


class StudyContextCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_sequence: Literal["MATB_LIFTOFF", "LIFTOFF_MATB"]
    prior_fpv_hours: float = Field(ge=0, allow_inf_nan=False)
    gaming_hours_per_week: float = Field(ge=0, allow_inf_nan=False)


class StudyContextView(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    participant_id: str
    protocol_id: str
    task_sequence: Literal["MATB_LIFTOFF", "LIFTOFF_MATB"]
    prior_fpv_hours: float
    gaming_hours_per_week: float
    created_at: datetime
