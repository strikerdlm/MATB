"""Deterministic experiment compilation for the visual designer."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from matb_integration.contracts import ExperimentSpecV1
from matb_integration.experiment_compiler import ExperimentCompileError, compile_experiment_spec


router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("/catalog")
def experiment_catalog(request: Request) -> dict[str, Any]:
    from app.experiment_catalog import EXPERIMENTS

    active = {item.component_id for item in request.app.state.component_registry.manifests()}
    return {"catalog_version": "1.0", "experiments": [
        {**item, "supported_modes": ["practice", "study"],
         "component_available": item["component_id"] is None or item["component_id"] in active,
         "unavailable_reason": None if item["component_id"] is None or item["component_id"] in active
         else "component_not_enabled"}
        for item in EXPERIMENTS
    ]}


def _source_dirty_from_environment() -> bool | None:
    raw = os.getenv("MATB_SOURCE_DIRTY")
    if raw is None or raw.strip().lower() == "unknown":
        return None
    normalized = raw.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise HTTPException(
        status_code=500,
        detail={
            "code": "invalid_source_provenance_configuration",
            "message": "MATB_SOURCE_DIRTY must be true, false, unknown, or unset",
        },
    )


class CompiledExperimentView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_text: str
    manifest: dict[str, Any]


@router.post("/compile", response_model=CompiledExperimentView)
def compile_experiment(spec: ExperimentSpecV1) -> CompiledExperimentView:
    try:
        compiled = compile_experiment_spec(
            spec,
            source_commit=os.getenv("MATB_SOURCE_COMMIT", "unavailable"),
            source_dirty=_source_dirty_from_environment(),
        )
    except ExperimentCompileError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "experiment_compile_error", "message": str(exc)},
        ) from exc
    return CompiledExperimentView(
        scenario_text=compiled.scenario_text,
        manifest=compiled.manifest,
    )
