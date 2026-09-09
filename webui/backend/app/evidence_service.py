"""Immutable storage and recoverable, versioned derivation of classic evidence."""
from __future__ import annotations

import hashlib
import io
import threading
import zipfile
from itertools import batched
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select, func

from app.models import Participant, Visit
from app.evidence_models import (EvidenceCapture, EvidenceArtifact, EvidenceRun, EvidenceRecord,
    EvidenceMetric, EvidenceMetricSource, EvidenceAnalysisInput)
from matb_integration.evidence.contracts import canonical_bytes, strict_json, DERIVATION_VERSION, CaptureManifestV1, MAX_STREAM_BYTES
from matb_integration.evidence.reconcile import parse_capture, reconcile

_DERIVATION_LOCK = threading.Lock()


class EvidenceError(ValueError):
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.status = status


def capture_or_error(db: Session, capture_id: str) -> EvidenceCapture:
    row = db.get(EvidenceCapture, capture_id)
    if row is None:
        raise EvidenceError("capture_not_found", 404)
    return row


def ingest_evidence(db: Session, artifacts: dict[str, bytes]) -> tuple[str, bool]:
    try:
        manifest = CaptureManifestV1.model_validate(strict_json(artifacts["capture_manifest"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise EvidenceError(f"invalid_evidence: {exc}", 422) from exc
    fingerprint = hashlib.sha256(canonical_bytes({k: hashlib.sha256(v).hexdigest() for k, v in artifacts.items()})).hexdigest()
    existing = db.get(EvidenceCapture, manifest.capture_id)
    if existing:
        if existing.artifact_fingerprint != fingerprint:
            try:
                parse_capture(artifacts)
            except (ValueError, KeyError, TypeError) as exc:
                raise EvidenceError(f"invalid_evidence: {exc}", 422) from exc
            raise EvidenceError("capture_identity_conflict")
        return existing.id, False
    # Identical immutable bytes were already validated. A new identity still
    # requires full schema, count and integrity validation before any storage.
    try:
        manifest, _scenario, events, timing = parse_capture(artifacts)
    except (ValueError, KeyError, TypeError) as exc:
        raise EvidenceError(f"invalid_evidence: {exc}", 422) from exc
    visit = None
    if manifest.participant_id:
        if db.get(Participant, manifest.participant_id) is None:
            raise EvidenceError("participant_not_found")
        if manifest.visit_ordinal is not None:
            visit = db.exec(select(Visit).where(Visit.participant_id == manifest.participant_id,
                                               Visit.visit_ordinal == manifest.visit_ordinal)).first()
            if visit is None:
                raise EvidenceError("visit_not_found")
    capture = EvidenceCapture(id=manifest.capture_id, manifest_sha256=hashlib.sha256(artifacts["capture_manifest"]).hexdigest(),
        artifact_fingerprint=fingerprint, session_id=manifest.session_id, block_instance_id=manifest.block_instance_id,
        participant_id=manifest.participant_id, visit_id=visit.id if visit else None,
        condition=manifest.condition, execution_purpose=manifest.execution_purpose, completion=manifest.completion,
        manifest_json=artifacts["capture_manifest"].decode("utf-8"))
    db.add(capture)
    pending_run_id = str(uuid4())
    try:
        db.flush()
        for role, content in artifacts.items():
            db.add(EvidenceArtifact(capture_id=capture.id, role=role, sha256=hashlib.sha256(content).hexdigest(), content=content))
        tasks = {str(event.event_id): event.task for event in events}
        for stream, records in (("events", events), ("timing", timing)):
            original_lines = io.BytesIO(artifacts[stream])
            for ordinal, record in enumerate(records):
                value = record.to_record()
                db.add(EvidenceRecord(capture_id=capture.id, stream=stream, ordinal=ordinal,
                    record_id=value.get("observation_id", value["event_id"]), event_id=value["event_id"],
                    task=tasks.get(value["event_id"]), record_json=next(original_lines).decode("utf-8")))
                if ordinal % 500 == 499:
                    db.flush()
        db.add(EvidenceRun(id=pending_run_id, capture_id=capture.id, version=DERIVATION_VERSION))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        winner = db.get(EvidenceCapture, manifest.capture_id)
        if winner and winner.artifact_fingerprint == fingerprint:
            return winner.id, False
        raise EvidenceError("capture_identity_conflict") from exc
    del events, timing
    run_derivation(db, capture.id, pending_run_id)
    return capture.id, True


def source_artifacts(db: Session, capture_id: str) -> dict[str, bytes]:
    return {a.role: a.content for a in db.exec(select(EvidenceArtifact).where(EvidenceArtifact.capture_id == capture_id))}


def run_derivation(db: Session, capture_id: str, pending_run_id: str | None = None) -> str:
    capture_or_error(db, capture_id)
    _DERIVATION_LOCK.acquire()
    try:
        run = db.get(EvidenceRun, pending_run_id) if pending_run_id else EvidenceRun(id=str(uuid4()), capture_id=capture_id, version=DERIVATION_VERSION)
        db.add(run)
        db.commit()
        try:
            result = reconcile(source_artifacts(db, capture_id))
            for metric in result["metrics"]:
                details = {k: v for k, v in metric.items() if k not in {"source_event_ids", "source_observation_ids"}}
                metric_row = EvidenceMetric(id=str(uuid4()), run_id=run.id, capture_id=capture_id,
                    key=metric["metric"], version=metric["metric_version"], status=metric["status"],
                    value=metric["value"], eligible=metric["confirmatory_eligible"], details_json=canonical_bytes(details).decode())
                db.add(metric_row)
                db.flush()
                for stream, key in (("events", "source_event_ids"), ("timing", "source_observation_ids")):
                    for batch in batched(dict.fromkeys(metric[key]), 500):
                        db.add_all([EvidenceMetricSource(metric_id=metric_row.id, stream=stream, record_id=rid) for rid in batch])
                        db.flush()
            run.status = result["status"]
            run.fingerprint = result["fingerprint"]
            run.result_json = canonical_bytes({k: v for k, v in result.items() if k != "metrics"}).decode()
            db.add(run)
            db.commit()
        except Exception as exc:
            db.rollback()
            run = db.get(EvidenceRun, run.id)
            run.status = "failed"
            run.reason = f"derivation_failed:{type(exc).__name__}"
            db.add(run)
            db.commit()
        return run.id
    finally:
        _DERIVATION_LOCK.release()


def recover_evidence_runs(engine) -> None:
    with Session(engine) as db:
        for run in db.exec(select(EvidenceRun).where(EvidenceRun.status == "pending")):
            run.status = "failed"
            run.reason = "interrupted_processing"
            db.add(run)
        db.commit()


def capture_summary(db: Session, capture_id: str) -> dict:
    from app.evidence_qualification import linked
    capture = capture_or_error(db, capture_id)
    runs = list(db.exec(select(EvidenceRun).where(EvidenceRun.capture_id == capture_id).order_by(EvidenceRun.created_at.desc(), EvidenceRun.id.desc())))
    latest = runs[0] if runs else None
    metrics = list(db.exec(select(EvidenceMetric).where(EvidenceMetric.run_id == latest.id))) if latest else []
    status = "processing_failed" if latest and not latest.result_json and latest.status == "failed" else (
        "pending" if latest is None or latest.status == "pending" else (
            "partially_excluded" if any(m.status == "failed" or (m.status != "not_applicable" and not m.eligible) for m in metrics) else "reconciled"))
    return {**capture.model_dump(), "manifest": strict_json(capture.manifest_json),
        "capture_status": status, "qualification": linked(db, capture_id),
        "runs": [{"id": r.id, "status": r.status, "reason": r.reason, "version": r.version} for r in runs],
        "reconciliation": strict_json(latest.result_json) if latest and latest.result_json else None,
        "metrics": [{"id": m.id, **strict_json(m.details_json)} for m in metrics]}


def metric_or_error(db: Session, capture_id: str, metric_id: str) -> EvidenceMetric:
    metric = db.get(EvidenceMetric, metric_id)
    if metric is None or metric.capture_id != capture_id:
        raise EvidenceError("metric_not_found", 404)
    return metric


def write_bundle(db: Session, capture_id: str, output) -> None:
    """Write seekable ZIP output in bounded chunks, retaining exact source bytes."""
    summary = capture_summary(db, capture_id)
    report = dict(summary)
    report.pop("created_at", None); report.pop("manifest_json", None)
    for metric in report["metrics"]:
        metric["sources"] = [{"stream": s.stream, "record_id": s.record_id} for s in db.exec(
            select(EvidenceMetricSource).where(EvidenceMetricSource.metric_id == metric["id"]).order_by(EvidenceMetricSource.id))]
    checksums = {}
    from app.evidence_models import EvidenceQualificationArtifact
    # Query metadata first. SQLite's incremental BLOB reader retrieves chunks;
    # no source-artifact dictionary or complete ZIP is held by the HTTP route.
    members = []
    for aid, role, digest, size in db.exec(select(EvidenceArtifact.id, EvidenceArtifact.role,
            EvidenceArtifact.sha256, func.length(EvidenceArtifact.content)).where(EvidenceArtifact.capture_id == capture_id)):
        suffix = 'jsonl' if role in {'events', 'timing', 'runtime_envelope'} else 'csv' if role == 'legacy_csv' else 'json'
        members.append((f"sources/{role}.{suffix}", EvidenceArtifact, aid, size, digest))
    seen = set()
    for item in summary["qualification"]["items"]:
        record = item["record"]
        if record["id"] in seen: continue
        seen.add(record["id"])
        for aid, name, size in db.exec(select(EvidenceQualificationArtifact.id, EvidenceQualificationArtifact.name,
                func.length(EvidenceQualificationArtifact.content)).where(EvidenceQualificationArtifact.qualification_id == record["id"])):
            members.append((f"qualification/{record['id']}/{name}", EvidenceQualificationArtifact, aid, size, record["evidence"][name]["sha256"]))
    def info(name):
        entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        entry.compress_type = zipfile.ZIP_DEFLATED
        return entry
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, model, aid, size, expected in sorted(members, key=lambda m: m[0]):
            digest = hashlib.sha256()
            connection = db.connection().connection.driver_connection
            with connection.blobopen(model.__tablename__, "content", aid, readonly=True) as source, archive.open(info(name), "w") as sink:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk); sink.write(chunk)
            if digest.hexdigest() != expected:
                raise EvidenceError("stored_artifact_integrity_mismatch")
            checksums[name] = expected
        for name, content in {
            "report.json": canonical_bytes(report),
            "README.txt": b"Classic MATB evidence bundle. Original sources are preserved byte-for-byte.\nRecompute: python -m matb_integration.evidence <bundle.zip>\nSoftware observations do not establish physical onset or human validity.\n",
        }.items():
            if len(content) > MAX_STREAM_BYTES:
                raise EvidenceError("export_report_capacity_exceeded", 413)
            archive.writestr(info(name), content)
            checksums[name] = hashlib.sha256(content).hexdigest()
        archive.writestr(info("checksums.json"), canonical_bytes(checksums))


def export_bundle(db: Session, capture_id: str) -> bytes:
    """Compatibility helper for in-process callers; HTTP uses write_bundle."""
    output = io.BytesIO()
    write_bundle(db, capture_id, output)
    return output.getvalue()


def freeze_analysis_input(db: Session, metric_ids: list[str]) -> dict:
    if not metric_ids or len(metric_ids) != len(set(metric_ids)) or len(metric_ids) > 1000:
        raise EvidenceError("select_unique_metric_results", 422)
    rows = []
    selected_blocks = set()
    for mid in sorted(metric_ids):
        metric = db.get(EvidenceMetric, mid)
        if metric is None or not metric.eligible or metric.status != "succeeded" or metric.value is None:
            raise EvidenceError("analysis_requires_eligible_metrics")
        capture = capture_or_error(db, metric.capture_id)
        run = db.get(EvidenceRun, metric.run_id)
        visit = db.get(Visit, capture.visit_id) if capture.visit_id is not None else None
        if capture.execution_purpose != "study":
            raise EvidenceError("analysis_requires_study_capture")
        block_metric = (capture.block_instance_id, metric.key)
        if block_metric in selected_blocks:
            raise EvidenceError("select_one_result_per_block_and_metric")
        selected_blocks.add(block_metric)
        rows.append({"metric_id": mid, "capture_id": capture.id, "block_instance_id": capture.block_instance_id,
            "participant_id": capture.participant_id, "visit_id": capture.visit_id, "condition": capture.condition,
            "visit_ordinal": visit.visit_ordinal if visit else None,
            "metrics_schema_version": "2.0", "scientific_source_status": "authoritative_event_stream_reconciled",
            "metric": metric.key, "metric_version": metric.version, "value": metric.value,
            "confirmatory_eligible": True, "reconciliation_fingerprint": run.fingerprint,
            "manifest_sha256": capture.manifest_sha256, "derivation_version": run.version,
            "analysis_execution": strict_json(run.result_json).get("analysis_execution") if run.result_json else None})
    payload = {"schema_version": "1.0", "rows": rows, "automatic_model": None}
    fid = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    if db.get(EvidenceAnalysisInput, fid) is None:
        db.add(EvidenceAnalysisInput(id=fid, input_json=canonical_bytes(payload).decode()))
        db.commit()
    return {"id": fid, **payload}
