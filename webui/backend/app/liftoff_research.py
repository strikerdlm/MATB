"""Optional Liftoff research projections used by console extensions."""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from app.constants import protocol_visits
from app.liftoff_models import LiftoffArtifact, LiftoffDeviation, LiftoffSession
from app.models import Participant, Visit


_LIFTOFF_UNITS = {
    "median_lap_time_s": "s",
    "best_lap_time_s": "s",
    "active_duration_s": "s",
    "lap_completion_proportion": "proportion",
    "input_saturation_fraction": "proportion",
    "lap_time_cv": "ratio",
}


def collect_liftoff_metric_rows(
    session: Session,
    participant_id: str | None = None,
) -> list[dict[str, Any]]:
    query = select(LiftoffSession, Visit).where(
        LiftoffSession.visit_id == Visit.id,
        LiftoffSession.validity == "valid",
        LiftoffSession.execution_purpose == "study",
    ).order_by(
        LiftoffSession.participant_id,
        Visit.visit_ordinal,
        LiftoffSession.attempt_number,
    )
    if participant_id is not None:
        query = query.where(LiftoffSession.participant_id == participant_id)
    selected: dict[tuple[str, int], tuple[LiftoffSession, Visit]] = {}
    for liftoff, visit in session.exec(query).all():
        selected.setdefault((liftoff.participant_id, visit.id), (liftoff, visit))
    rows: list[dict[str, Any]] = []
    for liftoff, visit in selected.values():
        if not liftoff.metrics_json:
            continue
        metrics = json.loads(liftoff.metrics_json)
        version = str(metrics.get("metrics_version", "liftoff-metrics-v1"))
        manifest = json.loads(liftoff.manifest_json or "{}")
        visit_code = str(manifest.get("visit_code", f"V{visit.visit_ordinal}"))
        for section, source in (("primary", "visible_result"), ("telemetry", "telemetry")):
            values = metrics.get(section, {})
            if not isinstance(values, dict):
                continue
            for metric, value in values.items():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                rows.append({
                    "participant_id": liftoff.participant_id,
                    "visit_ordinal": visit.visit_ordinal,
                    "visit_code": visit_code,
                    "session_id": liftoff.id,
                    "metric": metric,
                    "value": float(value),
                    "unit": _LIFTOFF_UNITS.get(metric, "native" if section == "telemetry" else "count"),
                    "metric_version": version,
                    "source": source,
                })
    return rows


def build_liftoff_completeness_grid(session: Session) -> list[dict[str, Any]]:
    participants = session.exec(select(Participant).order_by(Participant.id)).all()
    visits = session.exec(select(Visit)).all()
    attempts = session.exec(
        select(LiftoffSession).where(LiftoffSession.execution_purpose == "study").order_by(
            LiftoffSession.participant_id,
            LiftoffSession.visit_id,
            LiftoffSession.attempt_number,
        )
    ).all()
    visit_by_key = {(visit.participant_id, visit.visit_ordinal): visit for visit in visits}
    attempts_by_visit: dict[int, list[LiftoffSession]] = {}
    for attempt in attempts:
        attempts_by_visit.setdefault(attempt.visit_id, []).append(attempt)
    rows: list[dict[str, Any]] = []
    for participant in participants:
        for definition in protocol_visits():
            visit = visit_by_key.get((participant.id, definition.ordinal))
            visit_attempts = attempts_by_visit.get(visit.id, []) if visit is not None else []
            valid = next((row for row in visit_attempts if row.validity == "valid"), None)
            selected = valid or (visit_attempts[-1] if visit_attempts else None)
            if selected is None:
                state = "absent"
            elif selected.validity == "valid" and selected.hrv_measurement_id and selected.sync_quality == "good":
                state = "valid_good_sync"
            elif selected.validity == "valid" and selected.hrv_measurement_id and selected.sync_quality == "poor":
                state = "valid_poor_sync"
            elif selected.validity == "valid" and not selected.hrv_measurement_id:
                state = "valid_no_hrv"
            elif selected.validity == "partial":
                state = "partial"
            elif selected.validity == "invalid":
                state = "invalid"
            else:
                state = "pending"
            rows.append({
                "participant_id": participant.id,
                "visit_ordinal": definition.ordinal,
                "visit_code": definition.code,
                "scheduled_day": definition.scheduled_day,
                "attempt_count": len(visit_attempts),
                "session_id": valid.id if valid is not None else None,
                "status": selected.status if selected is not None else None,
                "validity": selected.validity if selected is not None else None,
                "metrics_present": bool(valid and valid.metrics_json),
                "hrv_measurement_id": valid.hrv_measurement_id if valid is not None else None,
                "sync_quality": valid.sync_quality if valid is not None else "missing",
                "present": valid is not None,
                "state": state,
            })
    return rows


def liftoff_provenance(session: Session) -> list[dict[str, Any]]:
    sessions = session.exec(
        select(LiftoffSession).where(LiftoffSession.execution_purpose == "study").order_by(
            LiftoffSession.participant_id,
            LiftoffSession.visit_id,
            LiftoffSession.attempt_number,
        )
    ).all()
    deviations = session.exec(select(LiftoffDeviation)).all()
    artifacts = session.exec(select(LiftoffArtifact)).all()
    deviations_by_session: dict[str, list[dict[str, Any]]] = {}
    for row in deviations:
        deviations_by_session.setdefault(row.session_id, []).append({
            "phase": row.phase,
            "code": row.code,
            "severity": row.severity,
            "disposition": row.disposition,
            "received_utc": row.received_utc.isoformat(),
        })
    artifacts_by_session: dict[str, list[dict[str, Any]]] = {}
    for row in artifacts:
        artifacts_by_session.setdefault(row.session_id, []).append({
            "kind": row.kind,
            "relative_path": row.relative_path,
            "sha256": row.sha256,
            "size_bytes": row.size_bytes,
        })
    return [{
        "session_id": row.id,
        "participant_id": row.participant_id,
        "visit_id": row.visit_id,
        "attempt_number": row.attempt_number,
        "status": row.status,
        "validity": row.validity,
        "manifest": json.loads(row.manifest_json),
        "configuration_sha256": row.configuration_sha256,
        "hrv_measurement_id": row.hrv_measurement_id,
        "hrv_file_sha256": row.hrv_file_sha256,
        "sync_quality": row.sync_quality,
        "deviations": deviations_by_session.get(row.id, []),
        "artifacts": artifacts_by_session.get(row.id, []),
    } for row in sessions]
