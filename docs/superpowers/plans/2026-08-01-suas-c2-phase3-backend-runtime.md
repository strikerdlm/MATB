# sUAS C2 Phase 3 — FastAPI Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose one persisted, controller-leased sUAS session through reliable FastAPI lifecycle/command endpoints and an ordered real-time WebSocket stream.

**Architecture:** A process-local `SimulationManager` owns one authoritative engine, recorder, 10 Hz tick task, and independent 4 Hz snapshot task. SQLModel persists low-rate metadata through a repository adapter; a bounded async hub fans already-recorded envelopes to one controller and optional observers.

**Tech Stack:** Python 3.12, FastAPI 0.110.3, Starlette 0.37.2, AnyIO 4.3, SQLModel 0.0.16+, SQLite, Phase 1/2 sUAS libraries, pytest/httpx.

## Global Constraints

- Complete and push Phases 1 and 2 first.
- Read the approved design and master interface ledger before editing.
- One active simulation process-wide; one valid controller lease; observers are read-only.
- The manager records and flushes each lifecycle/command/result/event before publishing it.
- Tick and snapshot loops are independent: engine at 100 ms, snapshot publication at 250 ms. Snapshot publication never steps the engine.
- Browser/controller disconnect pauses immediately; reconnect never auto-resumes.
- Stable machine error codes are authoritative; translated copy remains frontend-owned.
- Existing synchronous API tests and routes must continue working.
- Preserve all master-plan Git, offline, CORS, artifact, and pseudonymization constraints.

---

### Task 1: SQLModel simulation metadata and strict API schemas

**Files:**
- Create: `webui/backend/app/simulation_models.py`
- Create: `webui/backend/app/simulation_schemas.py`
- Modify: `webui/backend/app/db.py`
- Create: `webui/backend/tests/test_simulation_models.py`
- Modify: `webui/backend/tests/conftest.py`

**Interfaces:**
- Consumes: existing `Participant`, `Visit`, `get_engine()`, `get_session()`.
- Produces: `SimulationSession`, `SimulationBlock`, `SimulationArtifact`, `ProtocolDeviation`, and Pydantic request/response types named in the master ledger.

- [ ] **Step 1: Write failing metadata constraint and schema tests**

```python
def test_simulation_metadata_round_trip(engine) -> None:
    seed_participant_and_visit(engine)
    with Session(engine) as db:
        row = SimulationSession(
            id="sim-001", participant_id="P01", visit_id=1,
            scenario_id="reference_area_search", scenario_sha256="a" * 64,
            manifest_json="{}", locale="es-CO", lifecycle="PREPARED",
            validity="valid", artifact_root="exports/simulation/sim-001",
        )
        db.add(row)
        db.commit()
        assert db.get(SimulationSession, "sim-001").locale == "es-CO"

def test_block_id_is_unique_per_simulation(engine) -> None:
    seed_simulation_session(engine)
    with Session(engine) as db:
        db.add(SimulationBlock(session_id="sim-001", block_id="LOW",
                               profile="LOW", order_index=1, lifecycle="PREPARED"))
        db.commit()
        db.add(SimulationBlock(session_id="sim-001", block_id="LOW",
                               profile="LOW", order_index=2, lifecycle="PREPARED"))
        with pytest.raises(IntegrityError):
            db.commit()

def test_create_schema_rejects_real_identity_and_invalid_locale() -> None:
    with pytest.raises(ValidationError):
        CreateSimulationSession(participant_id="John Smith", visit_ordinal=1,
                                scenario_id="reference_area_search", locale="en")
    with pytest.raises(ValidationError):
        CreateSimulationSession(participant_id="P01", visit_ordinal=1,
                                scenario_id="reference_area_search", locale="fr")
```

- [ ] **Step 2: Run tests and confirm missing models**

Run: `cd webui/backend && python3 -m pytest tests/test_simulation_models.py -q`

Expected: FAIL importing `app.simulation_models`.

- [ ] **Step 3: Implement explicit table names and constraints**

```python
class SimulationSession(SQLModel, table=True):
    __tablename__ = "simulation_session"
    id: str = Field(primary_key=True)
    participant_id: str = Field(foreign_key="participant.id", index=True)
    visit_id: int = Field(foreign_key="visit.id", index=True)
    scenario_id: str
    scenario_sha256: str = Field(index=True)
    manifest_json: str
    locale: str
    lifecycle: str = "PREPARED"
    active_block_id: str | None = None
    validity: str = "valid"
    artifact_root: str
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    interrupted_at: datetime | None = None

class SimulationBlock(SQLModel, table=True):
    __tablename__ = "simulation_block"
    __table_args__ = (UniqueConstraint("session_id", "block_id"),)
    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="simulation_session.id", index=True)
    block_id: str
    profile: str
    order_index: int
    lifecycle: str = "PREPARED"
    validity: str = "valid"
    simulation_started_ms: int | None = None
    simulation_finished_ms: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    was_interrupted: bool = False
    recovered_from_checkpoint: int | None = None
    metrics_json: str | None = None

class SimulationArtifact(SQLModel, table=True):
    __tablename__ = "simulation_artifact"
    __table_args__ = (UniqueConstraint("session_id", "relative_path"),)
    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="simulation_session.id", index=True)
    kind: str
    relative_path: str
    sha256: str
    size_bytes: int
    created_at: datetime = Field(default_factory=_utcnow)

class ProtocolDeviation(SQLModel, table=True):
    __tablename__ = "protocol_deviation"
    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="simulation_session.id", index=True)
    block_id: str | None = None
    code: str
    severity: str
    simulation_time_ms: int
    detail_json: str
    disposition: str = "unreviewed"
    created_at: datetime = Field(default_factory=_utcnow)
```

Import `app.simulation_models` alongside `app.models` inside `init_db()` so test and production metadata register all tables.

- [ ] **Step 4: Implement strict request/response models**

Define `JsonValue`, `CreateSimulationSession`, `PreparedSession`, `SessionView`, `LifecycleRequest`, `FinishRequest`, `RecoverRequest`, `RecoveryView`, `CommandRequest`, `CommandResultView`, `ArtifactView`, `ScenarioSummary`, `ScenarioValidationView`, and `ErrorDetail`. Use `ConfigDict(extra="forbid")` everywhere. Lock these fields:

```python
class CreateSimulationSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    participant_id: str = Field(pattern=r"^P[0-9]{2,6}$")
    visit_ordinal: int = Field(ge=1, le=6)
    scenario_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    locale: Literal["en", "es-CO"]

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

class RecoverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checkpoint_version: int = Field(ge=0)
    confirm_process_restart: bool = False

class RecoveryView(SessionView):
    controller_lease: str | None = None

class CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: UUID
    expected_state_version: int = Field(ge=0)
    kind: Literal[
        "ASSIGN_SECTOR", "SET_WAYPOINT", "HOLD", "RESUME_MISSION",
        "RETURN_TO_BASE", "ACKNOWLEDGE_ALERT", "INSPECT_CONTACT",
        "CLASSIFY_CONTACT", "SET_CONTACT_PRIORITY", "REPORT_CONTACT",
    ]
    payload: dict[str, JsonValue]
```

`PreparedSession` uniquely includes the initial `controller_lease`; ordinary `SessionView` never returns it. `RecoveryView` returns a new lease only for an explicitly confirmed process-restart recovery and otherwise returns `null`. `ErrorDetail` has `code`, `message`, and optional `context`.

- [ ] **Step 5: Register test metadata and run model regressions**

Modify the `engine` fixture to import both `app.models` and `app.simulation_models`. Run:

`cd webui/backend && python3 -m pytest tests/test_simulation_models.py tests/test_models.py -q`

Expected: PASS.

- [ ] **Step 6: Commit and push Task 1**

```bash
git add webui/backend/app/simulation_models.py webui/backend/app/simulation_schemas.py webui/backend/app/db.py webui/backend/tests/test_simulation_models.py webui/backend/tests/conftest.py
git diff --cached --check
git commit -m "feat(webui): persist native simulation sessions"
git push origin HEAD
```

### Task 2: Persistence adapter and single-session lifecycle manager

**Files:**
- Create: `webui/backend/app/simulation_persistence.py`
- Create: `webui/backend/app/simulation_runtime.py`
- Create: `webui/backend/tests/test_simulation_runtime.py`

**Interfaces:**
- Consumes: Phase 1/2 engine/recording interfaces, simulation SQLModel tables/schemas.
- Produces: `SimulationPersistence`, `SQLModelSimulationPersistence`, `SimulationManager`, `RuntimeHandle`, `SimulationConflict`, `SimulationNotFound`, `InvalidLease`, `InvalidTransition`.

- [ ] **Step 1: Write failing lifecycle, lease, and independent-loop tests**

```python
@pytest.mark.anyio
async def test_prepare_creates_manifest_rows_and_unreturned_lease_hash(manager, db) -> None:
    prepared = await manager.prepare(create_request(), db)
    assert prepared.lifecycle == "PREPARED"
    assert prepared.controller_lease
    row = db.get(SimulationSession, prepared.id)
    assert row is not None
    assert prepared.controller_lease not in row.manifest_json
    assert {b.block_id for b in db.exec(select(SimulationBlock)).all()} == {
        "PRACTICE", "LOW", "MEDIUM", "HIGH"
    }

@pytest.mark.anyio
async def test_only_one_active_session_and_one_valid_lease(manager, db) -> None:
    first = await manager.prepare(create_request(), db)
    with pytest.raises(SimulationConflict, match="active session"):
        await manager.prepare(create_request(participant_id="P02"), db)
    with pytest.raises(InvalidLease):
        await manager.start(first.id, "PRACTICE", "wrong")

@pytest.mark.anyio
async def test_tick_and_snapshot_schedules_are_independent(manager, prepared_session) -> None:
    await manager.start(prepared_session.id, "PRACTICE", prepared_session.controller_lease)
    await manager.tick_once()
    await manager.tick_once()
    assert (await manager.state(prepared_session.id))["simulation_time_ms"] == 200
    first = await manager.snapshot_once()
    second = await manager.snapshot_once()
    assert first.state_version == second.state_version
```

- [ ] **Step 2: Run runtime tests and confirm missing manager**

Run: `cd webui/backend && python3 -m pytest tests/test_simulation_runtime.py -q`

Expected: FAIL importing `app.simulation_runtime`.

- [ ] **Step 3: Implement persistence protocol and SQLModel adapter**

```python
class SimulationPersistence(Protocol):
    def update_session(self, session_id: str, **fields: object) -> None: ...
    def update_block(self, session_id: str, block_id: str, **fields: object) -> None: ...
    def add_deviation(self, session_id: str, block_id: str | None,
                      code: str, severity: str, simulation_time_ms: int,
                      detail: Mapping[str, object]) -> None: ...
    def replace_artifacts(self, session_id: str,
                          artifacts: Sequence[ArtifactInfo]) -> None: ...
```

`SQLModelSimulationPersistence` receives the SQLAlchemy engine and opens a new short-lived SQLModel `Session` per call. It permits only an explicit allowlist of mutable fields, rolls back on error, and never stores a plaintext controller lease or lease hash.

- [ ] **Step 4: Implement prepare/start/pause/resume/finish state transitions**

`SimulationManager` accepts `scenario_root`, `artifact_root`, `persistence`, `tick_sleep`, `wall_clock`, and `run_background_tasks=True` dependencies. Focused manager/ASGI tests set `run_background_tasks=False` and drive one-shot ticks; production and E2E retain the default. Protect handle mutation with one `asyncio.Lock`. Generate session IDs as `sim-<UTC compact>-<8 lowercase hex>` and leases with `secrets.token_urlsafe(32)`; store only SHA-256 of the lease in the runtime handle.

Allowed transitions:

```text
PREPARED -> RUNNING | ABORTED
RUNNING  -> PAUSED | FINISHED | INTERRUPTED
PAUSED   -> RUNNING | FINISHED | ABORTED | INTERRUPTED
INTERRUPTED -> PAUSED only through explicit recover()
FINISHED/ABORTED -> terminal
```

`prepare()` validates Participant and Visit rows, loads only `<scenario_root>/<scenario_id>.yaml`, derives the parity-tested native `matb_integration.suas.scenarios.profiles.block_order_for_participant()`, writes session/block rows, creates `SessionRecorder(run_dir, manifest, loaded.normalized_yaml)`, and returns the plaintext lease once. `start()` requires the next allowed block, initializes an engine, records lifecycle, and starts tick/snapshot tasks. `pause()` stops simulation advancement without closing the recorder. `finish()` calls full `seal()` only when disposition is `complete`; abort writes lifecycle/deviation, closes the recorder, and calls `seal_partial(reason="aborted")`.

Lifecycle mutations are idempotent for the same completed intent: starting the already-running current block, pausing an already-paused session, resuming an already-running session, or repeating the same terminal finish returns the current view without another record. A different block, reason-sensitive recovery, or conflicting terminal disposition returns `InvalidTransition`.

- [ ] **Step 5: Implement testable 10 Hz and 4 Hz loops**

```python
async def _tick_loop(self) -> None:
    while self._handle and self._handle.lifecycle == "RUNNING":
        started = self._monotonic()
        await self.tick_once()
        await self._sleep(max(0.0, 0.100 - (self._monotonic() - started)))

async def _snapshot_loop(self) -> None:
    while self._handle and self._handle.lifecycle in {"RUNNING", "PAUSED"}:
        await self.snapshot_once()
        await self._sleep(0.250)
```

`submit()` validates the lease, enqueues a command/future pair, and awaits the next `tick_once()` result; it never calls the reducer directly. `tick_once()` drains the queue in receive order, records commands/results/events and due private `engine.checkpoint_snapshot()` values before handing envelopes to the hub added in Task 4, then resolves the corresponding futures. `snapshot_once()` serializes only `engine.snapshot()` without stepping. Track and cancel both tasks cleanly on finish/shutdown; tests call the one-shot methods without starting background loops and explicitly schedule `submit()` before invoking `tick_once()`.

- [ ] **Step 6: Run runtime and model tests**

Run: `cd webui/backend && python3 -m pytest tests/test_simulation_runtime.py tests/test_simulation_models.py -q`

Expected: PASS with no leaked asyncio tasks.

- [ ] **Step 7: Commit and push Task 2**

```bash
git add webui/backend/app/simulation_persistence.py webui/backend/app/simulation_runtime.py webui/backend/tests/test_simulation_runtime.py
git diff --cached --check
git commit -m "feat(webui): orchestrate one simulation runtime"
git push origin HEAD
```

### Task 3: REST scenario, lifecycle, state, command, and artifact endpoints

**Files:**
- Create: `webui/backend/app/routers/simulation.py`
- Modify: `webui/backend/app/main.py`
- Modify: `webui/backend/tests/conftest.py`
- Create: `webui/backend/tests/test_simulation_endpoints.py`

**Interfaces:**
- Consumes: `SimulationManager` and Phase 3 schemas.
- Produces: all REST endpoints in Design §11.1 plus explicit recovery endpoint and `get_simulation_manager()` dependency.

- [ ] **Step 1: Add a same-loop async ASGI fixture and failing endpoint contract tests**

```python
# conftest.py
@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture
async def simulation_client(engine, tmp_path, monkeypatch):
    manager = build_test_manager(engine=engine, artifact_root=tmp_path / "exports")
    app.state.simulation_manager = manager
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, manager
    await manager.shutdown()

@pytest.mark.anyio
async def test_prepare_start_command_state_flow(simulation_client, seeded_participant) -> None:
    client, manager = simulation_client
    prepared = await client.post("/simulation/sessions", json={
        "participant_id": "P01", "visit_ordinal": 1,
        "scenario_id": "reference_area_search", "locale": "en",
    })
    assert prepared.status_code == 201
    body = prepared.json()
    headers = {"X-Simulation-Controller": body["controller_lease"]}
    started = await client.post(f"/simulation/sessions/{body['id']}/start",
                                json={"block_id": "PRACTICE"}, headers=headers)
    assert started.status_code == 200
    command_task = asyncio.create_task(client.post(f"/simulation/sessions/{body['id']}/commands",
        json={"command_id": str(uuid4()), "expected_state_version": 0,
              "kind": "ASSIGN_SECTOR",
              "payload": {"aircraft_id": "UAS-01", "sector_id": "SECTOR-A"}},
        headers=headers))
    await manager.tick_once()
    command = await command_task
    assert command.status_code == 200
    assert command.json()["status"] == "accepted"
    state = await client.get(f"/simulation/sessions/{body['id']}/state")
    assert state.json()["aircraft"]["UAS-01"]["assigned_sector_id"] == "SECTOR-A"
```

Also test unknown participant/scenario (404), invalid YAML upload (422), second session (409), missing/wrong lease (403), stale command (200 with rejected result), duplicate UUID (200 duplicate), impossible lifecycle (409), observer-readable state, path traversal scenario ID rejection, and artifact/debrief 409 before finish.

- [ ] **Step 2: Run endpoint tests and confirm 404 routes**

Run: `cd webui/backend && python3 -m pytest tests/test_simulation_endpoints.py -q`

Expected: FAIL because `/simulation/*` routes are absent.

- [ ] **Step 3: Implement manager dependency and stable exception translation**

```python
def get_simulation_manager(request: Request) -> SimulationManager:
    manager = getattr(request.app.state, "simulation_manager", None)
    if manager is None:
        raise HTTPException(503, detail={"code": "simulation_unavailable",
                                         "message": "simulation runtime is unavailable"})
    return manager
```

Map `SimulationNotFound→404`, `InvalidLease→403`, `SimulationConflict/InvalidTransition→409`, scenario/Pydantic validation→422, and `RecordingError→507`. Each detail body uses `ErrorDetail` with a stable lowercase snake-case code.

- [ ] **Step 4: Implement the complete REST surface**

Create routes:

```text
GET    /simulation/scenarios
POST   /simulation/scenarios/validate
POST   /simulation/sessions                         201
GET    /simulation/sessions/{session_id}
POST   /simulation/sessions/{session_id}/start
POST   /simulation/sessions/{session_id}/pause
POST   /simulation/sessions/{session_id}/resume
POST   /simulation/sessions/{session_id}/recover
POST   /simulation/sessions/{session_id}/finish
POST   /simulation/sessions/{session_id}/commands
GET    /simulation/sessions/{session_id}/state
GET    /simulation/sessions/{session_id}/debrief
GET    /simulation/sessions/{session_id}/artifacts
```

Lifecycle and command endpoints read the lease only from `X-Simulation-Controller`. Recovery also requires that header while a runtime handle exists; only a stale-process recovery may omit it, and then `RecoverRequest.confirm_process_restart` must be true. Scenario validation accepts one UTF-8 file no larger than 1 MiB, calls `load_scenario_text()`, and never installs it. Scenario listing resolves only direct `.yaml` children of the configured root. State/debrief/artifacts never expose hidden contact truth, leases, or absolute filesystem paths.

- [ ] **Step 5: Register router and production manager lifespan**

In `lifespan`, initialize DB, construct `SQLModelSimulationPersistence(get_engine())`, build `SimulationManager` with repo `scenarios/suas` and `MATB_SIMULATION_OUTPUT_DIR` defaulting to repo `exports/simulation`, assign `app.state.simulation_manager`, yield, then `await manager.shutdown()`. Include the router after existing routers.

Preserve the four existing local CORS origins as defaults. Add `MATB_FRONTEND_ORIGINS` as an optional comma-separated list of exact `http://`/`https://` origins; reject credentials, paths, queries, fragments, empty entries, and wildcard origins at startup. Use the same parsed immutable set for HTTP CORS and WebSocket Origin validation. Never use `allow_origins=["*"]`.

- [ ] **Step 6: Run endpoint and existing backend regression tests**

Run: `cd webui/backend && python3 -m pytest tests/test_simulation_endpoints.py tests/test_health.py tests/test_endpoints.py -q`

Expected: PASS.

- [ ] **Step 7: Commit and push Task 3**

```bash
git add webui/backend/app/routers/simulation.py webui/backend/app/main.py webui/backend/tests/conftest.py webui/backend/tests/test_simulation_endpoints.py
git diff --cached --check
git commit -m "feat(webui): expose simulation REST lifecycle"
git push origin HEAD
```

### Task 4: Ordered WebSocket hub, controller/observer streams, and disconnect pause

**Files:**
- Create: `webui/backend/app/websocket/__init__.py`
- Create: `webui/backend/app/websocket/simulation.py`
- Modify: `webui/backend/app/main.py`
- Modify: `webui/backend/app/simulation_runtime.py`
- Create: `webui/backend/tests/test_simulation_hub.py`
- Create: `webui/backend/tests/test_simulation_websocket_unit.py`

**Interfaces:**
- Consumes: recorded runtime outcomes, controller lease validation, FastAPI `WebSocket`.
- Produces: `StreamKind`, `StreamEnvelope`, `SimulationHub.subscribe/publish/unsubscribe`, and `WS /simulation/sessions/{id}/stream`.

- [ ] **Step 1: Write failing bounded-queue and controller-disconnect tests**

```python
@pytest.mark.anyio
async def test_hub_preserves_order_and_initial_snapshot() -> None:
    hub = SimulationHub(queue_size=8)
    sub = await hub.subscribe("sim-1", role="observer", initial=env(10, "snapshot"))
    await hub.publish("sim-1", env(11, "domain_event"))
    assert (await sub.queue.get()).sequence == 10
    assert (await sub.queue.get()).sequence == 11

@pytest.mark.anyio
async def test_slow_observer_is_dropped_without_blocking_controller() -> None:
    hub = SimulationHub(queue_size=1)
    observer = await hub.subscribe("sim-1", role="observer", initial=None)
    controller = await hub.subscribe("sim-1", role="controller", initial=None)
    await hub.publish("sim-1", env(1, "snapshot"))
    await hub.publish("sim-1", env(2, "snapshot"))
    assert observer.closed_code == 4408
    assert (await controller.queue.get()).sequence == 1

@pytest.mark.anyio
async def test_controller_disconnect_pauses_but_observer_disconnect_does_not(manager, running) -> None:
    await manager.controller_disconnected(running.id, running.lease)
    assert (await manager.view(running.id)).lifecycle == "PAUSED"
    await manager.observer_disconnected(running.id)
    assert (await manager.view(running.id)).lifecycle == "PAUSED"
```

- [ ] **Step 2: Run hub tests and confirm missing websocket package**

Run: `cd webui/backend && python3 -m pytest tests/test_simulation_hub.py tests/test_simulation_websocket_unit.py -q`

Expected: FAIL importing `app.websocket.simulation`.

- [ ] **Step 3: Implement ordered envelopes and bounded subscribers**

`StreamEnvelope` is a Pydantic model matching the master JSON contract. `SimulationHub` keeps per-session subscriber objects with an `asyncio.Queue`, role, and close callback. `publish()` iterates a snapshot of subscribers without awaiting queue consumers. On `QueueFull`, close/drop an observer with code 4408; for a controller, request manager pause first, enqueue a fatal `error` if possible, then close 4408. Never let one subscriber delay ticks.

- [ ] **Step 4: Integrate record-before-publish in the manager**

For lifecycle, commands, command results, domain events, alerts, probes, and checkpoints:

```python
record = self._records.next(...)
self._handle.recorder.append(record)
await self._hub.publish(session_id, envelope_from_record(record))
```

Snapshots are not appended at 4 Hz; checkpoints provide persistent state. Snapshot envelopes receive the next transport sequence from a separate monotonic transport counter and include the authoritative event sequence/state version. Document both counters in payload; do not mix transport sequence into replay hashes.

- [ ] **Step 5: Implement the WebSocket endpoint**

The endpoint accepts `lease` and nonnegative `after_sequence` query parameters. Before accept, require the request `Origin` to match the parsed exact frontend-origin set; absent/invalid origin closes 4403. A correct lease registers controller; no lease registers observer; an incorrect lease closes 4403. A second controller closes 4409. After accept, allocate the next transport sequence and send a freshly serialized complete snapshot first, including `resynchronizes_after_sequence` in its payload, then queued envelopes. V1 does not replay transient 4 Hz snapshots; this first snapshot is the explicit resynchronization boundary. On receive, accept only JSON ping messages (`{"kind":"ping"}`) and answer pong; commands stay REST-only. On disconnect/finally, unsubscribe and invoke controller/observer disconnect behavior. Never auto-resume.

- [ ] **Step 6: Run WebSocket unit, manager, and REST tests**

Run: `cd webui/backend && python3 -m pytest tests/test_simulation_hub.py tests/test_simulation_websocket_unit.py tests/test_simulation_runtime.py tests/test_simulation_endpoints.py -q`

Expected: PASS.

- [ ] **Step 7: Commit and push Task 4**

```bash
git add webui/backend/app/websocket webui/backend/app/main.py webui/backend/app/simulation_runtime.py webui/backend/tests/test_simulation_hub.py webui/backend/tests/test_simulation_websocket_unit.py
git diff --cached --check
git commit -m "feat(webui): stream ordered simulation telemetry"
git push origin HEAD
```

### Task 5: Recorder failure pause, explicit checkpoint recovery, and Phase 3 regression gate

**Files:**
- Modify: `matb_integration/suas/recording/records.py`
- Modify: `matb_integration/suas/recording/replay.py`
- Modify: `matb_integration/suas/metrics/mission.py`
- Modify: `webui/backend/app/simulation_runtime.py`
- Modify: `webui/backend/app/simulation_persistence.py`
- Modify: `webui/backend/app/routers/simulation.py`
- Create: `webui/backend/tests/test_simulation_failures.py`
- Modify: `tests/suas/test_replay.py`
- Modify: `tests/suas/test_mission_metrics.py`
- Modify: `webui/backend/README.md`

**Interfaces:**
- Consumes: recorder errors, checkpoints, replay status, recovery endpoint.
- Produces: fail-closed runtime semantics, `recover()` implementation, persisted deviations/validity, documented API.

- [ ] **Step 1: Write failing recorder, exception, restart, and recovery tests**

```python
@pytest.mark.anyio
async def test_recording_error_pauses_before_next_tick(manager, running, monkeypatch) -> None:
    version = (await manager.state(running.id))["state_version"]
    monkeypatch.setattr(manager.active.recorder, "append",
                        Mock(side_effect=RecordingError("disk full")))
    await manager.tick_once()
    assert (await manager.view(running.id)).lifecycle == "INTERRUPTED"
    assert (await manager.state(running.id))["state_version"] == version
    assert manager.persistence.deviations[-1].code == "recording_failure"

@pytest.mark.anyio
async def test_explicit_recovery_restores_checkpoint_and_marks_deviation(manager, interrupted) -> None:
    recovered = await manager.recover(interrupted.id, interrupted.lease,
                                      checkpoint_version=1)
    assert recovered.lifecycle == "PAUSED"
    assert recovered.validity == "valid_with_deviation"
    assert (await manager.state(interrupted.id))["state_version"] == 50

@pytest.mark.anyio
async def test_process_restart_recovery_requires_confirmation_and_returns_new_lease(
    restarted_manager, stale_running_row,
) -> None:
    with pytest.raises(InvalidLease):
        await restarted_manager.recover(
            stale_running_row.id, None, checkpoint_version=1,
            confirm_process_restart=False,
        )
    recovered = await restarted_manager.recover(
        stale_running_row.id, None, checkpoint_version=1,
        confirm_process_restart=True,
    )
    assert recovered.lifecycle == "PAUSED"
    assert recovered.controller_lease
    assert recovered.controller_lease not in stale_running_row.manifest_json
```

Also cover unhandled subsystem exception, missing/corrupt checkpoint, wrong scenario hash, recovery of a non-interrupted session, shutdown with a running session, startup discovery of a DB row left RUNNING after process death, and a recovery whose selected checkpoint precedes otherwise-valid recorded events. The last case must retain those JSONL lines while excluding them from the continued replay/metric result.

- [ ] **Step 2: Run failure tests and confirm behavior is absent**

Run: `cd webui/backend && python3 -m pytest tests/test_simulation_failures.py -q`

Expected: FAIL assertions because failures/recovery are not yet persisted.

- [ ] **Step 3: Implement one fail-closed interruption path**

Create `_interrupt(code, detail, severity="fatal")` that cancels advancement, records the error when the recorder is writable, marks session/block `INTERRUPTED`, updates validity, persists a `ProtocolDeviation`, and publishes the fatal envelope. If recording itself failed, persist through SQLite and publish from memory; never take another engine tick.

Wrap `tick_once`, checkpoint, command append, and lifecycle record operations in narrow exception boundaries that call `_interrupt`. Preserve `CancelledError` during normal shutdown.

- [ ] **Step 4: Implement checkpoint recovery and stale-process startup audit**

`recover(session_id, lease, checkpoint_version, confirm_process_restart=False)` requires INTERRUPTED, treats `checkpoint_version` as the session-global checkpoint ordinal, loads exactly `checkpoint-<version:08d>.json.gz`, validates the closed wrapper, checks scenario/block/engine/hash, and restores `payload["engine"]` with its independent `state_version`. Phase 3 has no research-protocol state yet; Phase 5 extends this path with record-based protocol restoration through `payload["record_sequence"]`. It opens the append-only recorder through `SessionRecorder.open_existing()` and appends `checkpoint_recovery` containing the original interruption/checkpoint plus `invalidated_sequence_start=record_sequence+1` and `invalidated_sequence_end=<last sequence before this recovery>` (or both `null` when empty). It persists the deviation, preserves `SimulationBlock.was_interrupted=True`, sets `valid_with_deviation`, and returns PAUSED. Resume remains a separate call.

Add `effective_records(records)` as a closed two-pass reducer: validate global sequence continuity, collect non-overlapping invalidation ranges from valid recovery records, reject a range that reaches its own recovery record or invalidates an earlier recovery marker, and yield the authoritative branch plus every recovery/deviation audit record. Replay, mission metrics, research metrics, and debrief timelines use it; invalidated records remain available under a separate `invalidated_timeline` audit section and never contribute to outcomes. Replay accepts duplicate command UUIDs only when the prior occurrence lies in an invalidated range.

At application lifespan startup, mark any database session still RUNNING or PAUSED as INTERRUPTED with `process_restart`; do not automatically recreate a controller lease or runtime. For an in-process interruption, `recover` requires the existing lease and returns no new lease. For a stale-process row with no runtime handle, recovery requires `lease=None` plus `confirm_process_restart=True`; it reconstructs only from the frozen manifest/scenario and requested checkpoint, creates a new random lease/hash in memory, and returns the plaintext lease once in `RecoveryView`. A second recovery attempt uses that new lease and normal transition rules. This local confirmation is coordination on a localhost research workstation, not user authentication.

- [ ] **Step 5: Document endpoints and run the complete Phase 3 gate**

Update backend README with the simulation route table, controller header/query behavior, localhost/offline assumptions, recovery semantics, and artifact root environment variable.

Run:

```bash
python3 -m pytest tests/suas -q
python3 -m pytest tests -q
cd webui/backend && python3 -m pytest -q
```

Expected: all suites PASS and no asyncio task-leak warnings appear.

- [ ] **Step 6: Commit and push the Phase 3 gate**

```bash
git add matb_integration/suas/recording/records.py matb_integration/suas/recording/replay.py matb_integration/suas/metrics/mission.py webui/backend/app/simulation_runtime.py webui/backend/app/simulation_persistence.py webui/backend/app/routers/simulation.py webui/backend/tests/test_simulation_failures.py tests/suas/test_replay.py tests/suas/test_mission_metrics.py webui/backend/README.md
git diff --cached --check
git commit -m "feat(webui): fail closed and recover simulation sessions"
git push origin HEAD
```
