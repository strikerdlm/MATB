"""Legacy four-task screen: raw-trial ingestion + cohort HCF summary.

Scoring and the HCF mapping live in matb_integration.screen (single-sourced);
this router stores raw + scores and triggers the fit-HCF refresh (Task 4)."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session, select

from app.purpose_service import declare_acquisition
from app.db import get_session
from app.models import ArchivedAssessment, Participant, PracticeResult, ScreenResult

router = APIRouter(tags=["screen"])


def _score_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from matb_integration.screen.scoring import score_screen

    required = {"simple_rt", "choice_rt", "nback", "tracking"}
    missing = required - set(payload)
    if missing:
        raise HTTPException(status_code=422, detail=f"payload missing: {sorted(missing)}")
    try:
        return score_screen(payload)
    except (KeyError, IndexError, TypeError, AttributeError, ValueError) as exc:
        raise HTTPException(status_code=422,
                            detail=f"malformed screen payload: {exc}") from exc


@router.post("/screen", status_code=201)
def ingest_screen(
    participant_id: str = Body(...),
    payload: dict[str, Any] = Body(...),
    overwrite: bool = Body(False),
    attempt_id: str | None = Body(None),
    execution_purpose: Literal["practice", "study"] = Body(...),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from matb_integration.screen.hcf_mapping import SCREEN_VERSION

    if session.get(Participant, participant_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown participant {participant_id}")
    if "fast_mode" in payload and not isinstance(payload["fast_mode"], bool):
        raise HTTPException(422, "fast_mode must be a boolean")
    if execution_purpose == "study" and payload.get("fast_mode") is True:
        raise HTTPException(422, "fast_mode requires practice purpose")
    from app.assessment_service import prepare_result, save_result, raw_view
    attempt = None
    final_payload = {"participant_id": participant_id, "payload": payload, "execution_purpose": execution_purpose}
    if attempt_id:
        attempt, duplicate = prepare_result(session, attempt_id, instrument="screen", participant_id=participant_id,
            visit_id=None, purpose=execution_purpose, payload=final_payload)
        if duplicate:
            record = raw_view(session, attempt.id)["record"]
            result = json.loads(record["result_json"]) if execution_purpose == "practice" else {"participant_id": participant_id, "screen_version": record["screen_version"], "scores": json.loads(record["scores_json"]), "execution_purpose": execution_purpose}
            return {**result, "id": record["id"], "attempt_id": attempt.id, "purpose_provenance_id": attempt.purpose_provenance_id}
    scores = _score_payload(payload)
    version = SCREEN_VERSION if payload.get("schema_version") == 2 else 1
    if execution_purpose == "study":
        if version != SCREEN_VERSION:
            raise HTTPException(422, detail="Study collection requires version 2 timing and stimulus evidence.")
        if (len(payload["simple_rt"]["trials"]) != 30 or len(payload["choice_rt"]["trials"]) != 30
                or len(payload["nback"]["trials"]) != 60 or payload["nback"].get("soa_ms") != 2500
                or payload["tracking"].get("duration_ms") != 90000):
            raise HTTPException(422, detail="Study collection must use the assigned full four-task protocol.")
    if execution_purpose == "practice":
        result = {"participant_id": participant_id, "screen_version": SCREEN_VERSION,
                  "scores": scores, "execution_purpose": "practice"}
        practice = PracticeResult(experiment_id="screen", participant_id=participant_id,
                                  payload_json=json.dumps(payload, allow_nan=False),
                                  result_json=json.dumps(result, allow_nan=False))
        if attempt:
            save_result(session, attempt, practice, final_payload)
        else:
            declare_acquisition(session, practice, purpose="practice")
        result["id"] = practice.id
        result["attempt_id"] = practice.attempt_id
        result["purpose_provenance_id"] = practice.purpose_provenance_id
        session.commit()
        return result
    if attempt_id is None:
        existing_rows = session.exec(select(ScreenResult).where(ScreenResult.participant_id == participant_id)).all()
        if existing_rows:
            if len(existing_rows) == 1 and json.loads(existing_rows[0].raw_trials_json) == payload:
                existing = existing_rows[0]
                return {"id": existing.id, "attempt_id": existing.attempt_id, "participant_id": participant_id, "screen_version": existing.screen_version,
                        "scores": json.loads(existing.scores_json), "execution_purpose": "study", "purpose_provenance_id": existing.purpose_provenance_id}
            raise HTTPException(409, {"code": "explicit_repeat_required", "message": "Create an occasion/attempt or repeat a prior attempt.", "attempt_ids": [r.attempt_id for r in existing_rows]})
    row = ScreenResult(
        participant_id=participant_id,
        administered_at=str(payload.get("administered_at") or ""),
        screen_version=SCREEN_VERSION,
        raw_trials_json=json.dumps(payload, allow_nan=False),
        scores_json=json.dumps(scores, allow_nan=False),
    )
    if attempt:
        save_result(session, attempt, row, final_payload)
    else:
        declare_acquisition(session, row, purpose=execution_purpose)
    session.commit()
    from app.hcf_refresh import refresh_fit_hcf
    if not attempt:
        refresh_fit_hcf(session)
    return {"id": row.id, "attempt_id": row.attempt_id, "participant_id": participant_id, "screen_version": SCREEN_VERSION,
            "scores": scores, "execution_purpose": "study", "purpose_provenance_id": row.purpose_provenance_id}


@router.get("/screen")
def screen_summary(session: Session = Depends(get_session)) -> dict[str, Any]:
    from matb_integration.screen.hcf_mapping import (MIN_COHORT, SCREEN_VERSION,
                                                     compute_cohort_hcf)

    rows = session.exec(select(ScreenResult).where(ScreenResult.execution_purpose == "study", ScreenResult.screen_version == SCREEN_VERSION)).all()
    from app.assessment_readers import reject_ambiguous, exclude_known_nonstudy
    rows = exclude_known_nonstudy(session, rows)
    reject_ambiguous(rows)
    scores_by_pid = {r.participant_id: json.loads(r.scores_json) for r in rows}
    store = compute_cohort_hcf(scores_by_pid)
    screens = []
    for r in sorted(rows, key=lambda x: x.participant_id):
        est = store.get(r.participant_id)
        screens.append({
            "id": r.id, "attempt_id": r.attempt_id,
            "participant_id": r.participant_id,
            "purpose_provenance_id": r.purpose_provenance_id,
            "administered_at": r.administered_at,
            "screen_version": r.screen_version,
            "scores": scores_by_pid[r.participant_id],
            "hcf_value": est.value if est else None,
            "components": est.components if est else None,
        })
    return {"selection_mode": "legacy_unambiguous", "n_screened": len(rows), "min_cohort": MIN_COHORT,
            "hcf_active": bool(store), "screen_version": SCREEN_VERSION,
            "screens": screens}
