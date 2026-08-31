"""Optional Liftoff long-format metrics endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.db import get_session
from app.liftoff_research import collect_liftoff_metric_rows

router = APIRouter(tags=["liftoff"])


@router.get("/metrics/liftoff/long")
def liftoff_metrics_long(
    participant_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return collect_liftoff_metric_rows(session, participant_id)
