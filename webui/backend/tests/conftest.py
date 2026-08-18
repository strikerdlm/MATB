from __future__ import annotations

import sys
from pathlib import Path
import asyncio
from datetime import date

import fastapi.concurrency
import fastapi.dependencies.utils
import fastapi.routing
import httpx
import pytest
import starlette.concurrency
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app import db as db_module
from app.main import app
from app.simulation_persistence import SQLModelSimulationPersistence
from app.simulation_runtime import SimulationManager
from app.models import Participant, Visit

# Make `matb_integration` importable (repo root is three levels up from this file).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class SyncASGIClient:
    """Small sync wrapper around httpx's ASGI transport for endpoint tests."""

    def __init__(self, app):
        self._app = app

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        async def _send() -> httpx.Response:
            transport = httpx.ASGITransport(app=self._app, raise_app_exceptions=True)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                follow_redirects=True,
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(_send())

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs) -> httpx.Response:
        return self.request("PUT", url, **kwargs)


@pytest.fixture
def anyio_backend():
    """Keep async backend tests deterministic on the supported asyncio loop."""

    return "asyncio"


def build_test_manager(*, engine, artifact_root: Path) -> SimulationManager:
    """Build a same-loop manager with durable metadata and explicit one-shot ticks."""

    return SimulationManager(
        scenario_root=_REPO_ROOT / "scenarios" / "suas",
        artifact_root=artifact_root,
        persistence=SQLModelSimulationPersistence(engine),
        run_background_tasks=False,
    )


@pytest.fixture(name="engine")
def engine_fixture():
    # In-memory DB shared across the test's connections.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models  # noqa: F401  (register tables)
    import app.simulation_models  # noqa: F401  (register simulation tables)
    import app.study_models  # noqa: F401  (register study metadata/context tables)
    SQLModel.metadata.create_all(engine)
    yield engine


@pytest.fixture
def seeded_participant(engine):
    """Seed one pseudonymized participant and its planned visit rows."""

    with Session(engine) as session:
        session.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        session.add(Visit(participant_id="P01", visit_ordinal=1, scheduled_day=0))
        session.commit()
    return "P01"


@pytest.fixture
async def simulation_client(engine, tmp_path, monkeypatch):
    """Async ASGI client sharing its event loop with a one-shot runtime manager."""

    manager = build_test_manager(engine=engine, artifact_root=tmp_path / "exports")
    app.state.simulation_manager = manager
    session = Session(engine)

    async def _run_direct(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(starlette.concurrency, "run_in_threadpool", _run_direct)
    monkeypatch.setattr(fastapi.concurrency, "run_in_threadpool", _run_direct)
    monkeypatch.setattr(fastapi.dependencies.utils, "run_in_threadpool", _run_direct)
    monkeypatch.setattr(fastapi.routing, "run_in_threadpool", _run_direct)

    async def _get_session_override():
        return session

    app.dependency_overrides[db_module.get_session] = _get_session_override
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client, manager
    finally:
        session.close()
        app.dependency_overrides.clear()
        await manager.shutdown()


@pytest.fixture(name="client")
def client_fixture(engine, monkeypatch):
    async def _run_direct(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(starlette.concurrency, "run_in_threadpool", _run_direct)
    monkeypatch.setattr(fastapi.concurrency, "run_in_threadpool", _run_direct)
    monkeypatch.setattr(fastapi.dependencies.utils, "run_in_threadpool", _run_direct)
    monkeypatch.setattr(fastapi.routing, "run_in_threadpool", _run_direct)

    session = Session(engine)

    def _get_session_override():
        return session

    app.dependency_overrides[db_module.get_session] = _get_session_override
    try:
        yield SyncASGIClient(app)
    finally:
        session.close()
        app.dependency_overrides.clear()


@pytest.fixture
def sample_csv_bytes():
    """Minimal OpenMATB-style CSV with SYSMON rows convert_session can parse."""
    def _build(misses: tuple[float, ...] = (5.0, 25.0), raw_tlx: float = 60.0) -> bytes:
        lines = ["scenario_time,type,module,address,value"]
        lines.append(f"900.0,performance,genericscales,Mental demand,{raw_tlx}")
        for t in misses:
            lines.append(f"{t},performance,sysmon,signal_detection,MISS")
        lines.append("10.0,performance,sysmon,signal_detection,HIT")
        return ("\n".join(lines) + "\n").encode("utf-8")
    return _build


@pytest.fixture
def ingest_one_block(client, sample_csv_bytes):
    def _ingest(participant_id="P01", visit_ordinal=1, workload_level="LOW"):
        client.post("/participants",
                    json={"id": participant_id, "enrollment_date": "2026-06-01"})
        r = client.post(
            "/ingest",
            data={"participant_id": participant_id,
                  "visit_ordinal": str(visit_ordinal),
                  "workload_level": workload_level},
            files={"file": ("run.csv", sample_csv_bytes(), "text/csv")},
        )
        assert r.status_code == 201, r.text
        return r
    return _ingest
