"""Research-only scientific captures; never part of participant snapshots."""
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func
from starlette.concurrency import run_in_threadpool

from app.db import get_session
from app.evidence_models import EvidenceCapture, EvidenceRecord, EvidenceMetricSource, EvidenceAnalysisInput
from app.evidence_service import (EvidenceError, ingest_evidence, capture_summary, capture_or_error,
    metric_or_error, run_derivation, export_bundle, freeze_analysis_input)
from app.routers.ingest import _read_bounded
from matb_integration.evidence.contracts import MAX_STREAM_BYTES, strict_json

router = APIRouter(tags=["evidence"])


def checked(fn, *args):
    try:
        return fn(*args)
    except EvidenceError as exc:
        raise HTTPException(exc.status, detail={"code": str(exc)}) from exc


@router.post("/ingest/evidence")
async def ingest(
    response: Response,
    capture_manifest: UploadFile = File(...), scenario_manifest: UploadFile = File(...),
    events: UploadFile = File(...), timing: UploadFile = File(...),
    legacy_csv: UploadFile | None = File(None),
    db: Session = Depends(get_session),
):
    artifacts = {}
    for role, upload in (("capture_manifest", capture_manifest), ("scenario_manifest", scenario_manifest),
                         ("events", events), ("timing", timing), ("legacy_csv", legacy_csv)):
        if upload is not None:
            artifact_limit = 2 * 1024 * 1024 if "manifest" in role else (64 * 1024 * 1024 if role == "legacy_csv" else MAX_STREAM_BYTES)
            artifacts[role] = await _read_bounded(upload, limit=artifact_limit,
                                                   code="evidence_artifact_too_large")
    capture_id, created = await run_in_threadpool(checked, ingest_evidence, db, artifacts)
    response.status_code = 201 if created else 200
    return await run_in_threadpool(checked, capture_summary, db, capture_id)


@router.get("/evidence/captures")
def captures(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
             purpose: Literal["study", "practice", "exploration"] = "study", db: Session = Depends(get_session)):
    query = select(EvidenceCapture).where(EvidenceCapture.execution_purpose == purpose)
    total = db.exec(select(func.count()).select_from(EvidenceCapture).where(EvidenceCapture.execution_purpose == purpose)).one()
    rows = db.exec(query.order_by(EvidenceCapture.created_at.desc(), EvidenceCapture.id).offset(offset).limit(limit))
    return {"total": total, "offset": offset, "limit": limit,
            "items": [r.model_dump(exclude={"manifest_json"}) for r in rows]}


@router.get("/evidence/captures/{capture_id}")
def capture(capture_id: str, db: Session = Depends(get_session)):
    return checked(capture_summary, db, capture_id)


@router.post("/evidence/captures/{capture_id}/reconcile")
def retry(capture_id: str, db: Session = Depends(get_session)):
    return {"run_id": checked(run_derivation, db, capture_id)}


@router.get("/evidence/captures/{capture_id}/records")
def records(capture_id: str, stream: Literal["events", "timing"] = "events",
            task: str | None = None, event_id: str | None = None, metric_id: str | None = None,
            offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_session)):
    checked(capture_or_error, db, capture_id)
    conditions = [EvidenceRecord.capture_id == capture_id, EvidenceRecord.stream == stream]
    if task:
        conditions.append(EvidenceRecord.task == task)
    if event_id:
        conditions.append(EvidenceRecord.event_id == event_id)
    if metric_id:
        checked(metric_or_error, db, capture_id, metric_id)
        source_ids = select(EvidenceMetricSource.record_id).where(EvidenceMetricSource.metric_id == metric_id,
                                                                  EvidenceMetricSource.stream == stream)
        conditions.append(EvidenceRecord.record_id.in_(source_ids))
    total = db.exec(select(func.count()).select_from(EvidenceRecord).where(*conditions)).one()
    rows = list(db.exec(select(EvidenceRecord).where(*conditions).order_by(EvidenceRecord.ordinal).offset(offset).limit(limit)))
    items = [strict_json(r.record_json) for r in rows]
    return {"total": total, "offset": offset, "limit": limit, "items": items,
            "raw_items": [r.record_json for r in rows],
            "value_texts": [str(item["value"]) if stream == "timing" else None for item in items]}


@router.get("/evidence/captures/{capture_id}/metrics/{metric_id}")
def metric(capture_id: str, metric_id: str, db: Session = Depends(get_session)):
    row = checked(metric_or_error, db, capture_id, metric_id)
    return {"id": row.id, "run_id": row.run_id, **strict_json(row.details_json)}


@router.get("/evidence/captures/{capture_id}/export")
def export(capture_id: str, db: Session = Depends(get_session)):
    content = checked(export_bundle, db, capture_id)
    return Response(content, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="evidence-{capture_id}.zip"'})


class AnalysisSelection(BaseModel):
    metric_ids: list[str] = Field(min_length=1, max_length=1000)


@router.post("/evidence/analysis-inputs")
def analysis_input(selection: AnalysisSelection, db: Session = Depends(get_session)):
    return checked(freeze_analysis_input, db, selection.metric_ids)


@router.get("/evidence/analysis-inputs/{input_id}")
def read_analysis_input(input_id: str, db: Session = Depends(get_session)):
    row = db.get(EvidenceAnalysisInput, input_id)
    if row is None:
        raise HTTPException(404, "analysis_input_not_found")
    return {"id": row.id, **strict_json(row.input_json)}
