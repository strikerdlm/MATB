"""Single-session, controller-leased native sUAS runtime."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import secrets
import math
from collections import deque
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlmodel import Session, select

from matb_integration.suas.domain.commands import (
    AcknowledgeAlert, AssignSector, ClassifyContact, CommandEnvelope, CommandResult,
    Hold, InspectContact, ReportContact, ResumeMission, ReturnToBase,
    SetContactPriority, SetWaypoint,
)
from matb_integration.suas.domain.enums import ContactClassification, ContactPriority
from matb_integration.suas.domain.geometry import PointMM
from matb_integration.suas.domain.serialization import canonical_data, canonical_json
from matb_integration.suas.engine.runtime import (
    CHECKPOINT_INTERVAL_MS, ENGINE_VERSION, SNAPSHOT_INTERVAL_MS, TICK_MS, SimulationEngine,
)
from matb_integration.suas.metrics.mission import derive_block_metrics
from matb_integration.suas.recording.records import RecordKind, RecordingError, SessionRecord
from matb_integration.suas.recording.recorder import SessionRecorder
from matb_integration.suas.recording.checkpoints import load_checkpoint
from matb_integration.suas.recording.replay import ReplayVerifier, event_chain_hash
from matb_integration.suas.scenarios.loader import load_scenario
from matb_integration.suas.scenarios.manifest import build_session_manifest
from matb_integration.suas.scenarios.profiles import block_order_for_participant

from .models import Participant, Visit
from .simulation_models import SimulationBlock, SimulationSession
from .simulation_persistence import InMemorySimulationPersistence, SimulationPersistence
from .simulation_schemas import (
    CommandRequest, CreateSimulationSession, FinishRequest, PreparedSession, RecoveryView, SessionView,
)
from .websocket.simulation import SimulationHub, StreamEnvelope, StreamKind


class SimulationError(RuntimeError):
    code = "simulation_error"


class SimulationConflict(SimulationError):
    code = "active_session"


class SimulationNotFound(SimulationError):
    code = "simulation_not_found"


class InvalidLease(SimulationError):
    code = "invalid_lease"


class InvalidTransition(SimulationError):
    code = "invalid_transition"


@dataclass(slots=True)
class _QueuedCommand:
    envelope: CommandEnvelope
    future: asyncio.Future[CommandResult]


@dataclass(slots=True)
class RuntimeHandle:
    session_id: str
    participant_id: str
    visit_id: int
    locale: str
    scenario: Any
    manifest: dict[str, object]
    recorder: SessionRecorder
    lease_hash: str
    lifecycle: str = "PREPARED"
    active_block_id: str | None = None
    engine: SimulationEngine | None = None
    sequence: int = 0
    block_events: list[object] = field(default_factory=list)
    queue: deque[_QueuedCommand] = field(default_factory=deque)
    tick_task: asyncio.Task[Any] | None = None
    snapshot_task: asyncio.Task[Any] | None = None
    finish_disposition: str | None = None
    transport_sequence: int = 0
    validity: str = "valid"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _wall_time() -> str:
    return _utcnow().isoformat(timespec="milliseconds").replace("+00:00", "Z")


class SimulationManager:
    """Own exactly one authoritative process-local simulation handle."""

    def __init__(
        self,
        *,
        scenario_root: Path,
        artifact_root: Path,
        persistence: SimulationPersistence | None = None,
        tick_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        wall_clock: Callable[[], str] = _wall_time,
        run_background_tasks: bool = True,
        ui_version: str = "0.1.0",
        hub: SimulationHub | None = None,
        wall_time_scale: float = 1.0,
    ) -> None:
        self.scenario_root = Path(scenario_root)
        self.artifact_root = Path(artifact_root)
        self.persistence = persistence or InMemorySimulationPersistence()
        self._sleep = tick_sleep
        self._wall_clock = wall_clock
        self._run_background_tasks = run_background_tasks
        self._ui_version = ui_version
        if not math.isfinite(wall_time_scale) or not 0.05 <= wall_time_scale <= 1.0:
            raise ValueError("wall_time_scale must be a finite value in [0.05, 1.0]")
        self._wall_time_scale = wall_time_scale
        self.hub = hub or SimulationHub(on_controller_overflow=self._pause_for_stream_overflow)
        self._handle: RuntimeHandle | None = None
        self._lock = asyncio.Lock()
        self._shutdown = False

    @property
    def active(self) -> RuntimeHandle | None:
        return self._handle

    async def prepare(self, request: CreateSimulationSession, db: Session) -> PreparedSession:
        async with self._lock:
            if self._handle is not None and self._handle.lifecycle not in {"FINISHED", "ABORTED"}:
                raise SimulationConflict("an active session already exists")
            participant = db.get(Participant, request.participant_id)
            if participant is None:
                raise SimulationNotFound("participant not found")
            visit = db.exec(select(Visit).where(
                Visit.participant_id == request.participant_id,
                Visit.visit_ordinal == request.visit_ordinal,
            )).one_or_none()
            if visit is None:
                raise SimulationNotFound("visit not found")
            scenario_root = self.scenario_root.resolve()
            scenario_path = self.scenario_root / f"{request.scenario_id}.yaml"
            resolved_scenario = scenario_path.resolve()
            if (
                not scenario_path.is_file()
                or resolved_scenario.parent != scenario_root
                or not resolved_scenario.is_file()
            ):
                raise SimulationNotFound("scenario not found")
            loaded = load_scenario(resolved_scenario)
            order = block_order_for_participant(request.participant_id)
            manifest = build_session_manifest(
                loaded,
                participant_id=request.participant_id,
                visit_ordinal=request.visit_ordinal,
                locale=request.locale,
                block_order=order,
                ui_version=self._ui_version,
                engine_version=ENGINE_VERSION,
            )
            session_id = self._new_session_id()
            lease = secrets.token_urlsafe(32)
            run_dir = self.artifact_root / session_id
            recorder = SessionRecorder(run_dir, manifest, loaded.normalized_yaml)
            handle = RuntimeHandle(
                session_id=session_id, participant_id=request.participant_id, visit_id=int(visit.id),
                locale=request.locale, scenario=loaded, manifest=manifest, recorder=recorder,
                lease_hash=self._hash_lease(lease),
            )
            self._handle = handle
            self._append(handle, RecordKind.LIFECYCLE, {
                "event": "session_prepared", "scenario_id": loaded.definition.scenario_id,
            }, 0, 0)
            db.add(SimulationSession(
                id=session_id,
                participant_id=request.participant_id,
                visit_id=int(visit.id),
                scenario_id=loaded.definition.scenario_id,
                scenario_sha256=loaded.sha256,
                manifest_json=canonical_json(manifest),
                locale=request.locale,
                lifecycle="PREPARED",
                validity="valid",
                artifact_root=str(run_dir),
            ))
            for index, block_id in enumerate(("PRACTICE", *(item.value for item in order)), start=0):
                db.add(SimulationBlock(
                    session_id=session_id, block_id=block_id, profile=block_id,
                    order_index=index, lifecycle="PREPARED",
                ))
            db.commit()
            self.persistence.update_session(session_id, lifecycle="PREPARED")
            return self._prepared_view(handle, lease)

    async def start(self, session_id: str, block_id: str, lease: str) -> SessionView:
        async with self._lock:
            handle = self._require(session_id, lease)
            if handle.lifecycle == "RUNNING" and handle.active_block_id == block_id:
                return self._view(handle)
            if handle.lifecycle != "PREPARED":
                raise InvalidTransition(f"cannot start from {handle.lifecycle}")
            expected = ("PRACTICE", *handle.manifest["block_order"])
            if block_id != expected[0]:
                raise InvalidTransition("block is not next in protocol")
            handle.engine = SimulationEngine(handle.scenario.definition, block_id)
            handle.active_block_id = block_id
            handle.lifecycle = "RUNNING"
            self.persistence.update_session(session_id, lifecycle="RUNNING", active_block_id=block_id, started_at=_utcnow())
            self.persistence.update_block(session_id, block_id, lifecycle="RUNNING", simulation_started_ms=0, started_at=_utcnow())
            self._append(handle, RecordKind.LIFECYCLE, {"event": "block_started", "active_aircraft": len(handle.scenario.definition.blocks[block_id].aircraft_ids), "required_contacts": len(handle.scenario.definition.blocks[block_id].contact_ids), "required_actions": 0}, 0, 0)
            await self._publish_latest_record(handle, kind=StreamKind.LIFECYCLE)
            if self._run_background_tasks:
                handle.tick_task = asyncio.create_task(self._tick_loop())
                handle.snapshot_task = asyncio.create_task(self._snapshot_loop())
            return self._view(handle)

    async def pause(self, session_id: str, lease: str, reason: str = "operator_pause") -> SessionView:
        async with self._lock:
            handle = self._require(session_id, lease)
            if handle.lifecycle == "PAUSED":
                return self._view(handle)
            if handle.lifecycle != "RUNNING":
                raise InvalidTransition(f"cannot pause from {handle.lifecycle}")
            handle.lifecycle = "PAUSED"
            self.persistence.update_session(session_id, lifecycle="PAUSED")
            self._append(handle, RecordKind.LIFECYCLE, {"event": "session_paused", "reason": reason}, self._time(handle), self._version(handle))
            await self._publish_latest_record(handle, kind=StreamKind.LIFECYCLE)
            return self._view(handle)

    async def resume(self, session_id: str, lease: str) -> SessionView:
        async with self._lock:
            handle = self._require(session_id, lease)
            if handle.lifecycle == "RUNNING":
                return self._view(handle)
            if handle.lifecycle != "PAUSED":
                raise InvalidTransition(f"cannot resume from {handle.lifecycle}")
            handle.lifecycle = "RUNNING"
            self.persistence.update_session(session_id, lifecycle="RUNNING")
            self._append(handle, RecordKind.LIFECYCLE, {"event": "session_resumed"}, self._time(handle), self._version(handle))
            await self._publish_latest_record(handle, kind=StreamKind.LIFECYCLE)
            if self._run_background_tasks and handle.tick_task is None:
                handle.tick_task = asyncio.create_task(self._tick_loop())
            return self._view(handle)

    async def finish(self, session_id: str, lease: str, disposition: FinishRequest | str = "complete") -> SessionView:
        async with self._lock:
            handle = self._require(session_id, lease)
            value = disposition.disposition if isinstance(disposition, FinishRequest) else disposition
            if handle.lifecycle in {"FINISHED", "ABORTED"}:
                if handle.finish_disposition == value:
                    return self._view(handle)
                raise InvalidTransition("conflicting terminal disposition")
            if handle.lifecycle not in {"PREPARED", "RUNNING", "PAUSED"}:
                raise InvalidTransition(f"cannot finish from {handle.lifecycle}")
            if handle.lifecycle == "PREPARED" and value != "abort":
                raise InvalidTransition("a prepared session can only be aborted")
            handle.finish_disposition = value
            handle.lifecycle = "FINISHED" if value == "complete" else "ABORTED"
            now = self._time(handle)
            if value == "complete" and handle.active_block_id and handle.engine is not None:
                self._append(handle, RecordKind.LIFECYCLE, {
                    "event": "block_finished",
                    "state_sha256": handle.engine.state_hash,
                    "event_sha256": event_chain_hash(handle.block_events),
                }, now, self._version(handle))
            self._append(handle, RecordKind.LIFECYCLE, {"event": "session_finished", "disposition": value}, now, self._version(handle))
            await self._publish_latest_record(handle, kind=StreamKind.LIFECYCLE)
            self._cancel_tasks(handle)
            handle.recorder.close()
            if value == "abort":
                self.persistence.add_deviation(
                    handle.session_id, handle.active_block_id, "aborted", "warning", now,
                    {"reason": "aborted"},
                )
                artifacts = handle.recorder.seal_partial(reason="aborted")
                self.persistence.replace_artifacts(handle.session_id, artifacts)
            else:
                # A complete multi-block seal is finalized by the protocol layer; a
                # one-block runtime can still expose a deterministic partial view.
                replay = ReplayVerifier().verify(handle.recorder.run_dir)
                if replay.status.value == "match":
                    records = _read_records(handle.recorder.run_dir / "events.jsonl")
                    metrics = derive_block_metrics(records, handle.manifest).to_dict()
                    artifacts = handle.recorder.seal(questionnaires={}, metrics=metrics, debrief={"timeline": []}, replay=replay)
                    self.persistence.replace_artifacts(handle.session_id, artifacts)
            self.persistence.update_session(session_id, lifecycle=handle.lifecycle, finished_at=_utcnow(), active_block_id=handle.active_block_id)
            if handle.active_block_id:
                self.persistence.update_block(session_id, handle.active_block_id, lifecycle=handle.lifecycle, simulation_finished_ms=now, finished_at=_utcnow())
            return self._view(handle)

    async def submit(self, session_id: str, lease: str, request: CommandRequest) -> CommandResult:
        async with self._lock:
            handle = self._require(session_id, lease)
            if handle.lifecycle != "RUNNING" or handle.engine is None:
                raise InvalidTransition("commands require a running session")
            envelope = _command_envelope(request)
            future: asyncio.Future[CommandResult] = asyncio.get_running_loop().create_future()
            handle.queue.append(_QueuedCommand(envelope, future))
        return await future

    async def tick_once(self) -> None:
        async with self._lock:
            handle = self._handle
            if handle is None or handle.lifecycle != "RUNNING" or handle.engine is None:
                return
            queued = list(handle.queue)
            handle.queue.clear()
            commands = [item.envelope for item in queued]
            record_sequence_before = handle.sequence
            checkpoint_before = handle.engine.checkpoint_snapshot()
            try:
                result = handle.engine.step(commands)
                tick = int(result.snapshot["tick"])
                for item in queued:
                    self._append(handle, RecordKind.COMMAND, {"applied_tick": tick, "command": _serialize_command(item.envelope)}, result.snapshot["simulation_time_ms"], result.snapshot["state_version"])
                for command_result in result.command_results:
                    self._append(handle, RecordKind.COMMAND_RESULT, canonical_data(command_result), result.snapshot["simulation_time_ms"], result.snapshot["state_version"])
                for event in result.events:
                    value = canonical_data(event)
                    handle.block_events.append(value)
                    self._append(handle, RecordKind.DOMAIN_EVENT, {"event": value}, event.simulation_time_ms, result.snapshot["state_version"])
                if int(result.snapshot["simulation_time_ms"]) % CHECKPOINT_INTERVAL_MS == 0:
                    artifact = handle.recorder.checkpoint(handle.engine.checkpoint_snapshot())
                    self._append(handle, RecordKind.CHECKPOINT, {"path": artifact.path.name}, int(result.snapshot["simulation_time_ms"]), int(result.snapshot["state_version"]))
                for item, command_result in zip(queued, result.command_results, strict=False):
                    if not item.future.done():
                        item.future.set_result(command_result)
                await self._publish_tick_records(handle, result.snapshot, record_sequence_before)
            except RecordingError:
                try:
                    handle.engine.restore(checkpoint_before)
                except Exception:
                    pass
                await self._interrupt(handle, "recording_failure", {"reason": "recording_failure"})
                for item in queued:
                    if not item.future.done():
                        item.future.set_exception(RecordingError("recording failure"))
            except Exception as error:
                try:
                    handle.engine.restore(checkpoint_before)
                except Exception:
                    pass
                await self._interrupt(handle, "runtime_failure", {"reason": type(error).__name__})
                for item in queued:
                    if not item.future.done():
                        item.future.set_exception(error)
                return

    async def snapshot_once(self) -> dict[str, object]:
        async with self._lock:
            handle = self._handle
            if handle is None or handle.engine is None:
                raise SimulationNotFound("no active simulation")
            snapshot = dict(handle.engine.snapshot())
            await self._publish_snapshot(handle, snapshot)
            return snapshot

    async def state(self, session_id: str) -> dict[str, object]:
        async with self._lock:
            handle = self._require(session_id, None, check_lease=False)
            if handle.engine is None:
                return {"session_id": session_id, "lifecycle": handle.lifecycle, "simulation_time_ms": 0, "state_version": 0}
            return handle.engine.snapshot()

    async def view(self, session_id: str, lease: str | None = None) -> SessionView:
        """Return public lifecycle metadata without ever exposing a lease."""

        async with self._lock:
            handle = self._require(session_id, lease, check_lease=lease is not None)
            return self._view(handle)

    async def shutdown(self) -> None:
        async with self._lock:
            self._shutdown = True
            if self._handle is not None:
                if self._handle.lifecycle in {"RUNNING", "PAUSED"}:
                    await self._interrupt(self._handle, "process_shutdown", {"reason": "process_shutdown"}, severity="warning")
                self._cancel_tasks(self._handle)

    async def recover(
        self,
        session_id: str,
        lease: str | None,
        checkpoint_version: int,
        *,
        confirm_process_restart: bool = False,
    ) -> RecoveryView:
        """Restore one exact checkpoint and return a paused, deviated view."""

        async with self._lock:
            if self._handle is None:
                if lease is not None or not confirm_process_restart:
                    raise InvalidLease("process-restart recovery requires confirmation")
                return self._recover_stale_locked(session_id, checkpoint_version)
            handle = self._require(session_id, lease, check_lease=True)
            if handle.lifecycle != "INTERRUPTED":
                raise InvalidTransition(f"cannot recover from {handle.lifecycle}")
            if isinstance(checkpoint_version, bool) or not isinstance(checkpoint_version, int) or checkpoint_version <= 0:
                raise ValueError("checkpoint_version must be positive")
            path = handle.recorder.checkpoints_dir / f"checkpoint-{checkpoint_version:08d}.json.gz"
            wrapper = load_checkpoint(path)
            engine_snapshot = wrapper["engine"]
            if not isinstance(engine_snapshot, Mapping):
                raise RecordingError("checkpoint has no engine snapshot")
            if handle.engine is None:
                raise RecordingError("interrupted session has no engine")
            handle.engine.restore(engine_snapshot)
            old_recorder = handle.recorder
            old_recorder.close()
            reopened = SessionRecorder.open_existing(old_recorder.run_dir)
            previous_sequence = reopened._last_sequence
            record_sequence = wrapper["record_sequence"]
            if not isinstance(record_sequence, int) or record_sequence > previous_sequence:
                raise RecordingError("checkpoint record sequence is outside the recording")
            reopened.append(SessionRecord(
                session_id=session_id,
                block_id=handle.active_block_id or "PRACTICE",
                sequence=previous_sequence + 1,
                simulation_time_ms=int(engine_snapshot.get("simulation_time_ms", 0)),
                wall_time_utc=self._wall_clock(),
                state_version=int(engine_snapshot.get("state_version", 0)),
                kind=RecordKind.LIFECYCLE,
                payload={
                    "event": "checkpoint_recovery",
                    "checkpoint_version": checkpoint_version,
                    "record_sequence": record_sequence,
                    "invalidated_sequence_start": record_sequence + 1 if record_sequence < previous_sequence else None,
                    "invalidated_sequence_end": previous_sequence if record_sequence < previous_sequence else None,
                },
            ))
            handle.recorder = reopened
            handle.sequence = previous_sequence + 1
            handle.lifecycle = "PAUSED"
            handle.validity = "valid_with_deviation"
            self.persistence.update_session(
                session_id, lifecycle="PAUSED", validity="valid_with_deviation", active_block_id=handle.active_block_id,
            )
            if handle.active_block_id:
                self.persistence.update_block(
                    session_id,
                    handle.active_block_id,
                    lifecycle="PAUSED",
                    validity="valid_with_deviation",
                    was_interrupted=True,
                    recovered_from_checkpoint=checkpoint_version,
                    simulation_finished_ms=None,
                )
            self.persistence.add_deviation(
                session_id,
                handle.active_block_id,
                "checkpoint_recovery",
                "warning",
                int(engine_snapshot.get("simulation_time_ms", 0)),
                {"checkpoint_version": checkpoint_version, "record_sequence": record_sequence},
            )
            return RecoveryView.model_validate({**self._view(handle).model_dump(), "controller_lease": None})

    def _recover_stale_locked(self, session_id: str, checkpoint_version: int) -> RecoveryView:
        loader = getattr(self.persistence, "load_session", None)
        if loader is None:
            raise SimulationNotFound("simulation not found")
        row = loader(session_id)
        if row is None:
            raise SimulationNotFound("simulation not found")
        if isinstance(checkpoint_version, bool) or not isinstance(checkpoint_version, int) or checkpoint_version <= 0:
            raise ValueError("checkpoint_version must be positive")
        scenario_root = self.scenario_root.resolve()
        scenario_path = (scenario_root / f"{row.scenario_id}.yaml").resolve()
        if scenario_path.parent != scenario_root or not scenario_path.is_file():
            raise SimulationNotFound("scenario not found")
        loaded = load_scenario(scenario_path)
        if loaded.sha256 != row.scenario_sha256:
            raise RecordingError("scenario hash does not match persisted session")
        try:
            manifest = json.loads(row.manifest_json)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RecordingError("persisted manifest is invalid") from exc
        if not isinstance(manifest, dict) or manifest.get("scenario_sha256") != loaded.sha256:
            raise RecordingError("persisted manifest does not match scenario")
        configured_root = self.artifact_root.resolve()
        run_dir = Path(row.artifact_root)
        if not run_dir.is_absolute():
            run_dir = configured_root / run_dir
        run_dir = run_dir.resolve()
        if run_dir.parent != configured_root or run_dir.name != session_id:
            raise RecordingError("persisted artifact root is outside configured output")
        recorder = SessionRecorder.open_existing(run_dir)
        checkpoint_path = recorder.checkpoints_dir / f"checkpoint-{checkpoint_version:08d}.json.gz"
        wrapper = load_checkpoint(checkpoint_path)
        engine_snapshot = wrapper["engine"]
        if not isinstance(engine_snapshot, Mapping):
            raise RecordingError("checkpoint has no engine snapshot")
        block_id = engine_snapshot.get("block_id")
        if not isinstance(block_id, str) or block_id not in loaded.definition.blocks:
            raise RecordingError("checkpoint block does not match scenario")
        engine = SimulationEngine(loaded.definition, block_id)
        engine.restore(engine_snapshot)
        lease = secrets.token_urlsafe(32)
        handle = RuntimeHandle(
            session_id=session_id,
            participant_id=row.participant_id,
            visit_id=int(row.visit_id),
            locale=row.locale,
            scenario=loaded,
            manifest=manifest,
            recorder=recorder,
            lease_hash=self._hash_lease(lease),
            lifecycle="INTERRUPTED",
            active_block_id=block_id,
            engine=engine,
            validity="valid_with_deviation",
        )
        previous_sequence = recorder._last_sequence
        record_sequence = wrapper["record_sequence"]
        if not isinstance(record_sequence, int) or record_sequence > previous_sequence:
            raise RecordingError("checkpoint record sequence is outside the recording")
        recorder.append(SessionRecord(
            session_id=session_id,
            block_id=block_id,
            sequence=previous_sequence + 1,
            simulation_time_ms=int(engine_snapshot.get("simulation_time_ms", 0)),
            wall_time_utc=self._wall_clock(),
            state_version=int(engine_snapshot.get("state_version", 0)),
            kind=RecordKind.LIFECYCLE,
            payload={
                "event": "checkpoint_recovery",
                "checkpoint_version": checkpoint_version,
                "record_sequence": record_sequence,
                "invalidated_sequence_start": record_sequence + 1 if record_sequence < previous_sequence else None,
                "invalidated_sequence_end": previous_sequence if record_sequence < previous_sequence else None,
            },
        ))
        handle.sequence = previous_sequence + 1
        handle.lifecycle = "PAUSED"
        self._handle = handle
        self.persistence.update_session(session_id, lifecycle="PAUSED", validity="valid_with_deviation", active_block_id=block_id)
        self.persistence.update_block(
            session_id,
            block_id,
            lifecycle="PAUSED",
            validity="valid_with_deviation",
            was_interrupted=True,
            recovered_from_checkpoint=checkpoint_version,
        )
        self.persistence.add_deviation(
            session_id,
            block_id,
            "checkpoint_recovery",
            "warning",
            int(engine_snapshot.get("simulation_time_ms", 0)),
            {"checkpoint_version": checkpoint_version, "record_sequence": record_sequence, "process_restart": True},
        )
        return RecoveryView.model_validate({**self._view(handle).model_dump(), "controller_lease": lease})

    async def controller_connected(self, session_id: str, lease: str) -> None:
        """Validate a controller stream lease without changing lifecycle."""

        async with self._lock:
            self._require(session_id, lease)

    async def controller_disconnected(self, session_id: str, lease: str) -> None:
        """Pause immediately on a valid controller disconnect; never resume."""

        async with self._lock:
            handle = self._require(session_id, lease)
            if handle.lifecycle != "RUNNING":
                return
            handle.lifecycle = "PAUSED"
            self.persistence.update_session(session_id, lifecycle="PAUSED")
            self._append(handle, RecordKind.LIFECYCLE, {
                "event": "controller_disconnected", "reason": "controller_disconnect",
            }, self._time(handle), self._version(handle))
            await self._publish_latest_record(handle, kind=StreamKind.LIFECYCLE)

    async def observer_disconnected(self, session_id: str) -> None:
        """Observer disconnects are read-only and do not affect lifecycle."""

        async with self._lock:
            self._require(session_id, None, check_lease=False)

    async def snapshot_envelope(self, session_id: str, *, after_sequence: int = 0) -> StreamEnvelope:
        """Build a fresh complete snapshot for WebSocket resynchronization."""

        async with self._lock:
            handle = self._require(session_id, None, check_lease=False)
            snapshot = dict(handle.engine.snapshot()) if handle.engine is not None else {
                "session_id": session_id, "lifecycle": handle.lifecycle,
                "simulation_time_ms": 0, "state_version": 0,
            }
            return self._new_envelope(
                handle,
                StreamKind.SNAPSHOT,
                {**snapshot, "resynchronizes_after_sequence": max(0, int(after_sequence))},
                self._time(handle),
                self._version(handle),
            )

    async def _tick_loop(self) -> None:
        while True:
            async with self._lock:
                handle = self._handle
                if handle is None or handle.lifecycle != "RUNNING" or self._shutdown:
                    return
            started = asyncio.get_running_loop().time()
            await self.tick_once()
            remaining = max(0.0, (TICK_MS / 1000) - (asyncio.get_running_loop().time() - started))
            await self._sleep(remaining * self._wall_time_scale)

    async def _snapshot_loop(self) -> None:
        while True:
            async with self._lock:
                handle = self._handle
                if handle is None or handle.lifecycle not in {"RUNNING", "PAUSED"} or self._shutdown:
                    return
            await self.snapshot_once()
            await self._sleep((SNAPSHOT_INTERVAL_MS / 1000) * self._wall_time_scale)

    def _append(self, handle: RuntimeHandle, kind: RecordKind, payload: Mapping[str, object], time_ms: int, state_version: int) -> SessionRecord:
        handle.sequence += 1
        record = SessionRecord(
            session_id=handle.session_id,
            block_id=handle.active_block_id or "PRACTICE",
            sequence=handle.sequence,
            simulation_time_ms=time_ms,
            wall_time_utc=self._wall_clock(),
            state_version=state_version,
            kind=kind,
            payload=dict(payload),
        )
        handle.recorder.append(record)
        return record

    async def _publish_latest_record(self, handle: RuntimeHandle, *, kind: StreamKind | None = None) -> None:
        """Publish the most recently appended record after it is durable."""

        path = handle.recorder.run_dir / "events.jsonl"
        records = _read_records(path)
        if not records:
            return
        record = records[-1]
        selected = kind
        if selected is None:
            selected = {
                RecordKind.DOMAIN_EVENT: StreamKind.DOMAIN_EVENT,
                RecordKind.ALERT: StreamKind.ALERT,
                RecordKind.COMMAND_RESULT: StreamKind.COMMAND_RESULT,
                RecordKind.PROBE: StreamKind.PROBE,
                RecordKind.LIFECYCLE: StreamKind.LIFECYCLE,
                RecordKind.CHECKPOINT: StreamKind.CHECKPOINT,
            }.get(record.kind)
        if selected is not None:
            await self.hub.publish(handle.session_id, self._new_envelope(
                handle, selected, canonical_data(record.payload), record.simulation_time_ms, record.state_version,
            ))

    async def _publish_tick_records(
        self, handle: RuntimeHandle, snapshot: Mapping[str, object], record_sequence_before: int,
    ) -> None:
        records = _read_records(handle.recorder.run_dir / "events.jsonl")
        # Only records produced by the current tick are transport events.  The
        # recorder remains the authoritative order; transport subscribers see
        # the same order but with an independent sequence counter.
        for record in records:
            if record.sequence <= record_sequence_before:
                continue
            kind = {
                RecordKind.DOMAIN_EVENT: StreamKind.DOMAIN_EVENT,
                RecordKind.ALERT: StreamKind.ALERT,
                RecordKind.COMMAND_RESULT: StreamKind.COMMAND_RESULT,
                RecordKind.CHECKPOINT: StreamKind.CHECKPOINT,
            }.get(record.kind)
            if kind is not None:
                await self.hub.publish(handle.session_id, self._new_envelope(
                    handle, kind, canonical_data(record.payload), record.simulation_time_ms, record.state_version,
                ))

    async def _publish_snapshot(self, handle: RuntimeHandle, snapshot: Mapping[str, object]) -> None:
        await self.hub.publish(handle.session_id, self._new_envelope(
            handle, StreamKind.SNAPSHOT,
            {**canonical_data(snapshot), "authoritative_event_sequence": snapshot.get("event_sequence", 0)},
            int(snapshot.get("simulation_time_ms", 0)), int(snapshot.get("state_version", 0)),
        ))

    def _new_envelope(
        self, handle: RuntimeHandle, kind: StreamKind, payload: Mapping[str, object], time_ms: int, state_version: int,
    ) -> StreamEnvelope:
        handle.transport_sequence += 1
        return StreamEnvelope(
            session_id=handle.session_id,
            sequence=handle.transport_sequence,
            simulation_time_ms=max(0, int(time_ms)),
            wall_time_utc=self._wall_clock(),
            state_version=max(0, int(state_version)),
            kind=kind,
            payload=dict(payload),
        )

    async def _pause_for_stream_overflow(self, session_id: str) -> None:
        handle = self._handle
        if handle is None or handle.session_id != session_id or handle.lifecycle != "RUNNING":
            return
        if self._lock.locked():
            # Hub publication normally occurs while tick/lifecycle mutation is
            # protected by this lock.  Mutate the same handle directly to
            # avoid waiting on ourselves; the durable pause record is written
            # before the overflow callback returns.
            handle.lifecycle = "PAUSED"
            self.persistence.update_session(session_id, lifecycle="PAUSED")
            self._append(
                handle,
                RecordKind.LIFECYCLE,
                {"event": "session_paused", "reason": "stream_backpressure"},
                self._time(handle),
                self._version(handle),
            )
            return
        # Called by the hub outside its lock.  Reuse the normal disconnect
        # semantics with the in-memory lease hash already held by the manager.
        await self._pause_without_lease(session_id)

    async def _pause_without_lease(self, session_id: str) -> None:
        async with self._lock:
            handle = self._handle
            if handle is None or handle.session_id != session_id or handle.lifecycle != "RUNNING":
                return
            handle.lifecycle = "PAUSED"
            self.persistence.update_session(session_id, lifecycle="PAUSED")
            self._append(handle, RecordKind.LIFECYCLE, {"event": "session_paused", "reason": "stream_backpressure"}, self._time(handle), self._version(handle))

    def _require(self, session_id: str, lease: str | None, *, check_lease: bool = True) -> RuntimeHandle:
        handle = self._handle
        if handle is None or handle.session_id != session_id:
            raise SimulationNotFound("simulation not found")
        if check_lease and self._hash_lease(lease or "") != handle.lease_hash:
            raise InvalidLease("invalid controller lease")
        return handle

    @staticmethod
    def _hash_lease(lease: str) -> str:
        return hashlib.sha256(lease.encode("utf-8")).hexdigest()

    @staticmethod
    def _new_session_id() -> str:
        return f"sim-{_utcnow().strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(4)}"

    @staticmethod
    def _cancel_tasks(handle: RuntimeHandle) -> None:
        for task in (handle.tick_task, handle.snapshot_task):
            if task is not None and not task.done() and task is not asyncio.current_task():
                task.cancel()
        handle.tick_task = None
        handle.snapshot_task = None

    @staticmethod
    def _time(handle: RuntimeHandle) -> int:
        return int(handle.engine.snapshot()["simulation_time_ms"]) if handle.engine else 0

    @staticmethod
    def _version(handle: RuntimeHandle) -> int:
        return int(handle.engine.snapshot()["state_version"]) if handle.engine else 0

    def _view(self, handle: RuntimeHandle) -> SessionView:
        return SessionView(
            id=handle.session_id, participant_id=handle.participant_id, visit_id=handle.visit_id,
            scenario_id=handle.scenario.definition.scenario_id, scenario_sha256=handle.scenario.sha256,
            locale=handle.locale, lifecycle=handle.lifecycle, active_block_id=handle.active_block_id,
            block_order=list(handle.manifest["block_order"]), state_version=self._version(handle),
            simulation_time_ms=self._time(handle), validity=handle.validity,
        )

    async def _interrupt(
        self,
        handle: RuntimeHandle,
        code: str,
        detail: Mapping[str, object],
        *,
        severity: str = "fatal",
    ) -> None:
        handle.lifecycle = "INTERRUPTED"
        handle.validity = "invalid"
        self._cancel_tasks(handle)
        now = self._time(handle)
        self.persistence.update_session(
            handle.session_id,
            lifecycle="INTERRUPTED",
            interrupted_at=_utcnow(),
            validity="invalid",
        )
        if handle.active_block_id:
            self.persistence.update_block(
                handle.session_id,
                handle.active_block_id,
                lifecycle="INTERRUPTED",
                validity="invalid",
                was_interrupted=True,
            )
        self.persistence.add_deviation(handle.session_id, handle.active_block_id, code, severity, now, detail)
        try:
            record = self._append(
                handle,
                RecordKind.LIFECYCLE,
                {"event": code, **dict(detail)},
                now,
                self._version(handle),
            )
            await self.hub.publish(
                handle.session_id,
                self._new_envelope(handle, StreamKind.ERROR, {"code": code, "fatal": severity == "fatal"}, now, record.state_version),
            )
        except RecordingError:
            await self.hub.publish(
                handle.session_id,
                self._new_envelope(handle, StreamKind.ERROR, {"code": code, "fatal": severity == "fatal"}, now, self._version(handle)),
            )

    def _prepared_view(self, handle: RuntimeHandle, lease: str) -> PreparedSession:
        return PreparedSession.model_validate({**self._view(handle).model_dump(), "controller_lease": lease})


def _command_envelope(request: CommandRequest) -> CommandEnvelope:
    kind = request.kind
    names = {
        "ASSIGN_SECTOR": (AssignSector, {"aircraft_id", "sector_id"}),
        "SET_WAYPOINT": (SetWaypoint, {"aircraft_id", "waypoint"}),
        "HOLD": (Hold, {"aircraft_id"}), "RESUME_MISSION": (ResumeMission, {"aircraft_id"}),
        "RETURN_TO_BASE": (ReturnToBase, {"aircraft_id"}), "ACKNOWLEDGE_ALERT": (AcknowledgeAlert, {"alert_id"}),
        "INSPECT_CONTACT": (InspectContact, {"contact_id"}), "CLASSIFY_CONTACT": (ClassifyContact, {"contact_id", "classification"}),
        "SET_CONTACT_PRIORITY": (SetContactPriority, {"contact_id", "priority"}), "REPORT_CONTACT": (ReportContact, {"contact_id", "note_code"}),
    }
    cls, fields = names[kind]
    payload = dict(request.payload)
    if set(payload) != fields:
        raise ValueError("invalid command payload")
    if cls is SetWaypoint:
        waypoint = payload["waypoint"]
        if not isinstance(waypoint, Mapping) or set(waypoint) != {"x_mm", "y_mm"}:
            raise ValueError("invalid waypoint payload")
        command = cls(str(payload["aircraft_id"]), PointMM(int(waypoint["x_mm"]), int(waypoint["y_mm"])))
    elif cls is ClassifyContact:
        command = cls(str(payload["contact_id"]), ContactClassification(str(payload["classification"])))
    elif cls is SetContactPriority:
        command = cls(str(payload["contact_id"]), ContactPriority(str(payload["priority"])))
    else:
        command = cls(**{key: str(value) for key, value in payload.items()})
    return CommandEnvelope(str(request.command_id), request.expected_state_version, command)


def _serialize_command(envelope: CommandEnvelope) -> dict[str, object]:
    command = envelope.command
    payload = canonical_data(command)
    return {"command_id": envelope.command_id, "expected_state_version": envelope.expected_state_version, "kind": type(command).__name__, "payload": payload}


def _read_records(path: Path) -> list[SessionRecord]:
    import json
    return [SessionRecord(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line]


__all__ = [
    "InvalidLease", "InvalidTransition", "RuntimeHandle", "SimulationConflict", "SimulationError",
    "SimulationManager", "SimulationNotFound",
]
