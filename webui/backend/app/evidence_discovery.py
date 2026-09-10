"""Paginated researcher summaries without reading event/artifact payloads."""
from datetime import timezone
from sqlalchemy import or_
from sqlmodel import Session, select, func

from app.evidence_models import EvidenceCapture, EvidenceRun, EvidenceMetric
from app.models import Visit


def capture_list(db: Session, *, purpose: str, session_id: str | None, query: str,
                 offset: int, limit: int) -> dict:
    conditions = []
    if purpose != "all":
        conditions.append(EvidenceCapture.execution_purpose == purpose)
    if session_id:
        conditions.append(EvidenceCapture.parent_session_id == session_id)
    query = query.strip()
    if query:
        # A researcher searching a literal '%' or '_' must not get every row.
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        conditions.append(or_(*(column.ilike(pattern, escape="\\") for column in (
            EvidenceCapture.participant_id, EvidenceCapture.condition, EvidenceCapture.id,
            EvidenceCapture.block_instance_id, EvidenceCapture.session_id, EvidenceCapture.parent_session_id))))
    total = db.exec(select(func.count()).select_from(EvidenceCapture).where(*conditions)).one()
    columns = [getattr(EvidenceCapture, name) for name in (
        "id", "participant_id", "parent_session_id", "session_id", "block_instance_id", "visit_id",
        "condition", "execution_purpose", "completion", "created_at")]
    rows = db.exec(select(*columns, Visit.visit_ordinal).outerjoin(Visit, EvidenceCapture.visit_id == Visit.id)
                   .where(*conditions).order_by(EvidenceCapture.created_at.desc(), EvidenceCapture.id)
                   .offset(offset).limit(limit))
    items = []
    for row in rows:
        item = dict(row._mapping)
        if item["created_at"].tzinfo is None:
            item["created_at"] = item["created_at"].replace(tzinfo=timezone.utc)
        from app.assessment_adapters import source_identity
        item.update(source_identity(db, "evidence_capture", item["id"]))
        item.update(review_summary(db, item["id"]))
        items.append(item)
    return {"total": total, "offset": offset, "limit": limit, "items": items}


def review_summary(db: Session, capture_id: str) -> dict:
    from app.evidence_qualification import linked
    latest = db.exec(select(EvidenceRun.id, EvidenceRun.status, EvidenceRun.result_json.is_not(None).label("has_result"))
                     .where(EvidenceRun.capture_id == capture_id)
                     .order_by(EvidenceRun.created_at.desc(), EvidenceRun.id.desc()).limit(1)).first()
    excluded = False
    if latest:
        excluded = bool(db.exec(select(EvidenceMetric.id).where(EvidenceMetric.run_id == latest.id,
            or_(EvidenceMetric.status == "failed", (EvidenceMetric.status != "not_applicable") & (EvidenceMetric.eligible == False)))  # noqa: E712
            .limit(1)).first())
    status = ("pending" if latest is None or latest.status == "pending" else
              "processing_failed" if latest.status == "failed" and not latest.has_result else
              "partially_excluded" if excluded else "reconciled")
    qualification = linked(db, capture_id)
    return {"capture_status": status, "qualification": {key: value for key, value in qualification.items() if key != "items"}}
