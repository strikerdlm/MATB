"""MATB Research Console backend (Phase 1A)."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import get_engine, init_db
from app.simulation_persistence import SQLModelSimulationPersistence
from app.simulation_runtime import SimulationManager


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    manager = SimulationManager(
        scenario_root=_repo_root() / "scenarios" / "suas",
        artifact_root=_simulation_artifact_root(),
        persistence=SQLModelSimulationPersistence(get_engine()),
    )
    app.state.simulation_manager = manager
    try:
        yield
    finally:
        await manager.shutdown()


app = FastAPI(title="MATB Research Console", version="0.1.0", lifespan=lifespan)
app.state.frontend_origins = _FRONTEND_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_FRONTEND_ORIGINS),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import analysis, exports, fits, ingest, metrics, participants, screen, simulation, tracker  # noqa: E402

app.include_router(participants.router)
app.include_router(ingest.router)
app.include_router(tracker.router)
app.include_router(metrics.router)
app.include_router(fits.router)
app.include_router(analysis.router)
app.include_router(screen.router)
app.include_router(exports.router)
app.include_router(simulation.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
