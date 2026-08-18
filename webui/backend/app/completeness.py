"""Derive the expected-vs-actual OpenMATB completeness grid.

The expected grid = enrolled participants × active protocol visits × 3 workload levels.
Each cell is present (a Block row exists for that visit+level) or
expected-but-absent. Nothing about missingness is stored; it is derived.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.constants import WORKLOAD_LEVELS, protocol_visits
from app.liftoff_models import LiftoffSession
from app.models import Block, Participant, Visit


def build_completeness_grid(session: Session) -> list[dict[str, Any]]:
    participants = session.exec(select(Participant).order_by(Participant.id)).all()
    visits = session.exec(select(Visit)).all()
    blocks = session.exec(select(Block)).all()

    visit_by_key = {(v.participant_id, v.visit_ordinal): v for v in visits}
    present_levels: dict[int, set[str]] = {}
    for b in blocks:
        present_levels.setdefault(b.visit_id, set()).add(b.workload_level)

    grid: list[dict[str, Any]] = []
    for p in participants:
        for definition in protocol_visits():
            visit = visit_by_key.get((p.id, definition.ordinal))
            have = present_levels.get(visit.id, set()) if visit else set()
            for level in WORKLOAD_LEVELS:
                grid.append({
                    "participant_id": p.id,
                    "visit_ordinal": definition.ordinal,
                    "scheduled_day": definition.scheduled_day,
                    "workload_level": level,
                    "present": level in have,
                })
    return grid


def build_liftoff_completeness_grid(session: Session) -> list[dict[str, Any]]:
    participants = session.exec(select(Participant).order_by(Participant.id)).all()
    visits = session.exec(select(Visit)).all()
    attempts = session.exec(
        select(LiftoffSession).order_by(
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
