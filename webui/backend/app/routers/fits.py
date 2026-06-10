"""DEPDF fits endpoint. Curve points are computed server-side via the suhir
package so the model math stays single-sourced (no Eq-5.16 duplication in TS)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.db import get_session
from app.models import DepdfFit, Visit

router = APIRouter(tags=["fits"])

N_CURVE_POINTS = 51
R_MAX = 3.0  # Suhir: effects saturate beyond G/G0 ~ 3


def collect_fit_rows(session: Session) -> list[dict[str, Any]]:
    query = select(DepdfFit, Visit).where(DepdfFit.visit_id == Visit.id)
    return [
        {"participant_id": fit.participant_id, "visit_ordinal": visit.visit_ordinal,
         "g0": fit.g0, "p0": fit.p0, "tau0": fit.tau0}
        for fit, visit in session.exec(query).all()
    ]


def collect_full_fit_rows(session: Session, participant_id: str | None = None) -> list[dict[str, Any]]:
    query = select(DepdfFit, Visit).where(DepdfFit.visit_id == Visit.id)
    if participant_id is not None:
        query = query.where(DepdfFit.participant_id == participant_id)
    out: list[dict[str, Any]] = []
    for fit, visit in session.exec(query).all():
        out.append({
            "participant_id": fit.participant_id,
            "visit_ordinal": visit.visit_ordinal,
            "g0": fit.g0, "p0": fit.p0, "tau0": fit.tau0,
            "hcf_source": fit.hcf_source, "mwl_source": fit.mwl_source,
            "hcf_value": fit.hcf_value,
            "curve": _curve(fit.p0, fit.hcf_value if fit.hcf_source == "screen" else 1.0),
        })
    out.sort(key=lambda f: (f["participant_id"], f["visit_ordinal"]))
    return out


def _curve(p0: float, f_ratio: float = 1.0) -> list[dict[str, float]]:
    from matb_integration.suhir.depdf import p_bar

    points: list[dict[str, float]] = []
    for i in range(N_CURVE_POINTS):
        r = 1.0 + (R_MAX - 1.0) * i / (N_CURVE_POINTS - 1)
        points.append({"r": round(r, 4), "p": p0 * p_bar(r ** 2, f_ratio ** 2)})
    return points


@router.get("/fits")
def list_fits(
    participant_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return collect_full_fit_rows(session, participant_id)
