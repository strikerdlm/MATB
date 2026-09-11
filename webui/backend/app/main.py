"""Composable MATB Research Console backend."""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from importlib import import_module
import os
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.components import configure_components
from app.body_limits import ScientificRequestBodyLimitMiddleware
from app.db import get_engine, init_db
from app.request_security import LoopbackRequestSecurityMiddleware
from app.study_models import ensure_study_binding
from app.study_protocol import selected_protocol


_DEFAULT_FRONTEND_ORIGINS = (
    "http://localhost:3000",
    "http://localhost:3100",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3100",
)
_DEFAULT_ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "testserver"})


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


def _parse_allowed_hosts(raw: str | None) -> frozenset[str]:
    if raw is None:
        return _DEFAULT_ALLOWED_HOSTS
    values = raw.split(",")
    if any(not value.strip() for value in values):
        raise ValueError("MATB_ALLOWED_HOSTS must not contain empty entries")
    hosts = set(_DEFAULT_ALLOWED_HOSTS)
    for value in values:
        host = value.strip().lower()
        if (
            host == "*"
            or any(character.isspace() for character in host)
            or ":" in host
            or "/" in host
            or "@" in host
        ):
            raise ValueError("MATB_ALLOWED_HOSTS must contain exact hostnames without ports")
        hosts.add(host)
    return frozenset(hosts)


def _parse_api_token(raw: str | None) -> str | None:
    if raw is None:
        return None
    if raw != raw.strip() or len(raw) < 32 or any(character.isspace() for character in raw):
        raise ValueError("MATB_API_TOKEN must be at least 32 non-whitespace characters")
    return raw


_FRONTEND_ORIGINS = _parse_frontend_origins(os.getenv("MATB_FRONTEND_ORIGINS"))
_ALLOWED_HOSTS = _parse_allowed_hosts(os.getenv("MATB_ALLOWED_HOSTS"))
def _configured_api_token():
    from pathlib import Path
    token_file = os.getenv("MATB_API_TOKEN_FILE")
    # A restored workspace has new local authority; do not inherit the old token.
    return Path(token_file).read_text(encoding="utf-8").strip() if token_file else os.getenv("MATB_API_TOKEN")


_API_TOKEN = _parse_api_token(_configured_api_token())
_COMPONENT_REGISTRY, _COMPONENT_PROVIDERS = configure_components()


@asynccontextmanager
async def lifespan(app: FastAPI):
    model_modules = tuple(
        module
        for provider in _COMPONENT_PROVIDERS
        for module in provider.model_modules
    )
    from app.routers.analysis import (
        acquire_backend_instance_lease,
        reconcile_interrupted_bayes_jobs,
        release_backend_instance_lease,
        shutdown_bayes_jobs,
    )

    engine = get_engine()
    acquire_backend_instance_lease(engine)
    release_lease = True
    try:
        init_db(component_model_modules=model_modules)
        from app.station_resources import recover
        recover(engine)
        ensure_study_binding(engine, selected_protocol())
        reconcile_interrupted_bayes_jobs(engine)
        from app.evidence_service import recover_evidence_runs
        recover_evidence_runs(engine)
        try:
            async with AsyncExitStack() as cleanup:
                for provider in _COMPONENT_PROVIDERS:
                    # Register cleanup before startup so a partially initialized
                    # provider is still unwound. AsyncExitStack also continues through
                    # all callbacks if an earlier shutdown raises.
                    cleanup.push_async_callback(provider.shutdown, app)
                    await provider.startup(app)
                from app.station_worker import StationWorker
                worker = StationWorker(engine, app.router, application=app)
                app.state.station_worker = worker
                worker.start()
                yield
        finally:
            try:
                if hasattr(app.state, "station_worker"):
                    await app.state.station_worker.shutdown()
                shutdown_bayes_jobs(engine)
            except BaseException:
                # A live compute thread can still write through this process.
                # Retain the durable lease until the PID exits so no second
                # backend can enter the same research database concurrently.
                release_lease = False
                raise
    finally:
        if release_lease:
            release_backend_instance_lease(engine)


app = FastAPI(title="MATB Research Console", version="0.1.0", lifespan=lifespan)
app.state.frontend_origins = _FRONTEND_ORIGINS
app.state.allowed_hosts = _ALLOWED_HOSTS
app.state.api_token = _API_TOKEN
app.state.component_registry = _COMPONENT_REGISTRY


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
from app.station_http import StationWorkMiddleware
app.add_middleware(ScientificRequestBodyLimitMiddleware)
app.add_middleware(StationWorkMiddleware)
app.add_middleware(LoopbackRequestSecurityMiddleware, settings=app.state)


_CORE_ROUTER_MODULES = (
    "app.routers.analysis",
    "app.routers.station",
    "app.routers.assessments",
    "app.routers.experiments",
    "app.routers.exports",
    "app.routers.fits",
    "app.routers.ingest",
    "app.routers.evidence",
    "app.routers.journey",
    "app.routers.metrics",
    "app.routers.participants",
    "app.routers.pvt",
    "app.routers.purpose",
    "app.routers.screen",
    "app.routers.study",
    "app.routers.study_registry",
    "app.routers.study_analysis",
    "app.routers.study_preparation",
    "app.routers.tracker",
)


def _include_router(module_name: str) -> None:
    module = import_module(module_name)
    app.include_router(module.router)


for _router_module in _CORE_ROUTER_MODULES:
    _include_router(_router_module)
for _provider in _COMPONENT_PROVIDERS:
    for _router_module in _provider.router_modules:
        _include_router(_router_module)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/capabilities")
async def capabilities() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "components": [
            manifest.to_record() for manifest in _COMPONENT_REGISTRY.manifests()
        ],
    }
