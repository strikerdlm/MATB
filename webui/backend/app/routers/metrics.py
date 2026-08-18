"""Tidy long-format metrics endpoint for visualization/statistics."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.db import get_session
from app.metrics_long import extract_long_metrics
from app.models import Block, Visit
from app.liftoff_models import LiftoffSession

router = APIRouter(tags=["metrics"])


def collect_metric_rows(session: Session, participant_id: str | None = None) -> list[dict[str, Any]]:
    query = select(Block, Visit).where(Block.visit_id == Visit.id)
    if participant_id is not None:
        query = query.where(Visit.participant_id == participant_id)
    rows: list[dict[str, Any]] = []
    for block, visit in session.exec(query).all():
        record = json.loads(block.metrics_json)
        for metric, value in extract_long_metrics(record):
            rows.append({
                "participant_id": visit.participant_id,
                "visit_ordinal": visit.visit_ordinal,
                "workload_level": block.workload_level,
                "metric": metric,
                "value": value,
            })
    return rows


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


@router.get("/metrics/long")
def metrics_long(
    participant_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return collect_metric_rows(session, participant_id)


@router.get("/metrics/liftoff/long")
def liftoff_metrics_long(
    participant_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return collect_liftoff_metric_rows(session, participant_id)
