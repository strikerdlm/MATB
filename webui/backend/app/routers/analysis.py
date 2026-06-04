"""Statistics-engine endpoints. The engine itself lives in
matb_integration.analysis.stats (paper-first); this router only collects rows,
caches by input fingerprint, and persists artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models import AnalysisResult
from app.routers.fits import collect_fit_rows
from app.routers.metrics import collect_metric_rows

router = APIRouter(tags=["analysis"])


@router.post("/analysis/run")
def run_analysis_endpoint(session: Session = Depends(get_session)) -> dict[str, Any]:
    from matb_integration.analysis.stats import ENGINE_VERSION, fingerprint, run_analysis

    metric_rows = collect_metric_rows(session)
    fit_rows = collect_fit_rows(session)
    fp = fingerprint(metric_rows, fit_rows)
    existing = session.exec(
        select(AnalysisResult)
        .where(AnalysisResult.fingerprint == fp,
               AnalysisResult.engine_version == ENGINE_VERSION)
    ).first()
    if existing is not None:
        return {"cached": True, **json.loads(existing.artifact_json)}
    artifact = run_analysis(
        metric_rows, fit_rows,
        created_utc=datetime.now(timezone.utc).isoformat())
    session.add(AnalysisResult(fingerprint=fp, engine_version=ENGINE_VERSION,
                               artifact_json=json.dumps(artifact)))
    session.commit()
    return {"cached": False, **artifact}


@router.get("/analysis/latest")
def latest_analysis(session: Session = Depends(get_session)) -> dict[str, Any]:
    row = session.exec(
        select(AnalysisResult).order_by(AnalysisResult.created_at.desc(),
                                        AnalysisResult.id.desc())
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="no analysis has been run yet")
    return {"cached": True, **json.loads(row.artifact_json)}
