"""Optional Liftoff completeness endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.liftoff_research import build_liftoff_completeness_grid

router = APIRouter(tags=["liftoff"])


@router.get("/tracker/liftoff")
def liftoff_tracker(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return build_liftoff_completeness_grid(session)
