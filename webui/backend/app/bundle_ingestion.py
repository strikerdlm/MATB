"""Validated, bounded persistence for OpenMATB scientific bundles."""

from __future__ import annotations

import hashlib
from io import BytesIO
import json
import mimetypes
from pathlib import Path
import tempfile
from typing import Any
import zipfile

from sqlmodel import Session, select

from app.ingestion import IngestionError, WORKLOAD_LEVELS, ingest_csv
from app.models import Block, BlockArtifact, BlockBundle, Visit
from matb_integration.scientific_data.bundle import (
    CHECKSUM_NAME,
    MAX_COMPRESSED_BYTES,
    REQUIRED_ARTIFACTS,
    validate_bundle,
)
from matb_integration.scientific_data.schema import BUNDLE_SCHEMA_VERSION


ALLOWED_ARTIFACTS = REQUIRED_ARTIFACTS | {CHECKSUM_NAME, "partial-run.json"}


def _json_object(artifacts: dict[str, bytes], name: str) -> dict[str, Any]:
    try:
        value = json.loads(artifacts[name].decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IngestionError(f"invalid bundle JSON: {name}") from exc
    if not isinstance(value, dict):
        raise IngestionError(f"invalid bundle JSON object: {name}")
    return value


def _validated_artifacts(content: bytes) -> dict[str, bytes]:
    if len(content) > MAX_COMPRESSED_BYTES:
        raise IngestionError("bundle exceeds compressed size limit")
    with tempfile.NamedTemporaryFile(suffix=".matb.zip") as temporary:
        temporary.write(content)
        temporary.flush()
        result = validate_bundle(Path(temporary.name))
    if result["status"] != "ok":
        raise IngestionError("invalid scientific bundle: " + ", ".join(result["codes"]))
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            artifacts = {info.filename: archive.read(info) for info in archive.infolist()}
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise IngestionError("invalid scientific bundle ZIP") from exc
    unexpected = set(artifacts) - ALLOWED_ARTIFACTS
    if unexpected:
        raise IngestionError(f"unexpected bundle artifacts: {sorted(unexpected)}")
    return artifacts


def _manifest_content(manifest: dict[str, Any]) -> tuple[bytes | None, str | None]:
    source = manifest.get("source")
    if not isinstance(source, dict):
        return None, None
    scenario_manifest = source.get("scenario_manifest")
    if not isinstance(scenario_manifest, dict):
        return None, None
    scenario = source.get("scenario") if isinstance(source.get("scenario"), dict) else {}
    filename = str(scenario.get("filename", "scenario.txt")) + ".manifest.json"
    return json.dumps(scenario_manifest, ensure_ascii=False).encode("utf-8"), Path(filename).name


def _media_type(name: str) -> str:
    if name.endswith(".json"):
        return "application/json"
    if name.endswith(".csv"):
        return "text/csv"
    if name.endswith(".parquet"):
        return "application/vnd.apache.parquet"
    if name == CHECKSUM_NAME:
        return "text/plain"
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def ingest_scientific_bundle(
    session: Session,
    *,
    content: bytes,
    filename: str,
    participant_id: str,
    visit_ordinal: int,
    workload_level: str,
    artifact_root: Path,
    overwrite: bool = False,
) -> BlockBundle:
    if workload_level not in WORKLOAD_LEVELS:
        raise IngestionError(f"invalid workload_level {workload_level!r}")
    if not filename.lower().endswith(".matb.zip"):
        raise IngestionError("scientific bundle filename must end in .matb.zip")
    artifacts = _validated_artifacts(content)
    manifest = _json_object(artifacts, "manifest.json")
    summary = _json_object(artifacts, "summary.json")
    quality = _json_object(artifacts, "quality.json")
    dictionary = _json_object(artifacts, "data_dictionary.json")
    for name, document in (
        ("manifest.json", manifest),
        ("summary.json", summary),
        ("data_dictionary.json", dictionary),
    ):
        if document.get("schema_version") != BUNDLE_SCHEMA_VERSION:
            raise IngestionError(f"unsupported schema_version in {name}")
    if summary.get("status") not in {"complete", "partial"}:
        raise IngestionError("summary status must be complete or partial")
    if summary.get("status") == "partial" and "partial-run.json" not in artifacts:
        raise IngestionError("partial bundle is missing partial-run.json")

    visit = session.exec(
        select(Visit).where(
            Visit.participant_id == participant_id,
            Visit.visit_ordinal == visit_ordinal,
        )
    ).first()
    if visit is None:
        raise IngestionError(f"no visit {visit_ordinal} for participant {participant_id}")
    bundle_sha = hashlib.sha256(content).hexdigest()
    if session.exec(select(BlockBundle).where(BlockBundle.bundle_sha256 == bundle_sha)).first() is not None:
        raise IngestionError(f"bundle already ingested (sha {bundle_sha[:12]})")

    existing = session.exec(
        select(Block).where(Block.visit_id == visit.id, Block.workload_level == workload_level)
    ).first()
    events = artifacts["events.csv"]
    events_sha = hashlib.sha256(events).hexdigest()
    prior_filename: str | None = None
    if existing is not None:
        prior_bundle = session.exec(select(BlockBundle).where(BlockBundle.block_id == existing.id)).first()
        if prior_bundle is not None and not overwrite:
            raise IngestionError("cell already has a scientific bundle")
        if existing.source_csv_sha256 != events_sha and not overwrite:
            raise IngestionError(
                f"cell already filled: {participant_id} visit {visit_ordinal} {workload_level}"
            )
        if prior_bundle is not None:
            prior_filename = prior_bundle.stored_filename
            for artifact in session.exec(
                select(BlockArtifact).where(BlockArtifact.bundle_id == prior_bundle.id)
            ).all():
                session.delete(artifact)
            session.delete(prior_bundle)
            session.commit()

    root = Path(artifact_root)
    stored_filename = f"{bundle_sha}.matb.zip"
    destination = root / stored_filename
    root.mkdir(parents=True, exist_ok=True)
    if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() != bundle_sha:
        raise IngestionError("bundle storage collision")
    if not destination.exists():
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(destination)

    try:
        if existing is None or existing.source_csv_sha256 != events_sha:
            scenario_manifest, scenario_manifest_filename = _manifest_content(manifest)
            block = ingest_csv(
                session,
                content=events,
                filename="events.csv",
                participant_id=participant_id,
                visit_ordinal=visit_ordinal,
                workload_level=workload_level,
                overwrite=overwrite,
                manifest_content=scenario_manifest,
                manifest_filename=scenario_manifest_filename,
            )
        else:
            block = existing
        bundle = BlockBundle(
            block_id=block.id,
            bundle_sha256=bundle_sha,
            original_filename=Path(filename).name,
            stored_filename=stored_filename,
            schema_version=BUNDLE_SCHEMA_VERSION,
            run_status=str(summary["status"]),
            quality_status=str(quality.get("status", "unknown")),
            session_id=str(manifest.get("session_id", summary.get("session_id", ""))),
            summary_json=json.dumps(summary, ensure_ascii=False, sort_keys=True),
            manifest_json=json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            quality_json=json.dumps(quality, ensure_ascii=False, sort_keys=True),
        )
        session.add(bundle)
        session.commit()
        session.refresh(bundle)
        for name, payload in sorted(artifacts.items()):
            session.add(BlockArtifact(
                bundle_id=bundle.id,
                name=name,
                sha256=hashlib.sha256(payload).hexdigest(),
                size_bytes=len(payload),
                media_type=_media_type(name),
            ))
        session.commit()
    except Exception:
        session.rollback()
        destination.unlink(missing_ok=True)
        raise
    if prior_filename and prior_filename != stored_filename:
        (root / Path(prior_filename).name).unlink(missing_ok=True)
    return bundle


__all__ = ["ingest_scientific_bundle"]
