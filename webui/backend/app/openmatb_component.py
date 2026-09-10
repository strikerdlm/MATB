"""Optional classic OpenMATB controller component."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from app.db import get_engine
from app.openmatb_runtime import OpenMatbManager
from matb_integration.contracts import ComponentManifestV1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class OpenMatbComponentProvider:
    manifest = ComponentManifestV1.create(
        component_id="matb-openmatb", component_version="1.0.0-alpha.1",
        component_kind="simulation", stability="experimental", distribution="optional",
        capabilities=(
            "openmatb.native-control",
            "openmatb.presets",
            "openmatb.participant-instructions",
            "openmatb.visual-profiles",
            "openmatb.visual-preview",
        ),
        requires=("matb-console", "matb-runtime"), python_entrypoint="app.openmatb_component:provider",
        license_expression="CECILL-2.1",
    )
    model_modules = ("app.openmatb_models",)
    router_modules = ("app.routers.openmatb",)

    async def startup(self, app: FastAPI) -> None:
        root = _repo_root()
        configured = os.getenv("MATB_OPENMATB_OUTPUT_DIR")
        artifact_root = Path(configured) if configured else root / "exports" / "openmatb-controlled"
        if not artifact_root.is_absolute():
            artifact_root = root / artifact_root
        python = os.getenv("MATB_OPENMATB_PYTHON")
        app.state.openmatb_manager = OpenMatbManager(
            engine=get_engine(), repo_root=root, artifact_root=artifact_root,
            python_executable=Path(python) if python else None,
        )
        app.state.openmatb_manager.schedule_evidence_processing()

    async def shutdown(self, app: FastAPI) -> None:
        runtime = getattr(app.state, "openmatb_manager", None)
        if runtime is not None:
            await runtime.shutdown()
            del app.state.openmatb_manager


provider = OpenMatbComponentProvider()
