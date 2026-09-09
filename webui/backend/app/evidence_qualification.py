"""Append-only qualification records and capture-context attestations."""
from hashlib import sha256

from sqlmodel import Session, select

from app.evidence_models import (EvidenceQualification, EvidenceQualificationArtifact,
    EvidenceQualificationLink, EvidenceQualificationRevocation)
from app.evidence_service import EvidenceError, capture_or_error
from matb_integration.evidence.contracts import canonical_bytes, strict_json
from matb_integration.evidence.qualification import (QualificationSubmissionV1, QualificationBindingV1,
    prepare_qualification)


def register(db: Session, submission: QualificationSubmissionV1) -> dict:
    try:
        record, artifacts = prepare_qualification(submission)
    except (ValueError, TypeError, OverflowError) as exc:
        raise EvidenceError(f"invalid_qualification: {exc}", 422) from exc
    if db.get(EvidenceQualification, record["id"]) is None:
        db.add(EvidenceQualification(id=record["id"], record_json=canonical_bytes(record).decode()))
        db.flush()
        for name, content in artifacts.items():
            db.add(EvidenceQualificationArtifact(qualification_id=record["id"], name=name, content=content))
        db.commit()
    return read(db, record["id"])


def read(db: Session, record_id: str) -> dict:
    row = db.get(EvidenceQualification, record_id)
    if row is None:
        raise EvidenceError("qualification_not_found", 404)
    revocations = db.exec(select(EvidenceQualificationRevocation).where(
        EvidenceQualificationRevocation.qualification_id == record_id).order_by(EvidenceQualificationRevocation.id)).all()
    return {**strict_json(row.record_json), "revocations": [r.model_dump(mode="json") for r in revocations]}


def link(db: Session, capture_id: str, binding: QualificationBindingV1) -> dict:
    capture = capture_or_error(db, capture_id)
    record = read(db, binding.record_id)
    manifest = strict_json(capture.manifest_json)
    context = binding.context.model_dump()
    if record["revocations"]:
        raise EvidenceError("qualification_revoked")
    if (binding.capture_manifest_sha256 != capture.manifest_sha256 or context != record["context"]
            or context["software_versions"]["acquisition_commit"] != manifest["source_commit"]
            or context["presentation"]["profile_id"] != manifest["profile_id"]):
        raise EvidenceError("qualification_context_mismatch")
    value = {"capture_id": capture_id, **binding.model_dump()}
    lid = sha256(canonical_bytes(value)).hexdigest()
    if db.get(EvidenceQualificationLink, lid) is None:
        if len(db.exec(select(EvidenceQualificationLink).where(EvidenceQualificationLink.capture_id == capture_id)).all()) >= 32:
            raise EvidenceError("qualification_link_capacity", 422)
        db.add(EvidenceQualificationLink(id=lid, capture_id=capture_id, qualification_id=binding.record_id,
                                        binding_json=canonical_bytes(value).decode()))
        db.commit()
    return linked(db, capture_id)


def revoke(db: Session, record_id: str, reviewer: str, reason: str) -> dict:
    read(db, record_id)
    rid = sha256(canonical_bytes([record_id, reviewer, reason])).hexdigest()
    if db.get(EvidenceQualificationRevocation, rid) is None:
        db.add(EvidenceQualificationRevocation(id=rid, qualification_id=record_id, reviewer=reviewer, reason=reason))
        db.commit()
    return read(db, record_id)


def linked(db: Session, capture_id: str) -> dict:
    capture_or_error(db, capture_id)
    links = db.exec(select(EvidenceQualificationLink).where(EvidenceQualificationLink.capture_id == capture_id)
                    .order_by(EvidenceQualificationLink.id)).all()
    items = []
    for row in links:
        record = read(db, row.qualification_id)
        items.append({"id": row.id, "binding": strict_json(row.binding_json), "record": record,
                      "status": "invalidated" if record["revocations"] else "linked_report",
                      "result": record["assessment"]["status"]})
    return {"schema_version": "1.0", "items": items,
            "physical_timing": "linked_evidence" if any(i["record"]["kind"] == "physical_timing" and i["status"] == "linked_report" for i in items) else "not_qualified",
            "human_calibration": "linked_evidence" if any(i["record"]["kind"] == "human_calibration" and i["status"] == "linked_report" for i in items) else "not_qualified",
            "protocol_eligibility": {"status": "not_assessed", "reason": "requires_separate_protocol_review_and_session_quality_checks"}}
