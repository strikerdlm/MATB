"""Visit-linked Karolinska Sleepiness Scale and 10-minute PVT ingestion."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.purpose_service import declare_acquisition
from app.db import get_session
from app.models import ArchivedAssessment, Participant, PracticeResult, PvtAssessment, Visit

router = APIRouter(prefix="/pvt", tags=["pvt"])

from matb_integration.pvt_scoring import PVT_VERSION, PVT_DURATION_MS, PVT_RESPONSE_TIMEOUT_MS, PvtTrialIn, PvtAssessmentIn, _metrics


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
