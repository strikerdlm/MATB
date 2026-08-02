"""Single-session, controller-leased native sUAS runtime."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import secrets
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
    ) -> None:
        self.scenario_root = Path(scenario_root)
        self.artifact_root = Path(artifact_root)
        self.persistence = persistence or InMemorySimulationPersistence()
        self._sleep = tick_sleep
        self._wall_clock = wall_clock
        self._run_background_tasks = run_background_tasks
        self._ui_version = ui_version
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
            scenario_path = self.scenario_root / f"{request.scenario_id}.yaml"
            if not scenario_path.is_file() or scenario_path.parent.resolve() != self.scenario_root.resolve():
                raise SimulationNotFound("scenario not found")
            loaded = load_scenario(scenario_path)
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
            except RecordingError:
                handle.lifecycle = "INTERRUPTED"
                self.persistence.update_session(handle.session_id, lifecycle="INTERRUPTED", interrupted_at=_utcnow(), validity="invalid")
                self.persistence.add_deviation(handle.session_id, handle.active_block_id, "recording_failure", "fatal", self._time(handle), {"reason": "recording_failure"})
                for item in queued:
                    if not item.future.done():
                        item.future.set_exception(RecordingError("recording failure"))
            except Exception as error:
                for item in queued:
                    if not item.future.done():
                        item.future.set_exception(error)
                raise

    async def snapshot_once(self) -> dict[str, object]:
        async with self._lock:
            handle = self._handle
            if handle is None or handle.engine is None:
                raise SimulationNotFound("no active simulation")
            return dict(handle.engine.snapshot())

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
                self._cancel_tasks(self._handle)

    async def _tick_loop(self) -> None:
        while True:
            async with self._lock:
                handle = self._handle
                if handle is None or handle.lifecycle != "RUNNING" or self._shutdown:
                    return
            started = asyncio.get_running_loop().time()
            await self.tick_once()
            await self._sleep(max(0.0, (TICK_MS / 1000) - (asyncio.get_running_loop().time() - started)))

    async def _snapshot_loop(self) -> None:
        while True:
            async with self._lock:
                handle = self._handle
                if handle is None or handle.lifecycle not in {"RUNNING", "PAUSED"} or self._shutdown:
                    return
            await self.snapshot_once()
            await self._sleep(SNAPSHOT_INTERVAL_MS / 1000)

    def _append(self, handle: RuntimeHandle, kind: RecordKind, payload: Mapping[str, object], time_ms: int, state_version: int) -> None:
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
            simulation_time_ms=self._time(handle),
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
