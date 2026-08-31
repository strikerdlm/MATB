"""Optional Liftoff analysis endpoint."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db import get_session
from app.liftoff_research import collect_liftoff_metric_rows
from app.models import AnalysisResult
from app.study_models import StudyParticipantContext

router = APIRouter(tags=["liftoff"])


@router.post("/analysis/liftoff/run")
def run_liftoff_analysis_endpoint(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from matb_integration.analysis.liftoff import (
        LIFTOFF_ANALYSIS_VERSION,
        run_liftoff_analysis,
    )

    metric_rows = collect_liftoff_metric_rows(session)
    contexts = session.exec(
        select(StudyParticipantContext).order_by(StudyParticipantContext.participant_id)
    ).all()
    participant_context = [{
        "participant_id": row.participant_id,
        "sequence": row.task_sequence,
        "prior_fpv_hours": row.prior_fpv_hours,
        "gaming_hours_per_week": row.gaming_hours_per_week,
    } for row in contexts]
    fingerprint = hashlib.sha256(
        json.dumps(
            {"rows": metric_rows, "context": participant_context},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    existing = session.exec(
        select(AnalysisResult).where(
            AnalysisResult.fingerprint == fingerprint,
            AnalysisResult.engine_version == LIFTOFF_ANALYSIS_VERSION,
        )
    ).first()
    if existing is not None:
        return {"cached": True, **json.loads(existing.artifact_json)}
    artifact = run_liftoff_analysis(metric_rows, participant_context)
    session.add(AnalysisResult(
        fingerprint=fingerprint,
        engine_version=LIFTOFF_ANALYSIS_VERSION,
        artifact_json=json.dumps(artifact),
    ))
    session.commit()
    return {"cached": False, **artifact}
