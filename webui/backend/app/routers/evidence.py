"""Research-only scientific captures; never part of participant snapshots."""
from typing import Literal
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.db import get_session
from app.evidence_models import EvidenceCapture, EvidenceRecord, EvidenceMetricSource, EvidenceAnalysisInput
from app.evidence_service import (EvidenceError, ingest_evidence, capture_summary, capture_or_error,
    metric_or_error, run_derivation, write_bundle, freeze_analysis_input)
from app.routers.ingest import _read_bounded
from matb_integration.evidence.contracts import MAX_STREAM_BYTES, strict_json
from matb_integration.evidence.qualification import QualificationSubmissionV1, QualificationBindingV1
from app import evidence_qualification
from app.evidence_review import event_context

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
             purpose: Literal["study", "practice", "exploration", "all"] = "study",
             session: str | None = Query(None, max_length=64), q: str = Query("", max_length=200),
             db: Session = Depends(get_session)):
    from app.evidence_discovery import capture_list
    return capture_list(db, purpose=purpose, session_id=session, query=q, offset=offset, limit=limit)


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
    content = tempfile.TemporaryFile(mode="w+b")
    try:
        checked(write_bundle, db, capture_id, content)
        size = content.tell()
        content.seek(0)
    except BaseException:
        content.close()
        raise
    def chunks():
        try:
            while chunk := content.read(1024 * 1024):
                yield chunk
        finally:
            content.close()
    return StreamingResponse(chunks(), media_type="application/zip", background=BackgroundTask(content.close), headers={
        "Content-Length": str(size), "Content-Disposition": f'attachment; filename="evidence-{capture_id}.zip"'})


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


@router.post("/evidence/qualifications")
def register_qualification(submission: QualificationSubmissionV1, db: Session = Depends(get_session)):
    return checked(evidence_qualification.register, db, submission)


@router.get("/evidence/qualifications/{record_id}")
def read_qualification(record_id: str, db: Session = Depends(get_session)):
    return checked(evidence_qualification.read, db, record_id)


class QualificationRevocation(BaseModel):
    reviewer: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=4000)


@router.post("/evidence/qualifications/{record_id}/revoke")
def revoke_qualification(record_id: str, revocation: QualificationRevocation, db: Session = Depends(get_session)):
    return checked(evidence_qualification.revoke, db, record_id, revocation.reviewer, revocation.reason)


@router.post("/evidence/captures/{capture_id}/qualifications")
def link_qualification(capture_id: str, binding: QualificationBindingV1, db: Session = Depends(get_session)):
    return checked(evidence_qualification.link, db, capture_id, binding)


@router.get("/evidence/captures/{capture_id}/qualifications")
def capture_qualifications(capture_id: str, db: Session = Depends(get_session)):
    return checked(evidence_qualification.linked, db, capture_id)


@router.get("/evidence/captures/{capture_id}/events/{event_id}/context")
def review_event(capture_id: str, event_id: str, db: Session = Depends(get_session)):
    return checked(event_context, db, capture_id, event_id)
