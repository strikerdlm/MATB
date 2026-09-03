"""Optional native Polar H10 component provider."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from app.db import get_engine
from app.physiology_runtime import PolarCaptureManager
from matb_integration.contracts import ComponentManifestV1
from matb_integration.physiology.transport import PolarBleakTransport


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class PhysiologyComponentProvider:
    manifest = ComponentManifestV1.create(
        component_id="matb-physiology",
        component_version="0.1.0-alpha.1",
        component_kind="physiology",
        stability="experimental",
        distribution="optional",
        capabilities=(
            "physiology.polar-h10-live",
            "physiology.hrv-descriptors",
            "physiology.parquet-artifacts",
        ),
        requires=("matb-contracts", "matb-research", "matb-console"),
        python_entrypoint="app.physiology_component:provider",
        license_expression="MIT AND LicenseRef-Polar-SDK",
    )
    model_modules = ("app.physiology_models",)
    router_modules = ("app.routers.physiology",)

    async def startup(self, app: FastAPI) -> None:
        configured = os.getenv("MATB_PHYSIOLOGY_DIR")
        root = Path(configured).expanduser() if configured else _repo_root() / "exports" / "physiology"
        if not root.is_absolute():
            root = _repo_root() / root
        app.state.polar_manager = PolarCaptureManager(
            engine=get_engine(), artifact_root=root.resolve(), transport=PolarBleakTransport()
        )
        await app.state.polar_manager.startup()

    async def shutdown(self, app: FastAPI) -> None:
        manager = getattr(app.state, "polar_manager", None)
        if manager is not None:
            await manager.shutdown()
            del app.state.polar_manager


provider = PhysiologyComponentProvider()
