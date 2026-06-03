# MATB Research Console — Phase 1A (Backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `webui/backend/` FastAPI service — data model, file ingestion (reusing `matb_integration`), the derived study-completeness grid, and CRUD/ingest/tracker endpoints — fully covered by pytest.

**Architecture:** FastAPI + SQLModel over SQLite. Ingestion imports `matb_integration.log_converter` and `matb_integration.suhir.pipeline` as a library (no metric logic duplicated). Data hierarchy Participant → Visit (timepoint 1–6) → Block (LOW/MED/HIGH) → metrics; completeness is derived, not stored. This plan is **Phase 1A**; the Next.js tracker UI is **Phase 1B** (separate plan).

**Tech Stack:** Python 3.12, FastAPI, SQLModel, uvicorn, python-multipart, pytest, httpx (TestClient). Frontend stack (Phase 1B) is Next.js/TS.

**Spec:** `docs/superpowers/specs/2026-06-03-webui-phase1-data-tracker-design.md`

> **BASE-BRANCH REQUIREMENT:** the fit-trigger (Task 7) imports `matb_integration.suhir`, which lives in PR #5 (`feat/suhir-depdf-phase1`), not yet on `main`. Build this plan on a branch that contains BOTH `matb_integration.log_converter` (on `main`) and `matb_integration.suhir` (PR #5) — i.e. start after PR #5 merges to `main`, or branch from `feat/suhir-depdf-phase1`. Tasks 1–6 do not import suhir and work on either base.

---

## File structure

| File | Responsibility |
|---|---|
| `webui/backend/requirements.txt` | Backend Python deps. |
| `webui/backend/app/__init__.py` | Package marker. |
| `webui/backend/app/db.py` | SQLite engine + session dependency. |
| `webui/backend/app/models.py` | SQLModel tables: Participant, Visit, Block, DepdfFit. |
| `webui/backend/app/constants.py` | `SCHEDULED_DAYS`, `WORKLOAD_LEVELS`. |
| `webui/backend/app/main.py` | FastAPI app, CORS, router registration, `/health`. |
| `webui/backend/app/schemas.py` | Pydantic request/response models. |
| `webui/backend/app/ingestion.py` | file→identity mapping, guards, convert, store, fit-trigger. |
| `webui/backend/app/completeness.py` | derive the expected-vs-actual grid. |
| `webui/backend/app/routers/participants.py` | participant CRUD + visit auto-gen. |
| `webui/backend/app/routers/ingest.py` | upload + ingest endpoint. |
| `webui/backend/app/routers/tracker.py` | completeness grid endpoint. |
| `webui/backend/tests/conftest.py` | temp-DB fixture + TestClient + sample CSV builder. |
| `webui/backend/tests/test_*.py` | one per concern. |

---

### Task 1: Backend scaffold, deps, and health endpoint

**Files:** Create `webui/backend/requirements.txt`, `webui/backend/app/__init__.py`, `webui/backend/app/db.py`, `webui/backend/app/main.py`, `webui/backend/tests/__init__.py`, `webui/backend/tests/conftest.py`, `webui/backend/tests/test_health.py`.

- [ ] **Step 1: Create the venv and requirements, install**

Create `webui/backend/requirements.txt`:

```
fastapi>=0.110
sqlmodel>=0.0.16
uvicorn[standard]>=0.29
python-multipart>=0.0.9
pytest>=7.4
httpx>=0.27
```

Run:
```bash
python3 -m venv ~/.venvs/matb-webui
~/.venvs/matb-webui/bin/pip install -r /root/repos/MATB/webui/backend/requirements.txt
```
Expected: installs without error. Use `~/.venvs/matb-webui/bin/python -m pytest` for all test runs in this plan.

- [ ] **Step 2: Create package marker + DB module**

Create `webui/backend/app/__init__.py` (empty).

Create `webui/backend/app/db.py`:

```python
"""SQLite engine + FastAPI session dependency."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

_DB_PATH = Path(__file__).resolve().parents[1] / "matb_webui.db"
_engine = create_engine(f"sqlite:///{_DB_PATH}", connect_args={"check_same_thread": False})


def get_engine():
    return _engine


def init_db() -> None:
    """Create tables. Import models for side-effect registration first."""
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(_engine)


def get_session() -> Iterator[Session]:
    with Session(_engine) as session:
        yield session
```

- [ ] **Step 3: Write the failing health test**

Create `webui/backend/tests/__init__.py` (empty).

Create `webui/backend/tests/conftest.py`:

```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app import db as db_module
from app.main import app


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
```

Create `webui/backend/tests/test_health.py`:

```python
def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 4: Run to verify it fails**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_health.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 5: Create the FastAPI app**

Create `webui/backend/app/main.py`:

```python
"""MATB Research Console backend (Phase 1A)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="MATB Research Console", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3100"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Run to verify it passes**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_health.py -q`
Expected: 1 passed. (Tests run with `app` importable because pytest adds the rootdir; add Step 7 to guarantee imports.)

- [ ] **Step 7: Add pytest config so `app` imports from the backend dir**

Create `webui/backend/pytest.ini`:

```ini
[pytest]
pythonpath = .
testpaths = tests
```

Re-run Step 6; expected: 1 passed.

- [ ] **Step 8: Commit**

```bash
cd /root/repos/MATB
git add webui/backend/requirements.txt webui/backend/app/__init__.py webui/backend/app/db.py webui/backend/app/main.py webui/backend/pytest.ini webui/backend/tests/
git commit -m "feat(webui): backend scaffold + health endpoint"
```

---

### Task 2: Data model (SQLModel tables)

**Files:** Create `webui/backend/app/constants.py`, `webui/backend/app/models.py`, `webui/backend/tests/test_models.py`.

- [ ] **Step 1: Write the failing test**

Create `webui/backend/tests/test_models.py`:

```python
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.models import Block, DepdfFit, Participant, Visit


def test_participant_visit_block_roundtrip(engine):
    with Session(engine) as s:
        s.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        s.add(Visit(participant_id="P01", visit_ordinal=1, scheduled_day=0))
        s.commit()
        v = s.query(Visit).first()
        s.add(Block(visit_id=v.id, workload_level="LOW",
                    source_csv_filename="a.csv", source_csv_sha256="sha-a",
                    metrics_json="{}"))
        s.commit()
        assert s.query(Block).count() == 1


def test_block_sha256_is_unique(engine):
    with Session(engine) as s:
        s.add(Participant(id="P02", enrollment_date=date(2026, 6, 1)))
        s.add(Visit(participant_id="P02", visit_ordinal=1, scheduled_day=0))
        s.commit()
        vid = s.query(Visit).first().id
        s.add(Block(visit_id=vid, workload_level="LOW", source_csv_filename="a.csv",
                    source_csv_sha256="dup", metrics_json="{}"))
        s.commit()
        s.add(Block(visit_id=vid, workload_level="MEDIUM", source_csv_filename="b.csv",
                    source_csv_sha256="dup", metrics_json="{}"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_visit_ordinal_unique_per_participant(engine):
    with Session(engine) as s:
        s.add(Participant(id="P03", enrollment_date=date(2026, 6, 1)))
        s.add(Visit(participant_id="P03", visit_ordinal=1, scheduled_day=0))
        s.commit()
        s.add(Visit(participant_id="P03", visit_ordinal=1, scheduled_day=3))
        with pytest.raises(IntegrityError):
            s.commit()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models'`.

- [ ] **Step 3: Create constants and models**

Create `webui/backend/app/constants.py`:

```python
"""Study-protocol constants."""

from __future__ import annotations

SCHEDULED_DAYS: tuple[int, ...] = (0, 3, 6, 9, 12, 15)  # 6 visits over 15 days
N_VISITS: int = len(SCHEDULED_DAYS)
WORKLOAD_LEVELS: tuple[str, ...] = ("LOW", "MEDIUM", "HIGH")
```

Create `webui/backend/app/models.py`:

```python
"""SQLModel tables for the MATB Research Console (Phase 1A)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlmodel import Field, SQLModel, UniqueConstraint


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Participant(SQLModel, table=True):
    id: str = Field(primary_key=True)               # "P01"… pseudonymized, no PII
    enrollment_date: date
    sex: str | None = None
    age_band: str | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class Visit(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("participant_id", "visit_ordinal"),)
    id: int | None = Field(default=None, primary_key=True)
    participant_id: str = Field(foreign_key="participant.id", index=True)
    visit_ordinal: int                              # 1..6 (the timepoint)
    scheduled_day: int                              # 0/3/6/9/12/15 (target)
    actual_date: date | None = None
    status: str = "planned"                         # planned|in_progress|complete


class Block(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("visit_id", "workload_level"),)
    id: int | None = Field(default=None, primary_key=True)
    visit_id: int = Field(foreign_key="visit.id", index=True)
    workload_level: str                             # LOW|MEDIUM|HIGH
    source_csv_filename: str
    source_csv_sha256: str = Field(index=True, unique=True)
    ingested_at: datetime = Field(default_factory=_utcnow)
    metrics_json: str                               # full log_converter record


class DepdfFit(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    participant_id: str = Field(index=True)
    visit_id: int = Field(foreign_key="visit.id", unique=True)
    g0: float
    p0: float
    tau0: float
    hcf_value: float
    hcf_source: str
    criteria_version: int
    per_level_json: str
    fitted_at: datetime = Field(default_factory=_utcnow)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_models.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add webui/backend/app/constants.py webui/backend/app/models.py webui/backend/tests/test_models.py
git commit -m "feat(webui): SQLModel data model (participant/visit/block/depdf_fit)"
```

---

### Task 3: Participant CRUD + auto-generate 6 visits

**Files:** Create `webui/backend/app/schemas.py`, `webui/backend/app/routers/__init__.py`, `webui/backend/app/routers/participants.py`; Modify `webui/backend/app/main.py`; Create `webui/backend/tests/test_participants.py`.

- [ ] **Step 1: Write the failing test**

Create `webui/backend/tests/test_participants.py`:

```python
def test_create_participant_generates_six_visits(client):
    r = client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "P01"

    visits = client.get("/participants/P01/visits").json()
    assert [v["visit_ordinal"] for v in visits] == [1, 2, 3, 4, 5, 6]
    assert [v["scheduled_day"] for v in visits] == [0, 3, 6, 9, 12, 15]
    assert all(v["status"] == "planned" for v in visits)


def test_list_participants(client):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    client.post("/participants", json={"id": "P02", "enrollment_date": "2026-06-02"})
    ids = [p["id"] for p in client.get("/participants").json()]
    assert ids == ["P01", "P02"]


def test_duplicate_participant_rejected(client):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    r = client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    assert r.status_code == 409
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_participants.py -q`
Expected: FAIL — 404 (routes not registered) or import error.

- [ ] **Step 3: Create schemas**

Create `webui/backend/app/schemas.py`:

```python
"""Request/response models."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class ParticipantCreate(BaseModel):
    id: str
    enrollment_date: date
    sex: str | None = None
    age_band: str | None = None
    notes: str | None = None


class ParticipantOut(BaseModel):
    id: str
    enrollment_date: date
    sex: str | None = None
    age_band: str | None = None
    notes: str | None = None


class VisitOut(BaseModel):
    id: int
    participant_id: str
    visit_ordinal: int
    scheduled_day: int
    actual_date: date | None = None
    status: str
```

- [ ] **Step 4: Create the participants router**

Create `webui/backend/app/routers/__init__.py` (empty).

Create `webui/backend/app/routers/participants.py`:

```python
"""Participant CRUD; creating a participant auto-generates the 6 planned visits."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.constants import SCHEDULED_DAYS
from app.db import get_session
from app.models import Participant, Visit
from app.schemas import ParticipantCreate, ParticipantOut, VisitOut

router = APIRouter(prefix="/participants", tags=["participants"])


@router.post("", response_model=ParticipantOut, status_code=status.HTTP_201_CREATED)
def create_participant(body: ParticipantCreate, session: Session = Depends(get_session)):
    if session.get(Participant, body.id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"participant {body.id} exists")
    participant = Participant(**body.model_dump())
    session.add(participant)
    for ordinal, day in enumerate(SCHEDULED_DAYS, start=1):
        session.add(Visit(participant_id=body.id, visit_ordinal=ordinal, scheduled_day=day))
    session.commit()
    return participant


@router.get("", response_model=list[ParticipantOut])
def list_participants(session: Session = Depends(get_session)):
    return session.exec(select(Participant).order_by(Participant.id)).all()


@router.get("/{participant_id}/visits", response_model=list[VisitOut])
def list_visits(participant_id: str, session: Session = Depends(get_session)):
    if session.get(Participant, participant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "participant not found")
    return session.exec(
        select(Visit).where(Visit.participant_id == participant_id).order_by(Visit.visit_ordinal)
    ).all()
```

- [ ] **Step 5: Register the router in main.py**

In `webui/backend/app/main.py`, add the import and registration. After the `app = FastAPI(...)` block and before `@app.get("/health")`, insert:

```python
from app.routers import participants  # noqa: E402

app.include_router(participants.router)
```

- [ ] **Step 6: Run to verify it passes**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_participants.py -q`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
cd /root/repos/MATB
git add webui/backend/app/schemas.py webui/backend/app/routers/ webui/backend/app/main.py webui/backend/tests/test_participants.py
git commit -m "feat(webui): participant CRUD + auto-generated 6 visits"
```

---

### Task 4: Completeness grid derivation

**Files:** Create `webui/backend/app/completeness.py`, `webui/backend/tests/test_completeness.py`.

- [ ] **Step 1: Write the failing test**

Create `webui/backend/tests/test_completeness.py`:

```python
from __future__ import annotations

from datetime import date

from sqlmodel import Session

from app.completeness import build_completeness_grid
from app.models import Block, Participant, Visit


def _seed(engine):
    with Session(engine) as s:
        s.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        for ordinal, day in enumerate((0, 3, 6, 9, 12, 15), start=1):
            s.add(Visit(participant_id="P01", visit_ordinal=ordinal, scheduled_day=day))
        s.commit()
        v1 = s.exec(
            __import__("sqlmodel").select(Visit).where(Visit.visit_ordinal == 1)
        ).first()
        s.add(Block(visit_id=v1.id, workload_level="LOW", source_csv_filename="a.csv",
                    source_csv_sha256="sa", metrics_json="{}"))
        s.commit()


def test_grid_marks_present_and_absent(engine):
    _seed(engine)
    with Session(engine) as s:
        grid = build_completeness_grid(s)
    # one participant -> 6 visits x 3 levels = 18 cells
    assert len(grid) == 18
    present = {(c["participant_id"], c["visit_ordinal"], c["workload_level"])
               for c in grid if c["present"]}
    assert ("P01", 1, "LOW") in present
    absent = [c for c in grid if not c["present"]]
    assert len(absent) == 17
    # summary counts
    by_visit1 = [c for c in grid if c["visit_ordinal"] == 1]
    assert sum(c["present"] for c in by_visit1) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_completeness.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.completeness'`.

- [ ] **Step 3: Implement**

Create `webui/backend/app/completeness.py`:

```python
"""Derive the expected-vs-actual study completeness grid.

The expected grid = enrolled participants × 6 visits × 3 workload levels.
Each cell is present (a Block row exists for that visit+level) or
expected-but-absent. Nothing about missingness is stored; it is derived.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.constants import SCHEDULED_DAYS, WORKLOAD_LEVELS
from app.models import Block, Participant, Visit


def build_completeness_grid(session: Session) -> list[dict[str, Any]]:
    participants = session.exec(select(Participant).order_by(Participant.id)).all()
    visits = session.exec(select(Visit)).all()
    blocks = session.exec(select(Block)).all()

    visit_by_key = {(v.participant_id, v.visit_ordinal): v for v in visits}
    present_levels: dict[int, set[str]] = {}
    for b in blocks:
        present_levels.setdefault(b.visit_id, set()).add(b.workload_level)

    grid: list[dict[str, Any]] = []
    for p in participants:
        for ordinal, day in enumerate(SCHEDULED_DAYS, start=1):
            visit = visit_by_key.get((p.id, ordinal))
            have = present_levels.get(visit.id, set()) if visit else set()
            for level in WORKLOAD_LEVELS:
                grid.append({
                    "participant_id": p.id,
                    "visit_ordinal": ordinal,
                    "scheduled_day": day,
                    "workload_level": level,
                    "present": level in have,
                })
    return grid
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_completeness.py -q`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add webui/backend/app/completeness.py webui/backend/tests/test_completeness.py
git commit -m "feat(webui): derived study-completeness grid"
```

---

### Task 5: Ingestion core — file→identity mapping + guards

**Files:** Create `webui/backend/app/ingestion.py`; Modify `webui/backend/tests/conftest.py` (add a sample-CSV builder fixture); Create `webui/backend/tests/test_ingestion.py`.

This reuses `matb_integration.log_converter`. The MATB repo root must be importable; conftest adds it to `sys.path`.

- [ ] **Step 1: Add repo-root import + sample CSV builder to conftest**

Append to `webui/backend/tests/conftest.py`:

```python
import sys
from pathlib import Path

# Make `matb_integration` importable (repo root is three levels up from this file).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture
def sample_csv_bytes():
    """Minimal OpenMATB-style CSV with SYSMON rows convert_session can parse.

    Columns match what log_converter.parse_csv expects: scenario_time, type,
    module, address, value. Includes a raw_tlx scale row and SYSMON MISS rows.
    """
    def _build(misses: tuple[float, ...] = (5.0, 25.0), raw_tlx: float = 60.0) -> bytes:
        lines = ["scenario_time,type,module,address,value"]
        lines.append(f"900.0,performance,genericscales,nasatlx,{raw_tlx}")
        for i, t in enumerate(misses):
            lines.append(f"{t},performance,sysmon,signal_detection,MISS")
        lines.append("10.0,performance,sysmon,signal_detection,HIT")
        return ("\n".join(lines) + "\n").encode("utf-8")
    return _build
```

NOTE TO IMPLEMENTER: the NASA-TLX row format above is a guess at the genericscales
encoding. Before relying on it, open `matb_integration/log_converter.py`
(`_nasatlx_metrics`, `_sysmon_metrics`) and confirm the exact `module`/`address`
strings and value encoding the parser matches, then adjust the builder so
`convert_session` actually populates `nasatlx.raw_tlx` and `sysmon.n_misses`.
The ingestion tests below assert on `n_misses`, which only needs the SYSMON MISS
rows (address `signal_detection`, value `MISS`) — those field names are confirmed
in the existing `_sysmon_metrics`. If the TLX row format is uncertain, keep the
SYSMON assertions and drop any raw_tlx assertion.

- [ ] **Step 2: Write the failing test**

Create `webui/backend/tests/test_ingestion.py`:

```python
from __future__ import annotations

import json
from datetime import date

import pytest
from sqlmodel import Session, select

from app.ingestion import IngestionError, ingest_csv
from app.models import Block, Participant, Visit


def _participant_with_visits(engine):
    with Session(engine) as s:
        s.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        for ordinal, day in enumerate((0, 3, 6, 9, 12, 15), start=1):
            s.add(Visit(participant_id="P01", visit_ordinal=ordinal, scheduled_day=day))
        s.commit()


def test_ingest_stores_block_with_metrics(engine, sample_csv_bytes):
    _participant_with_visits(engine)
    with Session(engine) as s:
        block = ingest_csv(s, content=sample_csv_bytes(misses=(5.0, 25.0)),
                           filename="run1.csv", participant_id="P01",
                           visit_ordinal=1, workload_level="LOW")
        assert block.workload_level == "LOW"
        metrics = json.loads(block.metrics_json)
        assert metrics["sysmon"]["n_misses"] == 2


def test_duplicate_sha_rejected(engine, sample_csv_bytes):
    _participant_with_visits(engine)
    content = sample_csv_bytes()
    with Session(engine) as s:
        ingest_csv(s, content=content, filename="a.csv", participant_id="P01",
                   visit_ordinal=1, workload_level="LOW")
        with pytest.raises(IngestionError, match="already ingested"):
            ingest_csv(s, content=content, filename="b.csv", participant_id="P01",
                       visit_ordinal=2, workload_level="LOW")


def test_filled_cell_requires_overwrite(engine, sample_csv_bytes):
    _participant_with_visits(engine)
    with Session(engine) as s:
        ingest_csv(s, content=sample_csv_bytes(misses=(5.0,)), filename="a.csv",
                   participant_id="P01", visit_ordinal=1, workload_level="LOW")
        with pytest.raises(IngestionError, match="already filled"):
            ingest_csv(s, content=sample_csv_bytes(misses=(7.0,)), filename="c.csv",
                       participant_id="P01", visit_ordinal=1, workload_level="LOW")
        # overwrite=True replaces it
        block = ingest_csv(s, content=sample_csv_bytes(misses=(9.0,)), filename="d.csv",
                           participant_id="P01", visit_ordinal=1, workload_level="LOW",
                           overwrite=True)
        assert json.loads(block.metrics_json)["sysmon"]["n_misses"] == 1


def test_unknown_visit_rejected(engine, sample_csv_bytes):
    _participant_with_visits(engine)
    with Session(engine) as s:
        with pytest.raises(IngestionError, match="no visit"):
            ingest_csv(s, content=sample_csv_bytes(), filename="a.csv",
                       participant_id="P01", visit_ordinal=99, workload_level="LOW")


def test_csv_without_sysmon_rejected(engine):
    _participant_with_visits(engine)
    empty = b"scenario_time,type,module,address,value\n900.0,event,foo,bar,baz\n"
    with Session(engine) as s:
        with pytest.raises(IngestionError, match="no usable"):
            ingest_csv(s, content=empty, filename="a.csv", participant_id="P01",
                       visit_ordinal=1, workload_level="LOW")
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_ingestion.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ingestion'`.

- [ ] **Step 4: Implement ingestion (without the fit-trigger; that is Task 7)**

Create `webui/backend/app/ingestion.py`:

```python
"""CSV ingestion: file→identity mapping, integrity guards, convert, store.

Reuses matb_integration.log_converter (no metric logic duplicated). The
fit-trigger is added in a later task and imported lazily.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from sqlmodel import Session, select

from app.models import Block, Visit

WORKLOAD_LEVELS = ("LOW", "MEDIUM", "HIGH")


class IngestionError(Exception):
    """Raised when a file cannot be mapped/validated; never silently mislabel."""


def _convert(content: bytes, level: str) -> dict:
    """Run log_converter.convert_session on the uploaded bytes."""
    from matb_integration.log_converter import convert_session

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as fh:
        fh.write(content)
        tmp = Path(fh.name)
    try:
        return convert_session(tmp, workload_level=level)
    finally:
        tmp.unlink(missing_ok=True)


def ingest_csv(
    session: Session,
    *,
    content: bytes,
    filename: str,
    participant_id: str,
    visit_ordinal: int,
    workload_level: str,
    overwrite: bool = False,
) -> Block:
    if workload_level not in WORKLOAD_LEVELS:
        raise IngestionError(f"invalid workload_level {workload_level!r}")

    visit = session.exec(
        select(Visit).where(
            Visit.participant_id == participant_id,
            Visit.visit_ordinal == visit_ordinal,
        )
    ).first()
    if visit is None:
        raise IngestionError(f"no visit {visit_ordinal} for participant {participant_id}")

    sha = hashlib.sha256(content).hexdigest()
    dup = session.exec(select(Block).where(Block.source_csv_sha256 == sha)).first()
    if dup is not None and not (overwrite and dup.visit_id == visit.id
                                and dup.workload_level == workload_level):
        raise IngestionError(f"file already ingested (sha {sha[:12]})")

    existing = session.exec(
        select(Block).where(Block.visit_id == visit.id,
                            Block.workload_level == workload_level)
    ).first()
    if existing is not None and not overwrite:
        raise IngestionError(
            f"cell already filled: {participant_id} visit {visit_ordinal} {workload_level}"
        )

    record = _convert(content, workload_level)
    sysmon = record.get("sysmon") or {}
    if not sysmon.get("n_signals") and not sysmon.get("n_misses"):
        raise IngestionError("no usable metrics in CSV (no SYSMON signal rows)")

    if existing is not None:
        session.delete(existing)
        session.flush()

    block = Block(
        visit_id=visit.id,
        workload_level=workload_level,
        source_csv_filename=filename,
        source_csv_sha256=sha,
        metrics_json=json.dumps(record, ensure_ascii=False),
    )
    session.add(block)
    session.commit()
    session.refresh(block)
    return block
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_ingestion.py -q`
Expected: 5 passed. If the `n_misses` assertion fails, the SYSMON row format in the conftest builder is wrong — re-check `_sysmon_metrics` in `matb_integration/log_converter.py` for the exact match conditions and fix the builder (not the assertion).

- [ ] **Step 6: Commit**

```bash
cd /root/repos/MATB
git add webui/backend/app/ingestion.py webui/backend/tests/conftest.py webui/backend/tests/test_ingestion.py
git commit -m "feat(webui): CSV ingestion with file->identity mapping + integrity guards"
```

---

### Task 6: Ingest + tracker HTTP endpoints

**Files:** Create `webui/backend/app/routers/ingest.py`, `webui/backend/app/routers/tracker.py`; Modify `webui/backend/app/main.py`; Create `webui/backend/tests/test_endpoints.py`.

- [ ] **Step 1: Write the failing test**

Create `webui/backend/tests/test_endpoints.py`:

```python
from __future__ import annotations


def _enroll(client):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})


def test_ingest_endpoint_and_tracker(client, sample_csv_bytes):
    _enroll(client)
    files = {"file": ("run1.csv", sample_csv_bytes(misses=(5.0, 25.0)), "text/csv")}
    data = {"participant_id": "P01", "visit_ordinal": "1", "workload_level": "LOW"}
    r = client.post("/ingest", files=files, data=data)
    assert r.status_code == 201, r.text
    assert r.json()["workload_level"] == "LOW"

    grid = client.get("/tracker").json()
    assert len(grid) == 18
    present = [c for c in grid if c["present"]]
    assert present and present[0]["workload_level"] == "LOW"


def test_ingest_duplicate_returns_409(client, sample_csv_bytes):
    _enroll(client)
    content = sample_csv_bytes()
    files = {"file": ("a.csv", content, "text/csv")}
    data = {"participant_id": "P01", "visit_ordinal": "1", "workload_level": "LOW"}
    assert client.post("/ingest", files=files, data=data).status_code == 201
    files2 = {"file": ("b.csv", content, "text/csv")}
    data2 = {"participant_id": "P01", "visit_ordinal": "2", "workload_level": "LOW"}
    r = client.post("/ingest", files=files2, data=data2)
    assert r.status_code == 409
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_endpoints.py -q`
Expected: FAIL — 404 (routes not registered).

- [ ] **Step 3: Create the tracker router**

Create `webui/backend/app/routers/tracker.py`:

```python
"""Study-completeness grid endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.completeness import build_completeness_grid
from app.db import get_session

router = APIRouter(tags=["tracker"])


@router.get("/tracker")
def tracker(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return build_completeness_grid(session)
```

- [ ] **Step 4: Create the ingest router**

Create `webui/backend/app/routers/ingest.py`:

```python
"""Upload + ingest endpoint. Maps guard failures to HTTP 409."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlmodel import Session

from app.db import get_session
from app.ingestion import IngestionError, ingest_csv

router = APIRouter(tags=["ingest"])


@router.post("/ingest", status_code=status.HTTP_201_CREATED)
def ingest(
    file: UploadFile = File(...),
    participant_id: str = Form(...),
    visit_ordinal: int = Form(...),
    workload_level: str = Form(...),
    overwrite: bool = Form(False),
    session: Session = Depends(get_session),
):
    content = file.file.read()
    try:
        block = ingest_csv(
            session,
            content=content,
            filename=file.filename or "upload.csv",
            participant_id=participant_id,
            visit_ordinal=visit_ordinal,
            workload_level=workload_level,
            overwrite=overwrite,
        )
    except IngestionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"id": block.id, "workload_level": block.workload_level,
            "visit_id": block.visit_id}
```

- [ ] **Step 5: Register both routers in main.py**

In `webui/backend/app/main.py`, extend the router import/registration block:

```python
from app.routers import ingest, participants, tracker  # noqa: E402

app.include_router(participants.router)
app.include_router(ingest.router)
app.include_router(tracker.router)
```

- [ ] **Step 6: Run to verify it passes**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_endpoints.py -q`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
cd /root/repos/MATB
git add webui/backend/app/routers/ingest.py webui/backend/app/routers/tracker.py webui/backend/app/main.py webui/backend/tests/test_endpoints.py
git commit -m "feat(webui): /ingest and /tracker endpoints"
```

---

### Task 7: Suhir DEPDF fit-trigger on visit completion

**Requires `matb_integration.suhir` (PR #5) on the build branch — see the BASE-BRANCH REQUIREMENT at the top.**

**Files:** Modify `webui/backend/app/ingestion.py`; Create `webui/backend/tests/test_fit_trigger.py`.

- [ ] **Step 1: Write the failing test**

Create `webui/backend/tests/test_fit_trigger.py`:

```python
from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from app.ingestion import ingest_csv
from app.models import DepdfFit, Participant, Visit


def _enroll(engine):
    with Session(engine) as s:
        s.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        for ordinal, day in enumerate((0, 3, 6, 9, 12, 15), start=1):
            s.add(Visit(participant_id="P01", visit_ordinal=ordinal, scheduled_day=day))
        s.commit()


def test_fit_created_when_three_levels_present(engine, sample_csv_bytes):
    _enroll(engine)
    # MWL must increase with level for a valid Suhir fit; encode via raw_tlx and
    # decreasing MTTF (more misses earlier) at higher levels.
    plan = {
        "LOW":    dict(raw_tlx=40.0, misses=tuple(60.0 * i for i in range(1, 6))),
        "MEDIUM": dict(raw_tlx=60.0, misses=tuple(20.0 * i for i in range(1, 12))),
        "HIGH":   dict(raw_tlx=80.0, misses=tuple(12.0 * i for i in range(1, 20))),
    }
    with Session(engine) as s:
        for level, kw in plan.items():
            ingest_csv(s, content=sample_csv_bytes(misses=kw["misses"], raw_tlx=kw["raw_tlx"]),
                       filename=f"{level}.csv", participant_id="P01",
                       visit_ordinal=1, workload_level=level)
        fit = s.exec(select(DepdfFit).where(DepdfFit.participant_id == "P01")).first()
        assert fit is not None
        assert fit.g0 > 0 and 0 < fit.p0 <= 1
        assert fit.hcf_source == "F0_default"


def test_no_fit_with_two_levels(engine, sample_csv_bytes):
    _enroll(engine)
    with Session(engine) as s:
        for level in ("LOW", "MEDIUM"):
            ingest_csv(s, content=sample_csv_bytes(misses=(5.0, 30.0), raw_tlx=50.0),
                       filename=f"{level}.csv", participant_id="P01",
                       visit_ordinal=1, workload_level=level)
        assert s.exec(select(DepdfFit)).first() is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_fit_trigger.py -q`
Expected: FAIL — `DepdfFit` row is None (no trigger yet).

- [ ] **Step 3: Add the fit-trigger to ingestion.py**

In `webui/backend/app/ingestion.py`, add this function at the end of the file:

```python
def _maybe_fit_visit(session: Session, visit: "Visit") -> None:
    """If all 3 levels of this visit are present, run the Suhir fit and upsert.

    Imported lazily so Tasks 1-6 do not require matb_integration.suhir. Fit
    failures are swallowed (logged via the returned None) — ingestion must not
    fail because a fit could not be computed.
    """
    blocks = session.exec(select(Block).where(Block.visit_id == visit.id)).all()
    levels = {b.workload_level: b for b in blocks}
    if set(levels) != set(WORKLOAD_LEVELS):
        return

    from matb_integration.log_converter import parse_csv  # noqa: F401
    from matb_integration.suhir.pipeline import fit_participant
    from app.models import DepdfFit

    # Rebuild (record, raw_rows) per level from stored metrics + re-parsed rows.
    # raw rows are not stored; re-derive sysmon MISS times directly from metrics.
    # fit_participant needs (record, rows); reconstruct minimal rows from metrics.
    import json as _json

    blocks_arg: dict[str, tuple[dict, list[dict]]] = {}
    for level, b in levels.items():
        record = _json.loads(b.metrics_json)
        # Reconstruct SYSMON MISS rows from the stored count is NOT possible
        # (timestamps are lost). Store raw rows is out of scope; instead we
        # persist the rows at ingest time. See Step 4.
        rows = _json.loads(b.metrics_json).get("_raw_sysmon_rows", [])
        blocks_arg[level] = (record, rows)

    try:
        out = fit_participant("dummy", blocks_arg, source="raw_tlx")
    except Exception:
        return

    existing = session.exec(
        select(DepdfFit).where(DepdfFit.visit_id == visit.id)
    ).first()
    if existing is not None:
        session.delete(existing)
        session.flush()
    session.add(DepdfFit(
        participant_id=visit.participant_id,
        visit_id=visit.id,
        g0=out["g0"], p0=out["p0"], tau0=out["tau0"],
        hcf_value=out["hcf_value"], hcf_source=out["hcf_source"],
        criteria_version=out["criteria_version"],
        per_level_json=_json.dumps(out["per_level"], ensure_ascii=False),
    ))
    session.commit()
```

IMPLEMENTER — IMPORTANT DESIGN CORRECTION: `fit_participant` needs the raw SYSMON
rows (it calls `sysmon_failure_times(rows)` for MTTF), but the `Block` model
stores only the converted `metrics_json`, not the raw rows. Resolve this in
Step 4 by persisting the SYSMON MISS timestamps at ingest time.

- [ ] **Step 4: Persist SYSMON MISS times at ingest, and call the trigger**

In `ingest_csv` (in `ingestion.py`), after `record = _convert(content, workload_level)` and the validation block, embed the raw SYSMON detection rows into the stored record so the fit can reconstruct them. Replace the `record = _convert(...)` line's downstream so the stored JSON includes the raw rows:

```python
    record = _convert(content, workload_level)
    sysmon = record.get("sysmon") or {}
    if not sysmon.get("n_signals") and not sysmon.get("n_misses"):
        raise IngestionError("no usable metrics in CSV (no SYSMON signal rows)")

    # Persist the raw SYSMON rows the Suhir fit needs (timestamps), keyed
    # privately so they round-trip through metrics_json.
    from matb_integration.log_converter import parse_csv as _parse
    import tempfile as _tmp
    from pathlib import Path as _Path
    with _tmp.NamedTemporaryFile(suffix=".csv", delete=False) as _fh:
        _fh.write(content)
        _p = _Path(_fh.name)
    try:
        record["_raw_sysmon_rows"] = [
            r for r in _parse(_p)
            if r.get("module") == "sysmon" and r.get("address") == "signal_detection"
        ]
    finally:
        _p.unlink(missing_ok=True)
```

Then at the end of `ingest_csv`, before `return block`, add:

```python
    _maybe_fit_visit(session, visit)
```

Also update `_maybe_fit_visit`: `fit_participant` signature is
`fit_participant(participant_id, blocks, source="raw_tlx")` where `blocks`
maps level → (record, raw_rows). Pass `visit.participant_id` as the id. The
`rows` for each level come from `record["_raw_sysmon_rows"]`. Confirm against
the committed `matb_integration/suhir/pipeline.py` that `fit_participant` reads
`record["scenario_time_max_s"]` for duration — `convert_session` already sets it,
so it survives in `metrics_json`.

- [ ] **Step 5: Run to verify it passes**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_fit_trigger.py -q`
Expected: 2 passed. If `solve_g0` raises (unbracketed root) because the synthetic
MTTFs don't correspond to a valid model, adjust the per-level `misses` in the
test so MTTF strictly decreases with MWL and yields a valid fit (the fit is
wrapped in try/except, so a failed fit simply produces no DepdfFit row — the
first test asserts a fit IS created, so the synthetic data must be fit-valid).

- [ ] **Step 6: Run the full backend suite**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest -q`
Expected: all tests pass (health, models, participants, completeness, ingestion, endpoints, fit-trigger).

- [ ] **Step 7: Commit**

```bash
cd /root/repos/MATB
git add webui/backend/app/ingestion.py webui/backend/tests/test_fit_trigger.py
git commit -m "feat(webui): auto-run Suhir DEPDF fit when a visit's 3 levels complete"
```

---

### Task 8: Backend README + run instructions

**Files:** Create `webui/backend/README.md`; Create `webui/README.md`.

- [ ] **Step 1: Write the backend README**

Create `webui/backend/README.md`:

```markdown
# MATB Research Console — Backend (Phase 1A)

FastAPI + SQLModel (SQLite) service that ingests OpenMATB session CSVs via
`matb_integration`, tracks study completeness, and auto-fits the Suhir DEPDF
per completed visit.

## Setup
\`\`\`bash
python3 -m venv ~/.venvs/matb-webui
~/.venvs/matb-webui/bin/pip install -r webui/backend/requirements.txt
\`\`\`

## Run (dev)
\`\`\`bash
cd webui/backend
~/.venvs/matb-webui/bin/uvicorn app.main:app --reload --port 8000
\`\`\`

## Test
\`\`\`bash
cd webui/backend
~/.venvs/matb-webui/bin/python -m pytest -q
\`\`\`

## Endpoints
- `GET  /health`
- `POST /participants` · `GET /participants` · `GET /participants/{id}/visits`
- `POST /ingest` (multipart: file, participant_id, visit_ordinal, workload_level, overwrite)
- `GET  /tracker` — the 216-cell completeness grid

Reuses `matb_integration.log_converter` + `matb_integration.suhir.pipeline`
(requires the suhir package; see repo PR #5). No metric logic is duplicated.
```

(The backtick fences shown escaped above must be REAL triple-backticks in the file.)

- [ ] **Step 2: Write the webui top-level README**

Create `webui/README.md`:

```markdown
# MATB Research Console (webui)

Researcher console for the MATB longitudinal study (12 participants × 6 visits ×
3 workload levels). Backend: `backend/` (FastAPI, Phase 1A — built). Frontend:
`frontend/` (Next.js, Phase 1B — pending). Design system mirrors the HRV
"Mission Control" console for visual consistency.

See `docs/superpowers/specs/2026-06-03-webui-phase1-data-tracker-design.md`.
```

- [ ] **Step 3: Commit**

```bash
cd /root/repos/MATB
git add webui/backend/README.md webui/README.md
git commit -m "docs(webui): backend + webui READMEs"
```

---

## Self-review notes (completed by plan author)

- **Spec coverage:** spec §3 layout → Tasks 1–8 file structure. §4 data model → Task 2. §5 ingestion + guards → Task 5; fit-trigger → Task 7. §6 tracker (grid endpoint) → Tasks 4+6 (the UI itself is Phase 1B). §10 testing → every task is TDD. §2 constants/timepoint → Task 2 constants + Task 3 visit auto-gen. The depdf_fit shape (Task 2) matches `suhir.pipeline.fit_participant` output keys used in Task 7.
- **Known risk flagged in-plan (not a placeholder):** Task 5 conftest's NASA-TLX CSV row format is a documented guess; the implementer is told to verify against `_nasatlx_metrics`/`_sysmon_metrics` and that only the SYSMON MISS rows (confirmed format) are load-bearing for the assertions. Task 7 Step 3/4 carry an explicit design correction (raw SYSMON rows must be persisted at ingest because `Block` stores only converted metrics) — this is spelled out with the fix, not deferred.
- **Type consistency:** `ingest_csv(session, *, content, filename, participant_id, visit_ordinal, workload_level, overwrite)` is identical across Tasks 5, 6, 7. `build_completeness_grid(session)` identical in Tasks 4 and 6. `IngestionError` raised in Task 5, caught in Task 6.
- **Phase 1B (frontend) is a separate plan** — Next.js scaffold mirroring HRV, completeness-grid view, and upload flow consuming these endpoints.
