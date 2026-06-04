"""Baseline neurocognitive screen: raw-trial ingestion + cohort HCF summary.

Scoring and the HCF mapping live in matb_integration.screen (single-sourced);
this router stores raw + scores and triggers the fit-HCF refresh (Task 4)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models import Participant, ScreenResult

router = APIRouter(tags=["screen"])


def _score_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from matb_integration.screen.scoring import score_screen

    required = {"simple_rt", "choice_rt", "nback", "tracking"}
    missing = required - set(payload)
    if missing:
        raise HTTPException(status_code=422, detail=f"payload missing: {sorted(missing)}")
    return score_screen(payload)


@router.post("/screen", status_code=201)
def ingest_screen(
    participant_id: str = Body(...),
    payload: dict[str, Any] = Body(...),
    overwrite: bool = Body(False),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from matb_integration.screen.hcf_mapping import SCREEN_VERSION

    if session.get(Participant, participant_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown participant {participant_id}")
    existing = session.exec(
        select(ScreenResult).where(ScreenResult.participant_id == participant_id)
    ).first()
    if existing is not None and not overwrite:
        raise HTTPException(status_code=409,
                            detail=f"screen already recorded for {participant_id}")
    scores = _score_payload(payload)
    if existing is not None:
        session.delete(existing)
        session.flush()
    row = ScreenResult(
        participant_id=participant_id,
        administered_at=str(payload.get("administered_at") or ""),
        screen_version=SCREEN_VERSION,
        raw_trials_json=json.dumps(payload),
        scores_json=json.dumps(scores),
    )
    session.add(row)
    session.commit()
    from app.hcf_refresh import refresh_fit_hcf
    refresh_fit_hcf(session)
    return {"participant_id": participant_id, "screen_version": SCREEN_VERSION,
            "scores": scores}


@router.get("/screen")
def screen_summary(session: Session = Depends(get_session)) -> dict[str, Any]:
    from matb_integration.screen.hcf_mapping import (MIN_COHORT, SCREEN_VERSION,
                                                     compute_cohort_hcf)

    rows = session.exec(select(ScreenResult)).all()
    scores_by_pid = {r.participant_id: json.loads(r.scores_json) for r in rows}
    store = compute_cohort_hcf(scores_by_pid)
    screens = []
    for r in sorted(rows, key=lambda x: x.participant_id):
        est = store.get(r.participant_id)
        screens.append({
            "participant_id": r.participant_id,
            "administered_at": r.administered_at,
            "screen_version": r.screen_version,
            "scores": scores_by_pid[r.participant_id],
            "hcf_value": est.value if est else None,
            "components": est.components if est else None,
        })
    return {"n_screened": len(rows), "min_cohort": MIN_COHORT,
            "hcf_active": bool(store), "screen_version": SCREEN_VERSION,
            "screens": screens}
