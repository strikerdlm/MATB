"""Research context and reproducibility bundle export endpoints."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections.abc import Iterator
from datetime import datetime, timezone
from tempfile import SpooledTemporaryFile
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)
from sqlmodel import Session, select

from app.completeness import build_completeness_grid
from app.completeness import build_liftoff_completeness_grid
from app.components import is_component_active
from app.db import get_session
from app.models import AnalysisResult, BayesResult, BlockProvenance, Participant, Visit
from app.routers.analysis import artifact_data_fingerprint
from app.routers.fits import collect_fit_rows, collect_full_fit_rows
from app.routers.metrics import collect_liftoff_metric_rows, collect_metric_rows

router = APIRouter(prefix="/exports", tags=["exports"])

BUNDLE_VERSION = "research-bundle-v1"
_LIFTOFF_ANALYSIS_VERSION = "liftoff-analysis-v1"
MAX_BUNDLE_FIGURES = 16
MAX_FIGURE_OPTION_BYTES = 256 * 1024
MAX_TOTAL_FIGURE_OPTION_BYTES = 4 * 1024 * 1024


def _safe_name(name: str) -> str:
    out = re.sub(r"[^A-Za-z0-9_.-]+", "-", name.strip()).strip("-")
    return out[:96] or "figure"


def _finite_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


class ResearchFigureV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str | None = Field(default=None, max_length=96)
    option: dict[str, JsonValue]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or value != value.strip()):
            raise ValueError("figure name must be non-empty and trimmed")
        return value

    @field_validator("option")
    @classmethod
    def validate_option(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        try:
            size = len(_finite_json_bytes(value))
        except (TypeError, ValueError) as exc:
            raise ValueError("figure option must contain finite JSON values") from exc
        if size > MAX_FIGURE_OPTION_BYTES:
            raise ValueError(
                f"figure option exceeds {MAX_FIGURE_OPTION_BYTES} UTF-8 JSON bytes"
            )
        return value


class ResearchBundleRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    hcf_derivation_id: str | None = None

    figures: list[ResearchFigureV1] = Field(
        default_factory=list,
        max_length=MAX_BUNDLE_FIGURES,
    )

    @model_validator(mode="after")
    def validate_figure_set(self) -> "ResearchBundleRequestV1":
        total = sum(len(_finite_json_bytes(figure.option)) for figure in self.figures)
        if total > MAX_TOTAL_FIGURE_OPTION_BYTES:
            raise ValueError(
                "combined figure options exceed the research-bundle limit"
            )
        names = [
            _safe_name(figure.name or f"figure-{index}")
            for index, figure in enumerate(self.figures, start=1)
        ]
        if len(names) != len(set(names)):
            raise ValueError("figure names must be unique after filename normalization")
        return self


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return str(value)


def _dumps(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=_jsonable,
        allow_nan=False,
    ) + "\n"


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


def _latest_analysis(
    session: Session,
    current_data_fingerprint: str,
) -> tuple[dict[str, Any] | None, str]:
    from matb_integration.analysis.stats import ENGINE_VERSION

    row = session.exec(
        select(AnalysisResult)
        .where(
            AnalysisResult.engine_version == ENGINE_VERSION,
            AnalysisResult.fingerprint == current_data_fingerprint,
        )
        .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
    ).first()
    if row is not None:
        artifact = json.loads(row.artifact_json)
        if artifact_data_fingerprint(artifact) == current_data_fingerprint:
            return artifact, "current"
        return None, "invalid_artifact_omitted"
    previous = session.exec(
        select(AnalysisResult)
        .where(AnalysisResult.engine_version == ENGINE_VERSION)
        .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
    ).first()
    return (None, "stale_artifact_omitted") if previous is not None else (None, "not_run")


def _latest_liftoff_analysis(session: Session) -> dict[str, Any] | None:
    row = session.exec(
        select(AnalysisResult)
        .where(AnalysisResult.engine_version == _LIFTOFF_ANALYSIS_VERSION)
        .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
    ).first()
    return json.loads(row.artifact_json) if row is not None else None


def _latest_bayes(
    session: Session,
    current_data_fingerprint: str,
) -> tuple[dict[str, Any] | None, str]:
    from matb_integration.analysis.stats.bayes import BAYES_VERSION

    rows = session.exec(
        select(BayesResult)
        .where(
            BayesResult.status == "done",
            BayesResult.bayes_version == BAYES_VERSION,
        )
        .order_by(BayesResult.finished_at.desc(), BayesResult.id.desc())  # type: ignore[arg-type]
    ).all()
    invalid_artifact = False
    for row in rows:
        if not row.artifact_json:
            invalid_artifact = True
            continue
        try:
            artifact = json.loads(row.artifact_json)
        except json.JSONDecodeError:
            invalid_artifact = True
            continue
        if artifact_data_fingerprint(artifact) == current_data_fingerprint:
            return artifact, "current"
    if rows:
        return None, "invalid_artifact_omitted" if invalid_artifact else "stale_artifact_omitted"
    return None, "not_run"


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


def _liftoff_provenance(session: Session) -> list[dict[str, Any]]:
    from app.liftoff_research import liftoff_provenance

    return liftoff_provenance(session)


def build_research_context(session: Session, hcf_derivation_id: str | None = None) -> dict[str, Any]:
    from matb_integration.analysis.stats import fingerprint

    participants = _participants(session)
    tracker = build_completeness_grid(session)
    metrics = collect_metric_rows(session)
    analysis_fit_rows = collect_fit_rows(session)
    current_data_fingerprint = fingerprint(metrics, analysis_fit_rows)
    fits = collect_full_fit_rows(session, hcf_derivation_id=hcf_derivation_id)
    analysis, analysis_status = _latest_analysis(session, current_data_fingerprint)
    bayes, bayes_status = _latest_bayes(session, current_data_fingerprint)
    provenance = _block_provenance(session)
    liftoff_active = is_component_active("matb-liftoff")
    liftoff_tracker = build_liftoff_completeness_grid(session) if liftoff_active else []
    liftoff_metrics = collect_liftoff_metric_rows(session) if liftoff_active else []
    liftoff_provenance = _liftoff_provenance(session) if liftoff_active else []
    liftoff_analysis = _latest_liftoff_analysis(session) if liftoff_active else None
    status_counts: dict[str, int] = {}
    for row in provenance:
        status = row["validation_status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "scope": "legacy_block_visit_grid_and_inferential_snapshots",
        "planned_analysis_endpoint": "/study/analyses",
        "full_study_restoration": False,
        "bundle_version": BUNDLE_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "current_data_fingerprint": current_data_fingerprint,
        "participants": participants,
        "visits": _visits(session),
        "tracker": tracker,
        "metrics_long": metrics,
        "fits": fits,
        "analysis_latest": analysis,
        "analysis_status": analysis_status,
        "bayes_latest": bayes,
        "bayes_status": bayes_status,
        "block_provenance": provenance,
        "liftoff_tracker": liftoff_tracker,
        "liftoff_metrics_long": liftoff_metrics,
        "liftoff_provenance": liftoff_provenance,
        "liftoff_analysis_latest": liftoff_analysis,
        "validation_status_counts": status_counts,
        "counts": {
            "participants": len(participants),
            "tracker_cells": len(tracker),
            "metrics_long": len(metrics),
            "fits": len(fits),
            "block_provenance": len(provenance),
            "liftoff_tracker_cells": len(liftoff_tracker),
            "liftoff_metrics_long": len(liftoff_metrics),
            "liftoff_sessions": len(liftoff_provenance),
        },
    }


def _caveats_md(context: dict[str, Any]) -> str:
    lines = ["# MATB Research Bundle Caveats", ""]
    analysis = context.get("analysis_latest")
    if analysis and analysis.get("caveats"):
        lines += ["## Analysis Caveats", ""]
        lines += [f"- {c}" for c in analysis["caveats"]]
        lines.append("")
    if context.get("analysis_status") not in {"current", "not_run"}:
        lines.append(
            f"- Frequentist inference omitted: {context['analysis_status']}."
        )
    if context.get("bayes_status") not in {"current", "not_run"}:
        lines.append(f"- Bayesian inference omitted: {context['bayes_status']}.")
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


def _bundle_manifest(
    context: dict[str, Any], figures: list[ResearchFigureV1]
) -> dict[str, Any]:
    analysis = context.get("analysis_latest") or {}
    analysis_prov = analysis.get("provenance") or {}
    return {
        "bundle_version": BUNDLE_VERSION,
        "created_utc": context["created_utc"],
        "counts": context["counts"],
        "validation_status_counts": context["validation_status_counts"],
        "analysis_fingerprint": analysis_prov.get("fingerprint"),
        "current_data_fingerprint": context["current_data_fingerprint"],
        "analysis_status": context["analysis_status"],
        "bayes_status": context["bayes_status"],
        "figure_count": len(figures),
    }


@router.get("/research-context")
def research_context(session: Session = Depends(get_session), hcf_derivation_id: str | None = None) -> dict[str, Any]:
    return build_research_context(session, hcf_derivation_id=hcf_derivation_id)


@router.post("/research-bundle")
def research_bundle(
    payload: ResearchBundleRequestV1 | None = Body(default=None),
    session: Session = Depends(get_session),
) -> Response:
    figures = [] if payload is None else payload.figures
    context = build_research_context(session, hcf_derivation_id=payload.hcf_derivation_id if payload else None)
    buf = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
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
        zf.writestr("liftoff/tracker.json", _dumps(context["liftoff_tracker"]))
        zf.writestr("liftoff/metrics_long.json", _dumps(context["liftoff_metrics_long"]))
        zf.writestr("liftoff/provenance.json", _dumps(context["liftoff_provenance"]))
        zf.writestr("liftoff/analysis_latest.json", _dumps(context["liftoff_analysis_latest"]))
        zf.writestr("caveats.md", _caveats_md(context))

        for row in context["block_provenance"]:
            if not row.get("manifest_sha256"):
                continue
            prov = session.exec(
                select(BlockProvenance).where(BlockProvenance.block_id == row["block_id"])
            ).first()
            if prov and prov.manifest_json:
                exact_bytes = prov.manifest_json.encode("utf-8")
                observed_sha = hashlib.sha256(exact_bytes).hexdigest()
                if observed_sha != prov.manifest_sha256:
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "code": "stored_manifest_integrity_failure",
                            "message": f"manifest bytes for block {prov.block_id} do not match recorded SHA-256",
                        },
                    )
                original = _safe_name(
                    prov.manifest_filename or f"block-{prov.block_id}.manifest.json"
                )
                # Prefix the database identity so same-named source manifests
                # from different visits cannot collide inside the ZIP.
                name = f"block-{prov.block_id}-{original}"
                zf.writestr(f"scenario_manifests/{name}", exact_bytes)

        for idx, fig in enumerate(figures, start=1):
            name = _safe_name(fig.name or f"figure-{idx}")
            zf.writestr(f"figures/{name}.option.json", _dumps(fig.option))

    filename = f"matb_research_bundle_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.zip"

    def chunks() -> Iterator[bytes]:
        try:
            buf.seek(0)
            while chunk := buf.read(64 * 1024):
                yield chunk
        finally:
            buf.close()

    return StreamingResponse(
        chunks(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
