"""Scientific bundle ingest, inventory, and verified download endpoints."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import zipfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.bundle_ingestion import ingest_scientific_bundle
from app.db import get_session
from app.ingestion import IngestionError
from app.models import BlockArtifact, BlockBundle
from matb_integration.scientific_data.bundle import MAX_COMPRESSED_BYTES


router = APIRouter(tags=["scientific-bundles"])


def artifact_root() -> Path:
    configured = os.getenv("MATB_OPENMATB_BUNDLE_DIR")
    value = Path(configured) if configured else Path("exports") / "openmatb"
    if value.is_absolute():
        return value
    return Path(__file__).resolve().parents[4] / value


def _bundle_for_block(session: Session, block_id: int) -> BlockBundle:
    bundle = session.exec(select(BlockBundle).where(BlockBundle.block_id == block_id)).first()
    if bundle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scientific bundle not found")
    return bundle


def _stored_path(bundle: BlockBundle) -> Path:
    root = artifact_root().resolve()
    path = (root / Path(bundle.stored_filename).name).resolve()
    if path.parent != root:
        raise HTTPException(status.HTTP_409_CONFLICT, "invalid stored bundle path")
    if not path.is_file():
        raise HTTPException(status.HTTP_409_CONFLICT, "stored bundle is missing")
    return path


@router.post("/ingest-bundle", status_code=status.HTTP_201_CREATED)
def ingest_bundle(
    file: UploadFile = File(...),
    participant_id: str = Form(...),
    visit_ordinal: int = Form(...),
    workload_level: str = Form(...),
    overwrite: bool = Form(False),
    session: Session = Depends(get_session),
):
    content = file.file.read(MAX_COMPRESSED_BYTES + 1)
    try:
        bundle = ingest_scientific_bundle(
            session,
            content=content,
            filename=file.filename or "upload.matb.zip",
            participant_id=participant_id,
            visit_ordinal=visit_ordinal,
            workload_level=workload_level,
            artifact_root=artifact_root(),
            overwrite=overwrite,
        )
    except IngestionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {
        "id": bundle.id,
        "block_id": bundle.block_id,
        "bundle_sha256": bundle.bundle_sha256,
        "schema_version": bundle.schema_version,
        "run_status": bundle.run_status,
        "quality_status": bundle.quality_status,
    }


@router.get("/blocks/{block_id}/artifacts")
def list_bundle_artifacts(block_id: int, session: Session = Depends(get_session)):
    bundle = _bundle_for_block(session, block_id)
    return session.exec(
        select(BlockArtifact).where(BlockArtifact.bundle_id == bundle.id).order_by(BlockArtifact.name)
    ).all()


@router.get("/blocks/{block_id}/artifacts/{name}")
def download_bundle_artifact(block_id: int, name: str, session: Session = Depends(get_session)):
    bundle = _bundle_for_block(session, block_id)
    artifact = session.exec(
        select(BlockArtifact).where(BlockArtifact.bundle_id == bundle.id, BlockArtifact.name == name)
    ).first()
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "bundle artifact not found")
    try:
        with zipfile.ZipFile(_stored_path(bundle)) as archive:
            payload = archive.read(name)
    except (KeyError, OSError, zipfile.BadZipFile) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "stored bundle artifact is unavailable") from exc
    if hashlib.sha256(payload).hexdigest() != artifact.sha256:
        raise HTTPException(status.HTTP_409_CONFLICT, "stored bundle artifact checksum mismatch")
    return Response(
        content=payload,
        media_type=artifact.media_type,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/blocks/{block_id}/bundle")
def download_bundle(block_id: int, session: Session = Depends(get_session)):
    bundle = _bundle_for_block(session, block_id)
    path = _stored_path(bundle)
    if hashlib.sha256(path.read_bytes()).hexdigest() != bundle.bundle_sha256:
        raise HTTPException(status.HTTP_409_CONFLICT, "stored bundle checksum mismatch")
    return FileResponse(path, media_type="application/zip", filename=bundle.original_filename)
