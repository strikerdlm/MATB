"""Study-completeness grid endpoint."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlmodel import Session, select

from app.completeness import build_completeness_grid
from app.db import get_session
from app.models import Block, DepdfFit, Visit

router = APIRouter(tags=["tracker"])


@router.get("/tracker")
def tracker(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return build_completeness_grid(session)


@router.get("/block")
def block_detail(
    participant_id: str = Query(...),
    visit_ordinal: int = Query(...),
    workload_level: str = Query(...),
    session: Session = Depends(get_session),
):
    visit = session.exec(
        select(Visit).where(Visit.participant_id == participant_id,
                            Visit.visit_ordinal == visit_ordinal)
    ).first()
    if visit is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "visit not found")
    block = session.exec(
        select(Block).where(Block.visit_id == visit.id,
                            Block.workload_level == workload_level)
    ).first()
    if block is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "block not ingested")
    metrics = json.loads(block.metrics_json)
    metrics.pop("_raw_sysmon_rows", None)
    fit = session.exec(select(DepdfFit).where(DepdfFit.visit_id == visit.id)).first()
    fit_out = None
    if fit is not None:
        fit_out = {"g0": fit.g0, "p0": fit.p0, "tau0": fit.tau0,
                   "hcf_source": fit.hcf_source, "mwl_source": fit.mwl_source}
    return {"participant_id": participant_id, "visit_ordinal": visit_ordinal,
            "workload_level": workload_level, "metrics": metrics, "depdf_fit": fit_out}
