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


def _convert_and_rows(content: bytes, level: str) -> tuple[dict, list[dict]]:
    """Run convert_session and capture the raw SYSMON detection rows (timestamps).

    The Suhir fit needs the raw MISS timestamps; Block stores only the converted
    record, so we embed the rows into the record (see ingest_csv).
    """
    from matb_integration.log_converter import convert_session, parse_csv

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as fh:
        fh.write(content)
        tmp = Path(fh.name)
    try:
        record = convert_session(tmp, workload_level=level)
        sysmon_rows = [
            r for r in parse_csv(tmp)
            if r.get("module") == "sysmon" and r.get("address") == "signal_detection"
        ]
        return record, sysmon_rows
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

    record, sysmon_rows = _convert_and_rows(content, workload_level)
    sysmon = record.get("sysmon") or {}
    if not sysmon.get("n_signals") and not sysmon.get("n_misses"):
        raise IngestionError("no usable metrics in CSV (no SYSMON signal rows)")
    # Persist raw SYSMON detection rows (timestamps) the Suhir fit needs.
    record["_raw_sysmon_rows"] = sysmon_rows

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
    _maybe_fit_visit(session, visit)
    return block


def _maybe_fit_visit(session: Session, visit: Visit) -> None:
    """If all 3 levels of this visit are present, run the Suhir fit and upsert it.

    Imported lazily so Tasks 1-6 don't require matb_integration.suhir. A failed
    fit (e.g. unbracketed G0) is swallowed — ingestion must not fail because a
    fit could not be computed.
    """
    blocks = session.exec(select(Block).where(Block.visit_id == visit.id)).all()
    by_level = {b.workload_level: b for b in blocks}
    if set(by_level) != set(WORKLOAD_LEVELS):
        return

    from matb_integration.suhir.pipeline import fit_participant
    from app.models import DepdfFit

    blocks_arg: dict[str, tuple[dict, list[dict]]] = {}
    for level, b in by_level.items():
        record = json.loads(b.metrics_json)
        rows = record.get("_raw_sysmon_rows", [])
        blocks_arg[level] = (record, rows)

    try:
        out = fit_participant(visit.participant_id, blocks_arg, source="raw_tlx")
    except Exception:
        return

    existing = session.exec(
        select(DepdfFit).where(DepdfFit.visit_id == visit.id)
    ).first()
    if existing is not None:
        session.delete(existing)
        session.flush()
    session.add(DepdfFit(
        participant_id=visit.participant_id,
        visit_id=visit.id,
        mwl_source=out["mwl_source"],
        g0=out["g0"], p0=out["p0"], tau0=out["tau0"],
        hcf_value=out["hcf_value"], hcf_source=out["hcf_source"],
        criteria_version=out["criteria_version"],
        per_level_json=json.dumps(out["per_level"], ensure_ascii=False),
    ))
    session.commit()
