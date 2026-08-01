# sUAS C2 Phase 2 — Recording, Replay, and Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every deterministic sUAS block append-only, checkpointed, metrically useful, artifact-complete, and replay-verifiable.

**Architecture:** A synchronous recorder writes canonical ordered records before transport, atomically checkpoints authoritative snapshots, and seals immutable artifacts. Replay rebuilds engines from the frozen scenario and recorded applied ticks; metrics consume records rather than live mutable state.

**Tech Stack:** Python 3.12 stdlib (`json`, `gzip`, `hashlib`, `os`, `pathlib`, `zipfile`), Phase 1 sUAS core, pytest 7.4+.

## Global Constraints

- Complete and push Phase 1 before this plan.
- Read the approved design and master plan before editing.
- Preserve append-before-broadcast semantics: `SessionRecorder.append()` succeeds and flushes before a caller may publish the corresponding message.
- JSONL is canonical UTF-8, one complete object per line, monotonically sequenced, and never rewritten.
- Checkpoints and final JSON files use same-directory temporary files plus `os.replace()`.
- A failed write raises `RecordingError`; callers must not swallow it.
- Replay never substitutes a newer engine version for the manifest's exact semantic version.
- Preserve all master-plan Git, offline, pseudonymization, and regression constraints.

---

### Task 1: Ordered session records, append-only writer, and atomic checkpoints

**Files:**
- Create: `matb_integration/suas/recording/__init__.py`
- Create: `matb_integration/suas/recording/records.py`
- Create: `matb_integration/suas/recording/recorder.py`
- Create: `matb_integration/suas/recording/checkpoints.py`
- Create: `tests/suas/test_recorder.py`

**Interfaces:**
- Consumes: `canonical_data()`, `canonical_json()`, `canonical_sha256()`, private engine checkpoint snapshots.
- Produces: `RecordKind`, `SessionRecord`, `RecordingError`, `ArtifactInfo`, `SessionRecorder.append()`, `SessionRecorder.checkpoint()`, `SessionRecorder.open_existing()`, and `load_checkpoint()`.

- [ ] **Step 1: Write failing append, monotonicity, checkpoint, and disk-failure tests**

```python
def test_recorder_appends_canonical_lines_and_flushes(tmp_path: Path) -> None:
    recorder = SessionRecorder(tmp_path / "run", manifest(), scenario_yaml())
    recorder.append(record(sequence=1, kind=RecordKind.LIFECYCLE))
    recorder.append(record(sequence=2, kind=RecordKind.DOMAIN_EVENT))
    lines = (tmp_path / "run/events.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["sequence"] for line in lines] == [1, 2]
    assert all(" " not in line for line in lines)

def test_recorder_rejects_non_monotonic_sequence(tmp_path: Path) -> None:
    recorder = SessionRecorder(tmp_path / "run", manifest(), scenario_yaml())
    recorder.append(record(sequence=2))
    with pytest.raises(RecordingError, match="strictly increasing"):
        recorder.append(record(sequence=2))

def test_checkpoint_round_trip_and_atomic_name(tmp_path: Path) -> None:
    recorder = SessionRecorder(tmp_path / "run", manifest(), scenario_yaml())
    artifact = recorder.checkpoint(snapshot(version=50, simulation_time_ms=5_000))
    restored = load_checkpoint(artifact.path)
    assert artifact.path.name == "checkpoint-00000001.json.gz"
    assert restored["checkpoint_version"] == 1
    assert restored["record_sequence"] == 0
    assert restored["engine"]["state_version"] == 50
    assert not list((tmp_path / "run/checkpoints").glob("*.tmp"))

def test_write_failure_is_not_hidden(tmp_path: Path, monkeypatch) -> None:
    recorder = SessionRecorder(tmp_path / "run", manifest(), scenario_yaml())
    monkeypatch.setattr(recorder, "_write_line", Mock(side_effect=OSError("disk full")))
    with pytest.raises(RecordingError, match="disk full"):
        recorder.append(record(sequence=1))
```

- [ ] **Step 2: Run the recorder tests and confirm missing package failure**

Run: `python3 -m pytest tests/suas/test_recorder.py -q`

Expected: FAIL importing `matb_integration.suas.recording.recorder`.

- [ ] **Step 3: Implement record and artifact types**

```python
class RecordKind(StrEnum):
    LIFECYCLE = "lifecycle"
    COMMAND = "command"
    COMMAND_RESULT = "command_result"
    DOMAIN_EVENT = "domain_event"
    ALERT = "alert"
    PROBE = "probe"
    QUESTIONNAIRE = "questionnaire"
    PROTOCOL_DEVIATION = "protocol_deviation"
    CHECKPOINT = "checkpoint"

@dataclass(frozen=True, slots=True)
class SessionRecord:
    session_id: str
    block_id: str
    sequence: int
    simulation_time_ms: int
    wall_time_utc: str
    state_version: int
    kind: RecordKind
    payload: Mapping[str, object]

@dataclass(frozen=True, slots=True)
class ArtifactInfo:
    kind: str
    path: Path
    sha256: str
    size_bytes: int

class RecordingError(RuntimeError):
    pass
```

Validate nonempty session/block IDs, positive sequence, nonnegative times/versions, UTC timestamp parseability, and JSON-safe payloads in `SessionRecord.__post_init__()`.

- [ ] **Step 4: Implement the append-only writer and checkpoint cadence guard**

`SessionRecorder.__init__(run_dir, manifest, scenario_yaml)` creates only the run and checkpoint directories, writes `manifest.json` and the exact normalized `scenario_yaml` atomically, creates `events.jsonl` with exclusive mode, and initializes `_last_sequence=0`, `_checkpoint_version=0`, and no per-block checkpoint time. `SessionRecorder.open_existing(run_dir)` validates the frozen scenario/manifest pair, rejects a sealed or partial-sealed run for appends, reads the final complete record/checkpoint metadata, and reopens JSONL in append-only mode; it never truncates or repairs malformed data implicitly.

`append()` validates strict sequence increase, writes `canonical_json(record).encode("utf-8")`, flushes, calls `os.fsync()`, then updates `_last_sequence`. If any operation fails, retain the prior sequence and raise `RecordingError(f"record append failed: {exc}")`.

`checkpoint()` accepts only `SimulationEngine.checkpoint_snapshot()` output and reads `block_id`, `simulation_time_ms`, and `state_version` from it. It rejects a public/redacted snapshot, decreasing time within the same block, or invalid authoritative hash. It resets the cadence baseline when `block_id` changes and returns the prior artifact when fewer than 5,000 simulated milliseconds elapsed in that block. On a due write it increments the session-global checkpoint ordinal and writes the exact closed wrapper `{"checkpoint_version": int, "record_sequence": int, "engine": <private engine snapshot>}`; `record_sequence=_last_sequence` is the last durable JSONL record represented by this checkpoint. It writes canonical JSON through `gzip.GzipFile(filename=str(temp_path), mode="wb", mtime=0)`, fsyncs the temporary file, and atomically replaces `checkpoint-<checkpoint_version:08d>.json.gz`. State version remains independent and may restart at a block boundary, so checkpoint filenames cannot collide across PRACTICE/LOW/MEDIUM/HIGH.

- [ ] **Step 5: Run focused tests and a manual JSONL parse check**

Run: `python3 -m pytest tests/suas/test_recorder.py -q`

Expected: PASS.

- [ ] **Step 6: Commit and push Task 1**

```bash
git add matb_integration/suas/recording tests/suas/test_recorder.py
git diff --cached --check
git commit -m "feat(suas): add append-only session recording"
git push origin HEAD
```

### Task 2: Deterministic command/event replay verification

**Files:**
- Create: `matb_integration/suas/recording/replay.py`
- Create: `tests/suas/test_replay.py`

**Interfaces:**
- Consumes: `load_scenario_text()`, `SimulationEngine`, typed command deserialization, JSONL records.
- Produces: `ReplayStatus`, `ReplayResult`, `ReplayVerifier.verify()`, `event_chain_hash()`, and `deserialize_command()`.

- [ ] **Step 1: Write failing replay-match and tamper-detection tests**

```python
def test_replay_matches_final_state_and_event_chain(recorded_low_run: Path) -> None:
    result = ReplayVerifier().verify(recorded_low_run)
    assert result.status is ReplayStatus.MATCH
    assert result.expected_state_sha256 == result.actual_state_sha256
    assert result.expected_event_sha256 == result.actual_event_sha256

def test_replay_detects_tampered_applied_tick(recorded_low_run: Path) -> None:
    rewrite_record(recorded_low_run / "events.jsonl", kind="command", applied_tick=7)
    result = ReplayVerifier().verify(recorded_low_run)
    assert result.status is ReplayStatus.MISMATCH
    assert "state_sha256" in result.differences or "event_sha256" in result.differences

def test_replay_refuses_engine_version_mismatch(recorded_low_run: Path) -> None:
    rewrite_manifest(recorded_low_run, engine_version="99.0.0")
    result = ReplayVerifier().verify(recorded_low_run)
    assert result.status is ReplayStatus.INCOMPATIBLE_ENGINE
```

Add `recorded_low_run` and the mutation helpers directly to `tests/suas/test_replay.py`; build the fixture by running 100 LOW ticks, recording every accepted command/domain event, and appending `block_finished` with expected final and event hashes.

- [ ] **Step 2: Run replay tests and confirm missing verifier failure**

Run: `python3 -m pytest tests/suas/test_replay.py -q`

Expected: FAIL importing `ReplayVerifier`.

- [ ] **Step 3: Implement typed command deserialization and event-chain hashing**

Use a closed dictionary from the serialized `kind` string to the Phase 1 command dataclass. Reject unknown kinds and unknown payload keys. `event_chain_hash()` starts with 32 zero bytes and updates for each canonical domain event:

```python
chain = bytes(32)
for event in events:
    chain = hashlib.sha256(chain + canonical_json(event).encode("utf-8")).digest()
return chain.hex()
```

Do not include wall-clock values in this chain.

- [ ] **Step 4: Implement `ReplayVerifier.verify()`**

```python
class ReplayStatus(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"
    INVALID_RECORD = "invalid_record"
    INCOMPATIBLE_ENGINE = "incompatible_engine"

@dataclass(frozen=True, slots=True)
class ReplayResult:
    status: ReplayStatus
    expected_state_sha256: str | None
    actual_state_sha256: str | None
    expected_event_sha256: str | None
    actual_event_sha256: str | None
    records_read: int
    ticks_replayed: int
    differences: tuple[str, ...]
```

Verification must load the frozen `scenario.yaml`, verify its SHA against the manifest, require exact `ENGINE_VERSION`, group command records by block/applied tick, create a fresh engine on every `block_started`, step exactly to its matching `block_finished.simulation_time_ms`, compare each replayed deterministic domain event to recorded deterministic fields, and compare per-block plus session-chain state/event hashes. It supports either a one-block CLI run or the full four-block protocol. Convert malformed JSON, gaps, duplicate sequences, invalid command payloads, overlapping/missing lifecycle boundaries, or checkpoint ordinal gaps to `INVALID_RECORD` with a stable difference code; never raise raw parsing exceptions to callers.

- [ ] **Step 5: Run replay and runtime determinism tests**

Run: `python3 -m pytest tests/suas/test_replay.py tests/suas/test_runtime.py -q`

Expected: PASS.

- [ ] **Step 6: Commit and push Task 2**

```bash
git add matb_integration/suas/recording/replay.py tests/suas/test_replay.py
git diff --cached --check
git commit -m "feat(suas): verify deterministic mission replay"
git push origin HEAD
```

### Task 3: Component mission metrics and descriptive composite

**Files:**
- Create: `matb_integration/suas/metrics/__init__.py`
- Create: `matb_integration/suas/metrics/mission.py`
- Create: `tests/suas/test_mission_metrics.py`

**Interfaces:**
- Consumes: ordered `SessionRecord` values and scenario manifest thresholds.
- Produces: `BlockMetrics`, `derive_block_metrics()`, `normalize_component()`, and `mission_score()`.

- [ ] **Step 1: Write failing metric derivation tests using a complete synthetic record list**

```python
def test_metrics_keep_every_component_and_compute_feedback_score() -> None:
    metrics = derive_block_metrics(metric_records(), metric_manifest())
    assert metrics.coverage.percent == 80.0
    assert metrics.contacts.correct_reports == 3
    assert metrics.contacts.false_reports == 1
    assert metrics.commands.accepted == 5
    assert metrics.commands.rejected == 1
    assert metrics.links.lost_duration_ms == 10_000
    assert metrics.separation.critical_violations == 1
    assert metrics.assets.recovered == 3
    assert metrics.timeliness.on_time_fraction == 0.75
    assert metrics.mission_score == 74.0

def test_metrics_reject_sequence_gap() -> None:
    records = metric_records()
    with pytest.raises(ValueError, match="sequence gap"):
        derive_block_metrics(records[:2] + records[3:], metric_manifest())

def test_composite_is_clamped_and_labeled_descriptive() -> None:
    assert mission_score(200.0, 200.0, 200.0, 200.0) == 100.0
    assert mission_score(-1.0, -1.0, -1.0, -1.0) == 0.0
```

`metric_records()` must explicitly include lifecycle, coverage, contact workflow/report, command/result, link, alert/separation, aircraft recovery, and required-action records. Its declared thresholds must normalize to coverage `80`, contacts `60`, assets `90`, and timeliness `70`, producing exactly `0.30*80 + 0.30*60 + 0.20*90 + 0.20*70 = 74.0`; do not adjust the assertion after implementation.

- [ ] **Step 2: Run the metric tests and confirm missing module failure**

Run: `python3 -m pytest tests/suas/test_mission_metrics.py -q`

Expected: FAIL importing `matb_integration.suas.metrics.mission`.

- [ ] **Step 3: Implement typed component metric dataclasses**

Define frozen dataclasses `CoverageMetrics`, `ContactMetrics`, `CommandMetrics`, `AlertMetrics`, `LinkMetrics`, `SeparationMetrics`, `AssetMetrics`, `TimelinessMetrics`, and `BlockMetrics`. Each count defaults to zero, optional latencies use `None`, and `BlockMetrics.to_dict()` returns canonical JSON-safe snake_case keys. Human-factors fields are an empty `research` mapping until Phase 5 extends them.

- [ ] **Step 4: Implement one-pass record reduction and exact composite formula**

Validate session/block consistency and contiguous sequence first. Reduce stable event/result codes, retaining denominators as well as rates. Convert each observed fraction to ppm, then calculate `component = min(100, round(100 * observed_ppm / target_ppm, 2))` for coverage, contact effectiveness, asset preservation, and timeliness. The manifest targets must be positive. Explicit zero-denominator rules are: no required contacts yields `contact_effectiveness=100`, no required actions yields `timeliness=100`, and no active aircraft is invalid. Then compute:

```python
def mission_score(coverage: float, contacts: float, assets: float, timeliness: float) -> float:
    raw = 0.30 * coverage + 0.30 * contacts + 0.20 * assets + 0.20 * timeliness
    return round(max(0.0, min(100.0, raw)), 2)
```

Include `composite_label="descriptive_feedback_only"` and the four component inputs in output.

- [ ] **Step 5: Run metrics, replay, and root log-converter regression tests**

Run: `python3 -m pytest tests/suas/test_mission_metrics.py tests/suas/test_replay.py tests/test_log_converter.py -q`

Expected: PASS.

- [ ] **Step 6: Commit and push Task 3**

```bash
git add matb_integration/suas/metrics tests/suas/test_mission_metrics.py
git diff --cached --check
git commit -m "feat(suas): derive component mission outcomes"
git push origin HEAD
```

### Task 4: Artifact sealing, checksums, recorded CLI runs, and Phase 2 gate

**Files:**
- Create: `matb_integration/suas/recording/artifacts.py`
- Modify: `matb_integration/suas/recording/recorder.py`
- Modify: `matb_integration/suas/cli.py`
- Create: `tests/suas/test_artifacts.py`
- Modify: `tests/suas/test_cli.py`

**Interfaces:**
- Consumes: recorder, replay, metrics, engine CLI.
- Produces: atomic `questionnaires.json`, `metrics.json`, `debrief.json`, `replay-verification.json`, `checksums.sha256`, `SessionRecorder.seal()`, `SessionRecorder.seal_partial()`, CLI `record` and `verify` subcommands.

- [ ] **Step 1: Write failing artifact inventory and checksum tests**

```python
def test_seal_writes_complete_inventory_and_valid_checksums(recorded_low_run: Path) -> None:
    recorder = SessionRecorder.open_existing(recorded_low_run)
    replay = ReplayVerifier().verify(recorded_low_run)
    artifacts = recorder.seal(questionnaires={}, metrics={"coverage": {}},
                              debrief={"timeline": []}, replay=replay)
    names = {item.path.name for item in artifacts}
    assert {"questionnaires.json", "metrics.json", "debrief.json", "replay-verification.json",
            "checksums.sha256"} <= names
    assert verify_checksum_file(recorded_low_run / "checksums.sha256") == ()

def test_seal_refuses_replay_mismatch(recorded_low_run: Path) -> None:
    mismatch = replace(ReplayVerifier().verify(recorded_low_run), status=ReplayStatus.MISMATCH)
    with pytest.raises(RecordingError, match="replay must match"):
        SessionRecorder.open_existing(recorded_low_run).seal(
            questionnaires={}, metrics={}, debrief={}, replay=mismatch,
        )

def test_partial_seal_is_checksum_verifiable_but_not_replay_verified(recorded_low_run: Path) -> None:
    artifacts = SessionRecorder.open_existing(recorded_low_run).seal_partial(reason="aborted")
    assert verify_checksum_file(recorded_low_run / "checksums.sha256") == ()
    assert not (recorded_low_run / "replay-verification.json").exists()
    assert any(item.path.name == "partial-run.json" for item in artifacts)

def test_record_and_verify_cli_round_trip(tmp_path: Path) -> None:
    run = cli_record(tmp_path, block="LOW", ticks=300)
    verified = cli_verify(run)
    assert verified["status"] == "match"
    assert Path(run, "checksums.sha256").exists()
```

- [ ] **Step 2: Run artifact/CLI tests and confirm missing behavior**

Run: `python3 -m pytest tests/suas/test_artifacts.py tests/suas/test_cli.py -q`

Expected: FAIL because `SessionRecorder.seal` and CLI subcommands do not exist.

- [ ] **Step 3: Implement atomic JSON artifact writes and checksum verification**

`write_json_artifact(path, payload)` writes canonical JSON to `<name>.tmp`, flushes/fsyncs, then replaces the destination. `build_checksum_file(run_dir)` includes `scenario.yaml`, `manifest.json`, `events.jsonl`, every checkpoint, `questionnaires.json`, `metrics.json`, `debrief.json`, and `replay-verification.json` in sorted relative-path order for a complete run. For a partial run it includes `partial-run.json` plus every frozen/recorded artifact that exists. It excludes temporary files and `checksums.sha256` itself. `verify_checksum_file()` returns a tuple of stable mismatch/missing codes.

- [ ] **Step 4: Implement `SessionRecorder.seal()`**

Require recorder closed, a MATCH replay, and no existing checksum file. Write questionnaires, metrics, debrief, replay result, then checksums. Return `ArtifactInfo` for every artifact including manifest/scenario/events/checkpoints. A second identical seal returns the existing verified inventory; a differing second seal raises `RecordingError("sealed run is immutable")`.

`seal_partial(reason)` requires the recorder closed, writes canonical `partial-run.json` with the stable reason and last sequence/checkpoint, then checksums all extant immutable files. It does not write `questionnaires.json`, `metrics.json`, `debrief.json`, or `replay-verification.json`, and the artifact inventory labels it `partial_unverified`. It is idempotent only for the same reason and byte-identical inventory.

- [ ] **Step 5: Add `record` and `verify` CLI subcommands**

`record PATH --block PROFILE --ticks N --output DIR --session-id ID` must:

1. reject an existing nonempty run directory;
2. freeze the scenario/manifest;
3. append `session_prepared`, `block_started`, every command/result/event, due checkpoint, and `block_finished` records;
4. derive metrics and a minimal event-index debrief;
5. replay and seal with an empty `questionnaires={}` payload for this pre-protocol CLI;
6. print run directory, state/event hashes, metrics path, and replay status as JSON.

`verify RUN_DIR` verifies checksums first and replay second, prints both results, and exits 0 only when both match.

- [ ] **Step 6: Run the Phase 2 verification gate**

```bash
python3 -m pytest tests/suas -q
python3 -m pytest tests -q
task_tmp="$(mktemp -d)"
run_dir="$task_tmp/run"
python3 -m matb_integration.suas.cli record scenarios/suas/reference_area_search.yaml --block HIGH --ticks 1000 --output "$run_dir" --session-id phase2-smoke
python3 -m matb_integration.suas.cli verify "$run_dir"
```

Expected: all tests PASS; record and verify exit 0 with `status: match` and no network access.

- [ ] **Step 7: Commit and push the Phase 2 gate**

```bash
git add matb_integration/suas/recording/artifacts.py matb_integration/suas/recording/recorder.py matb_integration/suas/cli.py tests/suas/test_artifacts.py tests/suas/test_cli.py
git diff --cached --check
git commit -m "feat(suas): seal replayable research artifacts"
git push origin HEAD
```
