# sUAS C2 Phase 5 — Research Protocol, Debrief, and Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the guided practice and counterbalanced three-block research protocol with ISA, dynamic sUAS SAGAT, NASA-TLX, Bedford, debrief/replay, and reproducible export integration.

**Architecture:** A pure-Python protocol controller schedules block transitions and server-scored instruments against authoritative snapshots. FastAPI pauses/resumes the runtime around probes and post-block gates; the frontend presents focus-controlled bilingual overlays. Debrief and export derive from sealed records/checkpoints, never from browser state.

**Tech Stack:** Python 3.12, Phase 1–3 sUAS libraries/backend, existing SAGAT concepts and questionnaire constants, FastAPI/SQLModel, Next.js/React/TypeScript/Zustand, Radix Dialog, ECharts where already installed, pytest/Vitest.

## Global Constraints

- Complete and push Phases 1–4 first.
- Read the approved design and master interface ledger before editing.
- Practice is 5 minutes; LOW/MEDIUM/HIGH are 10 minutes each in existing participant Latin-square order.
- ISA is 1–10, NASA-TLX contains six 0–10 subscales, Bedford is 1–10.
- SAGAT correct answers are computed from the frozen authoritative snapshot, not hard-coded generic MATB answers.
- A SAGAT freeze immediately pauses and fully conceals operational state; disconnect marks the probe interrupted and never silently scores a miss.
- A block cannot advance until required post-block scales are validly submitted or the researcher explicitly aborts.
- Component outcomes remain first-class; the composite stays descriptive-only.
- Native sUAS metrics remain separate from existing OpenMATB confirmatory analysis inputs in V1.
- Preserve all master-plan privacy, offline, determinism, compatibility, test, and Git constraints.

---

### Task 1: Dynamic bilingual sUAS SAGAT templates and questionnaire scoring

**Files:**
- Create: `matb_integration/suas/research/__init__.py`
- Create: `matb_integration/suas/research/probes.py`
- Create: `matb_integration/suas/research/scoring.py`
- Create: `tests/suas/test_research_probes.py`
- Create: `tests/suas/test_research_scoring.py`

**Interfaces:**
- Consumes: private authoritative `WorldState`, public snapshot, block/scenario definitions, locale.
- Produces: `ProbeTemplate`, `RenderedProbe`, `ProbeAnswer`, `load_suas_probe_bank()`, `render_probe()`, `score_probe_answer()`, `score_isa()`, `score_nasa_tlx()`, `score_bedford()`, `aggregate_sagat()`.

- [ ] **Step 1: Write failing dynamic-answer and scale-validation tests**

```python
def test_dynamic_probe_answer_comes_from_freeze_state(private_freeze_state) -> None:
    template = load_suas_probe_bank(Locale.EN)["suas_l1_lost_links"]
    rendered = render_probe(template, private_freeze_state)
    assert rendered.options == ("0", "1", "2", "3", "4", "5", "6", "7", "8", "Unknown")
    assert rendered.correct_answer == "1"
    assert "truth" not in rendered.to_public_dict()
    assert "correct_answer" not in rendered.to_public_dict()

def test_projection_probe_uses_current_energy_and_routes(private_freeze_state) -> None:
    rendered = render_probe(
        load_suas_probe_bank(Locale.EN)["suas_l3_reserve_first"], private_freeze_state
    )
    assert rendered.correct_answer == "UAS-03"

@pytest.mark.parametrize("value", [0, 11, 2.5, "high"])
def test_isa_rejects_non_integer_or_out_of_range(value) -> None:
    with pytest.raises(ValueError, match="ISA"):
        score_isa(value)

def test_tlx_and_bedford_scoring() -> None:
    tlx = score_nasa_tlx({
        "mental_demand": 8, "physical_demand": 1, "temporal_demand": 7,
        "performance": 4, "effort": 8, "frustration": 2,
    })
    assert tlx.raw_tlx == 30.0
    assert score_bedford(7).value == 7
```

- [ ] **Step 2: Run tests and confirm missing research package**

Run: `python3 -m pytest tests/suas/test_research_probes.py tests/suas/test_research_scoring.py -q`

Expected: FAIL importing `matb_integration.suas.research`.

- [ ] **Step 3: Define and validate the sUAS probe-bank format**

Validate the two bundled YAML banks created in Phase 1. Each has `format_version: 1`, `locale`, and the same nine probe IDs: three perception, three comprehension, and three projection. Each row contains `probe_id`, `sa_level`, `domain`, `question`, `answer_evaluator`, `option_source`, and `timeout_s`. Use these evaluator IDs only:

```text
suas_l1_lost_links       -> count aircraft link == LOST
suas_l1_lowest_battery   -> active aircraft with lowest energy percentage
suas_l1_unreported       -> count detected/inspectable contacts not reported
suas_l2_largest_gap      -> sector with lowest coverage percentage
suas_l2_attention        -> highest-severity unresolved aircraft alert
suas_l2_mission_state    -> profile-specific coverage band
suas_l3_reserve_first    -> aircraft predicted to cross reserve first
suas_l3_next_sector      -> aircraft predicted to finish its current sector route first
suas_l3_conflict_risk    -> pair with minimum projected separation in 60 s
```

Option sources are `integer_0_8`, `active_aircraft`, `sectors`, `coverage_band`, `aircraft_or_none`, and `aircraft_pair_or_none`; every set gains `Unknown`/`No sé`. Bank loading fails on unknown keys/evaluators/sources, duplicate IDs, locale mismatch, level/domain mismatch, timeout outside 5–60 s, or EN/es key mismatch. The scenario references probe IDs, not bank paths.

- [ ] **Step 4: Implement private rendering and public redaction**

```python
@dataclass(frozen=True, slots=True)
class RenderedProbe:
    probe_id: str
    sa_level: int
    domain: str
    question: str
    options: tuple[str, ...]
    correct_answer: str
    timeout_ms: int

    def to_public_dict(self) -> dict[str, object]:
        return {"probe_id": self.probe_id, "sa_level": self.sa_level,
                "domain": self.domain, "question": self.question,
                "options": list(self.options), "timeout_ms": self.timeout_ms}
```

Evaluator functions receive private state plus scenario definitions and return one exact option. Projection uses only current energy, speed, route, mode, and separation geometry—never an undisclosed future schedule. When state cannot support an answer, return the locale's uncertainty option and add `unscorable_reason`; never guess. Store the private rendered probe in the protocol controller only; send `to_public_dict()` to clients.

- [ ] **Step 5: Implement strict server-side scoring**

- ISA accepts Python `int` only in 1–10.
- NASA-TLX requires exactly the six canonical snake-case keys, numeric values 0–10, and returns per-subscale values plus raw sum 0–60.
- Bedford accepts integer 1–10.
- SAGAT normalizes only surrounding whitespace, supports the locale's uncertainty option, records correctness/timeout/latency, and aggregates overall and SA-level accuracy with correct/total denominators.

Reuse `NASA_TLX_SUBSCALES` names from `log_converter` only for export mapping; do not invoke CSV parsing.

- [ ] **Step 6: Verify the reference scenario and manifest hashes semantically**

Load each reference block's three-probe set and ensure every referenced evaluator can answer or explicitly return unscorable from a valid freeze snapshot. Assert the bundled sUAS ISA assets retain the approved 1–10 range and English/Spanish NASA-TLX retain matching six-row structures. Recompute and test the manifest inventory; every instrument hash remains present and legacy OpenMATB hashes remain separate.

- [ ] **Step 7: Run focused research and scenario tests**

Run: `python3 -m pytest tests/suas/test_research_probes.py tests/suas/test_research_scoring.py tests/suas/test_scenario_schema.py -q`

Expected: PASS.

- [ ] **Step 8: Commit and push Task 1**

```bash
git add matb_integration/suas/research tests/suas/test_research_probes.py tests/suas/test_research_scoring.py
git diff --cached --check
git commit -m "feat(suas): add dynamic research instruments"
git push origin HEAD
```

### Task 2: Protocol controller, probe commands, backend pause gates, and persistence

**Files:**
- Create: `matb_integration/suas/research/protocol.py`
- Modify: `matb_integration/suas/domain/commands.py`
- Modify: `matb_integration/suas/engine/runtime.py`
- Modify: `webui/backend/app/simulation_schemas.py`
- Modify: `webui/backend/app/simulation_runtime.py`
- Modify: `webui/backend/app/routers/simulation.py`
- Create: `webui/backend/tests/test_simulation_protocol.py`
- Create: `tests/suas/test_protocol_controller.py`

**Interfaces:**
- Consumes: loaded profiles, Latin-square order, dynamic probes/scoring, manager lifecycle.
- Produces: `ProtocolController`, `ProtocolPhase`, `ActiveProbe`, `restore_protocol_from_records()`, `SubmitIsa`, `SubmitSagat`, `SubmitPostBlockScale`, and server-controlled block progression.

- [ ] **Step 1: Write failing practice/order/probe-gate tests**

```python
def test_protocol_requires_practice_then_participant_order(reference_scenario) -> None:
    controller = ProtocolController(reference_scenario, participant_id="P03", locale=Locale.EN)
    assert controller.block_order == (
        WorkloadProfile.PRACTICE, WorkloadProfile.MEDIUM,
        WorkloadProfile.HIGH, WorkloadProfile.LOW,
    )
    assert controller.phase is ProtocolPhase.READY_FOR_BLOCK

def test_sagat_freeze_captures_truth_and_exposes_only_public_probe(controller, state) -> None:
    due = controller.on_tick(state, simulation_time_ms=controller.sagat_due_ms)
    assert due.kind == "SAGAT"
    assert controller.phase is ProtocolPhase.SAGAT_ACTIVE
    assert "correct_answer" not in due.public_payload
    assert controller.private_probe.correct_answer

@pytest.mark.anyio
async def test_probe_pauses_and_only_accepts_probe_submission(manager, running_at_probe) -> None:
    assert (await manager.view(running_at_probe.id)).lifecycle == "PAUSED"
    rejected = await manager.submit(running_at_probe.id, running_at_probe.lease,
                                    hold_command())
    assert rejected.code == "probe_active"
    accepted = await manager.submit(running_at_probe.id, running_at_probe.lease,
                                    sagat_answer_command())
    assert accepted.status == "accepted"
```

- [ ] **Step 2: Run tests and confirm protocol symbols are absent**

Run: `python3 -m pytest tests/suas/test_protocol_controller.py -q && cd webui/backend && python3 -m pytest tests/test_simulation_protocol.py -q`

Expected: FAIL importing `ProtocolController`/new commands.

- [ ] **Step 3: Implement the pure protocol state machine**

```python
class ProtocolPhase(StrEnum):
    READY_FOR_BLOCK = "READY_FOR_BLOCK"
    BLOCK_RUNNING = "BLOCK_RUNNING"
    ISA_ACTIVE = "ISA_ACTIVE"
    SAGAT_ACTIVE = "SAGAT_ACTIVE"
    POST_BLOCK_ACTIVE = "POST_BLOCK_ACTIVE"
    COMPLETE = "COMPLETE"
    ABORTED = "ABORTED"
```

The controller prepends PRACTICE to `block_order_for_participant()`, consumes the normalized `block.isa_times_ms`, and derives one SAGAT time from its seeded private `protocol` PCG32 within the declared window. The minimum separation from ISA/block boundaries is `guard_ms = min(30_000, block.duration_ms // 10)`, rounded up to one 100 ms tick; this gives the reference blocks a 30 s guard while keeping strict short E2E fixtures valid. Scenario validation rejects a window with no eligible tick. The controller exposes `start_block`, `on_tick`, `submit_isa`, `submit_sagat`, `submit_post_block`, `interrupt_probe`, and `advance_block`. It cannot skip practice or a required scale.

`restore_protocol_from_records(scenario, participant_id, locale, records, through_sequence)` creates a fresh controller and reduces only `effective_records(records)` lifecycle/probe/questionnaire/deviation rows through the checkpoint's `record_sequence`. It reconstructs block index, phase, completed ISA/SAGAT items, scale gates, protocol PRNG state from recorded SAGAT due time, and validity without re-emitting records. Missing, contradictory, or future records fail recovery with a stable code. In this task, extend the Phase 3 recovery path to call this reducer before returning PAUSED; it never guesses protocol state from engine time alone.

ISA pauses with operational state still displayed but commands disabled. SAGAT pauses and publishes a conceal-state instruction plus public probes. Post-block starts at duration and remains paused until TLX+Bedford submission. Probe wall latency comes from an injected monotonic clock; simulation time remains frozen. For each SAGAT item the manager starts one cancellable server-side timeout task from `timeout_ms`; expiry records a timeout score and publishes the next probe or resumes after the final item. Client countdowns never decide timeout truth. Disconnect/answer cancels the exact task and tests assert no leaked timers.

- [ ] **Step 4: Extend the typed command envelope without changing existing command names**

Add:

```python
@dataclass(frozen=True, slots=True)
class SubmitIsa:
    probe_id: str
    rating: int

@dataclass(frozen=True, slots=True)
class SubmitSagat:
    probe_id: str
    answer: str

@dataclass(frozen=True, slots=True)
class SubmitPostBlockScale:
    scale_id: Literal["NASA_TLX", "BEDFORD"]
    answers: Mapping[str, int]
```

Add the corresponding request kinds to backend/TypeScript unions. Route these commands to `ProtocolController`, not the aircraft reducer. While a protocol gate is active, reject every mismatched command with `probe_active` or `post_block_active`.

- [ ] **Step 5: Integrate protocol records and automatic pauses in the manager**

On each tick after domain events, call `protocol.on_tick(private_state, time)`. If due, append a private `QUESTIONNAIRE` record containing the freeze state hash, evaluator inputs, correct answer, and unscorable reason, then append a separate redacted `PROBE` record and publish only the latter as a `probe` envelope. Private records are never passed to `envelope_from_record()`, state, stream, or debrief endpoints; this explicit allowlist is covered by a backend test. The final `questionnaires.json` is derived from those durable records rather than process memory. It is ordinary local JSON, not encrypted; document the required OS account/directory permissions. Transition the manager to PAUSED with reason. While `SAGAT_ACTIVE`, `snapshot_once()` emits no operational snapshot. On valid answers append response/scoring records; ISA resumes automatically after its one response, and SAGAT resumes automatically only after every scheduled probe is answered/timed out, publishing one fresh full snapshot first. An interrupted probe never auto-resumes. Post-block transitions to READY_FOR_BLOCK only after both scales.

Disconnect during a probe calls `interrupt_probe`, records `probe_interrupted`, sets block `valid_with_deviation`, and remains paused. It does not recreate or score the probe.

- [ ] **Step 6: Expose protocol status and exact next-block lifecycle**

Extend session/state views with `protocol_phase`, `block_order`, `current_block_index`, `active_probe` (public only), and `next_block_id`. `start` accepts only `next_block_id`; starting a different block returns `block_order_violation`. Persist block start/finish, validity, and scale summaries in `SimulationBlock`.

- [ ] **Step 7: Run core/backend protocol and regression tests**

```bash
python3 -m pytest tests/suas/test_protocol_controller.py tests/suas/test_research_scoring.py -q
cd webui/backend && python3 -m pytest tests/test_simulation_protocol.py tests/test_simulation_endpoints.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit and push Task 2**

```bash
git add matb_integration/suas/research/protocol.py matb_integration/suas/domain/commands.py matb_integration/suas/engine/runtime.py webui/backend/app/simulation_schemas.py webui/backend/app/simulation_runtime.py webui/backend/app/routers/simulation.py webui/backend/tests/test_simulation_protocol.py tests/suas/test_protocol_controller.py
git diff --cached --check
git commit -m "feat(suas): enforce the research block protocol"
git push origin HEAD
```

### Task 3: Bilingual ISA, SAGAT concealment, and post-block scale UI

**Files:**
- Modify: `webui/frontend/src/types/simulation.ts`
- Modify: `webui/frontend/src/lib/simulation/i18n.ts`
- Modify: `webui/frontend/src/lib/simulation/store.ts`
- Create: `webui/frontend/src/components/mission/probes/ProbeOverlay.tsx`
- Create: `webui/frontend/src/components/mission/probes/IsaProbe.tsx`
- Create: `webui/frontend/src/components/mission/probes/SagatFreeze.tsx`
- Create: `webui/frontend/src/components/mission/probes/PostBlockScales.tsx`
- Create: `webui/frontend/src/components/mission/probes/ProbeOverlay.test.tsx`
- Modify: `webui/frontend/src/components/mission/MissionConsole.tsx`

**Interfaces:**
- Consumes: protocol stream payloads and command API.
- Produces: keyboard-accessible blocking overlays, operational-state concealment, and complete bilingual scale submissions.

- [ ] **Step 1: Write failing concealment, focus, and validation tests**

```tsx
it("conceals all operational state during SAGAT and restores focus afterward", async () => {
  const trigger = document.createElement("button");
  document.body.append(trigger); trigger.focus();
  render(<MissionConsole initial={sagatActiveSnapshot} />);
  expect(screen.queryByRole("img", { name: /tactical mission map/i })).not.toBeInTheDocument();
  expect(screen.queryByText("UAS-01")).not.toBeInTheDocument();
  expect(screen.getByRole("dialog", { name: /situation awareness/i })).toHaveFocus();
  await answerAllSagat(user);
  expect(trigger).toHaveFocus();
});

it("requires all TLX fields and Bedford before submission", async () => {
  render(<PostBlockScales locale="en" onSubmit={submit} />);
  expect(screen.getByRole("button", { name: /submit block ratings/i })).toBeDisabled();
  await fillSixTlxAndBedford(user);
  expect(screen.getByRole("button", { name: /submit block ratings/i })).toBeEnabled();
});

it("ISA exposes exactly integer values 1 through 10", () => {
  render(<IsaProbe locale="es-CO" probe={isaProbe} onSubmit={submit} />);
  expect(screen.getAllByRole("radio")).toHaveLength(10);
});
```

- [ ] **Step 2: Run probe component tests and confirm missing components**

Run: `cd webui/frontend && npm test -- --run src/components/mission/probes/ProbeOverlay.test.tsx`

Expected: FAIL resolving probe components.

- [ ] **Step 3: Extend typed probe payloads/store semantics**

Add discriminated `IsaProbePayload`, `SagatProbePayload`, and `PostBlockPayload`. The store retains only public payloads and local pending answers. When SAGAT is active, set `concealOperationalState=true`; MissionConsole must not merely hide with CSS—it must not mount the map/fleet/alert/contact DOM. Clear cached interpolation frames while concealed. ISA keeps status visible but disables every mission command.

- [ ] **Step 4: Implement accessible timed overlays**

Use Radix Dialog primitives without a close button. Focus the dialog heading, trap Tab, block Escape/outside close, and announce remaining time through a throttled polite live region. The client timer is display-only: when a backend timeout envelope arrives, advance to the next public probe without sending an answer command. SAGAT renders backend options verbatim and sends at most one answer per probe. Do not expose correctness until debrief.

- [ ] **Step 5: Implement complete raw TLX and Bedford forms**

Render six labeled integer sliders/segmented controls 0–10 and Bedford 1–10 with endpoint descriptions in both locales. On submission, send `SUBMIT_POST_BLOCK_SCALE` for `NASA_TLX` followed by `BEDFORD`, each with a unique UUID/current state version. Disable repeated submission until results arrive; map server validation codes inline.

- [ ] **Step 6: Run probe, console, locale, type, and build checks**

```bash
cd webui/frontend
npm test -- --run src/components/mission/probes/ProbeOverlay.test.tsx src/components/mission/MissionConsole.test.tsx src/lib/simulation/i18n.test.ts
npm run typecheck
npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit and push Task 3**

```bash
git add webui/frontend/src/types/simulation.ts webui/frontend/src/lib/simulation/i18n.ts webui/frontend/src/lib/simulation/store.ts webui/frontend/src/components/mission/probes webui/frontend/src/components/mission/MissionConsole.tsx
git diff --cached --check
git commit -m "feat(frontend): administer mission research probes"
git push origin HEAD
```

### Task 4: Research metrics extension and sanitized debrief builder

**Files:**
- Create: `matb_integration/suas/metrics/research.py`
- Create: `matb_integration/suas/metrics/debrief.py`
- Modify: `matb_integration/suas/metrics/mission.py`
- Modify: `matb_integration/suas/recording/recorder.py`
- Create: `tests/suas/test_research_metrics.py`
- Create: `tests/suas/test_debrief.py`

**Interfaces:**
- Consumes: `effective_records()`, sealed records, private checkpoint snapshots, probe/scoring records.
- Produces: `ResearchMetrics`, `derive_research_metrics()`, `DebriefArtifact`, `public_frame_from_checkpoint()`, `build_debrief()`, sanitized five-second replay frames and event timeline.

- [ ] **Step 1: Write failing human-factors and hidden-truth debrief tests**

```python
def test_research_metrics_preserve_scores_and_denominators(research_records) -> None:
    metrics = derive_research_metrics(research_records)
    assert metrics.isa.values == (4, 6, 7)
    assert metrics.isa.mean == pytest.approx(5.6667)
    assert metrics.sagat.overall == {"correct": 2, "total": 3, "accuracy": 0.6667}
    assert metrics.sagat.by_level[1]["total"] == 1
    assert metrics.nasa_tlx.raw_tlx == 30.0
    assert metrics.bedford.value == 7

def test_debrief_frames_are_time_ordered_and_public_safe(sealed_run) -> None:
    debrief = build_debrief(sealed_run)
    assert [frame.simulation_time_ms for frame in debrief.frames] == sorted(
        frame.simulation_time_ms for frame in debrief.frames
    )
    rendered = canonical_json(debrief.to_dict())
    assert '"truth"' not in rendered
    assert '"correct_answer"' not in rendered
    assert debrief.replay_status == "match"
```

- [ ] **Step 2: Run metrics/debrief tests and confirm missing files**

Run: `python3 -m pytest tests/suas/test_research_metrics.py tests/suas/test_debrief.py -q`

Expected: FAIL importing the new modules.

- [ ] **Step 3: Implement research metrics reduction**

Reduce only the authoritative branch returned by `effective_records()`, then read `PROBE`/`QUESTIONNAIRE` records and calculate ISA values/mean/SD, SAGAT correct/total/accuracy overall and levels 1–3, timeout/interruption counts and answer latency, complete TLX subscales/raw sum, Bedford, and manipulation metadata. Missing/invalid instruments remain explicit with `status` and reason; never impute.

Extend `BlockMetrics.research` with `ResearchMetrics.to_dict()` without changing existing component keys or composite formula.

- [ ] **Step 4: Implement sanitized debrief generation**

Build one replay frame per 5-second private checkpoint through a closed `public_frame_from_checkpoint(checkpoint, frozen_scenario)` serializer. It emits the same redacted mission fields as `SimulationEngine.snapshot()` and rejects unknown private keys rather than copying mappings wholesale. Build timeline rows for lifecycle, accepted/rejected commands, contact workflow, alerts, link changes, conflicts, probes, and deviations. Add block summaries, full-session totals, research metrics, artifact inventory, checksums, engine/UI/scenario versions, validity, and replay status. Correctness may be shown as aggregate/per-probe `is_correct` after the full session, but never include correct answer, future schedules, PRNG/command-cache state, or hidden contact truth.

Require MATCH replay for `deterministic_replay_verified=true`; otherwise include the exact mismatch status and keep the run unsealed/invalid according to Phase 2 rules.

- [ ] **Step 5: Integrate final debrief into sealing**

At full-session completion derive all block/research metrics, build `questionnaire_payload` with ISA/SAGAT/TLX/Bedford prompts, responses, latencies, scores, interruptions, and private scoring provenance, generate `debrief_payload` from checkpoints/records, and create `replay_result`. Then call `seal(questionnaires=questionnaire_payload, metrics=metrics_payload, debrief=debrief_payload, replay=replay_result)`. Remove the Phase 2 minimal timeline fallback from normal backend completion but keep CLI single-block support. Only the native researcher bundle may include `questionnaires.json`; browser state/debrief endpoints receive its sanitized summaries.

- [ ] **Step 6: Run metric/debrief/replay regressions**

Run: `python3 -m pytest tests/suas/test_research_metrics.py tests/suas/test_debrief.py tests/suas/test_mission_metrics.py tests/suas/test_replay.py -q`

Expected: PASS.

- [ ] **Step 7: Commit and push Task 4**

```bash
git add matb_integration/suas/metrics/research.py matb_integration/suas/metrics/debrief.py matb_integration/suas/metrics/mission.py matb_integration/suas/recording/recorder.py tests/suas/test_research_metrics.py tests/suas/test_debrief.py
git diff --cached --check
git commit -m "feat(suas): build research-ready mission debriefs"
git push origin HEAD
```

### Task 5: Debrief/replay browser screen

**Files:**
- Modify: `webui/frontend/src/types/simulation.ts`
- Modify: `webui/frontend/src/lib/simulation/api.ts`
- Modify: `webui/frontend/src/lib/simulation/i18n.ts`
- Create: `webui/frontend/src/app/mission/debrief/page.tsx`
- Create: `webui/frontend/src/components/mission/debrief/DebriefScreen.tsx`
- Create: `webui/frontend/src/components/mission/debrief/ReplayTimeline.tsx`
- Create: `webui/frontend/src/components/mission/debrief/OutcomeCards.tsx`
- Create: `webui/frontend/src/components/mission/debrief/ResearchSummary.tsx`
- Create: `webui/frontend/src/components/mission/debrief/DebriefScreen.test.tsx`
- Modify: `webui/frontend/src/components/mission/MissionTopBar.tsx`

**Interfaces:**
- Consumes: sanitized `DebriefView`, artifact list/download endpoint.
- Produces: `/mission/debrief?session=...`, time-addressable map replay, component outcome and validity views.

- [ ] **Step 1: Write failing replay, component, and labeling tests**

```tsx
it("moves the map to the selected five-second replay frame", async () => {
  render(<DebriefScreen debrief={debriefWithFrames} locale="en" />);
  await user.click(screen.getByRole("slider", { name: /replay time/i }));
  await user.keyboard("{End}");
  expect(screen.getByTestId("replay-time")).toHaveTextContent("00:10");
  expect(screen.getByRole("img", { name: /tactical mission replay/i }))
    .toHaveAttribute("data-state-version", "100");
});

it("labels the composite descriptive and exposes all components", () => {
  renderDebrief();
  expect(screen.getByText(/descriptive feedback only/i)).toBeVisible();
  for (const name of ["Coverage", "Contacts", "Assets", "Timeliness"]) {
    expect(screen.getByText(name)).toBeVisible();
  }
});

it("shows protocol deviations and replay verification", () => {
  renderDebrief();
  expect(screen.getByText(/valid with deviation/i)).toBeVisible();
  expect(screen.getByText(/deterministic replay verified/i)).toBeVisible();
});
```

- [ ] **Step 2: Run the debrief component test and confirm route absence**

Run: `cd webui/frontend && npm test -- --run src/components/mission/debrief/DebriefScreen.test.tsx`

Expected: FAIL resolving debrief components.

- [ ] **Step 3: Implement typed debrief API and replay timeline**

Extend types exactly to backend debrief schema. `ReplayTimeline` uses checkpoint frame times as slider steps, supports Home/End/arrows, displays timeline events in the current window, and renders `MissionMap` in read-only replay mode with commands/selection side effects disabled. It never reconstructs truth between checkpoints; display interpolation may smooth matching aircraft only.

- [ ] **Step 4: Implement outcome, research, provenance, and validity sections**

Render per-block/full-session component values, descriptive composite, contact/command/link/separation details, ISA line chart, SAGAT by-level denominators, TLX subscales/raw sum, Bedford, protocol deviations/dispositions, manifest/hash/version provenance, replay/checksum badges, and artifact download action. Never render PII or hidden contact truth.

On mission completion, MissionTopBar navigates to debrief only after backend returns FINISHED and artifact sealing succeeds.

- [ ] **Step 5: Run debrief, all frontend tests, typecheck, and build**

```bash
cd webui/frontend
npm test -- --run src/components/mission/debrief/DebriefScreen.test.tsx
npm test -- --run
npm run typecheck
npm run build
```

Expected: PASS; debrief route builds.

- [ ] **Step 6: Commit and push Task 5**

```bash
git add webui/frontend/src/types/simulation.ts webui/frontend/src/lib/simulation/api.ts webui/frontend/src/lib/simulation/i18n.ts webui/frontend/src/app/mission/debrief/page.tsx webui/frontend/src/components/mission/debrief webui/frontend/src/components/mission/MissionTopBar.tsx
git diff --cached --check
git commit -m "feat(frontend): add mission replay and debrief"
git push origin HEAD
```

### Task 6: Native bundle download, research-context integration, and Phase 5 gate

**Files:**
- Modify: `webui/backend/app/routers/simulation.py`
- Modify: `webui/backend/app/routers/exports.py`
- Create: `webui/backend/tests/test_simulation_exports.py`
- Modify: `webui/backend/tests/test_endpoints.py`
- Modify: `webui/frontend/src/lib/simulation/api.ts`
- Modify: `webui/frontend/src/components/mission/debrief/DebriefScreen.tsx`
- Modify: `README.md`
- Modify: `webui/README.md`

**Interfaces:**
- Consumes: sealed artifact inventory and existing research bundle builder.
- Produces: `GET /simulation/sessions/{id}/bundle`, backward-compatible native simulation summaries in research context/bundle, browser download.

- [ ] **Step 1: Write failing path-safe bundle and research-context tests**

```python
def test_native_bundle_contains_only_verified_relative_artifacts(client, sealed_session) -> None:
    response = client.get(f"/simulation/sessions/{sealed_session.id}/bundle")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "events.jsonl" in names
        assert "checksums.sha256" in names
        assert all(not name.startswith("/") and ".." not in Path(name).parts for name in names)

def test_research_context_adds_native_sessions_without_changing_v1_fields(client, sealed_session) -> None:
    context = client.get("/exports/research-context").json()
    assert context["bundle_version"] == "research-bundle-v1"
    assert context["participants"]
    assert context["simulation_sessions"][0]["id"] == sealed_session.id
    assert "simulation_metrics_long" in context
```

- [ ] **Step 2: Run export tests and confirm missing route/fields**

Run: `cd webui/backend && python3 -m pytest tests/test_simulation_exports.py tests/test_endpoints.py -q`

Expected: FAIL for missing bundle route/context fields.

- [ ] **Step 3: Implement verified native bundle streaming**

Resolve artifact paths only by joining the configured artifact root with database relative paths, then require `resolved.is_relative_to(session_root.resolve())`. Verify every database SHA and `checksums.sha256` before creating the ZIP in memory. Include no temporary/unregistered file. Return 409 for unsealed runs and 500 `artifact_integrity_failed` for mismatch; never send a partial ZIP.

- [ ] **Step 4: Extend existing research context backward-compatibly**

Keep `bundle_version="research-bundle-v1"` and every existing field unchanged. Add `simulation_sessions`, `simulation_blocks`, `simulation_metrics_long`, `simulation_protocol_deviations`, and `native_simulation_bundle_version=1`. The research ZIP adds JSON summaries plus one nested `simulation_sessions/<safe-session-id>.zip` per sealed session. Native rows are not merged into existing `metrics_long` or confirmatory analysis inputs.

- [ ] **Step 5: Add browser download and update runbooks**

Add `downloadSimulationBundle(sessionId)` returning a Blob and wire it to debrief. Document offline setup, mission routes, protocol, artifact layout, non-kinetic/research-only scope, and explicit distinction from OpenMATB.

- [ ] **Step 6: Run the complete Phase 5 gate**

```bash
python3 -m pytest tests/suas -q
python3 -m pytest tests -q
cd webui/backend && python3 -m pytest -q
cd webui/frontend && npm test -- --run
cd webui/frontend && npm run typecheck
cd webui/frontend && npm run build
```

Expected: all suites PASS.

- [ ] **Step 7: Commit and push the Phase 5 gate**

```bash
git add webui/backend/app/routers/simulation.py webui/backend/app/routers/exports.py webui/backend/tests/test_simulation_exports.py webui/backend/tests/test_endpoints.py webui/frontend/src/lib/simulation/api.ts webui/frontend/src/components/mission/debrief/DebriefScreen.tsx README.md webui/README.md
git diff --cached --check
git commit -m "feat(suas): export complete research sessions"
git push origin HEAD
```
