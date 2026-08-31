"""Deterministic experiment compilation for the visual designer."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from matb_integration.contracts import ExperimentSpecV1
from matb_integration.experiment_compiler import ExperimentCompileError, compile_experiment_spec


router = APIRouter(prefix="/experiments", tags=["experiments"])


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
