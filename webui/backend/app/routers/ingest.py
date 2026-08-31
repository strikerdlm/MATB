"""Upload + ingest endpoint. Maps guard failures to HTTP 409."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from app.body_limits import MAX_SESSION_CSV_BYTES, MAX_SESSION_MANIFEST_BYTES
from app.db import get_session
from app.ingestion import IngestionError, block_validation_summary, ingest_csv

router = APIRouter(tags=["ingest"])
async def _read_bounded(upload: UploadFile, *, limit: int, code: str) -> bytes:
    content = await upload.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                "code": code,
                "message": f"uploaded file exceeds {limit} bytes",
            },
        )
    return content


@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest(
    file: UploadFile = File(...),
    manifest: UploadFile | None = File(None),
    participant_id: str = Form(...),
    visit_ordinal: int = Form(...),
    workload_level: str = Form(...),
    overwrite: bool = Form(False),
    session: Session = Depends(get_session),
):
    content = await _read_bounded(
        file,
        limit=MAX_SESSION_CSV_BYTES,
        code="session_csv_too_large",
    )
    manifest_content = (
        await _read_bounded(
            manifest,
            limit=MAX_SESSION_MANIFEST_BYTES,
            code="session_manifest_too_large",
        )
        if manifest is not None
        else None
    )
    try:
        block = await run_in_threadpool(
            ingest_csv,
            session,
            content=content,
            filename=file.filename or "upload.csv",
            participant_id=participant_id,
            visit_ordinal=visit_ordinal,
            workload_level=workload_level,
            overwrite=overwrite,
            manifest_content=manifest_content,
            manifest_filename=manifest.filename if manifest is not None else None,
        )
    except IngestionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    validation = await run_in_threadpool(block_validation_summary, session, block.id)
    return {"id": block.id, "workload_level": block.workload_level,
            "visit_id": block.visit_id, "validation": validation}
