"""CSV ingestion: file->identity mapping, integrity guards, convert, store.

Reuses matb_integration.log_converter (no metric logic duplicated). The
fit-trigger is added in a later task and imported lazily.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from pathlib import Path

from sqlmodel import Session, select

from app.classic_models import ClassicSessionSelection
from app.models import Block, BlockProvenance, Visit

WORKLOAD_LEVELS = ("LOW", "MEDIUM", "HIGH")

_log = logging.getLogger(__name__)


class IngestionError(Exception):
    """Raised when a file cannot be mapped/validated; never silently mislabel."""


def _convert_and_rows(content: bytes, level: str) -> tuple[dict, list[dict], list[dict]]:
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
        # MISS rows only: that is all the Suhir fit consumes
        # (sysmon_failure_times filters to MISS), and it keeps metrics_json lean.
        all_rows = parse_csv(tmp)
        sysmon_rows = [
            r for r in all_rows
            if r.get("module") == "sysmon"
            and r.get("address") == "signal_detection"
            and r.get("value", "").upper() == "MISS"
        ]
        return record, sysmon_rows, all_rows
    finally:
        tmp.unlink(missing_ok=True)


def _validation_payload(
    *,
    manifest_content: bytes | None,
    manifest_filename: str | None,
    csv_rows: list[dict],
    record: dict,
    participant_id: str,
    visit_ordinal: int,
    workload_level: str,
    source_csv_filename: str,
) -> dict:
    from matb_integration.scenario_manifest import (
        canonical_json,
        manifest_summary,
        sha256_bytes,
        validate_manifest_against_session,
        validation_status,
    )

    if manifest_content is None:
        return {
            "manifest_filename": None,
            "manifest_sha256": None,
            "manifest_json": None,
            "validation_status": "missing_manifest",
            "validation_issues": [{
                "severity": "warning",
                "code": "missing_manifest",
                "message": "No scenario manifest was uploaded with this CSV.",
            }],
            "manifest_summary": None,
        }

    manifest_sha = sha256_bytes(manifest_content)
    try:
        manifest = json.loads(manifest_content.decode("utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest root must be a JSON object")
    except Exception as exc:  # noqa: BLE001 — stored as validation metadata
        return {
            "manifest_filename": manifest_filename,
            "manifest_sha256": manifest_sha,
            "manifest_json": None,
            "validation_status": "invalid_manifest",
            "validation_issues": [{
                "severity": "error",
                "code": "invalid_manifest_json",
                "message": f"Manifest could not be parsed: {type(exc).__name__}: {exc}",
            }],
            "manifest_summary": None,
        }

    issues = validate_manifest_against_session(
        manifest,
        csv_rows=csv_rows,
        converted_record=record,
        participant_id=participant_id,
        visit_ordinal=visit_ordinal,
        workload_level=workload_level,
        source_csv_filename=source_csv_filename,
    )
    return {
        "manifest_filename": manifest_filename,
        "manifest_sha256": manifest_sha,
        "manifest_json": canonical_json(manifest),
        "validation_status": validation_status(issues),
        "validation_issues": issues,
        "manifest_summary": manifest_summary(manifest),
    }


def ingest_csv(
    session: Session,
    *,
    content: bytes,
    filename: str,
    participant_id: str,
    visit_ordinal: int,
    workload_level: str,
    overwrite: bool = False,
    manifest_content: bytes | None = None,
    manifest_filename: str | None = None,
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
    if existing is not None and overwrite:
        classic_selection = session.exec(
            select(ClassicSessionSelection).where(
                ClassicSessionSelection.visit_id == visit.id,
                ClassicSessionSelection.workload_level == workload_level,
            )
        ).first()
        if classic_selection is not None:
            raise IngestionError(
                "classic-selected cell cannot be overwritten by legacy CSV ingestion"
            )

    record, sysmon_rows, csv_rows = _convert_and_rows(content, workload_level)
    sysmon = record.get("sysmon") or {}
    if not sysmon.get("n_signals") and not sysmon.get("n_misses"):
        raise IngestionError("no usable metrics in CSV (no SYSMON signal rows)")
    # Persist raw SYSMON detection rows (timestamps) the Suhir fit needs.
    record["_raw_sysmon_rows"] = sysmon_rows

    if existing is not None:
        old_provenance = session.exec(
            select(BlockProvenance).where(BlockProvenance.block_id == existing.id)
        ).first()
        if old_provenance is not None:
            session.delete(old_provenance)
            session.flush()
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

    validation = _validation_payload(
        manifest_content=manifest_content,
        manifest_filename=manifest_filename,
        csv_rows=csv_rows,
        record=record,
        participant_id=participant_id,
        visit_ordinal=visit_ordinal,
        workload_level=workload_level,
        source_csv_filename=filename,
    )
    session.add(BlockProvenance(
        block_id=block.id,
        manifest_filename=validation["manifest_filename"],
        manifest_sha256=validation["manifest_sha256"],
        manifest_json=validation["manifest_json"],
        validation_status=validation["validation_status"],
        validation_issues_json=json.dumps(validation["validation_issues"], ensure_ascii=False),
    ))
    session.commit()

    _maybe_fit_visit(session, visit)
    return block


def block_validation_summary(session: Session, block_id: int) -> dict:
    prov = session.exec(
        select(BlockProvenance).where(BlockProvenance.block_id == block_id)
    ).first()
    if prov is None:
        return {
            "status": "missing_manifest",
            "issue_count": 0,
            "issues_preview": [],
        }
    issues = json.loads(prov.validation_issues_json or "[]")
    return {
        "status": prov.validation_status,
        "issue_count": len(issues),
        "issues_preview": issues[:3],
    }


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

    # The whole fit+upsert is isolated: ingestion must never fail (and the
    # already-committed Block must never roll back) because a fit could not be
    # computed or stored. Failures are logged, not raised.
    try:
        from app.hcf_refresh import build_hcf_store
        out = fit_participant(visit.participant_id, blocks_arg, source="raw_tlx",
                              hcf_store=build_hcf_store(session) or None)
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
    except Exception as exc:  # noqa: BLE001 — fit/store must not break ingestion
        session.rollback()
        _log.warning("Suhir fit failed/skipped for visit %s: %r", visit.id, exc)
