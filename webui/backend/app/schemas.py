"""Request/response models."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class ParticipantCreate(BaseModel):
    id: str
    enrollment_date: date
    sex: str | None = None
    age_band: str | None = None
    notes: str | None = None


class ParticipantOut(BaseModel):
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
