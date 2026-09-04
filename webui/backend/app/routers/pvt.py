"""Visit-linked Karolinska Sleepiness Scale and 10-minute PVT ingestion."""

from __future__ import annotations

import json
from statistics import median
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlmodel import Session, select

from app.db import get_session
from app.models import Participant, PvtAssessment, Visit

router = APIRouter(prefix="/pvt", tags=["pvt"])

PVT_VERSION = 1
PVT_DURATION_MS = 600_000
PVT_MIN_PROTOCOL_DURATION_MS = 590_000
PVT_RESPONSE_TIMEOUT_MS = 30_000


class PvtTrialIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    wait_ms: int = Field(ge=2_000, le=10_000)
    stimulus_at_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    response_at_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    rt_ms: float | None = Field(default=None, ge=0, le=PVT_RESPONSE_TIMEOUT_MS, allow_inf_nan=False)
    outcome: Literal["response", "lapse", "false_start", "timeout"]

    @model_validator(mode="after")
    def validate_timing(self) -> "PvtTrialIn":
        if self.outcome == "false_start":
            if self.response_at_ms is None or (self.rt_ms is not None and self.rt_ms >= 100):
                raise ValueError("false_start requires a response before 100 ms")
            return self
        if self.stimulus_at_ms is None:
            raise ValueError("stimulus_at_ms is required after stimulus onset")
        if self.outcome == "timeout":
            if self.response_at_ms is not None or self.rt_ms is not None:
                raise ValueError("timeout must not contain a response")
            return self
        if self.response_at_ms is None or self.rt_ms is None:
            raise ValueError("response timing is required")
        observed = self.response_at_ms - self.stimulus_at_ms
        if abs(observed - self.rt_ms) > 5:
            raise ValueError("rt_ms does not match stimulus and response timestamps")
        if self.outcome == "response" and not 100 <= self.rt_ms < 500:
            raise ValueError("response outcome requires 100 <= rt_ms < 500")
        if self.outcome == "lapse" and self.rt_ms < 500:
            raise ValueError("lapse outcome requires rt_ms >= 500")
        return self


class PvtAssessmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_id: str
    visit_ordinal: int = Field(ge=1)
    kss_score: int = Field(ge=1, le=9)
    administered_at: str = Field(min_length=1)
    duration_ms: int = Field(ge=1)
    fast_mode: bool = False
    trials: list[PvtTrialIn] = Field(min_length=1)
    overwrite: bool = False

    @model_validator(mode="after")
    def validate_protocol_duration(self) -> "PvtAssessmentIn":
        if not self.fast_mode and self.duration_ms < PVT_MIN_PROTOCOL_DURATION_MS:
            raise ValueError("the protocol PVT must run for 10 minutes")
        indices = [trial.index for trial in self.trials]
        if indices != list(range(len(indices))):
            raise ValueError("trial indices must be contiguous from zero")
        return self


def _metrics(trials: list[PvtTrialIn], *, duration_ms: int) -> dict[str, int | float | None]:
    response_times = [
        trial.rt_ms for trial in trials
        if trial.rt_ms is not None and trial.rt_ms >= 100
    ]
    reciprocal_speeds = [1_000 / value for value in response_times if value > 0]
    return {
        "duration_ms": duration_ms,
        "total_trials": len(trials),
        "valid_responses": len(response_times),
        "median_rt_ms": round(float(median(response_times)), 3) if response_times else None,
        "mean_reciprocal_rt_per_s": (
            round(sum(reciprocal_speeds) / len(reciprocal_speeds), 6)
            if reciprocal_speeds else None
        ),
        "lapses": sum(trial.outcome == "lapse" for trial in trials),
        "false_starts": sum(trial.outcome == "false_start" for trial in trials),
        "timeouts": sum(trial.outcome == "timeout" for trial in trials),
    }


def _visit(session: Session, participant_id: str, visit_ordinal: int) -> Visit:
    if session.get(Participant, participant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "participant not found")
    visit = session.exec(
        select(Visit).where(
            Visit.participant_id == participant_id,
            Visit.visit_ordinal == visit_ordinal,
        )
    ).first()
    if visit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "visit not found")
    return visit


def _view(row: PvtAssessment) -> dict[str, object]:
    return {
        "id": row.id,
        "participant_id": row.participant_id,
        "visit_id": row.visit_id,
        "kss_score": row.kss_score,
        "administered_at": row.administered_at,
        "duration_ms": row.duration_ms,
        "protocol_valid": row.protocol_valid,
        "pvt_version": row.pvt_version,
        "metrics": json.loads(row.metrics_json),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def ingest_pvt(body: PvtAssessmentIn, session: Session = Depends(get_session)) -> dict[str, object]:
    visit = _visit(session, body.participant_id, body.visit_ordinal)
    existing = session.exec(
        select(PvtAssessment).where(PvtAssessment.visit_id == visit.id)
    ).first()
    if existing is not None and not body.overwrite:
        raise HTTPException(status.HTTP_409_CONFLICT, "PVT already recorded for this visit")
    metrics = _metrics(body.trials, duration_ms=body.duration_ms)
    if existing is not None:
        session.delete(existing)
        session.flush()
    row = PvtAssessment(
        participant_id=body.participant_id,
        visit_id=visit.id,
        kss_score=body.kss_score,
        administered_at=body.administered_at,
        duration_ms=body.duration_ms,
        protocol_valid=not body.fast_mode and body.duration_ms >= PVT_MIN_PROTOCOL_DURATION_MS,
        pvt_version=PVT_VERSION,
        raw_trials_json=json.dumps([trial.model_dump() for trial in body.trials]),
        metrics_json=json.dumps(metrics),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _view(row)


@router.get("")
def list_pvt(
    participant_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    statement = select(PvtAssessment)
    if participant_id is not None:
        statement = statement.where(PvtAssessment.participant_id == participant_id)
    rows = session.exec(statement.order_by(PvtAssessment.participant_id, PvtAssessment.visit_id)).all()
    return {
        "pvt_version": PVT_VERSION,
        "protocol_duration_ms": PVT_DURATION_MS,
        "assessments": [_view(row) for row in rows],
    }
