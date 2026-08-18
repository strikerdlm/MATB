# Liftoff–ASTRA Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a research-grade, file-first integration of commercial Liftoff telemetry with the MATB research console and HRV Polar H10 analysis for ASTRA visits T0, DM8, and DM15.

**Architecture:** Liftoff remains an unmodified Windows application that emits UDP telemetry to a loopback-only MATB collector. MATB owns the task lifecycle, raw/canonical telemetry, outcomes, provenance, and sealed bundles; HRV owns precise Polar H10 capture metadata, RR persistence, signal quality, and baseline/task/recovery analysis. The two systems join by a UUID and immutable hashes after collection, so either stream can survive failure of the other.

**Tech Stack:** Python 3.12, `struct`, `asyncio` UDP, Pydantic 2, FastAPI, SQLModel/SQLite, NumPy/SciPy, Next.js 14, React 18, TypeScript, Vitest, Playwright, Polar BLE through `bleak`, SHA-256 artifact inventories.

## Global Constraints

- The active ASTRA schedule is exactly T0/day 0, DM8/day 8, and DM15/day 15.
- Existing six-visit databases are never rewritten automatically; use a new ASTRA database and retain an explicit compatibility profile.
- Liftoff is unmodified: no memory inspection, DLL injection, input automation, private-log scraping, or executable modification.
- Telemetry binds to loopback only and rejects unknown packet profiles rather than guessing.
- File-first artifacts are authoritative; LSL may mirror data but is never the sole record.
- MATB owns performance/task data; HRV owns RR data and physiology algorithms.
- Use pseudonymized participant IDs matching `^P[0-9]{2,6}$`; never persist Steam identity or raw BLE addresses.
- No VR, gamepad, combat, multiplayer, or leaderboard-dependent primary outcomes.
- No composite pilot score, workload classifier training, diagnosis, clearance, or go/no-go output.
- High-rate telemetry stays in files, not SQL rows.
- All artifact writes are atomic and checksum-covered after sealing.
- Do not commit, push, or alter unrelated worktree changes unless the user explicitly authorizes those actions during execution.

## Repository and execution boundaries

The plan is sequential but spans two Git repositories:

1. Tasks 1–11 and 14–18 run in `/root/repos/MATB`.
2. Tasks 12–13 run in `/root/repos/HRV` and produce a versioned HTTP contract.
3. Task 14 returns to MATB and consumes only that published contract.
4. Task 19 updates the Obsidian protocol only after hardware and pilot gates pass.

At execution time, create isolated worktrees separately for MATB and HRV. Never attempt a cross-repository atomic commit. Each repository must pass its own tests before the integration checkpoint.

## Planned file map

### MATB files to create

```text
matb_integration/recording/__init__.py
matb_integration/recording/artifacts.py
matb_integration/recording/records.py
matb_integration/liftoff/__init__.py
matb_integration/liftoff/protocol.py
matb_integration/liftoff/records.py
matb_integration/liftoff/receiver.py
matb_integration/liftoff/quality.py
matb_integration/liftoff/metrics.py
matb_integration/liftoff/session.py
webui/backend/app/study_protocol.py
webui/backend/app/study_models.py
webui/backend/app/liftoff_models.py
webui/backend/app/liftoff_schemas.py
webui/backend/app/liftoff_persistence.py
webui/backend/app/liftoff_runtime.py
webui/backend/app/hrv_task_client.py
webui/backend/app/routers/study.py
webui/backend/app/routers/liftoff.py
webui/backend/tests/test_study_protocol.py
webui/backend/tests/test_liftoff_models.py
webui/backend/tests/test_liftoff_endpoints.py
webui/backend/tests/test_liftoff_failures.py
tests/liftoff/__init__.py
tests/liftoff/fixtures/everything_v1_synthetic.bin
tests/liftoff/test_protocol.py
tests/liftoff/test_receiver.py
tests/liftoff/test_quality.py
tests/liftoff/test_metrics.py
tests/liftoff/test_session.py
webui/frontend/src/types/liftoff.ts
webui/frontend/src/lib/liftoff/api.ts
webui/frontend/src/lib/liftoff/api.test.ts
webui/frontend/src/components/liftoff/LiftoffSetupForm.tsx
webui/frontend/src/components/liftoff/LiftoffSetupForm.test.tsx
webui/frontend/src/components/liftoff/LiftoffSessionConsole.tsx
webui/frontend/src/components/liftoff/LiftoffSessionConsole.test.tsx
webui/frontend/src/components/liftoff/LiftoffDebrief.tsx
webui/frontend/src/components/liftoff/LiftoffDebrief.test.tsx
webui/frontend/src/app/liftoff/setup/page.tsx
webui/frontend/src/app/liftoff/session/page.tsx
webui/frontend/src/app/liftoff/debrief/page.tsx
webui/frontend/e2e/liftoff.spec.ts
scripts/capture_liftoff_fixture.py
scripts/run_liftoff_acceptance.py
docs/research/liftoff/ASTRA_LIFTOFF_SOP.md
docs/research/liftoff/PILOT_ACCEPTANCE_TEMPLATE.md
```

### HRV files to create

```text
app/task_session_hrv.py
api/task_session_hrv.py
tests/test_polar_h10_recording_metadata.py
tests/test_task_session_hrv.py
docs/contracts/task-session-hrv-v1.schema.json
```

### Existing files to modify

```text
MATB/webui/backend/app/constants.py
MATB/webui/backend/app/db.py
MATB/webui/backend/app/main.py
MATB/webui/backend/app/models.py
MATB/webui/backend/app/schemas.py
MATB/webui/backend/app/completeness.py
MATB/webui/backend/app/simulation_schemas.py
MATB/webui/backend/app/routers/participants.py
MATB/webui/backend/app/routers/exports.py
MATB/webui/backend/tests/conftest.py
MATB/webui/frontend/src/types/index.ts
MATB/webui/frontend/src/lib/api.ts
MATB/webui/frontend/src/lib/tracker.ts
MATB/webui/frontend/src/lib/viz.ts
MATB/webui/frontend/src/app/visualization/page.tsx
MATB/webui/frontend/src/components/participants/AddParticipantDialog.tsx
MATB/webui/frontend/src/components/participants/ParticipantTable.tsx
MATB/matb_integration/suas/recording/artifacts.py
MATB/matb_integration/suas/recording/recorder.py
MATB/README.md
MATB/webui/README.md
MATB/webui/frontend/README.md
HRV/app/polar_h10_recorder.py
HRV/api/main.py
HRV/api/research_endpoints.py
HRV/README.md
```

---

### Task 1: Add the backend study-protocol registry and database binding

**Repository:** `/root/repos/MATB`

**Files:**
- Create: `webui/backend/app/study_protocol.py`
- Create: `webui/backend/app/study_models.py`
- Create: `webui/backend/app/routers/study.py`
- Create: `webui/backend/tests/test_study_protocol.py`
- Modify: `webui/backend/app/db.py`
- Modify: `webui/backend/app/main.py`

**Interfaces:**
- Produces: `VisitDefinition`, `StudyProtocolDefinition`, `get_protocol(protocol_id)`, `selected_protocol()`, `ensure_study_binding(engine, protocol)`, and `GET /study/protocol`.
- The endpoint returns `protocol_id`, `protocol_version`, `schedule_sha256`, and three ordered visits.

- [ ] **Step 1: Write failing registry and binding tests**

```python
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

from app.study_protocol import get_protocol
from app.study_models import StudyMetadata, ensure_study_binding


def test_astra_protocol_has_three_canonical_visits():
    protocol = get_protocol("astra-2026")
    assert [(v.ordinal, v.code, v.scheduled_day) for v in protocol.visits] == [
        (1, "T0", 0), (2, "DM8", 8), (3, "DM15", 15)
    ]


def test_database_binding_rejects_conflicting_profile():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    ensure_study_binding(engine, get_protocol("astra-2026"))
    with pytest.raises(RuntimeError, match="study_protocol_mismatch"):
        ensure_study_binding(engine, get_protocol("matb-longitudinal-6-visit-v1"))
```

- [ ] **Step 2: Run the tests and verify the missing-module failure**

Run:

```bash
PYTHONPATH=.:webui/backend .venv-suas/bin/pytest webui/backend/tests/test_study_protocol.py -q
```

Expected: collection fails because `app.study_protocol` and `app.study_models` do not exist.

- [ ] **Step 3: Implement immutable protocol definitions**

```python
@dataclass(frozen=True, slots=True)
class VisitDefinition:
    ordinal: int
    code: str
    scheduled_day: int


@dataclass(frozen=True, slots=True)
class StudyProtocolDefinition:
    protocol_id: str
    protocol_version: str
    visits: tuple[VisitDefinition, ...]

    @property
    def schedule_sha256(self) -> str:
        payload = json.dumps(
            [asdict(visit) for visit in self.visits],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
```

Register exactly `astra-2026` and `matb-longitudinal-6-visit-v1`. `selected_protocol()` reads `MATB_STUDY_PROTOCOL`, defaulting to `astra-2026`, and rejects unknown or blank values.

- [ ] **Step 4: Implement persisted study binding and endpoint**

```python
class StudyMetadata(SQLModel, table=True):
    singleton_id: int = Field(default=1, primary_key=True)
    protocol_id: str
    protocol_version: str
    schedule_sha256: str


def ensure_study_binding(engine, protocol: StudyProtocolDefinition) -> None:
    with Session(engine) as db:
        row = db.get(StudyMetadata, 1)
        expected = (protocol.protocol_id, protocol.protocol_version, protocol.schedule_sha256)
        if row is None:
            db.add(StudyMetadata(
                protocol_id=expected[0], protocol_version=expected[1], schedule_sha256=expected[2]
            ))
            db.commit()
        elif (row.protocol_id, row.protocol_version, row.schedule_sha256) != expected:
            raise RuntimeError("study_protocol_mismatch")
```

Register `StudyMetadata` before `SQLModel.metadata.create_all`, call `ensure_study_binding` during application lifespan, and expose a strict response from `/study/protocol`.

- [ ] **Step 5: Run focused and database bootstrap tests**

```bash
PYTHONPATH=.:webui/backend .venv-suas/bin/pytest webui/backend/tests/test_study_protocol.py webui/backend/tests/test_bootstrap.py -q
```

Expected: all selected tests pass; a conflicting database/profile combination fails closed.

- [ ] **Step 6: Record the checkpoint**

If commits are authorized during execution:

```bash
git add webui/backend/app/study_protocol.py webui/backend/app/study_models.py webui/backend/app/routers/study.py webui/backend/app/db.py webui/backend/app/main.py webui/backend/tests/test_study_protocol.py
git commit -m "feat(protocol): bind MATB to ASTRA three-visit schedule"
```

Otherwise, retain the verified working-tree diff and report the checkpoint without committing.

---

### Task 2: Apply the three-visit protocol to backend consumers

**Repository:** `/root/repos/MATB`

**Files:**
- Modify: `webui/backend/app/constants.py`
- Modify: `webui/backend/app/completeness.py`
- Modify: `webui/backend/app/models.py`
- Modify: `webui/backend/app/study_models.py`
- Modify: `webui/backend/app/schemas.py`
- Modify: `webui/backend/app/simulation_schemas.py`
- Modify: `webui/backend/app/routers/participants.py`
- Modify: `webui/backend/tests/test_participants.py`
- Modify: `webui/backend/tests/test_completeness.py`
- Modify: `webui/backend/tests/conftest.py`

**Interfaces:**
- Consumes: `selected_protocol()` from Task 1.
- Produces: participants with exactly three `Visit` rows, a derived 3 × 3 OpenMATB completeness grid per participant, and one immutable `StudyParticipantContext` containing task sequence and prior-experience covariates.

- [ ] **Step 1: Change the tests to the approved schedule**

```python
def test_create_participant_generates_astra_visits(client):
    response = client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    assert response.status_code == 201
    visits = client.get("/participants/P01/visits").json()
    assert [row["visit_ordinal"] for row in visits] == [1, 2, 3]
    assert [row["scheduled_day"] for row in visits] == [0, 8, 15]


def test_one_participant_completeness_has_nine_cells(client):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    cells = client.get("/tracker").json()
    assert len(cells) == 9


def test_participant_study_context_is_structured_and_immutable(client):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    payload = {
        "task_sequence": "MATB_LIFTOFF",
        "prior_fpv_hours": 12.5,
        "gaming_hours_per_week": 3.0,
    }
    first = client.put("/participants/P01/study-context", json=payload)
    assert first.status_code == 201
    second = client.put("/participants/P01/study-context", json=payload)
    assert second.status_code == 409
```

- [ ] **Step 2: Run tests and observe the six-visit assertion failures**

```bash
PYTHONPATH=.:webui/backend .venv-suas/bin/pytest webui/backend/tests/test_participants.py webui/backend/tests/test_completeness.py -q
```

Expected: failures show six generated visits and 18 completeness cells.

- [ ] **Step 3: Replace schedule constants with protocol-derived visits**

```python
def protocol_visits() -> tuple[VisitDefinition, ...]:
    return selected_protocol().visits


for definition in protocol_visits():
    session.add(Visit(
        participant_id=body.id,
        visit_ordinal=definition.ordinal,
        scheduled_day=definition.scheduled_day,
    ))
```

In completeness, iterate `selected_protocol().visits`. Update model comments and bound transport ordinals to `1..16`; endpoint/runtime validation remains authoritative by resolving the actual participant visit row.

- [ ] **Step 4: Add immutable participant study context**

```python
class StudyParticipantContext(SQLModel, table=True):
    participant_id: str = Field(foreign_key="participant.id", primary_key=True)
    protocol_id: str
    task_sequence: str
    prior_fpv_hours: float = Field(ge=0)
    gaming_hours_per_week: float = Field(ge=0)
    created_at: datetime = Field(default_factory=_utcnow)
```

Add strict `StudyContextCreate`/`StudyContextView` schemas and `PUT`/`GET /participants/{id}/study-context`. Accept only `MATB_LIFTOFF` or `LIFTOFF_MATB`; reject overwrite with 409. In analysis, define `prior_fpv_experience = log1p(prior_fpv_hours)` and retain raw hours in provenance.

- [ ] **Step 5: Update every backend six-visit fixture**

Replace explicit `(0, 3, 6, 9, 12, 15)` fixture loops with:

```python
for visit in get_protocol("astra-2026").visits:
    session.add(Visit(
        participant_id=participant_id,
        visit_ordinal=visit.ordinal,
        scheduled_day=visit.scheduled_day,
    ))
```

- [ ] **Step 6: Run participant, completeness, ingestion, fit, and native-session tests**

```bash
PYTHONPATH=.:webui/backend .venv-suas/bin/pytest webui/backend/tests/test_participants.py webui/backend/tests/test_completeness.py webui/backend/tests/test_ingestion.py webui/backend/tests/test_fit_trigger.py webui/backend/tests/test_simulation_endpoints.py -q
```

Expected: all selected tests pass with three visits; OpenMATB still expects LOW/MEDIUM/HIGH within each visit.

- [ ] **Step 7: Record the checkpoint**

```bash
git add webui/backend/app/constants.py webui/backend/app/completeness.py webui/backend/app/models.py webui/backend/app/study_models.py webui/backend/app/schemas.py webui/backend/app/simulation_schemas.py webui/backend/app/routers/participants.py webui/backend/tests/conftest.py webui/backend/tests/test_participants.py webui/backend/tests/test_completeness.py webui/backend/tests/test_ingestion.py webui/backend/tests/test_fit_trigger.py
git commit -m "refactor(protocol): derive backend visits from ASTRA profile"
```

Run only if commits are authorized; otherwise retain the verified diff.

---

### Task 3: Make the frontend consume the active protocol

**Repository:** `/root/repos/MATB`

**Files:**
- Modify: `webui/frontend/src/types/index.ts`
- Modify: `webui/frontend/src/lib/api.ts`
- Modify: `webui/frontend/src/lib/tracker.ts`
- Modify: `webui/frontend/src/lib/viz.ts`
- Modify: `webui/frontend/src/lib/viz.test.ts`
- Modify: `webui/frontend/src/app/visualization/page.tsx`
- Modify: `webui/frontend/src/components/participants/AddParticipantDialog.tsx`
- Modify: `webui/frontend/src/components/participants/ParticipantTable.tsx`
- Modify: `webui/frontend/src/components/mission/setup/MissionSetupForm.tsx`

**Interfaces:**
- Consumes: `GET /study/protocol`.
- Produces: `StudyProtocol`, `StudyVisitDefinition`, `StudyParticipantContext`, `getStudyProtocol()`, `getStudyContext()`, `createStudyContext()`, and visualization functions receiving visit ordinals explicitly.

- [ ] **Step 1: Write failing dynamic-visit tests**

```typescript
it("renders three ASTRA visits without a frontend constant", () => {
  const visits = [1, 2, 3];
  const trajectory = trajectorySeries(rows, "P01", "nasatlx_raw_tlx", visits);
  expect(trajectory.visits).toEqual([1, 2, 3]);
  expect(trajectory.series.LOW).toHaveLength(3);
});
```

Add an API test asserting that `getStudyProtocol()` requests `/study/protocol` and parses T0/DM8/DM15.

- [ ] **Step 2: Run frontend tests and verify signature failures**

```bash
npm test -- src/lib/viz.test.ts src/lib/api.test.ts
```

Run from `webui/frontend`. Expected: `trajectorySeries` does not accept visit ordinals and `getStudyProtocol` is missing.

- [ ] **Step 3: Add protocol types and API**

```typescript
export interface StudyVisitDefinition {
  ordinal: number;
  code: "T0" | "DM8" | "DM15" | string;
  scheduled_day: number;
}

export interface StudyProtocol {
  protocol_id: string;
  protocol_version: string;
  schedule_sha256: string;
  visits: StudyVisitDefinition[];
}

export interface StudyParticipantContext {
  participant_id: string;
  protocol_id: string;
  task_sequence: "MATB_LIFTOFF" | "LIFTOFF_MATB";
  prior_fpv_hours: number;
  gaming_hours_per_week: number;
}

export async function getStudyProtocol(): Promise<StudyProtocol> {
  const res = await request("/study/protocol", { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getStudyContext(participantId: string): Promise<StudyParticipantContext | null> {
  const res = await request(`/participants/${encodeURIComponent(participantId)}/study-context`, { method: "GET" });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}
```

Add `createStudyContext(participantId, body)` using `PUT` and test that a second write surfaces the backend 409 rather than silently changing sequence or experience.

- [ ] **Step 4: Remove `N_VISITS` and `VISITS`**

Change visualization signatures to:

```typescript
export function trajectorySeries(
  rows: MetricRow[], participantId: string, metric: string, visits: number[],
): Trajectory;

export function groupOverview(
  rows: MetricRow[], metric: string, visits: number[],
): GroupStats;
```

Load protocol once in the visualization page and pass `protocol.visits.map(v => v.ordinal)`. Replace “generates 6 visits” UI copy with “generates T0, DM8, and DM15 visits.”

- [ ] **Step 5: Run unit, type, and build verification**

```bash
npm test -- src/lib/viz.test.ts src/lib/tracker.test.ts src/lib/api.test.ts
npm run typecheck
npm run build
```

Expected: tests, TypeScript, and Next.js build pass.

- [ ] **Step 6: Record the checkpoint when authorized**

```bash
git add webui/frontend/src/types/index.ts webui/frontend/src/lib/api.ts webui/frontend/src/lib/tracker.ts webui/frontend/src/lib/viz.ts webui/frontend/src/lib/viz.test.ts webui/frontend/src/app/visualization/page.tsx webui/frontend/src/components/participants/AddParticipantDialog.tsx webui/frontend/src/components/participants/ParticipantTable.tsx webui/frontend/src/components/mission/setup/MissionSetupForm.tsx webui/frontend/README.md webui/README.md
git commit -m "feat(protocol): render ASTRA T0 DM8 DM15 visits"
```

---

### Task 4: Extract domain-neutral atomic artifact primitives

**Repository:** `/root/repos/MATB`

**Files:**
- Create: `matb_integration/recording/__init__.py`
- Create: `matb_integration/recording/artifacts.py`
- Create: `matb_integration/recording/records.py`
- Modify: `matb_integration/suas/recording/artifacts.py`
- Modify: `matb_integration/suas/recording/records.py`
- Modify: `matb_integration/suas/recording/recorder.py`
- Modify: `tests/suas/test_artifacts.py`
- Create: `tests/liftoff/test_artifacts.py`

**Interfaces:**
- Produces: `ArtifactInfo`, `ArtifactProfile`, `write_json_artifact`, `build_checksum_file`, `verify_checksum_file`, and `artifact_inventory`.
- Preserves existing sUAS function signatures through wrappers.

- [ ] **Step 1: Write a failing profile-isolation test**

```python
def test_liftoff_profile_checksums_only_declared_files(tmp_path):
    profile = ArtifactProfile(
        frozen_names=("session-manifest.json", "telemetry.jsonl"),
        sealed_names=("metrics.json", "debrief.json"),
    )
    for name in (*profile.frozen_names, *profile.sealed_names):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    (tmp_path / "private.tmp").write_text("ignore", encoding="utf-8")
    checksum = build_checksum_file(tmp_path, profile=profile)
    assert verify_checksum_file(checksum, profile=profile) == ()
    assert "private.tmp" not in checksum.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the test and verify `ArtifactProfile` is missing**

```bash
PYTHONPATH=. .venv-suas/bin/pytest tests/liftoff/test_artifacts.py -q
```

- [ ] **Step 3: Implement the generic profile**

```python
@dataclass(frozen=True, slots=True)
class ArtifactProfile:
    frozen_names: tuple[str, ...]
    sealed_names: tuple[str, ...]
    partial_name: str = "partial-run.json"
    checksum_name: str = "checksums.sha256"


@dataclass(frozen=True, slots=True)
class ArtifactInfo:
    kind: str
    path: Path
    sha256: str
    size_bytes: int


def checksum_paths(run_dir: Path, *, profile: ArtifactProfile) -> tuple[Path, ...]:
    names = (*profile.frozen_names, *profile.sealed_names, profile.partial_name)
    return tuple(sorted(
        (run_dir / name for name in names if (run_dir / name).is_file()),
        key=lambda path: path.relative_to(run_dir).as_posix(),
    ))
```

Move `ArtifactInfo` into `matb_integration/recording/records.py`, and move the existing atomic-write/checksum logic without changing canonical JSON or line-ending behavior.

- [ ] **Step 4: Add sUAS compatibility wrappers**

```python
SUAS_PROFILE = ArtifactProfile(
    frozen_names=("scenario.yaml", "manifest.json", "events.jsonl"),
    sealed_names=("questionnaires.json", "metrics.json", "debrief.json", "replay-verification.json"),
)

def build_checksum_file(run_dir: Path) -> Path:
    return generic_build_checksum_file(run_dir, profile=SUAS_PROFILE)
```

Re-export `ArtifactInfo` from `matb_integration/suas/recording/records.py` so existing imports continue to work.

- [ ] **Step 5: Run all existing sUAS artifact/recorder tests plus the new profile test**

```bash
PYTHONPATH=. .venv-suas/bin/pytest tests/suas/test_artifacts.py tests/suas/test_recorder.py tests/liftoff/test_artifacts.py -q
```

Expected: byte-for-byte sUAS behavior remains accepted and the Liftoff profile is isolated.

- [ ] **Step 6: Record the checkpoint when authorized**

```bash
git add matb_integration/recording/__init__.py matb_integration/recording/artifacts.py matb_integration/recording/records.py matb_integration/suas/recording/artifacts.py matb_integration/suas/recording/records.py matb_integration/suas/recording/recorder.py tests/suas/test_artifacts.py tests/liftoff/test_artifacts.py
git commit -m "refactor(recording): share atomic research artifact primitives"
```

---

### Task 5: Implement strict Liftoff packet decoding and canonical records

**Repository:** `/root/repos/MATB`

**Files:**
- Create: `matb_integration/liftoff/__init__.py`
- Create: `matb_integration/liftoff/protocol.py`
- Create: `matb_integration/liftoff/records.py`
- Create: `tests/liftoff/fixtures/everything_v1_synthetic.bin`
- Create: `tests/liftoff/test_protocol.py`

**Interfaces:**
- Produces: `LIFTOFF_ALL_V1`, `LiftoffPacket`, `decode_packet(payload)`, `TelemetryRecord`, and `MarkerRecord`.
- The supported preliminary characterized layout is little-endian `20f`, one unsigned motor-count byte, and four motor-RPM floats; release remains gated on Task 18 commercial-fixture confirmation.

- [ ] **Step 1: Write failing decoder tests**

```python
import math
import struct
import pytest

from matb_integration.liftoff.protocol import PACKET_SIZE, decode_packet


def valid_payload() -> bytes:
    values = [float(index) for index in range(20)]
    return struct.pack("<20fB4f", *values, 4, 1000.0, 1001.0, 1002.0, 1003.0)


def test_decode_all_profile():
    packet = decode_packet(valid_payload())
    assert PACKET_SIZE == 97
    assert packet.simulator_time == 0.0
    assert packet.position_native == (1.0, 2.0, 3.0)
    assert packet.motor_count == 4
    assert packet.motor_rpm == (1000.0, 1001.0, 1002.0, 1003.0)


@pytest.mark.parametrize("payload", [b"", b"x" * 96, b"x" * 98])
def test_wrong_size_rejected(payload):
    with pytest.raises(PacketDecodeError, match="packet_size"):
        decode_packet(payload)
```

Add tests for nonfinite values and a motor count other than four.

- [ ] **Step 2: Run and observe missing decoder failures**

```bash
PYTHONPATH=. .venv-suas/bin/pytest tests/liftoff/test_protocol.py -q
```

- [ ] **Step 3: Implement the fixed-profile decoder**

```python
_PACKET = struct.Struct("<20fB4f")
PACKET_SIZE = _PACKET.size

@dataclass(frozen=True, slots=True)
class LiftoffPacket:
    simulator_time: float
    position_native: tuple[float, float, float]
    attitude_native: tuple[float, float, float, float]
    velocity_native: tuple[float, float, float]
    angular_rate_native: tuple[float, float, float]
    processed_input: tuple[float, float, float, float]
    battery_voltage: float
    charge_percent: float
    motor_count: int
    motor_rpm: tuple[float, float, float, float]


def decode_packet(payload: bytes) -> LiftoffPacket:
    if len(payload) != PACKET_SIZE:
        raise PacketDecodeError("packet_size")
    values = _PACKET.unpack(payload)
    floats, motor_count, rpms = values[:20], values[20], values[21:]
    if motor_count != 4 or not all(math.isfinite(value) for value in (*floats, *rpms)):
        raise PacketDecodeError("packet_values")
    return LiftoffPacket(
        simulator_time=floats[0],
        position_native=(floats[1], floats[2], floats[3]),
        attitude_native=(floats[4], floats[5], floats[6], floats[7]),
        velocity_native=(floats[8], floats[9], floats[10]),
        angular_rate_native=(floats[11], floats[12], floats[13]),
        processed_input=(floats[14], floats[15], floats[16], floats[17]),
        battery_voltage=floats[18],
        charge_percent=floats[19],
        motor_count=motor_count,
        motor_rpm=(rpms[0], rpms[1], rpms[2], rpms[3]),
    )
```

Map indices exactly as specified in the design. Do not rename `native` fields until Task 18 confirms units/frames.

- [ ] **Step 4: Implement strict immutable record types**

`TelemetryRecord` includes session UUID, positive sequence, `received_monotonic_ns`, UTC `received_utc`, and the decoded packet. `MarkerRecord` accepts only the ten design marker kinds plus `amendment` and requires monotonically increasing sequence.

- [ ] **Step 5: Run parser tests and static compilation**

```bash
PYTHONPATH=. .venv-suas/bin/pytest tests/liftoff/test_protocol.py -q
.venv-suas/bin/python -m compileall -q matb_integration/liftoff
```

- [ ] **Step 6: Record the checkpoint when authorized**

```bash
git add matb_integration/liftoff/__init__.py matb_integration/liftoff/protocol.py matb_integration/liftoff/records.py tests/liftoff/__init__.py tests/liftoff/fixtures/everything_v1_synthetic.bin tests/liftoff/test_protocol.py
git commit -m "feat(liftoff): decode strict commercial telemetry profile"
```

---

### Task 6: Add the bounded loopback UDP receiver and quality audit

**Repository:** `/root/repos/MATB`

**Files:**
- Create: `matb_integration/liftoff/receiver.py`
- Create: `matb_integration/liftoff/quality.py`
- Create: `tests/liftoff/test_receiver.py`
- Create: `tests/liftoff/test_quality.py`

**Interfaces:**
- Produces: `LiftoffUdpReceiver`, `ReceiverHealth`, `TelemetryQualityReport`, and `assess_quality(records, health, expected_rate_hz)`.
- Receiver callback: `Callable[[bytes, int, datetime], None]` where the integer is host monotonic nanoseconds.

- [ ] **Step 1: Write failing loopback and readiness tests**

```python
@pytest.mark.anyio
async def test_receiver_requires_loopback():
    with pytest.raises(ValueError, match="loopback_required"):
        LiftoffUdpReceiver(host="0.0.0.0", port=9001)


@pytest.mark.anyio
async def test_readiness_after_twenty_valid_packets(unused_udp_port):
    receiver = LiftoffUdpReceiver(host="127.0.0.1", port=unused_udp_port)
    await receiver.start()
    await send_packets(unused_udp_port, valid_payload(), count=20)
    assert await receiver.wait_ready(min_valid=20, timeout_seconds=2.0)
    await receiver.stop()
```

- [ ] **Step 2: Run and verify missing receiver failures**

```bash
PYTHONPATH=. .venv-suas/bin/pytest tests/liftoff/test_receiver.py tests/liftoff/test_quality.py -q
```

- [ ] **Step 3: Implement an asyncio datagram receiver with bounded accounting**

```python
class LiftoffUdpReceiver:
    def __init__(self, *, host: str, port: int, queue_size: int = 4096) -> None:
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError("loopback_required")
        if not 1 <= port <= 65535 or queue_size < 20:
            raise ValueError("invalid_receiver_configuration")
        self.host = host
        self.port = port
        self._queue: asyncio.Queue[ReceivedPacket] = asyncio.Queue(maxsize=queue_size)
        self._transport: asyncio.DatagramTransport | None = None
        self._health = ReceiverHealth()
        self._ready = asyncio.Event()

    async def start(self) -> None:
        if self._transport is not None:
            raise RuntimeError("receiver_already_started")
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _LiftoffDatagramProtocol(self._queue, self._health, self._ready),
            local_addr=(self.host, self.port),
        )
        self._transport = cast(asyncio.DatagramTransport, transport)

    async def stop(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    async def wait_ready(self, *, min_valid: int = 20, timeout_seconds: float = 2.0) -> bool:
        if min_valid != 20:
            raise ValueError("readiness_requires_twenty_packets")
        try:
            await asyncio.wait_for(self._ready.wait(), timeout_seconds)
        except TimeoutError:
            return False
        return self._health.valid_packets >= min_valid

    async def next_packet(self) -> ReceivedPacket:
        return await self._queue.get()

    def health(self) -> ReceiverHealth:
        return dataclasses.replace(self._health)
```

Implement `_LiftoffDatagramProtocol.datagram_received` in the same file. It captures `time.monotonic_ns()` and `datetime.now(timezone.utc)` before decoding, sets `_ready` on the twentieth valid packet, and increments separate invalid-size, invalid-value, overflow, duplicate-time, and out-of-order counters.

- [ ] **Step 4: Implement deterministic quality grading**

```python
@dataclass(frozen=True, slots=True)
class TelemetryQualityReport:
    packet_count: int
    expected_packet_count: int
    loss_pct: float
    observed_rate_hz: float
    maximum_gap_s: float
    invalid_packet_count: int
    overflow_count: int
    nonmonotonic_count: int
    clock_step_detected: bool
    validity: str
    reason_codes: tuple[str, ...]


def assess_quality(records, health, *, expected_rate_hz: float) -> TelemetryQualityReport:
    expected = max(1, round((records[-1].simulator_time - records[0].simulator_time) * expected_rate_hz))
    loss_pct = max(0.0, 100.0 * (expected - len(records)) / expected)
    if loss_pct >= 5.0:
        validity = "invalid"
    elif loss_pct >= 1.0:
        validity = "partial"
    else:
        validity = "valid"
    gaps = np.diff(np.asarray([record.simulator_time for record in records], dtype=float))
    nonmonotonic = int(np.count_nonzero(gaps <= 0))
    duration = max(records[-1].simulator_time - records[0].simulator_time, 1e-9)
    reason_codes = tuple(code for condition, code in (
        (loss_pct >= 5.0, "packet_loss_invalid"),
        (1.0 <= loss_pct < 5.0, "packet_loss_partial"),
        (health.overflow_count > 0, "receiver_overflow"),
        (nonmonotonic > 0, "simulator_time_nonmonotonic"),
        (health.clock_step_detected, "host_clock_step"),
    ) if condition)
    return TelemetryQualityReport(
        packet_count=len(records),
        expected_packet_count=expected,
        loss_pct=loss_pct,
        observed_rate_hz=len(records) / duration,
        maximum_gap_s=float(gaps.max(initial=0.0)),
        invalid_packet_count=health.invalid_packet_count,
        overflow_count=health.overflow_count,
        nonmonotonic_count=nonmonotonic,
        clock_step_detected=health.clock_step_detected,
        validity=validity,
        reason_codes=reason_codes,
    )
```

Include packet rate, maximum gap, nonmonotonic simulator times, overflow, invalid packets, and clock-step detection from monotonic-versus-UTC deltas.

- [ ] **Step 5: Run loss/reorder/silence tests and a 30-second synthetic soak**

```bash
PYTHONPATH=. .venv-suas/bin/pytest tests/liftoff/test_receiver.py tests/liftoff/test_quality.py -q
PYTHONPATH=. .venv-suas/bin/pytest tests/liftoff/test_receiver.py -q -m slow
```

Expected: loopback-only enforcement, readiness, loss thresholds, and bounded queues pass without leaked transports.

- [ ] **Step 6: Record the checkpoint when authorized**

```bash
git add matb_integration/liftoff/receiver.py matb_integration/liftoff/quality.py tests/liftoff/test_receiver.py tests/liftoff/test_quality.py
git commit -m "feat(liftoff): capture and grade bounded UDP telemetry"
```

---

### Task 7: Implement versioned telemetry performance metrics

**Repository:** `/root/repos/MATB`

**Files:**
- Create: `matb_integration/liftoff/metrics.py`
- Create: `tests/liftoff/test_metrics.py`

**Interfaces:**
- Produces: `METRICS_VERSION = "liftoff-metrics-v1"`, `VisibleResults`, and `compute_metrics(records, visible_results, reference_positions=None)`.
- Output preserves primary visible outcomes separately from secondary telemetry outcomes.

- [ ] **Step 1: Write failing deterministic metric tests**

```python
def test_metrics_keep_component_outcomes_separate():
    records = deterministic_records(sample_rate=60, seconds=10)
    visible = VisibleResults(
        valid_lap_times_s=(61.2, 63.0, 60.8),
        invalid_laps=1,
        observer_restart_count=2,
    )
    result = compute_metrics(records, visible)
    assert result["metrics_version"] == "liftoff-metrics-v1"
    assert result["primary"]["valid_laps"] == 3
    assert result["primary"]["median_lap_time_s"] == 61.2
    assert "composite_score" not in result
    assert 0.0 <= result["telemetry"]["input_saturation_fraction"] <= 1.0
```

Add tests for zero completed laps, constant inputs, irregular time, reference-path omission, and restart discrepancies.

- [ ] **Step 2: Run tests and verify missing metric symbols**

```bash
PYTHONPATH=. .venv-suas/bin/pytest tests/liftoff/test_metrics.py -q
```

- [ ] **Step 3: Implement primary and input metrics**

```python
def _normalized_entropy(values: np.ndarray, bins: int = 16) -> float:
    counts, _ = np.histogram(values, bins=bins, range=(-1.0, 1.0))
    probabilities = counts[counts > 0] / max(1, counts.sum())
    return float(-(probabilities * np.log2(probabilities)).sum() / np.log2(bins))


def _reversal_rate(values: np.ndarray, duration_min: float, deadband: float = 0.02) -> float:
    changes = np.diff(values)
    signs = np.sign(np.where(np.abs(changes) >= deadband, changes, 0.0))
    reversals = np.count_nonzero((signs[1:] * signs[:-1]) < 0)
    return float(reversals / max(duration_min, 1e-9))
```

Compute RMS, saturation fraction (`abs(input) >= 0.95`), entropy, reversal rate, active duration, velocity percentiles, and angular-rate summaries.

- [ ] **Step 4: Implement path and smoothness metrics with explicit eligibility**

Use a five-sample centered moving average before velocity differentiation. Compute jerk RMS only when median sampling interval is positive and rate is at least 20 Hz. Use `scipy.spatial.cKDTree` for reference-path nearest-neighbor distance only after `coordinate_units_validated=true`; otherwise return `not_computable` with a reason code.

- [ ] **Step 5: Run deterministic tests twice and compare canonical output hashes**

```bash
PYTHONPATH=. .venv-suas/bin/pytest tests/liftoff/test_metrics.py -q
PYTHONPATH=. .venv-suas/bin/pytest tests/liftoff/test_metrics.py -q
```

Expected: both runs pass and fixture artifact hashes match.

- [ ] **Step 6: Record the checkpoint when authorized**

```bash
git add matb_integration/liftoff/metrics.py tests/liftoff/test_metrics.py
git commit -m "feat(liftoff): derive versioned component performance metrics"
```

---

### Task 8: Implement the file-first Liftoff session recorder

**Repository:** `/root/repos/MATB`

**Files:**
- Create: `matb_integration/liftoff/session.py`
- Create: `tests/liftoff/test_session.py`

**Interfaces:**
- Produces: `LiftoffSessionRecorder.prepare`, `append_packet`, `mark`, `attach_results`, `attach_questionnaires`, `attach_physiology_link`, `seal`, and `seal_partial`.
- Consumes: generic artifacts (Task 4), records (Task 5), quality (Task 6), and metrics (Task 7).

- [ ] **Step 1: Write failing lifecycle and immutability tests**

```python
def test_recorder_requires_ordered_phases_and_seals(tmp_path):
    recorder = LiftoffSessionRecorder.prepare(tmp_path, manifest=manifest())
    recorder.mark("recording_started")
    recorder.mark("baseline_started")
    with pytest.raises(SessionLifecycleError, match="task_before_baseline_finished"):
        recorder.mark("task_started")
    recorder.mark("baseline_finished")
    recorder.mark("task_started")
    recorder.mark("task_finished")
    recorder.mark("recovery_started")
    recorder.mark("recovery_finished")
    recorder.mark("recording_finished")
    artifacts = recorder.seal(results=visible_results(), questionnaires=questionnaires())
    assert (tmp_path / "checksums.sha256").is_file()
    with pytest.raises(SessionLifecycleError, match="session_sealed"):
        recorder.mark("amendment")
```

- [ ] **Step 2: Run and verify missing recorder failure**

```bash
PYTHONPATH=. .venv-suas/bin/pytest tests/liftoff/test_session.py -q
```

- [ ] **Step 3: Implement append-only raw, JSONL, and marker writes**

The raw frame is:

```text
magic[4] = LFT1
sequence uint64 little-endian
received_monotonic_ns uint64 little-endian
received_utc_unix_ns int64 little-endian
payload_length uint16 little-endian
payload bytes
```

Open files in exclusive-create mode, flush high-rate data in bounded batches, and `fsync` at each phase boundary.

- [ ] **Step 4: Implement seal and partial seal**

`seal()` writes visible results, questionnaires, physiology link, quality, metrics, and debrief atomically, then creates checksums and closes the recorder. `seal_partial(reason_code)` writes `partial-run.json`, checksums all extant immutable files, and never writes a complete debrief.

- [ ] **Step 5: Run lifecycle, recovery, and artifact verification tests**

```bash
PYTHONPATH=. .venv-suas/bin/pytest tests/liftoff/test_session.py tests/liftoff/test_artifacts.py -q
```

- [ ] **Step 6: Record the checkpoint when authorized**

```bash
git add matb_integration/liftoff/session.py tests/liftoff/test_session.py
git commit -m "feat(liftoff): seal file-first research sessions"
```

---

### Task 9: Add Liftoff SQLModel metadata and persistence

**Repository:** `/root/repos/MATB`

**Files:**
- Create: `webui/backend/app/liftoff_models.py`
- Create: `webui/backend/app/liftoff_persistence.py`
- Create: `webui/backend/tests/test_liftoff_models.py`
- Modify: `webui/backend/app/db.py`
- Modify: `webui/backend/tests/conftest.py`

**Interfaces:**
- Produces: `LiftoffSession`, `LiftoffArtifact`, `LiftoffDeviation`, `LiftoffResult`, and `SQLModelLiftoffPersistence`.
- Database uniqueness: `(participant_id, visit_id, attempt_number)`.

- [ ] **Step 1: Write failing uniqueness and first-valid-attempt tests**

```python
def test_attempt_numbers_are_unique(engine, seeded_participant):
    with Session(engine) as db:
        db.add(liftoff_row(id="a", attempt_number=1))
        db.commit()
        db.add(liftoff_row(id="b", attempt_number=1))
        with pytest.raises(IntegrityError):
            db.commit()


def test_analysis_attempt_is_first_valid(engine):
    persistence = SQLModelLiftoffPersistence(engine)
    persistence.insert_session(liftoff_row(id="bad", attempt_number=1, validity="invalid"))
    persistence.insert_session(liftoff_row(id="good", attempt_number=2, validity="valid"))
    assert persistence.analysis_attempt("P01", visit_id=1).id == "good"
```

- [ ] **Step 2: Run and verify missing model failures**

```bash
PYTHONPATH=.:webui/backend .venv-suas/bin/pytest webui/backend/tests/test_liftoff_models.py -q
```

- [ ] **Step 3: Implement low-rate tables**

```python
class LiftoffSession(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("participant_id", "visit_id", "attempt_number"),)
    id: str = Field(primary_key=True)
    participant_id: str = Field(foreign_key="participant.id", index=True)
    visit_id: int = Field(foreign_key="visit.id", index=True)
    attempt_number: int = Field(ge=1)
    protocol_id: str
    protocol_version: str
    liftoff_build: str
    configuration_sha256: str = Field(index=True)
    track_id: str
    telemetry_profile: str
    status: str = "PREPARED"
    validity: str = "pending_review"
    artifact_root: str
    controller_lease_hash: str = Field(repr=False)
    hrv_measurement_id: str | None = None
    hrv_file_sha256: str | None = None
    sync_quality: str = "missing"
    metrics_json: str | None = None
```

Add UTC timestamps and separate artifact/deviation/result tables as specified.

- [ ] **Step 4: Implement allowlisted persistence mutations**

Follow `simulation_persistence.py`: one short SQLModel session per mutation, explicit allowed field sets, orphan active sessions marked `INTERRUPTED`, and artifact replacement from `ArtifactInfo`.

- [ ] **Step 5: Register tables and run model/bootstrap tests**

```bash
PYTHONPATH=.:webui/backend .venv-suas/bin/pytest webui/backend/tests/test_liftoff_models.py webui/backend/tests/test_bootstrap.py -q
```

- [ ] **Step 6: Record the checkpoint when authorized**

```bash
git add webui/backend/app/liftoff_models.py webui/backend/app/liftoff_persistence.py webui/backend/app/db.py webui/backend/tests/conftest.py webui/backend/tests/test_liftoff_models.py
git commit -m "feat(liftoff): persist session provenance and attempts"
```

---

### Task 10: Implement the Liftoff backend runtime and API

**Repository:** `/root/repos/MATB`

**Files:**
- Create: `webui/backend/app/liftoff_schemas.py`
- Create: `webui/backend/app/liftoff_runtime.py`
- Create: `webui/backend/app/routers/liftoff.py`
- Create: `webui/backend/tests/test_liftoff_endpoints.py`
- Create: `webui/backend/tests/test_liftoff_failures.py`
- Modify: `webui/backend/app/main.py`
- Modify: `webui/backend/tests/conftest.py`

**Interfaces:**
- Produces: strict `/liftoff/*` endpoints from the specification.
- Uses an `X-Liftoff-Controller` one-time lease stored only as a hash server-side and in browser session storage client-side.

- [ ] **Step 1: Write failing prepare/readiness/lifecycle endpoint tests**

```python
@pytest.mark.anyio
async def test_create_session_returns_one_time_lease(liftoff_client):
    client, manager = liftoff_client
    manager.receiver.inject_valid_packets(20)
    response = await client.post("/liftoff/sessions", json=create_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PREPARED"
    assert body["controller_lease"]
    fetched = await client.get(f"/liftoff/sessions/{body['id']}")
    assert "controller_lease" not in fetched.json()


@pytest.mark.anyio
async def test_task_cannot_start_before_baseline_finishes(liftoff_client):
    session, lease = await prepared_session(liftoff_client)
    response = await post_transition(liftoff_client, session, "task/start", lease)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "liftoff_phase_order"
```

- [ ] **Step 2: Run endpoint tests and verify missing router/runtime failures**

```bash
PYTHONPATH=.:webui/backend .venv-suas/bin/pytest webui/backend/tests/test_liftoff_endpoints.py webui/backend/tests/test_liftoff_failures.py -q
```

- [ ] **Step 3: Define strict configuration and transport schemas**

```python
class LiftoffConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    liftoff_build: str = Field(min_length=1, max_length=64)
    track_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
    drone_id: str = Field(min_length=1, max_length=128)
    flight_mode: str = Field(min_length=1, max_length=32)
    camera_angle_deg: float = Field(ge=0, le=90)
    fov_deg: float = Field(gt=0, le=180)
    rates_profile: str = Field(min_length=1, max_length=64)
    controller_model: str = Field(min_length=1, max_length=128)
    controller_firmware: str = Field(min_length=1, max_length=64)
    resolution: str = Field(pattern=r"^[0-9]{3,5}x[0-9]{3,5}$")
    refresh_rate_hz: int = Field(ge=30, le=500)
    graphics_preset: str = Field(min_length=1, max_length=32)
    damage_enabled: bool
    battery_enabled: bool
    telemetry_profile: Literal["liftoff-telemetry-all-v1"]


LiftoffAction = Literal[
    "baseline/start", "baseline/finish", "task/start", "task/finish",
    "recovery/start", "recovery/finish",
]


class CreateLiftoffSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    participant_id: str = Field(pattern=r"^P[0-9]{2,6}$")
    visit_ordinal: int = Field(ge=1, le=16)
    configuration: LiftoffConfiguration
    polar_recording_confirmed: bool
    performance_only_reason: str | None = Field(default=None, min_length=1, max_length=64)


class VisibleResultsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valid_lap_times_s: list[float] = Field(max_length=100)
    invalid_laps: int = Field(ge=0, le=1000)
    observer_restart_count: int = Field(ge=0, le=1000)
    screenshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
```

Add `PreparedLiftoffSession`, `LiftoffSessionView`, `QuestionnairesRequest`, `PhysiologyLinkRequest`, `TelemetryQualityView`, `LiftoffDebriefView`, and `LiftoffArtifactView`, all with `extra="forbid"`. Require a bounded `performance_only_reason` when `polar_recording_confirmed` is false.

- [ ] **Step 4: Implement `LiftoffManager` and endpoint preconditions**

```python
_ACTION_MARKER = {
    "baseline/start": "baseline_started",
    "baseline/finish": "baseline_finished",
    "task/start": "task_started",
    "task/finish": "task_finished",
    "recovery/start": "recovery_started",
    "recovery/finish": "recovery_finished",
}


def build_session_manifest(*, request, session_id, configuration_sha256, protocol) -> dict[str, object]:
    visit = next(item for item in protocol.visits if item.ordinal == request.visit_ordinal)
    return {
        "schema_version": "liftoff-session-manifest-v1",
        "session_id": session_id,
        "participant_id": request.participant_id,
        "visit_ordinal": visit.ordinal,
        "visit_code": visit.code,
        "scheduled_day": visit.scheduled_day,
        "protocol_id": protocol.protocol_id,
        "protocol_version": protocol.protocol_version,
        "schedule_sha256": protocol.schedule_sha256,
        "configuration_sha256": configuration_sha256,
        "configuration": request.configuration.model_dump(mode="json"),
        "polar_recording_confirmed": request.polar_recording_confirmed,
        "performance_only_reason": request.performance_only_reason,
    }


class LiftoffManager:
    def __init__(self, *, artifact_root: Path, receiver: LiftoffUdpReceiver, persistence: LiftoffPersistence) -> None:
        self.artifact_root = artifact_root.resolve()
        self.receiver = receiver
        self.persistence = persistence
        self._active: dict[str, _ActiveLiftoffSession] = {}

    async def create_session(self, request: CreateLiftoffSession) -> PreparedLiftoffSession:
        visit = self.persistence.require_visit(request.participant_id, request.visit_ordinal)
        self.persistence.require_retake_allowed(request.participant_id, visit.id)
        if not await self.receiver.wait_ready(min_valid=20, timeout_seconds=2.0):
            raise LiftoffRuntimeError("liftoff_telemetry_not_ready")
        session_id = str(uuid.uuid4())
        lease = secrets.token_urlsafe(32)
        configuration_json = canonical_json(request.configuration.model_dump(mode="json"))
        configuration_sha256 = hashlib.sha256(configuration_json.encode("utf-8")).hexdigest()
        run_dir = (self.artifact_root / session_id).resolve()
        if self.artifact_root not in run_dir.parents:
            raise LiftoffRuntimeError("liftoff_artifact_path")
        manifest = build_session_manifest(
            request=request,
            session_id=session_id,
            configuration_sha256=configuration_sha256,
            protocol=selected_protocol(),
        )
        recorder = LiftoffSessionRecorder.prepare(run_dir, manifest=manifest)
        self.persistence.insert_prepared(
            request=request,
            session_id=session_id,
            visit_id=visit.id,
            configuration_sha256=configuration_sha256,
            artifact_root=run_dir,
            controller_lease_hash=hashlib.sha256(lease.encode("utf-8")).hexdigest(),
        )
        self._active[session_id] = _ActiveLiftoffSession(recorder=recorder, lease_hash=hashlib.sha256(lease.encode()).hexdigest())
        return self.persistence.prepared_view(session_id, controller_lease=lease)

    async def transition(self, session_id: str, action: LiftoffAction, lease: str) -> LiftoffSessionView:
        active = self._require_controller(session_id, lease)
        marker = _ACTION_MARKER[action]
        active.recorder.mark(marker)
        self.persistence.apply_marker(session_id, marker)
        return self.persistence.session_view(session_id)

    async def submit_results(self, session_id: str, lease: str, results: VisibleResultsRequest) -> None:
        active = self._require_controller(session_id, lease)
        active.recorder.attach_results(results.model_dump(mode="json"))
        self.persistence.save_results(session_id, results)

    async def attach_physiology(self, session_id: str, lease: str, link: PhysiologyLinkRequest) -> None:
        active = self._require_controller(session_id, lease)
        active.recorder.attach_physiology_link(link.model_dump(mode="json"))
        self.persistence.save_physiology_link(session_id, link)

    async def seal(self, session_id: str, lease: str) -> LiftoffDebriefView:
        active = self._require_controller(session_id, lease)
        inventory = active.recorder.seal()
        self.persistence.mark_finished(session_id, inventory)
        self._active.pop(session_id, None)
        return self.persistence.debrief_view(session_id)
```

Calculate configuration hashes server-side. Validate participant/visit identity against the active protocol. Refuse retakes unless the prior attempt is technically invalid. Register the manager in FastAPI lifespan and mark orphaned sessions interrupted at startup.

- [ ] **Step 5: Implement multipart screenshot and bundle endpoints**

Limit result screenshots to PNG/JPEG and 10 MB; validate magic bytes, generate a safe fixed filename, and never trust the upload name. A session bundle is available only after sealing or partial sealing and includes the checksum inventory.

- [ ] **Step 6: Run focused backend tests**

```bash
PYTHONPATH=.:webui/backend .venv-suas/bin/pytest webui/backend/tests/test_liftoff_endpoints.py webui/backend/tests/test_liftoff_failures.py webui/backend/tests/test_health.py -q
```

- [ ] **Step 7: Record the checkpoint when authorized**

```bash
git add webui/backend/app/liftoff_schemas.py webui/backend/app/liftoff_runtime.py webui/backend/app/routers/liftoff.py webui/backend/app/main.py webui/backend/tests/conftest.py webui/backend/tests/test_liftoff_endpoints.py webui/backend/tests/test_liftoff_failures.py
git commit -m "feat(liftoff): expose guarded session lifecycle API"
```

---

### Task 11: Build the Liftoff frontend workflow

**Repository:** `/root/repos/MATB`

**Files:**
- Create all `webui/frontend/src/types/liftoff.ts`, `src/lib/liftoff/*`, `src/components/liftoff/*`, and `src/app/liftoff/*` files listed in the file map.
- Modify: `webui/frontend/src/components/layout/SidebarNav.tsx`
- Modify: `webui/frontend/src/components/layout/RouteShell.tsx`

**Interfaces:**
- Consumes: Task 10 API and Task 3 study protocol.
- Produces: setup, live session, and debrief pages; lease is stored under `matb.liftoff.<session>.lease` in `sessionStorage`.

- [ ] **Step 1: Write failing API and setup-component tests**

```typescript
it("stores the one-time lease outside the URL", async () => {
  mockCreateSession(preparedSession);
  render(<LiftoffSetupForm participants={participants} protocol={protocol} />);
  await user.selectOptions(screen.getByLabelText(/participant/i), "P01");
  await user.selectOptions(screen.getByLabelText(/visit/i), "2");
  await user.click(screen.getByRole("button", { name: /prepare/i }));
  expect(sessionStorage.getItem(`matb.liftoff.${preparedSession.id}.lease`)).toBe("secret");
  expect(mockPush).toHaveBeenCalledWith(`/liftoff/session?session=${preparedSession.id}`);
  expect(mockPush.mock.calls[0][0]).not.toContain("secret");
});
```

- [ ] **Step 2: Run tests and verify missing modules/components**

```bash
npm test -- src/lib/liftoff/api.test.ts src/components/liftoff/LiftoffSetupForm.test.tsx
```

- [ ] **Step 3: Implement typed API and setup readiness**

Define exact TypeScript equivalents of backend views. Setup selects participant/visit, displays attempt history, validates telemetry readiness and configuration, records whether Polar is running, and requires explicit performance-only confirmation when Polar is absent. It also fetches `StudyParticipantContext`; when absent, it collects the fixed task sequence, prior FPV hours, and weekly gaming hours once through `createStudyContext`. Existing context is read-only in the Liftoff workflow.

- [ ] **Step 4: Implement phase console**

The session console polls session/receiver health once per second, displays current phase timer, valid packet rate, estimated loss, last-packet age, schema status, and bounded warnings. Buttons enforce the legal phase transition order and require confirmation at task start/end.

- [ ] **Step 5: Implement debrief**

The debrief accepts valid lap times, invalid-lap count, observer restart count, result screenshot, KSS, NASA-TLX subscales, deviations, and Polar file/sidecar. It displays sync grade and quality before seal. It never displays absolute paths or Steam identity.

- [ ] **Step 6: Run component, accessibility, type, and build tests**

```bash
npm test -- src/lib/liftoff src/components/liftoff
npm run typecheck
npm run build
```

- [ ] **Step 7: Record the checkpoint when authorized**

```bash
git add webui/frontend/src/types/liftoff.ts webui/frontend/src/lib/liftoff/api.ts webui/frontend/src/lib/liftoff/api.test.ts webui/frontend/src/components/liftoff/LiftoffSetupForm.tsx webui/frontend/src/components/liftoff/LiftoffSetupForm.test.tsx webui/frontend/src/components/liftoff/LiftoffSessionConsole.tsx webui/frontend/src/components/liftoff/LiftoffSessionConsole.test.tsx webui/frontend/src/components/liftoff/LiftoffDebrief.tsx webui/frontend/src/components/liftoff/LiftoffDebrief.test.tsx webui/frontend/src/app/liftoff/setup/page.tsx webui/frontend/src/app/liftoff/session/page.tsx webui/frontend/src/app/liftoff/debrief/page.tsx webui/frontend/src/components/layout/SidebarNav.tsx webui/frontend/src/components/layout/RouteShell.tsx
git commit -m "feat(liftoff): add ASTRA collection workflow"
```

---

### Task 12: Add precise Polar H10 timing sidecars

**Repository:** `/root/repos/HRV`

**Files:**
- Modify: `app/polar_h10_recorder.py`
- Create: `tests/test_polar_h10_recording_metadata.py`

**Interfaces:**
- Produces: `PolarRecordingMetadata`, `<recording>.metadata.json`, and `PolarH10Recorder.set_external_context(session_id, participant_id)`.
- Existing one-RR-per-line text files remain unchanged.

- [ ] **Step 1: Write failing metadata tests without BLE hardware**

```python
def test_recorder_writes_utc_monotonic_sidecar(tmp_path, monkeypatch):
    recorder = PolarH10Recorder(output_dir=tmp_path)
    recorder.set_external_context(session_id="550e8400-e29b-41d4-a716-446655440000", participant_id="P01")
    prepare_connected_fake_client(recorder)
    assert asyncio.run(recorder.start_recording())
    recorder._hr_notification_handler(None, rr_notification(hr=72, rr_1024_units=1024))
    path = asyncio.run(recorder.stop_recording())
    metadata = json.loads(Path(path).with_suffix(".metadata.json").read_text())
    assert metadata["external_session_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert metadata["participant_id"] == "P01"
    assert metadata["recording_start_utc"].endswith("Z")
    assert metadata["start_monotonic_ns"] < metadata["end_monotonic_ns"]
    assert metadata["rr_file_sha256"] == sha256(Path(path).read_bytes()).hexdigest()
```

- [ ] **Step 2: Run and verify missing context/sidecar behavior**

```bash
pytest tests/test_polar_h10_recording_metadata.py -q
```

- [ ] **Step 3: Implement metadata state and UTC clocks**

```python
@dataclass(frozen=True, slots=True)
class PolarRecordingMetadata:
    schema_version: str
    recorder_version: str
    capture_id: str
    external_session_id: str | None
    participant_id: str | None
    recording_start_utc: str
    recording_end_utc: str
    start_monotonic_ns: int
    end_monotonic_ns: int
    first_rr_received_monotonic_ns: int | None
    last_rr_received_monotonic_ns: int | None
    device_identifier_hash: str
    rr_count: int
    rr_file_sha256: str
```

Use `datetime.now(timezone.utc)` and `time.monotonic_ns()`. Hash the device address with a deployment salt before persistence; never write the raw address.

- [ ] **Step 4: Write the sidecar atomically at stop**

Write `<stem>.metadata.json.tmp`, flush and `fsync`, then `os.replace`. If sidecar writing fails, retain the RR text file and return a bounded error state rather than deleting source data.

- [ ] **Step 5: Run recorder metadata and existing HRV core tests**

```bash
pytest tests/test_polar_h10_recording_metadata.py tests/test_workload_state.py -q
```

- [ ] **Step 6: Record the HRV checkpoint when authorized**

```bash
git add app/polar_h10_recorder.py tests/test_polar_h10_recording_metadata.py
git commit -m "feat(polar): preserve task-session timing metadata"
```

---

### Task 13: Add the versioned HRV task-session upload contract

**Repository:** `/root/repos/HRV`

**Files:**
- Create: `app/task_session_hrv.py`
- Create: `api/task_session_hrv.py`
- Create: `tests/test_task_session_hrv.py`
- Create: `docs/contracts/task-session-hrv-v1.schema.json`
- Modify: `api/main.py`
- Modify: `api/research_endpoints.py`
- Modify: `README.md`

**Interfaces:**
- Produces: `TaskSessionHrvRequest`, `TaskSessionHrvResponse`, `UtcSegment`, `SegmentIndex`, `POST /api/research/hrv/task-sessions/analyze`, and JSON Schema `task-session-hrv-v1`.
- Response fields: authoritative measurement ID, RR hash/count, exact start time, signal-quality summary, segment indices, phase metrics, and excluded legacy probability field.

- [ ] **Step 1: Write failing contract tests**

```python
def test_task_session_upload_persists_same_session_identity(client, tmp_path):
    rr = "\n".join(["800"] * 1900)
    metadata = timing_metadata(session_id=SESSION_ID, participant_id="P01", rr_bytes=rr.encode())
    response = client.post("/api/research/hrv/task-sessions/analyze", json={
        "contract_version": "task-session-hrv-v1",
        "external_session_id": SESSION_ID,
        "participant_id": "P01",
        "rr_filename": "polar.txt",
        "rr_content": rr,
        "rr_file_sha256": hashlib.sha256(rr.encode()).hexdigest(),
        "timing": metadata,
        "segments": [
            {"label": "baseline", "start_utc": metadata["recording_start_utc"], "end_utc": plus_seconds(metadata, 300)},
            {"label": "task", "start_utc": plus_seconds(metadata, 300), "end_utc": plus_seconds(metadata, 1200)},
            {"label": "recovery", "start_utc": plus_seconds(metadata, 1200), "end_utc": plus_seconds(metadata, 1500)},
        ],
    })
    assert response.status_code == 200
    body = response.json()
    assert body["external_session_id"] == SESSION_ID
    assert body["measurement_id"]
    assert set(body["phase_metrics"]) == {"baseline", "task", "recovery"}
    assert "high_workload_probability" not in body
```

Add tests for hash mismatch, participant mismatch, overlapping markers, too-short phases, duplicate upload, and UTC-naive timestamps.

- [ ] **Step 2: Run and verify route-not-found failure**

```bash
pytest tests/test_task_session_hrv.py -q
```

Expected: 404 before the router exists.

- [ ] **Step 3: Implement parsing and time-to-index conversion**

```python
class PolarRecordingMetadataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["polar-task-capture-v1"]
    recorder_version: str = Field(min_length=1, max_length=64)
    capture_id: UUID
    external_session_id: UUID
    participant_id: str = Field(pattern=r"^P[0-9]{2,6}$")
    recording_start_utc: AwareDatetime
    recording_end_utc: AwareDatetime
    start_monotonic_ns: int = Field(ge=0)
    end_monotonic_ns: int = Field(gt=0)
    first_rr_received_monotonic_ns: int | None = Field(default=None, ge=0)
    last_rr_received_monotonic_ns: int | None = Field(default=None, ge=0)
    device_identifier_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    rr_count: int = Field(ge=30)
    rr_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class UtcSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: Literal["baseline", "task", "recovery"]
    start_utc: AwareDatetime
    end_utc: AwareDatetime


class SegmentIndex(BaseModel):
    label: Literal["baseline", "task", "recovery"]
    start_idx: int = Field(ge=0)
    end_idx: int = Field(ge=1)


class PhaseHrvMetrics(BaseModel):
    mean_hr_bpm: float | None
    rmssd_ms: float | None
    lnrmssd: float | None
    artifact_percentage: float
    usable_coverage_pct: float


class HrvTaskQuality(BaseModel):
    status: Literal["good", "moderate", "poor"]
    artifact_percentage: float
    usable_rr_count: int
    reason_codes: list[str]


class TaskSessionHrvRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal["task-session-hrv-v1"]
    external_session_id: UUID
    participant_id: str = Field(pattern=r"^P[0-9]{2,6}$")
    rr_filename: str = Field(min_length=1, max_length=255)
    rr_content: str = Field(min_length=1, max_length=5_000_000)
    rr_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    timing: PolarRecordingMetadataRequest
    segments: list[UtcSegment] = Field(min_length=3, max_length=3)


class TaskSessionHrvResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal["task-session-hrv-v1"]
    external_session_id: UUID
    participant_id: str
    measurement_id: str
    rr_file_sha256: str
    rr_count: int
    recording_start_utc: AwareDatetime
    segment_indices: list[SegmentIndex]
    phase_metrics: dict[Literal["baseline", "task", "recovery"], PhaseHrvMetrics]
    delta_lnrmssd_baseline_task: float | None
    delta_lnrmssd_task_recovery: float | None
    quality: HrvTaskQuality


def segment_indices(rr_ms: Sequence[float], recording_start: datetime, segments: Sequence[UtcSegment]) -> list[SegmentIndex]:
    cumulative = np.cumsum(np.asarray(rr_ms, dtype=float)) / 1000.0
    output = []
    for segment in segments:
        start_s = (segment.start_utc - recording_start).total_seconds()
        end_s = (segment.end_utc - recording_start).total_seconds()
        start_idx = int(np.searchsorted(cumulative, start_s, side="left"))
        end_idx = int(np.searchsorted(cumulative, end_s, side="right") - 1)
        if start_idx < 0 or end_idx <= start_idx:
            raise TaskSessionHrvError("segment_too_short")
        output.append(SegmentIndex(segment.label, start_idx, end_idx))
    return output
```

Validate canonical UTC, hash, participant/session consistency, non-overlap, required labels, and RR count.

- [ ] **Step 4: Refactor existing upload logic into a shared service**

Move persistence operations used by `/hrv/upload` into a callable service without changing the existing endpoint response. The new endpoint supplies `measurement_id=external_session_id`, `user_id=participant_id`, and the exact start timestamp, then computes per-phase mean HR, RMSSD, `lnRMSSD`, artifact percentage, and baseline/task/recovery deltas. Store the external session and segment contract in `analysis_settings_json`.

- [ ] **Step 5: Generate and validate the JSON Schema**

Export Pydantic `model_json_schema()` to `docs/contracts/task-session-hrv-v1.schema.json`. Test the committed schema against a known request and response with `jsonschema` only if already installed; otherwise compare the generated canonical JSON SHA-256 in the test.

- [ ] **Step 6: Run focused and backward-compatibility tests**

```bash
pytest tests/test_task_session_hrv.py tests/test_workload_state.py tests/test_research_windowed_endpoint.py -q
```

- [ ] **Step 7: Record the HRV contract checkpoint when authorized**

```bash
git add app/task_session_hrv.py api/task_session_hrv.py api/main.py api/research_endpoints.py tests/test_task_session_hrv.py docs/contracts/task-session-hrv-v1.schema.json README.md
git commit -m "feat(hrv): analyze timestamped external task sessions"
```

Before returning to MATB, record the HRV commit SHA or working-tree patch hash and the JSON Schema SHA-256 in the execution log.

---

### Task 14: Link Polar data through a backend-only MATB HRV client

**Repository:** `/root/repos/MATB`

**Files:**
- Create: `webui/backend/app/hrv_task_client.py`
- Modify: `webui/backend/app/liftoff_schemas.py`
- Modify: `webui/backend/app/liftoff_runtime.py`
- Modify: `webui/backend/app/routers/liftoff.py`
- Modify: `webui/backend/tests/test_liftoff_endpoints.py`
- Modify: `webui/backend/tests/test_liftoff_failures.py`

**Interfaces:**
- Consumes: HRV `task-session-hrv-v1` from Task 13.
- Produces: `HrvTaskClient.analyze`, pending/retry linkage, and `physiology-link.json`.

- [ ] **Step 1: Write failing success/outage/mismatch tests**

```python
@pytest.mark.anyio
async def test_hrv_link_persists_authoritative_response(liftoff_client, hrv_mock):
    hrv_mock.respond_with(valid_hrv_response(measurement_id="hrv-123"))
    response = await upload_polar_link(liftoff_client, session_id=SESSION_ID)
    assert response.status_code == 200
    assert response.json()["hrv_measurement_id"] == "hrv-123"
    assert response.json()["sync_quality"] == "good"


@pytest.mark.anyio
async def test_hrv_outage_leaves_retryable_pending_link(liftoff_client, hrv_mock):
    hrv_mock.raise_connect_error()
    response = await upload_polar_link(liftoff_client, session_id=SESSION_ID)
    assert response.status_code == 202
    assert response.json()["status"] == "pending"
```

- [ ] **Step 2: Run and verify missing client failures**

```bash
PYTHONPATH=.:webui/backend .venv-suas/bin/pytest webui/backend/tests/test_liftoff_endpoints.py webui/backend/tests/test_liftoff_failures.py -q -k hrv
```

- [ ] **Step 3: Implement the backend-only client**

```python
class HrvTaskClient:
    def __init__(self, *, base_url: str, token: str, timeout_seconds: float = 30.0) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
            raise ValueError("invalid_hrv_api_url")
        if not token or timeout_seconds <= 0:
            raise ValueError("invalid_hrv_client_configuration")
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout_seconds

    async def analyze(self, request: TaskSessionHrvRequest) -> TaskSessionHrvResponse:
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            response = await client.post("/api/research/hrv/task-sessions/analyze", json=request.model_dump(mode="json"), headers=headers)
        if response.status_code >= 500:
            raise HrvTaskTemporaryError("hrv_unavailable")
        if response.status_code != 200:
            raise HrvTaskContractError("hrv_contract_rejected")
        return TaskSessionHrvResponse.model_validate(response.json())
```

Read `HRV_API_URL` and `HRV_API_TOKEN` at startup; never return the token or base URL.

- [ ] **Step 4: Implement upload validation and pending retry**

Accept RR text and metadata JSON as multipart files with bounded sizes. Verify both hashes before calling HRV. On temporary error, atomically store a private pending request artifact under the session root with owner-only permissions and return 202. Add `POST /liftoff/sessions/{id}/physiology-link/retry`; delete the pending request only after the response and `physiology-link.json` are durable.

- [ ] **Step 5: Grade synchronization**

Use common monotonic origins when present. Return `good` at uncertainty ≤100 ms and loss <1%; `acceptable` at uncertainty ≤1 s and loss <5%; `poor` otherwise; `missing` when no link exists. Never promote a poor link to event-level analysis.

- [ ] **Step 6: Run contract tests against the recorded HRV schema fixture**

```bash
PYTHONPATH=.:webui/backend .venv-suas/bin/pytest webui/backend/tests/test_liftoff_endpoints.py webui/backend/tests/test_liftoff_failures.py -q -k "hrv or physiology or sync"
```

- [ ] **Step 7: Record the checkpoint when authorized**

```bash
git add webui/backend/app/hrv_task_client.py webui/backend/app/liftoff_schemas.py webui/backend/app/liftoff_runtime.py webui/backend/app/routers/liftoff.py webui/backend/tests/test_liftoff_endpoints.py webui/backend/tests/test_liftoff_failures.py
git commit -m "feat(liftoff): link authoritative Polar task analysis"
```

---

### Task 15: Integrate Liftoff completion, metrics, and exports

**Repository:** `/root/repos/MATB`

**Files:**
- Modify: `webui/backend/app/completeness.py`
- Modify: `webui/backend/app/routers/tracker.py`
- Modify: `webui/backend/app/routers/exports.py`
- Modify: `webui/backend/app/routers/metrics.py`
- Modify: `webui/backend/tests/test_completeness.py`
- Modify: `webui/backend/tests/test_endpoints.py`
- Modify: `webui/frontend/src/types/index.ts`
- Modify: `webui/frontend/src/lib/tracker.ts`
- Modify: `webui/frontend/src/components/tracker/CompletenessGrid.tsx`

**Interfaces:**
- Produces: Liftoff completion per participant/visit, `liftoff_metrics_long`, physiology-link provenance, and combined research-bundle entries.

- [ ] **Step 1: Write failing tracker/export tests**

```python
def test_research_context_includes_liftoff_three_visit_grid(client, sealed_liftoff_session):
    context = client.get("/exports/research-context").json()
    assert len(context["liftoff_tracker"]) == 3
    assert context["liftoff_tracker"][0]["visit_code"] == "T0"
    assert context["liftoff_tracker"][0]["present"] is True
    assert context["liftoff_metrics_long"]
    assert context["liftoff_tracker"][0]["hrv_measurement_id"] == "hrv-123"
```

- [ ] **Step 2: Run and verify missing Liftoff context fields**

```bash
PYTHONPATH=.:webui/backend .venv-suas/bin/pytest webui/backend/tests/test_completeness.py webui/backend/tests/test_endpoints.py -q -k liftoff
```

- [ ] **Step 3: Add derived Liftoff completeness**

For every participant and protocol visit, return attempt count, first valid session ID, status, validity, metric presence, HRV link presence, and sync grade. Missingness remains derived and is not filled with synthetic values.

- [ ] **Step 4: Add long-form component metrics and bundle entries**

Flatten only scalar component metrics with fields:

```json
{
  "participant_id": "P01",
  "visit_ordinal": 1,
  "visit_code": "T0",
  "session_id": "uuid",
  "metric": "median_lap_time_s",
  "value": 61.2,
  "unit": "s",
  "metric_version": "liftoff-metrics-v1",
  "source": "visible_result"
}
```

Include Liftoff manifests, quality, metrics, deviations, artifact hashes, and physiology links in the research bundle. Keep raw telemetry in the explicit session bundle, not the summary bundle.

- [ ] **Step 5: Update tracker UI**

Display one Liftoff status cell alongside LOW/MEDIUM/HIGH for each visit. Use distinct states for absent, pending, partial, invalid, valid-no-HRV, valid-poor-sync, and valid-good-sync.

- [ ] **Step 6: Run backend/frontend tests and build**

```bash
PYTHONPATH=.:webui/backend .venv-suas/bin/pytest webui/backend/tests/test_completeness.py webui/backend/tests/test_endpoints.py -q
cd webui/frontend
npm test -- src/lib/tracker.test.ts src/components/tracker
npm run typecheck
npm run build
```

Execute the frontend commands from `webui/frontend`; the `cd` line is explanatory and should be run as a separate shell action.

- [ ] **Step 7: Record the checkpoint when authorized**

```bash
git add webui/backend/app/completeness.py webui/backend/app/routers/tracker.py webui/backend/app/routers/exports.py webui/backend/app/routers/metrics.py webui/backend/tests/test_completeness.py webui/backend/tests/test_endpoints.py webui/frontend/src/types/index.ts webui/frontend/src/lib/tracker.ts webui/frontend/src/components/tracker/CompletenessGrid.tsx
git commit -m "feat(liftoff): expose longitudinal completion and exports"
```

---

### Task 16: Implement the prespecified Liftoff longitudinal analysis

**Repository:** `/root/repos/MATB`

**Files:**
- Create: `matb_integration/analysis/liftoff.py`
- Create: `tests/analysis_stats/test_liftoff.py`
- Create: `webui/backend/tests/test_liftoff_analysis_endpoint.py`
- Modify: `webui/backend/app/routers/analysis.py`
- Modify: `webui/backend/app/routers/exports.py`

**Interfaces:**
- Produces: `LIFTOFF_ANALYSIS_VERSION = "liftoff-analysis-v1"`, `run_liftoff_analysis(metric_rows, participant_context)`, and `POST /analysis/liftoff/run`.
- Continuous model: `outcome ~ C(visit_code) + C(sequence) + prior_fpv_experience + (1 | participant_id)`.
- Count model: hierarchical Poisson when dispersion is acceptable; hierarchical negative binomial when variance exceeds 1.5 times the mean.

- [ ] **Step 1: Write failing model-selection and artifact tests**

```python
def test_liftoff_analysis_runs_three_visit_mixed_model():
    rows, context = synthetic_liftoff_cohort(participants=12, visits=("T0", "DM8", "DM15"))
    artifact = run_liftoff_analysis(rows, context)
    assert artifact["analysis_version"] == "liftoff-analysis-v1"
    assert artifact["status"] == "ok"
    assert artifact["continuous"]["median_lap_time_s"]["formula"] == (
        "value ~ C(visit_code) + C(sequence) + prior_fpv_experience"
    )
    assert [contrast["name"] for contrast in artifact["continuous"]["median_lap_time_s"]["contrasts"]] == [
        "T0_vs_DM8", "T0_vs_DM15", "DM8_vs_DM15"
    ]
    assert "classifier" not in json.dumps(artifact).lower()


def test_overdispersed_counts_select_negative_binomial():
    assert select_count_family(np.array([0, 0, 1, 1, 2, 12, 15])) == "negative_binomial"
```

Add an insufficient-data test requiring at least three participants with two observed visits; no imputation is permitted.

- [ ] **Step 2: Run and verify missing analysis module failures**

```bash
PYTHONPATH=. .venv-suas/bin/pytest tests/analysis_stats/test_liftoff.py -q
```

- [ ] **Step 3: Implement continuous random-intercept models**

```python
LIFTOFF_ANALYSIS_VERSION = "liftoff-analysis-v1"


def fit_continuous(df: pd.DataFrame, outcome: str) -> dict[str, object]:
    subset = df.loc[df["metric"] == outcome].dropna(subset=["value"]).copy()
    if subset["participant_id"].nunique() < 3 or subset["visit_code"].nunique() < 2:
        return {"status": "insufficient_data", "outcome": outcome}
    subset["prior_fpv_experience"] = np.log1p(subset["prior_fpv_hours"].astype(float))
    formula = "value ~ C(visit_code) + C(sequence) + prior_fpv_experience"
    result = smf.mixedlm(formula, subset, groups=subset["participant_id"]).fit(reml=True)
    return serialize_mixedlm(result, outcome=outcome, formula=formula, contrasts=(
        ("T0_vs_DM8", "T0", "DM8"),
        ("T0_vs_DM15", "T0", "DM15"),
        ("DM8_vs_DM15", "DM8", "DM15"),
    ))
```

Report coefficients, 95% confidence intervals, standardized effects, random-intercept variance, residual variance, convergence, and all three prespecified contrasts.

- [ ] **Step 4: Implement hierarchical count models with a fixed seed**

```python
def select_count_family(values: np.ndarray) -> str:
    mean = float(values.mean())
    variance = float(values.var(ddof=1)) if values.size > 1 else 0.0
    return "negative_binomial" if mean > 0 and variance > 1.5 * mean else "poisson"


def fit_count(df: pd.DataFrame, outcome: str, *, seed: int = 20260817) -> dict[str, object]:
    subset, X, participant_index = count_design_matrix(df, outcome)
    family = select_count_family(subset["value"].to_numpy(dtype=float))
    with pm.Model() as model:
        beta = pm.Normal("beta", mu=0.0, sigma=1.5, shape=X.shape[1])
        sigma_participant = pm.HalfNormal("sigma_participant", sigma=1.0)
        participant_offset = pm.Normal(
            "participant_offset", mu=0.0, sigma=sigma_participant,
            shape=subset["participant_id"].nunique(),
        )
        mu = pm.math.exp(pm.math.dot(X, beta) + participant_offset[participant_index])
        if family == "negative_binomial":
            alpha = pm.Exponential("alpha", 1.0)
            pm.NegativeBinomial("observed", mu=mu, alpha=alpha, observed=subset["value"])
        else:
            pm.Poisson("observed", mu=mu, observed=subset["value"])
        trace = pm.sample(draws=1000, tune=1000, chains=4, cores=1, random_seed=seed, target_accept=0.9)
    return serialize_count_posterior(trace, subset, X, outcome=outcome, family=family)
```

Gate publication output on `r_hat <= 1.01`, bulk ESS ≥400, and zero unresolved divergences. Keep a deterministic reduced-draw test configuration separate from production settings.

- [ ] **Step 5: Assemble the versioned artifact and multiplicity control**

Primary outcomes remain valid laps, median lap time, best lap time, lap-completion proportion, and restart count. Apply Benjamini–Hochberg FDR only to secondary telemetry/physiology families. Store library versions, input fingerprint, exclusions, missingness, model diagnostics, and exploratory caveats.

- [ ] **Step 6: Add backend endpoint and research-bundle inclusion**

`POST /analysis/liftoff/run` collects first-valid-attempt metric rows and participant context, computes a SHA-256 fingerprint, reuses a cached `AnalysisResult` with the same fingerprint/version, and returns the artifact. `exports.py` includes the latest Liftoff artifact separately from the existing MATB analysis.

- [ ] **Step 7: Run focused analysis and endpoint tests**

```bash
PYTHONPATH=.:webui/backend .venv-suas/bin/pytest tests/analysis_stats/test_liftoff.py webui/backend/tests/test_liftoff_analysis_endpoint.py -q
```

Expected: deterministic fixtures pass; production sampling settings remain recorded in the artifact.

- [ ] **Step 8: Record the checkpoint when authorized**

```bash
git add matb_integration/analysis/liftoff.py tests/analysis_stats/test_liftoff.py webui/backend/app/routers/analysis.py webui/backend/app/routers/exports.py webui/backend/tests/test_liftoff_analysis_endpoint.py
git commit -m "feat(liftoff): add prespecified longitudinal analysis"
```

---

### Task 17: Add complete browser and synthetic-system verification

**Repository:** `/root/repos/MATB`

**Files:**
- Create: `webui/frontend/e2e/liftoff.spec.ts`
- Create: `webui/backend/tests/test_liftoff_system.py`
- Modify: `scripts/test_suas_offline.sh` only if a generic local-stack helper is required; do not couple Liftoff tests to native sUAS startup.

**Interfaces:**
- Produces: deterministic end-to-end evidence without requiring the commercial application in CI.

- [ ] **Step 1: Write the failing system test**

The backend test starts a synthetic 60 Hz UDP sender, creates a participant/session, advances baseline/task/recovery, submits results/questionnaires, mocks a good HRV response, seals the session, verifies every checksum, and re-decodes raw frames to match canonical JSONL.

```python
@pytest.mark.anyio
async def test_full_liftoff_collection_round_trip(liftoff_client, synthetic_sender, hrv_mock):
    session, lease = await create_ready_session(liftoff_client, synthetic_sender)
    await complete_three_phases(liftoff_client, session, lease)
    await submit_verified_results(liftoff_client, session, lease)
    await attach_good_hrv(liftoff_client, session, lease, hrv_mock)
    debrief = await seal(liftoff_client, session, lease)
    assert debrief["validity"] == "valid"
    assert verify_session_bundle(debrief["artifact_root"]) == ()
    assert raw_redecode_matches_jsonl(debrief["artifact_root"])
```

- [ ] **Step 2: Implement the Playwright path**

The browser test covers setup, session storage lease, phase transitions, telemetry warning recovery, result screenshot, Polar pending then successful retry, NASA-TLX, seal, and bundle download. Assert no console errors and run an Axe accessibility scan on setup, session, and debrief.

- [ ] **Step 3: Run focused system verification**

```bash
PYTHONPATH=.:webui/backend .venv-suas/bin/pytest webui/backend/tests/test_liftoff_system.py -q
```

- [ ] **Step 4: Run all Liftoff Python and frontend tests**

```bash
PYTHONPATH=.:webui/backend .venv-suas/bin/pytest tests/liftoff webui/backend/tests/test_liftoff_models.py webui/backend/tests/test_liftoff_endpoints.py webui/backend/tests/test_liftoff_failures.py webui/backend/tests/test_liftoff_system.py -q
```

From `webui/frontend`:

```bash
npm test -- src/lib/liftoff src/components/liftoff src/lib/tracker.test.ts
npm run typecheck
npm run build
npm run test:e2e -- liftoff.spec.ts
```

- [ ] **Step 5: Run native sUAS and OpenMATB regression gates**

```bash
PYTHONPATH=. .venv-suas/bin/pytest tests/suas -q
PYTHONPATH=.:webui/backend .venv-suas/bin/pytest webui/backend/tests/test_ingestion.py webui/backend/tests/test_fit_trigger.py webui/backend/tests/test_simulation_endpoints.py -q
```

- [ ] **Step 6: Record the checkpoint when authorized**

```bash
git add webui/frontend/e2e/liftoff.spec.ts webui/backend/tests/test_liftoff_system.py
git commit -m "test(liftoff): verify complete ASTRA collection path"
```

---

### Task 18: Characterize the commercial telemetry and run hardware acceptance

**Repository:** `/root/repos/MATB`

**Files:**
- Create: `scripts/capture_liftoff_fixture.py`
- Create: `scripts/run_liftoff_acceptance.py`
- Create: `tests/liftoff/fixtures/commercial_everything_v1.bin`
- Create: `docs/research/liftoff/PILOT_ACCEPTANCE_TEMPLATE.md`
- Modify: `matb_integration/liftoff/protocol.py` only if commercial evidence contradicts the preliminary layout.

**Interfaces:**
- Produces: a reviewed commercial golden fixture, characterization report, and pass/fail acceptance JSON.

- [ ] **Step 1: Implement the fixture-capture script**

```python
def main() -> int:
    args = parse_args()
    packets = capture_packets(host="127.0.0.1", port=args.port, count=args.count, timeout=args.timeout)
    diagnostics = characterize_packets(packets)
    write_framed_fixture(args.output, packets)
    write_json_artifact(args.report, diagnostics)
    return 0 if diagnostics["single_packet_size"] and diagnostics["finite_values"] else 1
```

The script records packet-size distribution, rate, simulator-time monotonicity, stationary values, individual-axis maneuvers, motor count, and raw hashes. It never accesses Liftoff files or memory.

- [ ] **Step 2: Capture a commercial all-fields fixture**

Run on the Windows ASTRA workstation while Liftoff emits its documented full profile:

```powershell
python scripts/capture_liftoff_fixture.py --port 9001 --count 1200 --output tests/liftoff/fixtures/commercial_everything_v1.bin --report exports/liftoff-characterization.json
```

Expected: one stable packet size, finite values, monotonic simulator time, and a report identifying unresolved units/frames explicitly.

- [ ] **Step 3: Confirm or revise the decoder through a failing fixture test**

Add a test that decodes every commercial frame. If the preliminary layout is wrong, first assert the observed mismatch, then change the profile/version and decoder. Do not silently keep the `v1` name after an incompatible change.

- [ ] **Step 4: Implement and run the acceptance script**

The script performs a 30-minute telemetry soak and records packet loss, maximum gap, invalid packets, queue overflows, monotonic/UTC clock behavior, checksum status, and bundle recovery after intentional UDP interruption.

```powershell
python scripts/run_liftoff_acceptance.py --protocol astra-2026 --duration-min 30 --output exports/liftoff-acceptance.json
```

Pass criteria: median loss below 1%, zero schema errors, zero unrecoverable bundles, no clock step, and valid checksum verification on a second machine.

- [ ] **Step 5: Exercise failure cards manually**

Record evidence for Bluetooth disconnect, UDP interruption, Liftoff crash/restart, MATB backend restart, offline Steam operation, visible stutter, forced partial seal, and later HRV retry. Each card must produce the exact validity/deviation state specified in the design.

- [ ] **Step 6: Run four-person calibration pilot**

Each of at least four pilot users completes three sessions. Fill the acceptance template and confirm median loss <1%, HRV linkage ≥90%, no severe simulator-sickness event, 70–90% track completion, and successful second-operator SOP completion.

- [ ] **Step 7: Record the checkpoint when authorized**

```bash
git add scripts/capture_liftoff_fixture.py scripts/run_liftoff_acceptance.py tests/liftoff/fixtures/commercial_everything_v1.bin docs/research/liftoff/PILOT_ACCEPTANCE_TEMPLATE.md matb_integration/liftoff/protocol.py
git commit -m "test(liftoff): characterize commercial telemetry and acceptance"
```

Do not commit participant or identifiable pilot data; commit only de-identified fixtures and templates whose reuse is permitted.

---

### Task 19: Publish the collection SOP and update canonical documentation

**Repositories:** `/root/repos/MATB`, `/root/repos/HRV`, then `/root/repos/obsidian`

**Files:**
- Create: `MATB/docs/research/liftoff/ASTRA_LIFTOFF_SOP.md`
- Modify: `MATB/README.md`
- Modify: `MATB/webui/README.md`
- Modify: `MATB/webui/frontend/README.md`
- Modify: `HRV/README.md`
- Modify after acceptance: `obsidian/Research/ASTRA/Manual de Operaciones/Manual de Operaciones ASTRA 2026.md`
- Modify after acceptance: `obsidian/Research/ASTRA/Protocolo/Metodos.md`

**Interfaces:**
- Produces: operator-facing SOP, deployment configuration, recovery cards, and canonical ASTRA protocol language.

- [ ] **Step 1: Write the SOP from verified behavior**

The SOP must contain workstation preparation, neutral Steam account, controller calibration, frozen Liftoff configuration, Polar start/sidecar confirmation, participant/visit selection, familiarization, 5/15/5 timing, task-order sequence, result screenshot, NASA-TLX, HRV linkage, quality review, seal, recovery, retake rules, and shutdown.

- [ ] **Step 2: Add exact deployment environment documentation**

Document:

```text
MATB_STUDY_PROTOCOL=astra-2026
MATB_DB_PATH=C:\ASTRA\data\matb_astra_2026.db
MATB_LIFTOFF_OUTPUT_DIR=C:\ASTRA\data\liftoff_sessions
MATB_LIFTOFF_HOST=127.0.0.1
MATB_LIFTOFF_PORT=9001
HRV_API_URL=http://127.0.0.1:8180
```

The documentation must state that the two Windows paths are the approved workstation defaults and require an intentional deployment change on another host. `HRV_API_TOKEN` is mandatory but receives no example value; inject it through the operating-system secret environment and never commit or print it.

- [ ] **Step 3: Update README limitations and evidence boundaries**

State that Liftoff telemetry units/frames are valid only after the characterized profile, HRV is descriptive/evidence-bounded, raw telemetry is not a fitness decision, and six-visit databases require the compatibility profile.

- [ ] **Step 4: Update the Obsidian canonical protocol only after release gates pass**

Add Liftoff at T0/DM8/DM15, 5/15/5 baseline-task-recovery, fixed two-sequence MATB/Liftoff order, familiarization criterion, primary outcomes, HRV linkage, technical validity rules, and exploratory-analysis language. Preserve the vault's existing source citations and privacy conventions.

- [ ] **Step 5: Run documentation consistency checks**

```bash
rg -n "6 visits|0/3/6/9/12/15|DM7|T1.*DM7" MATB/README.md MATB/webui MATB/docs/research/liftoff HRV/README.md "obsidian/Research/ASTRA/Manual de Operaciones/Manual de Operaciones ASTRA 2026.md" "obsidian/Research/ASTRA/Protocolo/Metodos.md"
```

Review every match. Legacy-history references must be explicitly labeled; active protocol references must say T0/DM8/DM15.

- [ ] **Step 6: Run final repository gates**

MATB:

```bash
PYTHONPATH=.:webui/backend .venv-suas/bin/pytest tests/liftoff webui/backend/tests/test_liftoff_models.py webui/backend/tests/test_liftoff_endpoints.py webui/backend/tests/test_liftoff_failures.py webui/backend/tests/test_liftoff_system.py -q
PYTHONPATH=. .venv-suas/bin/pytest tests/suas -q
```

HRV:

```bash
pytest tests/test_polar_h10_recording_metadata.py tests/test_task_session_hrv.py tests/test_workload_state.py -q
```

Frontend from `MATB/webui/frontend`:

```bash
npm test
npm run typecheck
npm run build
npm run test:e2e -- liftoff.spec.ts
```

- [ ] **Step 7: Record documentation checkpoints only when authorized**

Use separate commits per repository:

```bash
git add README.md webui/README.md webui/frontend/README.md docs/research/liftoff/ASTRA_LIFTOFF_SOP.md docs/research/liftoff/PILOT_ACCEPTANCE_TEMPLATE.md
git commit -m "docs(liftoff): publish ASTRA collection SOP"
```

```bash
git add README.md
git commit -m "docs(hrv): document Liftoff task-session linkage"
```

```bash
git add "Research/ASTRA/Manual de Operaciones/Manual de Operaciones ASTRA 2026.md" "Research/ASTRA/Protocolo/Metodos.md"
git commit -m "docs(astra): add three-visit Liftoff protocol"
```

Run each command only from its repository and only with explicit commit authorization.

---

## Specification coverage map

| Approved design requirement | Implementing tasks |
|---|---|
| Three visits and legacy-database isolation | 1–3 |
| Structured task sequence and prior experience | 2–3, 11, 16 |
| Domain-neutral atomic artifacts | 4 |
| Strict commercial telemetry contract | 5, 18 |
| Loopback receiver and quality grades | 6, 10, 18 |
| Component performance metrics, no composite | 7 |
| Append-only lifecycle, partial recovery, sealed bundle | 8–10 |
| Liftoff SQL metadata, attempts, first-valid rule | 9–10 |
| Setup/session/debrief workflow | 10–11 |
| Precise Polar timing and authoritative HRV analysis | 12–14 |
| Baseline/task/recovery synchronization grades | 12–14 |
| Longitudinal completion, metrics, and exports | 15 |
| Prespecified continuous/count analysis and contrasts | 16 |
| Unit, integration, browser, regression, and accessibility gates | 17 |
| Commercial fixture, hardware soak, failure cards, pilot gate | 18 |
| Security, permission, SOP, and canonical ASTRA documentation | 10, 14, 18–19 |

Every approved design section maps to at least one task. The two-repository boundary is explicit at Tasks 12–14, and no task requires a cross-repository atomic commit.

## Final release checklist

- [ ] New ASTRA database is bound to `astra-2026` and generates only T0/DM8/DM15.
- [ ] Legacy six-visit database opens only with its compatibility profile.
- [ ] Commercial Liftoff all-fields fixture passes strict decoding.
- [ ] Raw packet re-decoding matches canonical JSONL.
- [ ] Session lifecycle and partial recovery are append-only and checksum-valid.
- [ ] Primary visible outcomes retain screenshot/observer provenance.
- [ ] Telemetry metrics report `liftoff-metrics-v1` and never emit a composite score.
- [ ] Polar sidecar preserves UTC, monotonic timing, UUID, pseudonym, and hashes.
- [ ] MATB stores the authoritative returned HRV measurement ID and link hash.
- [ ] HRV legacy probability is absent from the Liftoff outcome contract.
- [ ] Sync grade follows the 100 ms / 1 s thresholds.
- [ ] HRV outage leaves a retryable pending link without blocking flight evidence.
- [ ] Native sUAS and OpenMATB regression gates pass.
- [ ] Frontend unit, type, build, accessibility, and e2e gates pass.
- [ ] Thirty-minute hardware soak and failure cards pass.
- [ ] Four-person calibration pilot meets every release threshold.
- [ ] Written institutional research-use permission is retained outside the code bundle.
- [ ] ASTRA SOP and canonical protocol are updated only after acceptance.
