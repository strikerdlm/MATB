"""Optional sUAS simulation console component provider."""

from __future__ import annotations

import math
import os
from pathlib import Path

from fastapi import FastAPI

from app.db import get_engine
from app.simulation_persistence import SQLModelSimulationPersistence
from app.simulation_runtime import SimulationManager
from matb_integration.contracts import ComponentManifestV1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _path_from_environment(name: str, default: Path) -> Path:
    configured = os.getenv(name)
    value = Path(configured) if configured else default
    return value if value.is_absolute() else _repo_root() / value


def _wall_time_scale() -> float:
    if os.getenv("MATB_SIMULATION_TEST_MODE") != "1":
        return 1.0
    raw = os.getenv("MATB_SIMULATION_WALL_TIME_SCALE", "1.0")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("MATB_SIMULATION_WALL_TIME_SCALE must be a finite decimal in [0.05, 1.0]") from exc
    if not math.isfinite(value) or not 0.05 <= value <= 1.0:
        raise ValueError("MATB_SIMULATION_WALL_TIME_SCALE must be a finite decimal in [0.05, 1.0]")
    return value


class SimulationComponentProvider:
    manifest = ComponentManifestV1.create(
        component_id="matb-suas",
        component_version="1.0.0-alpha.1",
        component_kind="simulation",
        stability="experimental",
        distribution="optional",
        capabilities=("simulation.suas", "simulation.websocket"),
        requires=("matb-console",),
        python_entrypoint="app.simulation_component:provider",
        license_expression="MIT",
    )
    model_modules = ("app.simulation_models",)
    router_modules = ("app.routers.simulation", "app.routers.geography")

    async def startup(self, app: FastAPI) -> None:
        persistence = SQLModelSimulationPersistence(get_engine())
        persistence.mark_orphaned_sessions()
        manager = SimulationManager(
            scenario_root=_path_from_environment("MATB_SIMULATION_SCENARIO_DIR", Path("scenarios") / "suas"),
            artifact_root=_path_from_environment("MATB_SIMULATION_OUTPUT_DIR", Path("exports") / "simulation"),
            persistence=persistence,
            wall_time_scale=_wall_time_scale(),
        )
        app.state.simulation_manager = manager

    async def shutdown(self, app: FastAPI) -> None:
        from app.routers.geography import stop_jobs
        manager = getattr(app.state, "simulation_manager", None)
        try:
            if manager is not None:
                await manager.shutdown()
        finally:
            await stop_jobs()


provider = SimulationComponentProvider()
