"""Study-completeness grid endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.completeness import build_completeness_grid
from app.db import get_session

router = APIRouter(tags=["tracker"])


@router.get("/tracker")
def tracker(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return build_completeness_grid(session)
