"""CSV ingestion: file->identity mapping, integrity guards, convert, store.

Reuses matb_integration.log_converter (no metric logic duplicated). The
fit-trigger is added in a later task and imported lazily.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from sqlmodel import Session, select

from app.models import Block, Visit

WORKLOAD_LEVELS = ("LOW", "MEDIUM", "HIGH")


class IngestionError(Exception):
    """Raised when a file cannot be mapped/validated; never silently mislabel."""


def _convert(content: bytes, level: str) -> dict:
    """Run log_converter.convert_session on the uploaded bytes."""
    from matb_integration.log_converter import convert_session

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as fh:
        fh.write(content)
        tmp = Path(fh.name)
    try:
        return convert_session(tmp, workload_level=level)
    finally:
        tmp.unlink(missing_ok=True)


def ingest_csv(
    session: Session,
    *,
    content: bytes,
    filename: str,
    participant_id: str,
    visit_ordinal: int,
    workload_level: str,
    overwrite: bool = False,
) -> Block:
    if workload_level not in WORKLOAD_LEVELS:
        raise IngestionError(f"invalid workload_level {workload_level!r}")

    visit = session.exec(
        select(Visit).where(
            Visit.participant_id == participant_id,
            Visit.visit_ordinal == visit_ordinal,
        )
    ).first()
    if visit is None:
        raise IngestionError(f"no visit {visit_ordinal} for participant {participant_id}")

    sha = hashlib.sha256(content).hexdigest()
    dup = session.exec(select(Block).where(Block.source_csv_sha256 == sha)).first()
    if dup is not None and not (overwrite and dup.visit_id == visit.id
                                and dup.workload_level == workload_level):
        raise IngestionError(f"file already ingested (sha {sha[:12]})")

    existing = session.exec(
        select(Block).where(Block.visit_id == visit.id,
                            Block.workload_level == workload_level)
    ).first()
    if existing is not None and not overwrite:
        raise IngestionError(
            f"cell already filled: {participant_id} visit {visit_ordinal} {workload_level}"
        )

    record = _convert(content, workload_level)
    sysmon = record.get("sysmon") or {}
    if not sysmon.get("n_signals") and not sysmon.get("n_misses"):
        raise IngestionError("no usable metrics in CSV (no SYSMON signal rows)")

    if existing is not None:
        session.delete(existing)
        session.flush()

    block = Block(
        visit_id=visit.id,
        workload_level=workload_level,
        source_csv_filename=filename,
        source_csv_sha256=sha,
        metrics_json=json.dumps(record, ensure_ascii=False),
    )
    session.add(block)
    session.commit()
    session.refresh(block)
    return block
