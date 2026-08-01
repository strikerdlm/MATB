# sUAS Supervisory C2 Research Simulator V1 Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved offline, bilingual, deterministic, non-kinetic multi-sUAS supervisory C2 research simulator without breaking the existing OpenMATB or research-console workflows.

**Architecture:** A pure-Python fixed-step simulation and artifact library under `matb_integration/suas` is wrapped by a single-session FastAPI runtime and rendered by a full-screen Next.js operator console. Authoritative state remains server-side; REST carries lifecycle and idempotent commands, WebSocket carries ordered snapshots/events, and append-only JSONL plus checkpoints makes every session replayable.

**Tech Stack:** Python 3.12+, dataclasses, Pydantic 2.5+, PyYAML 6+, FastAPI 0.110.3, SQLModel 0.0.16+, SQLite, Next.js 14.2+, React 18.2+, TypeScript 5.3+, Zustand 4.5+, React SVG, Vitest 2.1+, Playwright, pytest 7.4+.

## Global Constraints

- Source of truth: `docs/superpowers/specs/2026-08-01-suas-c2-research-simulator-design.md`.
- Runtime target: one fully offline Linux workstation; development and browser QA run headlessly.
- Mission scope: fictional, non-kinetic ISR only; do not add weapon, engagement, targeting, payload-employment, or damage behavior.
- Fleet bounds: 2–8 aircraft; the reference MEDIUM/default setup uses 4.
- Control boundary: supervisory commands only; no manual flight input.
- Time constants: 100 ms authoritative tick, 250 ms snapshots, 5,000 ms checkpoints.
- Numerical authority: integer milliseconds, millimetres, millidegrees, and integer energy units; UI floats never feed back into state.
- Randomness: independent PCG32 streams seeded from the approved SHA-256 tuple construction.
- Scenario input: strict, versioned, safe-loaded YAML; unknown keys and invalid cross-references fail closed.
- Persistence: SQLite for metadata; append-only JSONL/checkpoints for high-rate records; pseudonymized IDs only; no free text.
- Languages: complete English and es-CO key parity; session language freezes at setup.
- UI: minimum 1280×720, reference 1920×1080, keyboard and mouse operable, status never color-only, reduced motion honored.
- Networking: no runtime internet dependency; bind backend to `127.0.0.1` by default; no remote tiles, fonts, telemetry, or analytics.
- Compatibility: preserve every existing OpenMATB CSV, tracker, analysis, screen, and export workflow.
- Testing: use TDD for every task; run the task's focused tests before its regression gate.
- Git hygiene: inspect `git status --short` before every task; never clean, restore, or stage unrelated user files; never use `git add .`.
- Commit cadence: one focused commit per independently testable task, followed immediately by `git push origin HEAD` after its scoped regression suite passes.
- Stop condition: if a task cannot pass its stated tests, do not commit or push it; diagnose and repair within that task.

---

## Plan Suite and Required Order

| Gate | Detailed plan | Working deliverable |
|---|---|---|
| 1 | `2026-08-01-suas-c2-phase1-core.md` | Strict reference YAML runs through a deterministic headless 2–8-aircraft engine |
| 2 | `2026-08-01-suas-c2-phase2-recording-replay.md` | Engine sessions record, checkpoint, derive metrics, seal artifacts, and replay to matching hashes |
| 3 | `2026-08-01-suas-c2-phase3-backend-runtime.md` | FastAPI prepares and controls one persisted session through REST and ordered WebSocket messages |
| 4 | `2026-08-01-suas-c2-phase4-operator-ui.md` | Researcher can launch and operate a synthetic mission through the browser console |
| 5 | `2026-08-01-suas-c2-phase5-research-debrief.md` | Practice/three-block protocol, ISA/SAGAT/TLX/Bedford, debrief, and research export work end to end |
| 6 | `2026-08-01-suas-c2-phase6-linux-hardening.md` | Offline launcher, accessibility, headless E2E, soak tests, documentation, and full regression gate pass |

Do not start a later gate before the prior gate's final verification commit is on the remote. Each phase plan repeats the interfaces it consumes so an implementer can execute it without guessing.

## Cross-Phase Interface Ledger

These names are locked across the plan suite. If implementation proves one impossible, update the design and every consuming plan in one documentation-only commit before changing code.

### Python domain and scenario interfaces

```python
# matb_integration/suas/scenarios/loader.py
@dataclass(frozen=True, slots=True)
class LoadedScenario:
    definition: ScenarioDefinition
    normalized_document: dict[str, object]
    normalized_yaml: str
    sha256: str

def load_scenario(path: Path) -> LoadedScenario: ...
def load_scenario_text(text: str, *, source_name: str = "<memory>") -> LoadedScenario: ...

# matb_integration/suas/scenarios/manifest.py
def build_session_manifest(
    loaded: LoadedScenario,
    *,
    participant_id: str,
    visit_ordinal: int,
    locale: Locale,
    block_order: tuple[WorkloadProfile, ...],
    ui_version: str,
) -> dict[str, object]: ...
```

```python
# matb_integration/suas/engine/runtime.py
ENGINE_VERSION = "1.0.0"
TICK_MS = 100
SNAPSHOT_INTERVAL_MS = 250
CHECKPOINT_INTERVAL_MS = 5_000

@dataclass(frozen=True, slots=True)
class StepResult:
    snapshot: dict[str, object]
    events: tuple[DomainEvent, ...]
    command_results: tuple[CommandResult, ...]

class SimulationEngine:
    def __init__(self, scenario: ScenarioDefinition, block_id: str): ...
    def step(self, commands: Sequence[CommandEnvelope] = ()) -> StepResult: ...
    def snapshot(self) -> dict[str, object]: ...
    def checkpoint_snapshot(self) -> dict[str, object]: ...
    def restore(self, checkpoint_snapshot: Mapping[str, object]) -> None: ...
    @property
    def state_hash(self) -> str: ...
```

```python
# matb_integration/suas/adapters/base.py
class VehicleBackend(Protocol):
    def initialize(self, scenario: ScenarioDefinition, block: BlockDefinition) -> WorldState: ...
    def advance(self, state: WorldState, *, tick_ms: int) -> tuple[WorldState, tuple[DomainEvent, ...]]: ...
```

### Recording and metrics interfaces

```python
# matb_integration/suas/recording/recorder.py
class SessionRecorder:
    def __init__(self, run_dir: Path, manifest: Mapping[str, object], scenario_yaml: str): ...
    @classmethod
    def open_existing(cls, run_dir: Path) -> "SessionRecorder": ...
    def append(self, record: SessionRecord) -> None: ...
    def checkpoint(self, snapshot: Mapping[str, object]) -> ArtifactInfo: ...
    def seal(self, *, questionnaires: Mapping[str, object], metrics: Mapping[str, object], debrief: Mapping[str, object], replay: ReplayResult) -> tuple[ArtifactInfo, ...]: ...
    def seal_partial(self, *, reason: str) -> tuple[ArtifactInfo, ...]: ...

# matb_integration/suas/recording/replay.py
class ReplayVerifier:
    def verify(self, run_dir: Path) -> ReplayResult: ...

# matb_integration/suas/metrics/mission.py
def derive_block_metrics(records: Iterable[SessionRecord], manifest: Mapping[str, object]) -> BlockMetrics: ...
```

### Backend runtime interfaces

```python
# webui/backend/app/simulation_runtime.py
class SimulationManager:
    async def prepare(self, request: CreateSimulationSession, db: Session) -> PreparedSession: ...
    async def start(self, session_id: str, block_id: str, lease: str) -> SessionView: ...
    async def pause(self, session_id: str, lease: str, reason: str) -> SessionView: ...
    async def resume(self, session_id: str, lease: str) -> SessionView: ...
    async def finish(self, session_id: str, lease: str, disposition: FinishDisposition) -> SessionView: ...
    async def recover(self, session_id: str, lease: str | None, checkpoint_version: int,
                      *, confirm_process_restart: bool = False) -> RecoveryView: ...
    async def submit(self, session_id: str, lease: str, command: CommandRequest) -> CommandResultView: ...
    async def state(self, session_id: str) -> dict[str, object]: ...
    async def controller_connected(self, session_id: str, lease: str) -> None: ...
    async def controller_disconnected(self, session_id: str, lease: str) -> None: ...
```

### JSON/WebSocket contract

```json
{
  "session_id": "sim-...",
  "sequence": 42,
  "simulation_time_ms": 12500,
  "wall_time_utc": "2026-08-01T12:00:00Z",
  "state_version": 125,
  "kind": "snapshot",
  "payload": {}
}
```

Allowed `kind` values are `snapshot`, `domain_event`, `alert`, `command_result`, `probe`, `lifecycle`, `checkpoint`, and `error`.

### Frontend interfaces

```ts
// webui/frontend/src/types/simulation.ts
export type Locale = "en" | "es-CO";
export type ConnectionMode = "live" | "reconnecting" | "paused" | "observer" | "disconnected";

export interface StreamEnvelope<T = unknown> {
  session_id: string;
  sequence: number;
  simulation_time_ms: number;
  wall_time_utc: string;
  state_version: number;
  kind: "snapshot" | "domain_event" | "alert" | "command_result" | "probe" | "lifecycle" | "checkpoint" | "error";
  payload: T;
}

// webui/frontend/src/lib/simulation/api.ts
export async function createSimulationSession(body: CreateSimulationSession): Promise<PreparedSession>;
export async function transitionSession(id: string, action: "start" | "pause" | "resume" | "finish", lease: string, body?: object): Promise<SessionView>;
export async function submitSimulationCommand(id: string, lease: string, command: CommandRequest): Promise<CommandResultView>;
export async function getSimulationState(id: string): Promise<WorldSnapshot>;

// webui/frontend/src/lib/simulation/stream.ts
export class SimulationStream {
  connect(options: StreamOptions): void;
  close(): void;
}
```

## Design Acceptance Coverage

| Design §17 criterion | Planned implementation | Evidence gate |
|---|---|---|
| 1. Strict stable 2–8-aircraft scenario | Phase 1 Tasks 1–2 | `test_scenario_schema.py`, manifest hash checks, CLI validate |
| 2. Pseudonymized bilingual browser launch | Phase 3 Tasks 1–3; Phase 4 Tasks 1–2 | backend session-contract tests, setup component test, E2E setup |
| 3. Practice plus counterbalanced blocks and supervisory commands | Phase 1 Task 5; Phase 5 Tasks 2–3 | reducer/protocol tests and full mission-flow E2E |
| 4. Battery, contacts, link, coverage, and separation behavior in truth/UI | Phase 1 Tasks 3–5; Phase 4 Tasks 4–5 | subsystem boundary tests, console tests, browser mission flow |
| 5. ISA/SAGAT/TLX/Bedford administered and scored | Phase 5 Tasks 1–4 | scoring, protocol, overlay, and research-metric tests |
| 6. Disconnect pause and explicit authoritative recovery | Phase 3 Tasks 4–5; Phase 4 Task 3; Phase 6 Task 2 | hub/failure/store/reconnect browser tests |
| 7. Debrief outcomes, replay, validity, deviations | Phase 5 Tasks 4–5 | debrief builder/component tests |
| 8. Complete checksummed research export | Phase 2 Tasks 1–4; Phase 5 Task 6 | artifact/checksum and bundle path-integrity tests |
| 9. Matching event/final-state replay hashes | Phase 2 Task 2; Phase 6 Task 4 | tamper tests, all-profile soak, CLI verify |
| 10. Linux plus existing-suite compatibility | every phase regression gate; Phase 6 Tasks 1–5 | root/backend/frontend/E2E/offline/soak matrix and verification report |

Design §18 deferrals are enforced by the global constraints, the non-kinetic identifier audit in Phase 6, and the final stop instruction. No task introduces manual piloting, real maps, moving contacts, multiple controllers, external vehicle integration, physiology, adaptive automation, or kinetic behavior.

## Repository-Level Verification Commands

Run these at every phase's final gate from `/root/repos/MATB`:

```bash
python3 -m pytest tests/suas -q
python3 -m pytest tests -q
cd webui/backend && python3 -m pytest -q
cd webui/frontend && npm test -- --run
cd webui/frontend && npm run typecheck
```

From Phase 4 onward also run:

```bash
cd webui/frontend && npm run build
```

From Phase 6 onward also run:

```bash
cd webui/frontend && npm run test:e2e
bash scripts/test_suas_offline.sh
```

If the repository virtual environment is present, replace `python3` with `.venv/bin/python` at the root and use the documented backend environment inside `webui/backend`; do not silently install packages into the system interpreter.

## Commit and Push Protocol

Every task ends with the exact sequence below, substituting only the task's listed paths and commit message:

```bash
git status --short
git add <only-the-files-listed-by-the-task>
git diff --cached --check
git diff --cached --name-only
git commit -m "<task commit message>"
git push origin HEAD
```

The cached name list must contain no pre-existing `__pycache__`, `.playwright-mcp`, image, roadmap, or other unrelated workspace artifact. If it does, unstage only the unintended path with `git restore --staged <path>` and re-check; never discard the underlying user file.

## Execution Readiness Gate

Planning is complete when this master file and all six linked phase plans:

1. contain no placeholder instructions;
2. cover every approved design requirement;
3. use the same type, endpoint, event, and file names across phases;
4. pass `git diff --check`;
5. are committed in one documentation-only commit and pushed to the current remote branch;
6. have been reported to the user before any implementation begins.
