"""Statistics-engine endpoints. The engine itself lives in
matb_integration.analysis.stats (paper-first); this router only collects rows,
caches by input fingerprint, and persists artifacts."""

from __future__ import annotations

import json
import hashlib
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session, select

from app.db import get_session
from app.models import AnalysisResult
from app.routers.fits import collect_fit_rows
from app.routers.metrics import collect_liftoff_metric_rows, collect_metric_rows
from app.study_models import StudyParticipantContext

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


def _bayes_worker(engine, job_id: int, metric_rows, fit_rows,
                  seed: int, draws: int, tune: int, chains: int) -> None:
    from matb_integration.analysis.stats.bayes import run_bayes

    from app.models import BayesResult as BR

    def _update(**fields) -> None:
        with Session(engine) as s:
            row = s.get(BR, job_id)
            for k, v in fields.items():
                setattr(row, k, v)
            s.add(row)
            s.commit()

    _update(status="running")
    try:
        artifact = run_bayes(metric_rows, fit_rows, seed=seed, draws=draws,
                             tune=tune, chains=chains,
                             created_utc=datetime.now(timezone.utc).isoformat())
        _update(status="done", artifact_json=json.dumps(artifact),
                finished_at=datetime.now(timezone.utc))
    except Exception as e:  # noqa: BLE001 — job must record its own failure
        _update(status="failed", error=f"{type(e).__name__}: {e}",
                finished_at=datetime.now(timezone.utc))


@router.post("/analysis/bayes/run", status_code=202)
def run_bayes_endpoint(
    response: Response,
    seed: int = 20260604, draws: int = 1000, tune: int = 1000, chains: int = 4,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from matb_integration.analysis.stats import fingerprint
    from matb_integration.analysis.stats.bayes import BAYES_VERSION

    from app.models import BayesResult

    metric_rows = collect_metric_rows(session)
    fit_rows = collect_fit_rows(session)
    fp = fingerprint(metric_rows, fit_rows)
    done = session.exec(
        select(BayesResult).where(BayesResult.fingerprint == fp,
                                  BayesResult.bayes_version == BAYES_VERSION,
                                  BayesResult.status == "done")
        .order_by(BayesResult.id.desc())  # type: ignore[arg-type]
    ).first()
    if done is not None:
        response.status_code = 200
        return {"job_id": done.id, "status": "done", "cached": True,
                "artifact": json.loads(done.artifact_json)}
    active = session.exec(
        select(BayesResult).where(BayesResult.fingerprint == fp,
                                  BayesResult.bayes_version == BAYES_VERSION,
                                  BayesResult.status.in_(("queued", "running")))  # type: ignore[attr-defined]
    ).first()
    if active is not None:
        response.status_code = 200
        return {"job_id": active.id, "status": active.status, "cached": False}
    row = BayesResult(fingerprint=fp, bayes_version=BAYES_VERSION)
    session.add(row)
    session.commit()
    session.refresh(row)
    engine = session.get_bind()
    threading.Thread(
        target=_bayes_worker,
        args=(engine, row.id, metric_rows, fit_rows, seed, draws, tune, chains),
        daemon=True,
    ).start()
    return {"job_id": row.id, "status": "queued", "cached": False}


@router.get("/analysis/bayes/status")
def bayes_status(session: Session = Depends(get_session)) -> dict[str, Any]:
    from app.models import BayesResult

    row = session.exec(
        select(BayesResult).order_by(BayesResult.id.desc())  # type: ignore[arg-type]
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="no Bayesian job yet")
    out: dict[str, Any] = {
        "job_id": row.id, "status": row.status, "error": row.error,
        "created_at": row.created_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }
    if row.status == "done" and row.artifact_json:
        out["artifact"] = json.loads(row.artifact_json)
    return out
