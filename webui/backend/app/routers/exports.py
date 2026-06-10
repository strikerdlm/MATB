"""Research context and reproducibility bundle export endpoints."""

from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends
from fastapi.responses import Response
from sqlmodel import Session, select

from app.completeness import build_completeness_grid
from app.db import get_session
from app.models import AnalysisResult, BayesResult, BlockProvenance, Participant, Visit
from app.routers.fits import collect_full_fit_rows
from app.routers.metrics import collect_metric_rows

router = APIRouter(prefix="/exports", tags=["exports"])

BUNDLE_VERSION = "research-bundle-v1"


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return str(value)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=_jsonable) + "\n"


def _safe_name(name: str) -> str:
    out = re.sub(r"[^A-Za-z0-9_.-]+", "-", name.strip()).strip("-")
    return out[:96] or "figure"


def _participants(session: Session) -> list[dict[str, Any]]:
    rows = session.exec(select(Participant).order_by(Participant.id)).all()
    return [{
        "id": p.id,
        "enrollment_date": p.enrollment_date.isoformat(),
        "sex": p.sex,
        "age_band": p.age_band,
        "notes": p.notes,
        "created_at": p.created_at.isoformat(),
    } for p in rows]


def _visits(session: Session) -> list[dict[str, Any]]:
    rows = session.exec(select(Visit).order_by(Visit.participant_id, Visit.visit_ordinal)).all()
    return [{
        "id": v.id,
        "participant_id": v.participant_id,
        "visit_ordinal": v.visit_ordinal,
        "scheduled_day": v.scheduled_day,
        "actual_date": v.actual_date.isoformat() if v.actual_date else None,
        "status": v.status,
    } for v in rows]


def _latest_analysis(session: Session) -> dict[str, Any] | None:
    row = session.exec(
        select(AnalysisResult).order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
    ).first()
    return json.loads(row.artifact_json) if row is not None else None


def _latest_bayes(session: Session) -> dict[str, Any] | None:
    row = session.exec(
        select(BayesResult)
        .where(BayesResult.status == "done")
        .order_by(BayesResult.finished_at.desc(), BayesResult.id.desc())  # type: ignore[arg-type]
    ).first()
    return json.loads(row.artifact_json) if row is not None and row.artifact_json else None


def _block_provenance(session: Session) -> list[dict[str, Any]]:
    rows = session.exec(select(BlockProvenance).order_by(BlockProvenance.block_id)).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        manifest = json.loads(row.manifest_json) if row.manifest_json else None
        summary = None
        if manifest is not None:
            from matb_integration.scenario_manifest import manifest_summary

            summary = manifest_summary(manifest)
        out.append({
            "block_id": row.block_id,
            "manifest_filename": row.manifest_filename,
            "manifest_sha256": row.manifest_sha256,
            "validation_status": row.validation_status,
            "validation_issues": json.loads(row.validation_issues_json or "[]"),
            "manifest_summary": summary,
            "created_at": row.created_at.isoformat(),
        })
    return out


def build_research_context(session: Session) -> dict[str, Any]:
    participants = _participants(session)
    tracker = build_completeness_grid(session)
    metrics = collect_metric_rows(session)
    fits = collect_full_fit_rows(session)
    analysis = _latest_analysis(session)
    bayes = _latest_bayes(session)
    provenance = _block_provenance(session)
    status_counts: dict[str, int] = {}
    for row in provenance:
        status = row["validation_status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "bundle_version": BUNDLE_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "participants": participants,
        "visits": _visits(session),
        "tracker": tracker,
        "metrics_long": metrics,
        "fits": fits,
        "analysis_latest": analysis,
        "bayes_latest": bayes,
        "block_provenance": provenance,
        "validation_status_counts": status_counts,
        "counts": {
            "participants": len(participants),
            "tracker_cells": len(tracker),
            "metrics_long": len(metrics),
            "fits": len(fits),
            "block_provenance": len(provenance),
        },
    }


def _caveats_md(context: dict[str, Any]) -> str:
    lines = ["# MATB Research Bundle Caveats", ""]
    analysis = context.get("analysis_latest")
    if analysis and analysis.get("caveats"):
        lines += ["## Analysis Caveats", ""]
        lines += [f"- {c}" for c in analysis["caveats"]]
        lines.append("")
    lines += ["## Validation Issues", ""]
    any_issue = False
    for row in context.get("block_provenance", []):
        for issue in row.get("validation_issues", []):
            any_issue = True
            lines.append(
                f"- Block {row['block_id']} [{row['validation_status']}]: "
                f"{issue.get('code')} - {issue.get('message')}"
            )
    if not any_issue:
        lines.append("- No block validation issues recorded.")
    lines.append("")
    return "\n".join(lines)


def _bundle_manifest(context: dict[str, Any], figures: list[dict[str, Any]]) -> dict[str, Any]:
    analysis = context.get("analysis_latest") or {}
    analysis_prov = analysis.get("provenance") or {}
    return {
        "bundle_version": BUNDLE_VERSION,
        "created_utc": context["created_utc"],
        "counts": context["counts"],
        "validation_status_counts": context["validation_status_counts"],
        "analysis_fingerprint": analysis_prov.get("fingerprint"),
        "figure_count": len(figures),
    }


@router.get("/research-context")
def research_context(session: Session = Depends(get_session)) -> dict[str, Any]:
    return build_research_context(session)


@router.post("/research-bundle")
def research_bundle(
    payload: dict[str, Any] | None = Body(default=None),
    session: Session = Depends(get_session),
) -> Response:
    payload = payload or {}
    figures = payload.get("figures") if isinstance(payload.get("figures"), list) else []
    context = build_research_context(session)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", _dumps(_bundle_manifest(context, figures)))
        zf.writestr("participants.json", _dumps(context["participants"]))
        zf.writestr("visits.json", _dumps(context["visits"]))
        zf.writestr("tracker.json", _dumps(context["tracker"]))
        zf.writestr("metrics_long.json", _dumps(context["metrics_long"]))
        zf.writestr("fits.json", _dumps(context["fits"]))
        zf.writestr("analysis_latest.json", _dumps(context["analysis_latest"]))
        zf.writestr("bayes_latest.json", _dumps(context["bayes_latest"]))
        zf.writestr("provenance/block_validations.json", _dumps(context["block_provenance"]))
        zf.writestr("caveats.md", _caveats_md(context))

        for row in context["block_provenance"]:
            if not row.get("manifest_sha256"):
                continue
            prov = session.exec(
                select(BlockProvenance).where(BlockProvenance.block_id == row["block_id"])
            ).first()
            if prov and prov.manifest_json:
                name = _safe_name(prov.manifest_filename or f"block-{prov.block_id}.manifest.json")
                zf.writestr(f"scenario_manifests/{name}", prov.manifest_json)

        for idx, fig in enumerate(figures, start=1):
            if not isinstance(fig, dict) or "option" not in fig:
                continue
            name = _safe_name(str(fig.get("name") or f"figure-{idx}"))
            zf.writestr(f"figures/{name}.option.json", _dumps(fig["option"]))

    filename = f"matb_research_bundle_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
