"""Bounded event-linked review of recorded native task evidence.

This reconstructs recorded task context, not pixels or physical exposure.
"""
from sqlmodel import Session, select, func

from app.evidence_models import EvidenceRecord
from app.evidence_service import capture_or_error, EvidenceError
from matb_integration.evidence.contracts import strict_json


def event_context(db: Session, capture_id: str, event_id: str) -> dict:
    capture_or_error(db, capture_id)
    matches = db.exec(select(EvidenceRecord).where(EvidenceRecord.capture_id == capture_id,
        EvidenceRecord.stream == "events", EvidenceRecord.record_id == event_id).limit(2)).all()
    if not matches:
        raise EvidenceError("event_not_found", 404)
    if len(matches) != 1:
        raise EvidenceError("ambiguous_event_identity")
    selected = matches[0]
    event = strict_json(selected.record_json)
    opportunity_id = event.get("opportunity_id")
    related = [selected]
    if opportunity_id:
        related = db.exec(select(EvidenceRecord).where(EvidenceRecord.capture_id == capture_id,
            EvidenceRecord.stream == "events", func.json_extract(EvidenceRecord.record_json, "$.opportunity_id") == opportunity_id)
            .order_by(EvidenceRecord.ordinal).limit(33)).all()
    window = related[:32]
    if all(row.id != selected.id for row in window):
        window = sorted([*window[:31], selected], key=lambda row: row.ordinal)
    # A bounded source window makes incomplete context explicit. It is never
    # extrapolated across a missing event or a different task/capture.
    preceding = db.exec(select(EvidenceRecord).where(EvidenceRecord.capture_id == capture_id,
        EvidenceRecord.stream == "events", EvidenceRecord.task == selected.task,
        EvidenceRecord.ordinal <= selected.ordinal).order_by(EvidenceRecord.ordinal.desc()).limit(33)).all()
    fields = {}
    for row in preceding[:32]:
        value = strict_json(row.record_json)
        payload = value["payload"]
        key = (payload["record_type"], payload["address"])
        if key not in fields and not payload.get("opportunity"):
            fields[key] = {"kind": key[0], "address": key[1], "value": payload["value"],
                           "event_id": row.event_id, "scenario_time_ns_text": str(value["scenario_time_ns"])}
    ids = {row.event_id for row in window}
    observations = db.exec(select(EvidenceRecord).where(EvidenceRecord.capture_id == capture_id,
        EvidenceRecord.stream == "timing", EvidenceRecord.event_id.in_(ids))
        .order_by(EvidenceRecord.ordinal).limit(129)).all()
    return {"schema_version": "1.0", "selected_event_id": event_id, "task": selected.task,
        "precision": "recorded_task_context_with_software_observations",
        "events": [{"record": strict_json(row.record_json), "raw_json": row.record_json,
                    "scenario_time_ns_text": str(strict_json(row.record_json)["scenario_time_ns"])} for row in window],
        "task_fields": list(fields.values()),
        "timing": [{"record": strict_json(row.record_json), "value_text": str(strict_json(row.record_json)["value"])} for row in observations[:128]],
        "truncated": {"opportunity_events": len(related) > 32, "preceding_task_window": len(preceding) > 32,
                      "timing_observations": len(observations) > 128},
        "unavailable_streams": ["native_visual_exposure", "physical_onset", "synchronized_physiology", "gaze"],
        "limitations": ["task_context_is_not_a_recording_of_visual_exposure", "different_clock_domains_are_not_subtracted",
                        "physiology_requires_a_qualified_clock_mapping"]}
