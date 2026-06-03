"""Upload + ingest endpoint. Maps guard failures to HTTP 409."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlmodel import Session

from app.db import get_session
from app.ingestion import IngestionError, ingest_csv

router = APIRouter(tags=["ingest"])


@router.post("/ingest", status_code=status.HTTP_201_CREATED)
def ingest(
    file: UploadFile = File(...),
    participant_id: str = Form(...),
    visit_ordinal: int = Form(...),
    workload_level: str = Form(...),
    overwrite: bool = Form(False),
    session: Session = Depends(get_session),
):
    content = file.file.read()
    try:
        block = ingest_csv(
            session,
            content=content,
            filename=file.filename or "upload.csv",
            participant_id=participant_id,
            visit_ordinal=visit_ordinal,
            workload_level=workload_level,
            overwrite=overwrite,
        )
    except IngestionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"id": block.id, "workload_level": block.workload_level,
            "visit_id": block.visit_id}
