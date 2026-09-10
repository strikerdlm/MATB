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
    CommandStatus,
    Hold, InspectContact, ReportContact, ResumeMission, ReturnToBase,
    SetContactPriority, SetWaypoint,
)
from matb_integration.suas.domain.enums import ContactClassification, ContactPriority, Locale
from matb_integration.suas.domain.geometry import PointMM
from matb_integration.suas.domain.serialization import canonical_data, canonical_json
from matb_integration.suas.engine.runtime import (
    CHECKPOINT_INTERVAL_MS, ENGINE_VERSION, SNAPSHOT_INTERVAL_MS, TICK_MS, SimulationEngine,
)
from matb_integration.suas.metrics.debrief import build_public_debrief, block_metric_summary
from matb_integration.suas.metrics.research import derive_research_metrics
from matb_integration.suas.recording.records import RecordKind, RecordingError, SessionRecord
from matb_integration.suas.recording.recorder import SessionRecorder
from matb_integration.suas.recording.checkpoints import load_checkpoint
from matb_integration.suas.recording.replay import ReplayVerifier, event_chain_hash, effective_records
from matb_integration.suas.scenarios.loader import load_scenario
from app.console_profile import current_console_profile

from matb_integration.suas.scenarios.manifest import build_session_manifest, build_technical_session_manifest
from matb_integration.suas.scenarios.profiles import block_order_for_participant
from matb_integration.suas.research.protocol import (
    ActiveProbe, ProtocolController, ProtocolError, ProtocolPhase,
)
from matb_integration.suas.research.scoring import ProbeAnswer

from .models import Participant, Visit
from .simulation_models import (
    SimulationBlock,
    SimulationSession,
    TechnicalSimulationBlock,
    TechnicalSimulationSession,
)
from .simulation_persistence import InMemorySimulationPersistence, SimulationPersistence
from .simulation_schemas import (
    CommandRequest, CreateSimulationSession, CreateTechnicalSimulationSession, FinishRequest,
    PreparedSession, RecoveryView, SessionView,
)
from .websocket.simulation import SimulationHub, StreamEnvelope, StreamKind
from .simulation_schemas import PresentationEvent
from matb_integration.suas.presentation.packages import read_package


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


class ProtocolGateActive(SimulationError):
    code = "probe_active"


class PostBlockGateActive(SimulationError):
    code = "post_block_active"


@dataclass(slots=True)
class _QueuedCommand:
    envelope: CommandEnvelope
    future: asyncio.Future[CommandResult]


@dataclass(slots=True)
class RuntimeHandle:
    session_id: str
    participant_id: str | None
    visit_id: int | None
    locale: str
    scenario: Any
    manifest: dict[str, object]
    recorder: SessionRecorder
    presentation_fallbacks: set[str] = field(default_factory=set, init=False)
    presentation_ready: set[str] = field(default_factory=set, init=False)
    presentation_ids: set[str] = field(default_factory=set, init=False)
    presentation_states: dict[str, dict] = field(default_factory=dict, init=False)
    presentation_sequence: int = field(default=-1, init=False)
    lease_hash: str
    lifecycle: str = "PREPARED"
    active_block_id: str | None = None
    engine: SimulationEngine | None = None
    sequence: int = 0
    block_events: list[object] = field(default_factory=list)
    queue: deque[_QueuedCommand] = field(default_factory=deque)
    tick_task: asyncio.Task[Any] | None = None
    traffic_task: asyncio.Task[Any] | None = None
    traffic_frame: dict | None = None
    traffic_discontinuity: bool = True
    traffic_recording: dict | None = None
    traffic_scene: dict | None = None
    snapshot_task: asyncio.Task[Any] | None = None
    finish_disposition: str | None = None
    transport_sequence: int = 0
    validity: str = "valid"
    protocol: ProtocolController | None = None
    probe_timeout_task: asyncio.Task[Any] | None = None
    block_closed: bool = False
    session_mode: str = "research"
    record_class: str = "research"
    selected_block_id: str | None = None


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
        self._pending_controller_streams: dict[tuple[str, str], int] = {}
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
            from app.experiment_catalog import require_study_pvt
            require_study_pvt(db, int(visit.id))
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
            # Bind the immutable manifest to the durable session identity before
            # it is written into the append-only run directory.
            manifest["session_id"] = session_id
            manifest["console_profile"] = current_console_profile()
            self._bind_presentation(manifest, request, loaded)
            lease = secrets.token_urlsafe(32)
            run_dir = self.artifact_root / session_id
            recorder = SessionRecorder(run_dir, manifest, loaded.normalized_yaml)
            if request.presentation and request.presentation.traffic.mode == "recorded":
                from .traffic_service import recording_path
                (run_dir / "traffic-source.json").write_bytes(recording_path(request.presentation.traffic.recording_id).read_bytes())
            handle = RuntimeHandle(
                session_id=session_id, participant_id=request.participant_id, visit_id=int(visit.id),
                locale=request.locale, scenario=loaded, manifest=manifest, recorder=recorder,
                lease_hash=self._hash_lease(lease),
                protocol=ProtocolController(
                    loaded.definition,
                    participant_id=request.participant_id,
                    locale=Locale(request.locale),
                    monotonic_clock=lambda: asyncio.get_running_loop().time(),
                ),
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
            db.flush()
            for index, block_id in enumerate(("PRACTICE", *(item.value for item in order)), start=0):
                db.add(SimulationBlock(
                    session_id=session_id, block_id=block_id, profile=block_id,
                    order_index=index, lifecycle="PREPARED",
                ))
            db.commit()
            self.persistence.update_session(session_id, lifecycle="PREPARED")
            return self._prepared_view(handle, lease)

    async def prepare_technical(
        self,
        request: CreateTechnicalSimulationSession,
        db: Session,
    ) -> PreparedSession:
        """Prepare one directly selected block outside the research protocol."""

        async with self._lock:
            if self._handle is not None and self._handle.lifecycle not in {"FINISHED", "ABORTED"}:
                raise SimulationConflict("an active session already exists")
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
            if request.block_id not in loaded.definition.blocks:
                raise SimulationNotFound("scenario block not found")
            session_id = self._new_session_id()
            manifest = build_technical_session_manifest(
                loaded,
                block_id=request.block_id,
                locale=request.locale,
                ui_version=self._ui_version,
                engine_version=ENGINE_VERSION,
            )
            manifest["session_id"] = session_id
            manifest["console_profile"] = current_console_profile()
            self._bind_presentation(manifest, request, loaded)
            lease = secrets.token_urlsafe(32)
            run_dir = self.artifact_root / "technical" / session_id
            recorder = SessionRecorder(run_dir, manifest, loaded.normalized_yaml)
            if request.presentation and request.presentation.traffic.mode == "recorded":
                from .traffic_service import recording_path
                (run_dir / "traffic-source.json").write_bytes(recording_path(request.presentation.traffic.recording_id).read_bytes())
            handle = RuntimeHandle(
                session_id=session_id,
                participant_id=None,
                visit_id=None,
                locale=request.locale,
                scenario=loaded,
                manifest=manifest,
                recorder=recorder,
                lease_hash=self._hash_lease(lease),
                validity="technical_only",
                session_mode="interactive_technical",
                record_class="technical_only",
                selected_block_id=request.block_id,
                protocol=ProtocolController(
                    loaded.definition,
                    participant_id=session_id,
                    locale=Locale(request.locale),
                    block_order=(request.block_id,),
                    initial_validity="technical_only",
                    monotonic_clock=lambda: asyncio.get_running_loop().time(),
                ),
            )
            self._handle = handle
            self._append(handle, RecordKind.LIFECYCLE, {
                "event": "session_prepared",
                "scenario_id": loaded.definition.scenario_id,
                "session_mode": "interactive_technical",
                "record_class": "technical_only",
                "execution_purpose": "practice",
                "selected_block_id": request.block_id,
            }, 0, 0)
            db.add(TechnicalSimulationSession(
                id=session_id,
                scenario_id=loaded.definition.scenario_id,
                scenario_sha256=loaded.sha256,
                selected_block_id=request.block_id,
                manifest_json=canonical_json(manifest),
                locale=request.locale,
                lifecycle="PREPARED",
                validity="technical_only",
                record_class="technical_only",
                artifact_root=str(run_dir),
            ))
            db.flush()
            db.add(TechnicalSimulationBlock(
                session_id=session_id,
                block_id=request.block_id,
                profile=request.block_id,
                order_index=0,
                lifecycle="PREPARED",
                validity="technical_only",
            ))
            db.commit()
            self.persistence.update_session(
                session_id,
                lifecycle="PREPARED",
                validity="technical_only",
            )
            return self._prepared_view(handle, lease)

    @staticmethod
    def _bind_presentation(manifest, request, loaded):
        config = request.presentation
        if config is None:
            return
        if config.scene_id:
            read_package(config.scene_id, config.scene_sha256)
            if loaded.definition.terrain.bounds != (0, 0, 12000000, 8000000):
                raise ValueError("scene package requires the 12 by 8 km reference footprint")
        if config.traffic.mode == "live" and not isinstance(request, CreateTechnicalSimulationSession):
            raise ValueError("research sessions require recorded traffic")
        if config.traffic.mode == "recorded":
            from .traffic_service import load_recording
            recording = load_recording(config.traffic.recording_id, config.traffic.recording_sha256)
            if recording["scene_id"] != config.scene_id or recording["scene_sha256"] != config.scene_sha256:
                raise ValueError("traffic recording belongs to a different scene")
            if recording["provider"] != config.traffic.provider:
                raise ValueError("traffic recording belongs to a different provider")
            blocks = [request.block_id] if isinstance(request, CreateTechnicalSimulationSession) else list(loaded.definition.blocks)
            if any(recording["duration_ms"] < loaded.definition.blocks[b].duration_ms for b in blocks):
                raise ValueError("traffic recording is shorter than the mission block")
        manifest["presentation"] = config.model_dump(mode="json")

    @staticmethod
    def _require_presentation_ready(handle, block_id):
        config = handle.manifest.get("presentation") or {}
        if handle.session_mode == "interactive_technical" and block_id in handle.presentation_fallbacks:
            return
        if config.get("blocks", {}).get(block_id) == "3d":
            read_package(config["scene_id"], config["scene_sha256"])
            if block_id not in handle.presentation_ready:
                raise InvalidTransition("presentation_not_ready")

    async def presentation_event(self, session_id: str, lease: str, event: PresentationEvent):
        async with self._lock:
            handle = self._require(session_id, lease)
            if handle.lifecycle not in {"PREPARED", "RUNNING", "PAUSED"}:
                raise InvalidTransition("presentation log is sealed")
            if event.block_id not in handle.scenario.definition.blocks:
                raise ValueError("unknown presentation block")
            event_id = str(event.event_id)
            if event_id in handle.presentation_ids:
                return
            if len(handle.presentation_ids) >= 20000 and (event.kind != "failure" or len(handle.presentation_ids) > 20000):
                await self._presentation_failed(handle, event.block_id)
                raise ValueError("presentation event limit reached")
            config = handle.manifest.get("presentation") or {}
            if config.get("version") == 2 and event.version != 2:
                raise ValueError("v2 sessions require v2 exposure records")
            if event.version == 2:
                self._validate_exposure(handle, config, event)
            if event.kind == "ready":
                if not config.get("scene_id") or event.scene_sha256 != config.get("scene_sha256"):
                    raise ValueError("presentation scene mismatch")
                read_package(config["scene_id"], config["scene_sha256"])
            if event.kind == "fallback" and handle.session_mode != "interactive_technical":
                raise InvalidTransition("research condition is locked")
            payload = event.model_dump(mode="json")
            payload["server_simulation_time_ms"] = self._time(handle)
            payload["server_state_version"] = self._version(handle)
            payload["wall_time_utc"] = self._wall_clock()
            try:
                with (handle.recorder.run_dir / "presentation.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
            except OSError:
                await self._presentation_failed(handle, event.block_id)
                raise
            handle.presentation_ids.add(event_id)
            if event.version == 2:
                handle.presentation_sequence = event.sequence
                handle.presentation_states[event.block_id] = event.resolved.model_dump(mode="json")
            if event.kind == "ready":
                handle.presentation_fallbacks.discard(event.block_id)
                handle.presentation_ready.add(event.block_id)
            elif event.kind == "fallback":
                handle.presentation_fallbacks.add(event.block_id)
            elif event.kind == "failure":
                await self._presentation_failed(handle, event.block_id)

    async def _presentation_failed(self, handle, block_id):
        handle.presentation_ready.discard(block_id)
        if handle.active_block_id:
            handle.presentation_ready.discard(handle.active_block_id)
        if handle.session_mode != "research":
            return
        was_running = handle.lifecycle == "RUNNING"
        if was_running:
            handle.lifecycle = "PAUSED"
        existing_validity = self._view(handle).validity
        handle.validity = "valid_with_deviation" if existing_validity == "valid" else existing_validity
        self.persistence.update_session(handle.session_id, validity=handle.validity, lifecycle=handle.lifecycle)
        # Stop the task before attempting further writes: a full disk must not leave it running.
        self._append(handle, RecordKind.PROTOCOL_DEVIATION, {"code": "presentation_failure"}, self._time(handle), self._version(handle))
        if was_running:
            self._append(handle, RecordKind.LIFECYCLE, {"event": "session_paused", "reason": "presentation_failure"}, self._time(handle), self._version(handle))
            await self._publish_latest_record(handle, kind=StreamKind.LIFECYCLE)

    def _validate_exposure(self, handle, config, event):
        state = event.resolved
        if config.get("version") != 2:
            raise ValueError("v2 exposure requires v2 configuration")
        if event.sequence <= handle.presentation_sequence:
            raise ValueError("presentation sequence must increase")
        if state.scene_sha256 != config.get("scene_sha256") or state.capture_sha256 != config.get("traffic", {}).get("recording_sha256"):
            raise ValueError("presentation asset mismatch")
        if event.kind == "failure":
            return  # A failure report must remain possible after capacity or validation failure.
        controls = config.get("controls", {})
        if event.kind in {"navigate", "navigation_filter"} and not controls.get("contact_cycling"):
            raise ValueError("contact navigation is not enabled")
        if not controls.get("smooth_camera") and state.transition_ms:
            raise ValueError("camera assistance is not enabled")
        if (state.interpolation_policy is not None and state.interpolation_policy != config.get("interpolation_policy", "linear-320-v1")) or (config.get("interpolation_policy") == "none-v1" and state.interpolation_ms != 0):
            raise ValueError("interpolation policy differs from the pinned condition")
        if handle.session_mode == "research" and state.condition != config.get("blocks", {}).get(event.block_id, "2d"):
            raise InvalidTransition("research condition is locked")
        if not controls.get("adjustable_layers"):
            if not all(state.operational_layers.model_dump().values()) or state.geographic_layers != config.get("layers", []):
                raise ValueError("display layers are locked")
        if not set(state.geographic_layers).issubset(config.get("layers", [])):
            raise ValueError("layer is outside the pinned condition")
        if state.camera == "drone" and state.focus and state.focus.category != "aircraft":
            raise ValueError("drone camera requires a simulated aircraft")
        if state.camera == "follow" and state.focus and state.focus.category == "contact":
            raise ValueError("task contacts support inspection only")
        previous = handle.presentation_states.get(event.block_id, {})
        snapshot = handle.engine.snapshot() if handle.engine else {}
        # Validate newly selected entities against public engine state. Existing selections
        # may outlive a snapshot while a delayed exposure record is in flight.
        for field, category in (("aircraft_id", "aircraft"), ("contact_id", "contacts"), ("observed_id", "observed")):
            identifier = getattr(state, field)
            if not identifier or identifier == previous.get(field):
                continue
            if category == "observed":
                eligible = {t["id"] for t in (handle.traffic_frame or {}).get("tracks", []) if t.get("age_s", 0) <= 60}
            else:
                entries = snapshot.get(category, {})
                eligible = {key for key, value in entries.items() if category == "aircraft" or (value.get("position") and value.get("evidence") != "NONE")}
            if identifier not in eligible:
                raise ValueError("entity is not in the permitted snapshot")
        if state.focus:
            field = {"aircraft": "aircraft_id", "contact": "contact_id", "observed": "observed_id"}[state.focus.category]
            if state.focus.id != getattr(state, field):
                raise ValueError("camera focus must reference its categorized selection")

    async def start(self, session_id: str, block_id: str, lease: str) -> SessionView:
        async with self._lock:
            handle = self._require(session_id, lease)
            if handle.lifecycle == "RUNNING" and handle.active_block_id == block_id:
                return self._view(handle)
            if handle.lifecycle not in {"PREPARED", "PAUSED"}:
                raise InvalidTransition(f"cannot start from {handle.lifecycle}")
            expected = (
                handle.protocol.next_block_id
                if handle.protocol is not None
                else ("PRACTICE", *handle.manifest["block_order"])[0]
            )
            if block_id != expected:
                raise InvalidTransition("block_order_violation")
            self._require_presentation_ready(handle, block_id)
            if handle.protocol is not None:
                try:
                    handle.protocol.start_block(block_id)
                except ProtocolError as error:
                    if error.code == "block_order_violation":
                        raise InvalidTransition(str(error)) from error
                    raise
            handle.engine = SimulationEngine(handle.scenario.definition, block_id)
            handle.active_block_id = block_id
            handle.block_events.clear()
            handle.block_closed = False
            handle.lifecycle = "RUNNING"
            self.persistence.update_session(session_id, lifecycle="RUNNING", active_block_id=block_id, started_at=_utcnow())
            self.persistence.update_block(session_id, block_id, lifecycle="RUNNING", simulation_started_ms=0, started_at=_utcnow())
            self._append(handle, RecordKind.LIFECYCLE, {"event": "block_started", "active_aircraft": len(handle.scenario.definition.blocks[block_id].aircraft_ids), "required_contacts": len(handle.scenario.definition.blocks[block_id].contact_ids), "required_actions": 0}, 0, 0)
            await self._publish_latest_record(handle, kind=StreamKind.LIFECYCLE)
            self._start_background_tasks(handle)
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
            self._require_presentation_ready(handle, handle.active_block_id)
            handle.lifecycle = "RUNNING"
            handle.traffic_discontinuity = True
            self.persistence.update_session(session_id, lifecycle="RUNNING")
            self._append(handle, RecordKind.LIFECYCLE, {"event": "session_resumed"}, self._time(handle), self._version(handle))
            await self._publish_latest_record(handle, kind=StreamKind.LIFECYCLE)
            self._start_background_tasks(handle)
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
            if value == "complete" and handle.active_block_id and handle.engine is not None and not handle.block_closed:
                self._append(handle, RecordKind.LIFECYCLE, {
                    "event": "block_finished",
                    "state_sha256": handle.engine.state_hash,
                    "event_sha256": event_chain_hash(handle.block_events),
                }, now, self._version(handle))
                handle.block_closed = True
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
                replay = ReplayVerifier().verify(handle.recorder.run_dir)
                if replay.status.value == "match":
                    records = _read_records(handle.recorder.run_dir / "events.jsonl")
                    debrief, questionnaires = build_public_debrief(
                        handle.recorder.run_dir,
                        handle.manifest,
                        replay,
                        records,
                        validity=handle.validity,
                        live_frames=(handle.engine.snapshot(),) if handle.engine is not None else (),
                    )
                    metrics = debrief.get("metrics", {})
                    metrics_mapping = metrics if isinstance(metrics, Mapping) else {}
                    artifacts = handle.recorder.seal(
                        questionnaires=questionnaires,
                        metrics=metrics_mapping,
                        debrief=debrief,
                        replay=replay,
                    )
                    self.persistence.replace_artifacts(handle.session_id, artifacts)
                    effective = tuple(effective_records(records))
                    for block_id in sorted({record.block_id for record in effective}):
                        block_records = tuple(record for record in effective if record.block_id == block_id)
                        block_metrics = {**block_metric_summary(block_records, handle.manifest),
                                         **derive_research_metrics(block_records).to_dict(),
                                         "calculation_version": "suas-debrief-v2"}
                        self.persistence.update_block(
                            handle.session_id,
                            block_id,
                            metrics_json=canonical_json(block_metrics),
                        )
            self.persistence.update_session(session_id, lifecycle=handle.lifecycle, finished_at=_utcnow(), active_block_id=handle.active_block_id)
            if handle.active_block_id:
                self.persistence.update_block(session_id, handle.active_block_id, lifecycle=handle.lifecycle, simulation_finished_ms=now, finished_at=_utcnow())
            return self._view(handle)

    async def submit(self, session_id: str, lease: str, request: CommandRequest) -> CommandResult:
        async with self._lock:
            handle = self._require(session_id, lease)
            if handle.protocol is not None and handle.protocol.phase in {
                ProtocolPhase.ISA_ACTIVE,
                ProtocolPhase.SAGAT_ACTIVE,
                ProtocolPhase.POST_BLOCK_ACTIVE,
            }:
                if request.kind in {"SUBMIT_ISA", "SUBMIT_SAGAT", "SUBMIT_POST_BLOCK_SCALE"}:
                    return await self._submit_protocol_locked(handle, request)
                code = (
                    "post_block_active"
                    if handle.protocol.phase is ProtocolPhase.POST_BLOCK_ACTIVE
                    else "probe_active"
                )
                return CommandResult(
                    command_id=str(request.command_id), status=CommandStatus.REJECTED,
                    code=code, applied_tick=None, state_version=self._version(handle),
                )
            if request.kind in {"SUBMIT_ISA", "SUBMIT_SAGAT", "SUBMIT_POST_BLOCK_SCALE"}:
                return CommandResult(
                    command_id=str(request.command_id), status=CommandStatus.REJECTED,
                    code="invalid_protocol_phase", applied_tick=None, state_version=self._version(handle),
                )
            if handle.lifecycle != "RUNNING" or handle.engine is None:
                raise InvalidTransition("commands require a running session")
            envelope = _command_envelope(request)
            future: asyncio.Future[CommandResult] = asyncio.get_running_loop().create_future()
            handle.queue.append(_QueuedCommand(envelope, future))
        return await future

    async def _submit_protocol_locked(self, handle: RuntimeHandle, request: CommandRequest) -> CommandResult:
        """Apply one server-scored instrument command while the engine is paused."""

        protocol = handle.protocol
        if protocol is None:
            return CommandResult(
                command_id=str(request.command_id), status=CommandStatus.REJECTED,
                code="invalid_protocol_phase", applied_tick=None, state_version=self._version(handle),
            )
        payload = dict(request.payload)
        try:
            if request.kind == "SUBMIT_ISA":
                if set(payload) != {"probe_id", "rating"}:
                    raise ValueError("invalid ISA payload")
                probe_id, rating = payload["probe_id"], payload["rating"]
                if not isinstance(probe_id, str) or isinstance(rating, bool) or not isinstance(rating, int):
                    raise ValueError("invalid ISA payload")
                score = protocol.submit_isa(probe_id, rating)
                self._append(handle, RecordKind.QUESTIONNAIRE, {
                    "instrument": "ISA", "probe_id": probe_id, "rating": score.value,
                }, self._time(handle), self._version(handle))
                code = "accepted"
            elif request.kind == "SUBMIT_SAGAT":
                if set(payload) != {"probe_id", "answer"}:
                    raise ValueError("invalid SAGAT payload")
                probe_id, answer = payload["probe_id"], payload["answer"]
                if not isinstance(probe_id, str) or not isinstance(answer, str):
                    raise ValueError("invalid SAGAT payload")
                result = protocol.submit_sagat(probe_id, answer)
                self._append(handle, RecordKind.QUESTIONNAIRE, {
                    "instrument": "SAGAT", "probe_id": result.probe_id,
                    "sa_level": result.sa_level, "answer": result.answer,
                    "correct_answer": result.correct_answer, "correct": result.correct,
                    "timed_out": result.timed_out, "latency_ms": result.latency_ms,
                    "unscorable_reason": result.unscorable_reason,
                }, self._time(handle), self._version(handle))
                code = "accepted"
            else:
                if set(payload) != {"scale_id", "answers"}:
                    raise ValueError("invalid post-block scale payload")
                scale_id, answers = payload["scale_id"], payload["answers"]
                if scale_id not in {"NASA_TLX", "BEDFORD"} or not isinstance(answers, Mapping):
                    raise ValueError("invalid post-block scale payload")
                if any(isinstance(value, bool) or not isinstance(value, int) for value in answers.values()):
                    raise ValueError("invalid post-block scale payload")
                score = protocol.submit_post_block(str(scale_id), answers)
                score_payload: dict[str, object] = {"instrument": str(scale_id), "scale_id": str(scale_id)}
                if hasattr(score, "raw_tlx"):
                    score_payload["raw_tlx"] = float(score.raw_tlx)  # type: ignore[attr-defined]
                elif hasattr(score, "value"):
                    score_payload["value"] = int(score.value)  # type: ignore[attr-defined]
                self._append(handle, RecordKind.QUESTIONNAIRE, score_payload, self._time(handle), self._version(handle))
                code = "accepted"
        except ProtocolError as error:
            return CommandResult(
                command_id=str(request.command_id), status=CommandStatus.REJECTED,
                code=error.code, applied_tick=None, state_version=self._version(handle),
            )
        except (TypeError, ValueError) as error:
            return CommandResult(
                command_id=str(request.command_id), status=CommandStatus.REJECTED,
                code="invalid_protocol_payload", applied_tick=None, state_version=self._version(handle),
            )

        handle.validity = protocol.validity

        if protocol.active_probe is not None:
            await self._publish_protocol_probe_locked(handle, protocol.active_probe)
        elif protocol.phase is ProtocolPhase.BLOCK_RUNNING:
            await self._resume_after_protocol_locked(handle)
        elif protocol.phase in {ProtocolPhase.READY_FOR_BLOCK, ProtocolPhase.COMPLETE}:
            # The next block is explicitly started by the controller; scales
            # close this block's gate but never auto-advance the protocol.
            handle.lifecycle = "PAUSED"
            self.persistence.update_session(handle.session_id, lifecycle="PAUSED", validity=protocol.validity)
            if not handle.block_closed and handle.active_block_id and handle.engine is not None:
                now = self._time(handle)
                self._append(handle, RecordKind.LIFECYCLE, {
                    "event": "block_finished",
                    "state_sha256": handle.engine.state_hash,
                    "event_sha256": event_chain_hash(handle.block_events),
                }, now, self._version(handle))
                handle.block_closed = True
                self.persistence.update_block(
                    handle.session_id,
                    handle.active_block_id,
                    lifecycle="FINISHED",
                    simulation_finished_ms=now,
                    finished_at=_utcnow(),
                    validity=protocol.validity,
                )
                await self._publish_latest_record(handle, kind=StreamKind.LIFECYCLE)
        return CommandResult(
            command_id=str(request.command_id), status=CommandStatus.ACCEPTED,
            code=code, applied_tick=self._tick(handle), state_version=self._version(handle),
        )

    async def _publish_protocol_probe_locked(self, handle: RuntimeHandle, probe: ActiveProbe) -> None:
        """Publish only redacted probe data; private scoring stays on disk."""
        self._append(
            handle,
            RecordKind.PROBE,
            dict(probe.public_payload),
            self._time(handle),
            self._version(handle),
        )
        await self._publish_latest_record(handle, kind=StreamKind.PROBE)

    def _schedule_probe_timeout_locked(self, handle: RuntimeHandle, probe: ActiveProbe) -> None:
        if not self._run_background_tasks or probe.timeout_ms <= 0:
            return
        if handle.probe_timeout_task is not None and not handle.probe_timeout_task.done():
            handle.probe_timeout_task.cancel()
        handle.probe_timeout_task = asyncio.create_task(
            self._protocol_timeout_loop(handle.session_id, probe.kind, probe.probe_id, probe.timeout_ms),
        )

    async def _protocol_timeout_loop(
        self, session_id: str, kind: str, probe_id: str | None, timeout_ms: int,
    ) -> None:
        await asyncio.sleep(max(0, timeout_ms) / 1_000)
        async with self._lock:
            handle = self._handle
            if (
                handle is None
                or handle.session_id != session_id
                or handle.protocol is None
                or handle.protocol.active_probe is None
                or handle.protocol.active_probe.kind != kind
                or handle.protocol.active_probe.probe_id != probe_id
            ):
                return
            handle.probe_timeout_task = None
            try:
                result = handle.protocol.timeout_active_probe()
            except ProtocolError:
                return
            handle.validity = handle.protocol.validity
            self.persistence.update_session(
                handle.session_id,
                lifecycle=handle.lifecycle,
                validity=handle.protocol.validity,
            )
            if handle.active_block_id:
                self.persistence.update_block(
                    handle.session_id,
                    handle.active_block_id,
                    lifecycle=handle.lifecycle,
                    validity=handle.protocol.validity,
                )
            self._append(handle, RecordKind.PROTOCOL_DEVIATION, {
                "code": "probe_timeout", "kind": kind, "probe_id": probe_id,
            }, self._time(handle), self._version(handle))
            if result is not None:
                self._append(handle, RecordKind.QUESTIONNAIRE, {
                    "instrument": "SAGAT", "probe_id": result.probe_id,
                    "sa_level": result.sa_level, "correct": result.correct,
                    "timed_out": True, "latency_ms": result.latency_ms,
                    "unscorable_reason": result.unscorable_reason,
                }, self._time(handle), self._version(handle))
            if handle.protocol.active_probe is not None:
                await self._publish_protocol_probe_locked(handle, handle.protocol.active_probe)
                self._schedule_probe_timeout_locked(handle, handle.protocol.active_probe)
            elif handle.protocol.phase is ProtocolPhase.BLOCK_RUNNING:
                await self._resume_after_protocol_locked(handle)

    async def _pause_for_protocol_locked(self, handle: RuntimeHandle, reason: str) -> None:
        handle.traffic_discontinuity = True
        if handle.lifecycle == "PAUSED":
            return
        handle.lifecycle = "PAUSED"
        self._cancel_tasks(handle)
        self.persistence.update_session(handle.session_id, lifecycle="PAUSED", validity=handle.protocol.validity if handle.protocol else handle.validity)
        self._append(handle, RecordKind.LIFECYCLE, {"event": "session_paused", "reason": reason}, self._time(handle), self._version(handle))
        if handle.active_block_id:
            self.persistence.update_block(handle.session_id, handle.active_block_id, lifecycle="PAUSED")

    async def _resume_after_protocol_locked(self, handle: RuntimeHandle) -> None:
        handle.lifecycle = "RUNNING"
        self.persistence.update_session(handle.session_id, lifecycle="RUNNING")
        self._append(handle, RecordKind.LIFECYCLE, {"event": "session_resumed", "reason": "protocol_gate_complete"}, self._time(handle), self._version(handle))
        if handle.active_block_id:
            self.persistence.update_block(handle.session_id, handle.active_block_id, lifecycle="RUNNING")
        if handle.engine is not None:
            await self._publish_snapshot(handle, handle.engine.snapshot())
        self._start_background_tasks(handle)

    @staticmethod
    def _tick(handle: RuntimeHandle) -> int | None:
        return int(handle.engine.snapshot()["tick"]) if handle.engine else None

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
                await self._process_protocol_tick_locked(handle)
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
            if handle.protocol is None or not handle.protocol.conceal_operational_state:
                await self._publish_snapshot(handle, snapshot)
            return snapshot

    async def state(self, session_id: str) -> dict[str, object]:
        async with self._lock:
            handle = self._require(session_id, None, check_lease=False)
            if handle.engine is None:
                return {"session_id": session_id, "lifecycle": handle.lifecycle, "simulation_time_ms": 0, "state_version": 0}
            if handle.protocol is not None and handle.protocol.conceal_operational_state:
                return {
                    "session_id": session_id,
                    "lifecycle": handle.lifecycle,
                    "simulation_time_ms": self._time(handle),
                    "state_version": self._version(handle),
                    **handle.protocol.status(),
                }
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
            recovery_validity = self._deviated_validity(handle)
            handle.validity = recovery_validity
            self.persistence.update_session(
                session_id, lifecycle="PAUSED", validity=recovery_validity, active_block_id=handle.active_block_id,
            )
            if handle.active_block_id:
                self.persistence.update_block(
                    session_id,
                    handle.active_block_id,
                    lifecycle="PAUSED",
                    validity=recovery_validity,
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
        technical = isinstance(row, TechnicalSimulationSession)
        session_mode = "interactive_technical" if technical else "research"
        record_class = "technical_only" if technical else "research"
        selected_block_id = row.selected_block_id if technical else None
        configured_root = (
            (self.artifact_root / "technical").resolve()
            if technical
            else self.artifact_root.resolve()
        )
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
        recovered_validity = "technical_only_with_deviation" if technical else "valid_with_deviation"
        participant_id = getattr(row, "participant_id", None)
        visit_id = getattr(row, "visit_id", None)
        handle = RuntimeHandle(
            session_id=session_id,
            participant_id=participant_id,
            visit_id=int(visit_id) if visit_id is not None else None,
            locale=row.locale,
            scenario=loaded,
            manifest=manifest,
            recorder=recorder,
            lease_hash=self._hash_lease(lease),
            lifecycle="INTERRUPTED",
            active_block_id=block_id,
            engine=engine,
            validity=recovered_validity,
            session_mode=session_mode,
            record_class=record_class,
            selected_block_id=selected_block_id,
            protocol=ProtocolController(
                loaded.definition,
                participant_id=participant_id or session_id,
                locale=Locale(row.locale),
                block_order=(selected_block_id,) if technical and selected_block_id else None,
                initial_validity=recovered_validity,
                monotonic_clock=lambda: asyncio.get_running_loop().time(),
            ),
        )
        presentation_path = recorder.run_dir / "presentation.jsonl"
        if presentation_path.exists():
            for line in presentation_path.read_text(encoding="utf-8").splitlines():
                exposure = json.loads(line)
                handle.presentation_ids.add(str(exposure["event_id"]))
                if exposure.get("version") == 2:
                    handle.presentation_sequence = max(handle.presentation_sequence, exposure["sequence"])
                    handle.presentation_states[exposure["block_id"]] = exposure["resolved"]
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
        self.persistence.update_session(session_id, lifecycle="PAUSED", validity=recovered_validity, active_block_id=block_id)
        self.persistence.update_block(
            session_id,
            block_id,
            lifecycle="PAUSED",
            validity=recovered_validity,
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
            handle = self._require(session_id, lease)
            key = (session_id, handle.lease_hash)
            self._pending_controller_streams[key] = self._pending_controller_streams.get(key, 0) + 1

    async def controller_stream_established(self, session_id: str, lease: str) -> None:
        """Mark a validated controller stream as subscribed to the hub."""

        async with self._lock:
            handle = self._require(session_id, lease)
            key = (session_id, handle.lease_hash)
            pending = self._pending_controller_streams.get(key, 0)
            if pending <= 1:
                self._pending_controller_streams.pop(key, None)
            else:
                self._pending_controller_streams[key] = pending - 1

    async def controller_stream_failed(self, session_id: str, lease: str) -> None:
        """Release a failed handshake and fail closed if no stream remains."""

        async with self._lock:
            handle = self._require(session_id, lease)
            key = (session_id, handle.lease_hash)
            pending = self._pending_controller_streams.get(key, 0)
            if pending <= 1:
                self._pending_controller_streams.pop(key, None)
            else:
                self._pending_controller_streams[key] = pending - 1
            if pending > 1 or handle.lifecycle != "RUNNING":
                return
            subscribers = await self.hub.subscribers(session_id)
            if any(item.role == "controller" and not item.closed for item in subscribers):
                return
            paused = self._pause_controller_locked(handle)
            if paused:
                await self._publish_latest_record(handle, kind=StreamKind.LIFECYCLE)

    async def controller_disconnected(self, session_id: str, lease: str) -> None:
        """Pause immediately on a valid controller disconnect; never resume."""

        async with self._lock:
            handle = self._require(session_id, lease)
            key = (session_id, handle.lease_hash)
            if self._pending_controller_streams.get(key, 0) > 0:
                return
            # React StrictMode and a browser reconnect can close an older
            # socket after its replacement has already subscribed.  The hub
            # removes the old subscription before this callback, so a live
            # controller subscriber is authoritative evidence that this
            # disconnect is stale.  Do not pause a healthy replacement stream.
            subscribers = await self.hub.subscribers(session_id)
            if any(item.role == "controller" and not item.closed for item in subscribers):
                return
            paused = self._pause_controller_locked(handle)
            if paused:
                await self._publish_latest_record(handle, kind=StreamKind.LIFECYCLE)

    def _pause_controller_locked(self, handle: RuntimeHandle) -> bool:
        """Persist the controller disconnect transition while manager lock is held."""

        if handle.lifecycle != "RUNNING":
            return False
        # A disconnected controller must not leave a high-rate snapshot loop
        # running against observers while the session is paused.  Resume will
        # recreate both publishers once a valid controller returns.
        self._cancel_tasks(handle)
        handle.lifecycle = "PAUSED"
        self.persistence.update_session(handle.session_id, lifecycle="PAUSED")
        self._append(handle, RecordKind.LIFECYCLE, {
            "event": "controller_disconnected", "reason": "controller_disconnect",
        }, self._time(handle), self._version(handle))
        return True

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
                {
                    **snapshot,
                    "lifecycle": handle.lifecycle,
                    "resynchronizes_after_sequence": max(0, int(after_sequence)),
                },
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

    async def traffic_once(self):
        from .traffic_service import traffic_service
        from matb_integration.suas.presentation.geography import projected_track
        async with self._lock:
            handle = self._handle
            if not handle or handle.lifecycle != "RUNNING" or not handle.engine:
                return
            if handle.protocol and handle.protocol.conceal_operational_state:
                handle.traffic_discontinuity = True
                return
            config = handle.manifest.get("presentation") or {}
            traffic = config.get("traffic") or {}
            if traffic.get("mode", "off") == "off": return
            if handle.traffic_scene is None:
                handle.traffic_scene = read_package(config["scene_id"], config["scene_sha256"])
            scene = handle.traffic_scene
            block_id = handle.active_block_id
            sampled_time = self._time(handle)
            if traffic["mode"] == "recorded":
                if handle.traffic_recording is None:
                    raw=(handle.recorder.run_dir / "traffic-source.json").read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=traffic["recording_sha256"]: raise ValueError("traffic source checksum mismatch")
                    handle.traffic_recording = json.loads(raw)
                available = [f for f in handle.traffic_recording["frames"] if f["simulation_time_ms"] <= sampled_time]
                frame = dict(available[-1]) if available else {"tracks": [], "status": "unavailable", "provider": traffic["provider"], "sampled_at": 0}
                frame["source_simulation_time_ms"] = frame.get("simulation_time_ms", 0)
                age_delta = max(0, sampled_time - frame["source_simulation_time_ms"]) / 1000
                frame["tracks"] = [{**track, "age_s": track["age_s"] + age_delta, "stale": track["age_s"] + age_delta > 15} for track in frame["tracks"] if track["age_s"] + age_delta <= 60]
                frame["sampled_at"] = frame.get("sampled_at", 0) + age_delta
            else: frame = None
        # Network I/O never holds the simulation lock or delays engine ticks.
        if frame is None:
            frame = await traffic_service.snapshot(scene["origin"]["lat"], scene["origin"]["lon"], 50, traffic["provider"])
        async with self._lock:
            if self._handle is not handle or handle.lifecycle != "RUNNING" or handle.active_block_id != block_id or (handle.protocol and handle.protocol.conceal_operational_state): return
            frame = {**frame, "block_id": block_id, "simulation_time_ms": self._time(handle), "state_version": self._version(handle), "mode": traffic["mode"], "origin": scene["origin"], "discontinuity": handle.traffic_discontinuity,
                     "frame_id": f"{block_id}-{handle.transport_sequence+1}", "tracks": [dict(t) if traffic["mode"] == "recorded" and "position" in t and "orthometric_altitude_m" in t else projected_track(t, scene["origin"]) for t in frame["tracks"]]}
            handle.traffic_discontinuity = False
            with (handle.recorder.run_dir / "traffic.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(frame, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
            handle.traffic_frame = frame
            await self.hub.publish(handle.session_id, self._new_envelope(handle, StreamKind.TRAFFIC, frame, self._time(handle), self._version(handle)))

    async def _traffic_loop(self):
        while not self._shutdown:
            handle=self._handle
            if not handle or handle.lifecycle != "RUNNING": return
            try:
                await self.traffic_once()
            except (OSError, ValueError, KeyError) as error:
                async with self._lock:
                    if self._handle is handle and handle.lifecycle == "RUNNING":
                        await self._interrupt(handle, "traffic_recording_failure", {"reason": type(error).__name__})
                return
            await self._sleep(self._wall_time_scale)

    async def _snapshot_loop(self) -> None:
        while True:
            async with self._lock:
                handle = self._handle
                if handle is None or handle.lifecycle != "RUNNING" or self._shutdown:
                    return
            await self.snapshot_once()
            await self._sleep((SNAPSHOT_INTERVAL_MS / 1000) * self._wall_time_scale)

    def _append(self, handle: RuntimeHandle, kind: RecordKind, payload: Mapping[str, object], time_ms: int, state_version: int) -> SessionRecord:
        handle.sequence += 1
        record = SessionRecord(
            session_id=handle.session_id,
            block_id=handle.active_block_id or handle.selected_block_id or "PRACTICE",
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

    async def _process_protocol_tick_locked(self, handle: RuntimeHandle) -> None:
        """Run protocol scheduling after one authoritative engine step."""

        protocol = handle.protocol
        if protocol is None or handle.engine is None or protocol.phase is not ProtocolPhase.BLOCK_RUNNING:
            return
        active = protocol.on_tick(handle.engine._state, simulation_time_ms=self._time(handle))  # noqa: SLF001
        if active is None:
            return
        reason = {
            "ISA": "isa_probe",
            "SAGAT": "sagat_freeze",
            "POST_BLOCK": "post_block_active",
        }[active.kind]
        await self._pause_for_protocol_locked(handle, reason)
        if active.kind == "SAGAT" and active.private_probe is not None:
            private = active.private_probe
            self._append(handle, RecordKind.QUESTIONNAIRE, {
                "instrument": "SAGAT",
                "event": "probe_started",
                "probe_id": private.probe_id,
                "sa_level": private.sa_level,
                "domain": private.domain,
                "question": private.question,
                "options": list(private.options),
                "correct_answer": private.correct_answer,
                "timeout_ms": private.timeout_ms,
                "unscorable_reason": private.unscorable_reason,
                "state_sha256": handle.engine.state_hash,
                "freeze_time_ms": self._time(handle),
            }, self._time(handle), self._version(handle))
        await self._publish_protocol_probe_locked(handle, active)
        self._schedule_probe_timeout_locked(handle, active)

    async def _publish_snapshot(self, handle: RuntimeHandle, snapshot: Mapping[str, object]) -> None:
        await self.hub.publish(handle.session_id, self._new_envelope(
            handle, StreamKind.SNAPSHOT,
            {
                **canonical_data(snapshot),
                "lifecycle": handle.lifecycle,
                "authoritative_event_sequence": snapshot.get("event_sequence", 0),
            },
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

    def _start_background_tasks(self, handle: RuntimeHandle) -> None:
        """Start the live engine publishers after a block start or resume."""

        if not self._run_background_tasks:
            return
        if handle.tick_task is None or handle.tick_task.done():
            handle.tick_task = asyncio.create_task(self._tick_loop())
        if (handle.manifest.get("presentation", {}).get("traffic", {}).get("mode", "off") != "off") and (handle.traffic_task is None or handle.traffic_task.done()):
            handle.traffic_task = asyncio.create_task(self._traffic_loop())
        if handle.snapshot_task is None or handle.snapshot_task.done():
            handle.snapshot_task = asyncio.create_task(self._snapshot_loop())

    @staticmethod
    def _cancel_tasks(handle: RuntimeHandle) -> None:
        for task in (handle.tick_task, handle.snapshot_task, handle.probe_timeout_task, handle.traffic_task):
            if task is not None and not task.done() and task is not asyncio.current_task():
                task.cancel()
        handle.traffic_task = None
        handle.tick_task = None
        handle.snapshot_task = None
        handle.probe_timeout_task = None

    @staticmethod
    def _time(handle: RuntimeHandle) -> int:
        return int(handle.engine.snapshot()["simulation_time_ms"]) if handle.engine else 0

    @staticmethod
    def _version(handle: RuntimeHandle) -> int:
        return int(handle.engine.snapshot()["state_version"]) if handle.engine else 0

    def _view(self, handle: RuntimeHandle) -> SessionView:
        protocol = handle.protocol.status() if handle.protocol is not None else {
            "protocol_phase": "READY_FOR_BLOCK",
            "current_block_index": 0,
            "active_probe": None,
            "next_block_id": handle.active_block_id,
        }
        protocol_validity = str(protocol.get("validity", "valid"))
        effective_validity = handle.validity if handle.validity != "valid" else protocol_validity
        protocol_order = (
            [handle.selected_block_id] if handle.session_mode == "interactive_technical" and handle.selected_block_id
            else list(handle.manifest.get("block_order", []))
        )
        return SessionView(
            id=handle.session_id, participant_id=handle.participant_id, visit_id=handle.visit_id,
            presentation=handle.manifest.get("presentation"),
            console_profile=handle.manifest.get("console_profile"),
            scenario_id=handle.scenario.definition.scenario_id, scenario_sha256=handle.scenario.sha256,
            locale=handle.locale, lifecycle=handle.lifecycle, active_block_id=handle.active_block_id,
            block_order=list(protocol_order), state_version=self._version(handle),
            simulation_time_ms=self._time(handle), validity=effective_validity,
            execution_purpose="practice" if handle.record_class == "technical_only" else "study",
            session_mode=handle.session_mode,
            record_class=handle.record_class,
            selected_block_id=handle.selected_block_id,
            protocol_phase=str(protocol["protocol_phase"]),
            current_block_index=int(protocol["current_block_index"]),
            active_probe=protocol["active_probe"],
            next_block_id=protocol["next_block_id"],
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
        interrupted_validity = (
            "technical_only_with_deviation"
            if handle.record_class == "technical_only"
            else "invalid"
        )
        handle.validity = interrupted_validity
        self._cancel_tasks(handle)
        now = self._time(handle)
        self.persistence.update_session(
            handle.session_id,
            lifecycle="INTERRUPTED",
            interrupted_at=_utcnow(),
            validity=interrupted_validity,
        )
        if handle.active_block_id:
            self.persistence.update_block(
                handle.session_id,
                handle.active_block_id,
                lifecycle="INTERRUPTED",
                validity=interrupted_validity,
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

    @staticmethod
    def _deviated_validity(handle: RuntimeHandle) -> str:
        return (
            "technical_only_with_deviation"
            if handle.record_class == "technical_only"
            else "valid_with_deviation"
        )


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
