"""MATB Research Console backend (Phase 1A)."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
from urllib.parse import urlsplit
import asyncio
import json
import math

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db import get_engine, init_db
from app.hrv_task_client import HrvTaskClient
from app.liftoff_persistence import SQLModelLiftoffPersistence
from app.liftoff_runtime import LiftoffManager
from app.simulation_persistence import SQLModelSimulationPersistence
from app.simulation_runtime import SimulationManager
from app.study_models import ensure_study_binding
from app.study_protocol import selected_protocol
from app.websocket.simulation import HubConflict
from matb_integration.liftoff.receiver import LiftoffUdpReceiver


_DEFAULT_FRONTEND_ORIGINS = (
    "http://localhost:3000",
    "http://localhost:3100",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3100",
)


def _parse_frontend_origins(raw: str | None) -> frozenset[str]:
    """Parse exact browser origins and reject credentials/path/wildcards."""

    if raw is None:
        return frozenset(_DEFAULT_FRONTEND_ORIGINS)
    entries = raw.split(",")
    if not entries or any(not entry.strip() for entry in entries):
        raise ValueError("MATB_FRONTEND_ORIGINS must not contain empty entries")
    origins: set[str] = set()
    for entry in entries:
        origin = entry.strip()
        if origin == "*" or any(character.isspace() for character in origin):
            raise ValueError("MATB_FRONTEND_ORIGINS must contain exact http(s) origins")
        try:
            parsed = urlsplit(origin)
            hostname = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise ValueError("MATB_FRONTEND_ORIGINS contains an invalid origin") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.geturl() != origin
            or parsed.netloc.endswith(":")
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError(
                "MATB_FRONTEND_ORIGINS entries must be exact http:// or https:// origins "
                "without credentials, paths, queries, fragments, or wildcards"
            )
        origins.add(origin)
    return frozenset(origins)


_FRONTEND_ORIGINS = _parse_frontend_origins(os.getenv("MATB_FRONTEND_ORIGINS"))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _simulation_artifact_root() -> Path:
    configured = os.getenv("MATB_SIMULATION_OUTPUT_DIR")
    value = Path(configured) if configured else Path("exports") / "simulation"
    return value if value.is_absolute() else _repo_root() / value


def _simulation_scenario_root() -> Path:
    configured = os.getenv("MATB_SIMULATION_SCENARIO_DIR")
    value = Path(configured) if configured else Path("scenarios") / "suas"
    return value if value.is_absolute() else _repo_root() / value


def _liftoff_artifact_root() -> Path:
    configured = os.getenv("MATB_LIFTOFF_OUTPUT_DIR")
    value = Path(configured) if configured else Path("exports") / "liftoff"
    return value if value.is_absolute() else _repo_root() / value


def _liftoff_port() -> int:
    raw = os.getenv("MATB_LIFTOFF_PORT", "9001")
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError("MATB_LIFTOFF_PORT must be an integer in 1..65535") from exc
    if not 1 <= port <= 65535:
        raise ValueError("MATB_LIFTOFF_PORT must be an integer in 1..65535")
    return port


def _simulation_wall_time_scale() -> float:
    """Return an accelerated wall-clock factor only for explicit test mode."""

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_study_binding(get_engine(), selected_protocol())
    liftoff_persistence = SQLModelLiftoffPersistence(get_engine())
    liftoff_persistence.mark_orphaned_sessions()
    liftoff_receiver = LiftoffUdpReceiver(
        host=os.getenv("MATB_LIFTOFF_HOST", "127.0.0.1"),
        port=_liftoff_port(),
    )
    await liftoff_receiver.start()
    hrv_api_url = os.getenv("HRV_API_URL", "").strip()
    hrv_client = (
        HrvTaskClient(
            base_url=hrv_api_url,
            token=os.getenv("HRV_API_TOKEN", "").strip(),
        )
        if hrv_api_url
        else None
    )
    liftoff_manager = LiftoffManager(
        artifact_root=_liftoff_artifact_root(),
        receiver=liftoff_receiver,
        persistence=liftoff_persistence,
        hrv_client=hrv_client,
    )
    liftoff_manager.start_capture()
    app.state.liftoff_manager = liftoff_manager
    persistence = SQLModelSimulationPersistence(get_engine())
    persistence.mark_orphaned_sessions()
    manager = SimulationManager(
        scenario_root=_simulation_scenario_root(),
        artifact_root=_simulation_artifact_root(),
        persistence=persistence,
        wall_time_scale=_simulation_wall_time_scale(),
    )
    app.state.simulation_manager = manager
    try:
        yield
    finally:
        await liftoff_manager.shutdown()
        await liftoff_receiver.stop()
        await manager.shutdown()


app = FastAPI(title="MATB Research Console", version="0.1.0", lifespan=lifespan)
app.state.frontend_origins = _FRONTEND_ORIGINS


@app.exception_handler(RequestValidationError)
async def request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Use one stable error shape for all JSON/form validation failures."""

    del request
    fields = [
        ".".join(str(part) for part in error.get("loc", ()))
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "code": "invalid_request",
                "message": "request validation failed",
                "context": {"fields": fields},
            }
        },
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_FRONTEND_ORIGINS),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import analysis, bundles, exports, fits, ingest, liftoff, metrics, participants, screen, simulation, study, tracker  # noqa: E402

app.include_router(participants.router)
app.include_router(ingest.router)
app.include_router(bundles.router)
app.include_router(tracker.router)
app.include_router(metrics.router)
app.include_router(fits.router)
app.include_router(analysis.router)
app.include_router(screen.router)
app.include_router(exports.router)
app.include_router(simulation.router)
app.include_router(study.router)
app.include_router(liftoff.router)


@app.websocket("/simulation/sessions/{session_id}/stream")
async def simulation_stream(websocket: WebSocket, session_id: str) -> None:
    """Serve one ordered controller or observer stream for a session."""

    origin = websocket.headers.get("origin")
    if origin is None or origin not in websocket.app.state.frontend_origins:
        await websocket.close(code=4403)
        return
    manager = getattr(websocket.app.state, "simulation_manager", None)
    if manager is None:
        await websocket.close(code=4503)
        return
    try:
        after_sequence = int(websocket.query_params.get("after_sequence", "0"))
    except (TypeError, ValueError):
        await websocket.close(code=4400)
        return
    if after_sequence < 0:
        await websocket.close(code=4400)
        return
    lease = websocket.query_params.get("lease")
    role = "controller" if lease else "observer"
    controller_handshake_pending = False
    subscription = None
    try:
        if lease:
            await manager.controller_connected(session_id, lease)
            controller_handshake_pending = True
        else:
            await manager.view(session_id)
        subscription = await manager.hub.subscribe(
            session_id,
            role=role,
            identity=lease if role == "controller" else None,
        )
        if lease:
            await manager.controller_stream_established(session_id, lease)
            controller_handshake_pending = False
        # Subscribe before taking the snapshot. Any event published during
        # snapshot capture is then queued behind the snapshot boundary rather
        # than being lost between an old sequence and the first live frame.
        initial = await manager.snapshot_envelope(session_id, after_sequence=after_sequence)
    except HubConflict:
        if lease and controller_handshake_pending:
            await manager.controller_stream_failed(session_id, lease)
        await websocket.close(code=4409)
        return
    except Exception:
        # Do not expose lease/hash/path details during the pre-accept phase.
        if lease and controller_handshake_pending:
            try:
                await manager.controller_stream_failed(session_id, lease)
            except Exception:
                pass
        if subscription is not None:
            await manager.hub.unsubscribe(subscription)
        await websocket.close(code=4403 if lease else 4404)
        return

    await websocket.accept()
    try:
        await websocket.send_json(initial.as_json())
        receive_task = asyncio.create_task(websocket.receive())
        queue_task = asyncio.create_task(subscription.queue.get())
        closed_task = asyncio.create_task(subscription._closed.wait())
        while True:
            done, _ = await asyncio.wait(
                {receive_task, queue_task, closed_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if closed_task in done:
                if not websocket.client_state.value == "DISCONNECTED":
                    await websocket.close(code=subscription.closed_code or 4408)
                break
            if queue_task in done:
                envelope = queue_task.result()
                await websocket.send_json(envelope.as_json())
                queue_task = asyncio.create_task(subscription.queue.get())
            if receive_task in done:
                message = receive_task.result()
                if message.get("type") == "websocket.disconnect":
                    break
                raw = message.get("text")
                if raw is None:
                    await websocket.close(code=4400)
                    break
                try:
                    payload = json.loads(raw)
                except (TypeError, ValueError, json.JSONDecodeError):
                    await websocket.close(code=4400)
                    break
                if payload != {"kind": "ping"}:
                    await websocket.close(code=4400)
                    break
                await websocket.send_json({"kind": "pong"})
                receive_task = asyncio.create_task(websocket.receive())
    except WebSocketDisconnect:
        pass
    finally:
        for task in (receive_task, queue_task, closed_task):
            if not task.done():
                task.cancel()
        await manager.hub.unsubscribe(subscription)
        try:
            if role == "controller":
                await manager.controller_disconnected(session_id, lease or "")
            else:
                await manager.observer_disconnected(session_id)
        except Exception:
            # A terminal session or an already-closed process needs no further
            # lifecycle mutation; the durable session state remains authoritative.
            pass


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
