"""Visit-linked Karolinska Sleepiness Scale and 10-minute PVT ingestion."""

from __future__ import annotations

import json
from statistics import median
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlmodel import Session, select

from app.purpose_service import declare_acquisition
from app.db import get_session
from app.models import ArchivedAssessment, Participant, PracticeResult, PvtAssessment, Visit

router = APIRouter(prefix="/pvt", tags=["pvt"])

PVT_VERSION = 2
PVT_DURATION_MS = 600_000
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
            if self.stimulus_at_ms is None:
                if self.rt_ms is not None:
                    raise ValueError("a response before stimulus onset cannot have rt_ms")
            elif self.rt_ms is None or abs(self.response_at_ms - self.stimulus_at_ms - self.rt_ms) > 5:
                raise ValueError("false-start timing does not match stimulus and response")
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

    attempt_id: str | None = None
    participant_id: str
    visit_ordinal: int = Field(ge=1)
    kss_score: int = Field(ge=1, le=9)
    administered_at: str = Field(min_length=1)
    duration_ms: int = Field(ge=1)
    fast_mode: bool = False
    trials: list[PvtTrialIn] = Field(min_length=0, max_length=10000)
    overwrite: bool = False
    execution_purpose: Literal["practice", "study"]
    locale: Literal["es-419", "en"] = "es-419"
    timing_version: Literal[1, 2] = 1
    interruption_count: int = Field(default=0, ge=0)
    max_frame_gap_ms: float = Field(default=0, ge=0, allow_inf_nan=False)
    terminal_phase: Literal["waiting", "stimulus", "feedback", "complete"] | None = None
    terminal_stimulus_at_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_protocol_duration(self) -> "PvtAssessmentIn":
        if self.fast_mode and self.execution_purpose == "study":
            raise ValueError("fast_mode requires practice purpose")
        indices = [trial.index for trial in self.trials]
        if indices != list(range(len(indices))):
            raise ValueError("trial indices must be contiguous from zero")
        previous_end = 0.0
        for trial in self.trials:
            start = trial.stimulus_at_ms if trial.stimulus_at_ms is not None else trial.response_at_ms
            end = trial.response_at_ms if trial.response_at_ms is not None else (trial.stimulus_at_ms or 0) + PVT_RESPONSE_TIMEOUT_MS
            if start is None or start < previous_end or end < start or end > self.duration_ms:
                raise ValueError("trial timeline must be ordered and inside the session duration")
            previous_end = end
        if self.timing_version == 2:
            if self.terminal_phase is None:
                raise ValueError("version 2 requires terminal phase evidence")
            if self.terminal_phase == "stimulus":
                if self.terminal_stimulus_at_ms is None or not previous_end <= self.terminal_stimulus_at_ms <= self.duration_ms:
                    raise ValueError("terminal stimulus must follow recorded trials within the session")
            elif self.terminal_stimulus_at_ms is not None:
                raise ValueError("terminal stimulus is only valid for an unfinished stimulus")
        return self

    def validity_reasons(self) -> list[str]:
        reasons = []
        if not self.trials:
            reasons.append("no_completed_trials")
        if self.fast_mode or self.execution_purpose == "practice":
            reasons.append("practice")
        if self.timing_version < 2:
            reasons.append("legacy_timing_evidence_missing")
        if self.duration_ms < PVT_DURATION_MS:
            reasons.append("duration_below_10_minutes")
        if self.interruption_count or self.max_frame_gap_ms > 250:
            reasons.append("interrupted_or_delayed_presentation")
        previous_end = 0.0
        for trial in self.trials:
            start = trial.stimulus_at_ms if trial.stimulus_at_ms is not None else trial.response_at_ms or 0
            if self.timing_version == 2:
                if trial.stimulus_at_ms is not None and abs(start - previous_end - trial.wait_ms) > 250:
                    reasons.append("wait_timing_mismatch")
                if trial.stimulus_at_ms is None and start - previous_end > trial.wait_ms + 250:
                    reasons.append("false_start_after_expected_onset")
            if start - previous_end > 11250:
                reasons.append("unexplained_timeline_gap")
            previous_end = trial.response_at_ms if trial.response_at_ms is not None else (trial.stimulus_at_ms or 0) + PVT_RESPONSE_TIMEOUT_MS
        if self.terminal_phase == "stimulus" and self.terminal_stimulus_at_ms is not None:
            if self.terminal_stimulus_at_ms - previous_end > 10250 or self.duration_ms - self.terminal_stimulus_at_ms > 30250:
                reasons.append("terminal_timing_mismatch")
        terminal_limit = 40500 if self.terminal_phase == "stimulus" else 11250
        if self.duration_ms - previous_end > terminal_limit:
            reasons.append("incomplete_timeline")
        return list(dict.fromkeys(reasons))


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
        "attempt_id": row.attempt_id,
        "purpose_provenance_id": row.purpose_provenance_id,
        "participant_id": row.participant_id,
        "visit_id": row.visit_id,
        "kss_score": row.kss_score,
        "administered_at": row.administered_at,
        "duration_ms": row.duration_ms,
        "protocol_valid": row.protocol_valid and row.pvt_version >= PVT_VERSION,
        "historical_protocol_valid": row.protocol_valid if row.pvt_version < PVT_VERSION else None,
        "pvt_version": row.pvt_version,
        "metrics": json.loads(row.metrics_json),
        "execution_purpose": row.execution_purpose,
        "timing_evidence": json.loads(row.timing_evidence_json),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def ingest_pvt(body: PvtAssessmentIn, session: Session = Depends(get_session)) -> dict[str, object]:
    visit = _visit(session, body.participant_id, body.visit_ordinal)
    from app.assessment_service import prepare_result, save_result, raw_view
    attempt = None
    from app.study_admission import resolve_assignment
    resolve_assignment(session, attempt_id=body.attempt_id, instrument='pvt', participant_id=body.participant_id, visit_id=visit.id, purpose=body.execution_purpose, require_started=True)
    final_payload = body.model_dump(exclude={"overwrite", "attempt_id"})
    if body.attempt_id:
        attempt, duplicate = prepare_result(session, body.attempt_id, instrument="pvt", participant_id=body.participant_id,
            visit_id=visit.id, purpose=body.execution_purpose, payload=final_payload)
        if duplicate:
            links = raw_view(session, attempt.id)["record"]
            if body.execution_purpose == "practice":
                return {"id": links["id"], "attempt_id": attempt.id, "purpose_provenance_id": attempt.purpose_provenance_id, **json.loads(links["result_json"])}
            return _view(session.get(PvtAssessment, links["id"]))
    metrics = _metrics(body.trials, duration_ms=body.duration_ms)
    timing = {"locale": body.locale, "timing_version": body.timing_version, "interruption_count": body.interruption_count,
              "max_frame_gap_ms": body.max_frame_gap_ms, "terminal_phase": body.terminal_phase,
              "terminal_stimulus_at_ms": body.terminal_stimulus_at_ms,
              "validity_reasons": body.validity_reasons()}
    if body.execution_purpose == "practice" or body.fast_mode:
        result = {"participant_id": body.participant_id, "visit_id": visit.id,
                  "kss_score": body.kss_score, "administered_at": body.administered_at,
                  "duration_ms": body.duration_ms, "protocol_valid": False,
                  "pvt_version": PVT_VERSION, "metrics": metrics,
                  "execution_purpose": "practice", "timing_evidence": timing}
        practice = PracticeResult(experiment_id="pvt", participant_id=body.participant_id,
                                  payload_json=body.model_dump_json(), result_json=json.dumps(result, allow_nan=False))
        if attempt:
            save_result(session, attempt, practice, final_payload)
        else:
            declare_acquisition(session, practice, purpose="practice")
        session.commit()
        session.refresh(practice)
        return {"id": practice.id, "attempt_id": practice.attempt_id, "purpose_provenance_id": practice.purpose_provenance_id, **result}
    if body.attempt_id is None:
        existing_rows = session.exec(select(PvtAssessment).where(PvtAssessment.visit_id == visit.id)).all()
        if existing_rows:
            if len(existing_rows) == 1:
                existing = existing_rows[0]
                if existing.administered_at == body.administered_at and existing.kss_score == body.kss_score and existing.duration_ms == body.duration_ms and json.loads(existing.raw_trials_json) == [trial.model_dump() for trial in body.trials] and json.loads(existing.timing_evidence_json) == timing:
                    return _view(existing)
            raise HTTPException(409, {"code": "explicit_repeat_required", "message": "Create an occasion/attempt or repeat a prior attempt.", "attempt_ids": [r.attempt_id for r in existing_rows]})
    row = PvtAssessment(
        participant_id=body.participant_id,
        visit_id=visit.id,
        kss_score=body.kss_score,
        administered_at=body.administered_at,
        duration_ms=body.duration_ms,
        protocol_valid=not body.validity_reasons(),
        pvt_version=PVT_VERSION,
        raw_trials_json=json.dumps([trial.model_dump() for trial in body.trials]),
        metrics_json=json.dumps(metrics),
        execution_purpose="study",
        timing_evidence_json=json.dumps(timing, allow_nan=False),
    )
    if attempt:
        save_result(session, attempt, row, final_payload)
    else:
        declare_acquisition(session, row, purpose=body.execution_purpose)
    session.commit()
    session.refresh(row)
    return _view(row)


@router.get("")
def list_pvt(
    participant_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    statement = select(PvtAssessment).where(PvtAssessment.execution_purpose == "study")
    if participant_id is not None:
        statement = statement.where(PvtAssessment.participant_id == participant_id)
    rows = session.exec(statement.order_by(PvtAssessment.participant_id, PvtAssessment.visit_id)).all()
    return {
        "selection_mode": "all_attempts",
        "pvt_version": PVT_VERSION,
        "protocol_duration_ms": PVT_DURATION_MS,
        "assessments": [_view(row) for row in rows],
    }
