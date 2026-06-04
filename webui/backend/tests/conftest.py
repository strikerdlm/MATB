from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app import db as db_module
from app.main import app

# Make `matb_integration` importable (repo root is three levels up from this file).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture(name="engine")
def engine_fixture():
    # In-memory DB shared across the test's connections.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models  # noqa: F401  (register tables)
    SQLModel.metadata.create_all(engine)
    yield engine


@pytest.fixture(name="client")
def client_fixture(engine):
    def _get_session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[db_module.get_session] = _get_session_override
    with TestClient(app) as c:
        yield c
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
