"""Optional Liftoff console component provider."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from app.db import get_engine
from app.hrv_task_client import HrvTaskClient
from app.liftoff_persistence import SQLModelLiftoffPersistence
from app.liftoff_runtime import LiftoffManager
from matb_integration.contracts import ComponentManifestV1
from matb_integration.liftoff.receiver import LiftoffUdpReceiver


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _artifact_root() -> Path:
    configured = os.getenv("MATB_LIFTOFF_OUTPUT_DIR")
    value = Path(configured) if configured else Path("exports") / "liftoff"
    return value if value.is_absolute() else _repo_root() / value


def _port() -> int:
    raw = os.getenv("MATB_LIFTOFF_PORT", "9001")
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError("MATB_LIFTOFF_PORT must be an integer in 1..65535") from exc
    if not 1 <= port <= 65535:
        raise ValueError("MATB_LIFTOFF_PORT must be an integer in 1..65535")
    return port


class LiftoffComponentProvider:
    manifest = ComponentManifestV1.create(
        component_id="matb-liftoff",
        component_version="0.1.0-alpha.1",
        component_kind="simulation",
        stability="experimental",
        distribution="optional",
        capabilities=("liftoff.analysis", "liftoff.collection", "liftoff.physiology"),
        requires=("matb-console",),
        python_entrypoint="app.liftoff_component:provider",
        license_expression="MIT",
    )
    model_modules = ("app.liftoff_models",)
    router_modules = (
        "app.routers.liftoff",
        "app.routers.liftoff_analysis",
        "app.routers.liftoff_metrics",
        "app.routers.liftoff_tracker",
    )

    async def startup(self, app: FastAPI) -> None:
        persistence = SQLModelLiftoffPersistence(get_engine())
        persistence.mark_orphaned_sessions()
        receiver = LiftoffUdpReceiver(
            host=os.getenv("MATB_LIFTOFF_HOST", "127.0.0.1"),
            port=_port(),
        )
        # Publish each allocation before the operation that can fail so the
        # lifespan's pre-registered provider cleanup can always reach it.
        app.state.liftoff_receiver = receiver
        await receiver.start()
        hrv_api_url = os.getenv("HRV_API_URL", "").strip()
        hrv_client = (
            HrvTaskClient(base_url=hrv_api_url, token=os.getenv("HRV_API_TOKEN", "").strip())
            if hrv_api_url
            else None
        )
        manager = LiftoffManager(
            artifact_root=_artifact_root(),
            receiver=receiver,
            persistence=persistence,
            hrv_client=hrv_client,
        )
        app.state.liftoff_manager = manager
        manager.start_capture()

    async def shutdown(self, app: FastAPI) -> None:
        manager = getattr(app.state, "liftoff_manager", None)
        receiver = getattr(app.state, "liftoff_receiver", None)
        errors: list[BaseException] = []
        try:
            if manager is not None:
                await manager.shutdown()
        except BaseException as exc:
            errors.append(exc)
        try:
            if receiver is not None:
                await receiver.stop()
        except BaseException as exc:
            errors.append(exc)
        finally:
            if hasattr(app.state, "liftoff_manager"):
                del app.state.liftoff_manager
            if hasattr(app.state, "liftoff_receiver"):
                del app.state.liftoff_receiver
        if errors:
            raise BaseExceptionGroup("Liftoff component shutdown failed", errors)


provider = LiftoffComponentProvider()
