"""Single-slot Polar H10 capture manager with bounded loss-visible queues."""

from __future__ import annotations

from app.purpose_service import declare_acquisition

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
from app.artifact_paths import resolve_artifact
from pathlib import Path
import secrets
import time
from typing import Any
from uuid import uuid4
import zipfile

from sqlmodel import Session, select

from app.models import Participant
from app.physiology_models import PolarCaptureMarkerRecord, PolarCaptureRecord
from matb_integration.physiology.analysis import HRV_ALGORITHM_VERSIONS, analyze_rr_window, workload_response
from matb_integration.physiology.artifacts import ParquetCaptureWriter
from matb_integration.physiology.rr_export import RRExportError, export_rr_capture
from matb_integration.physiology.contracts import (
    PolarArtifactManifestV1,
    PolarCaptureEventV1,
    PolarCaptureV1,
    PolarDeviceCapabilitiesV1,
)
from matb_integration.physiology.transport import (
    AccPacket,
    DeviceCandidate,
    EcgPacket,
    HrPacket,
    PolarTransport,
    TransportCapabilities,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PolarRuntimeError(RuntimeError):
    def __init__(self, code: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.context = context or {}


@dataclass(slots=True)
class _CaptureContext:
    capture_id: str
    writer: ParquetCaptureWriter
    settings: dict[str, int]
    queues: dict[str, asyncio.Queue[Any]]
    tasks: list[asyncio.Task[None]] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=lambda: {
        "hr_notifications": 0, "rr_intervals": 0, "ecg_packets": 0,
        "ecg_samples": 0, "acc_packets": 0, "acc_samples": 0,
        "queue_overflow_packets": 0,
    })
    incomplete_reasons: set[str] = field(default_factory=set)
    gap_count: int = 0
    connection_epoch: int = 0
    notification_index: int = 0
    beat_index: int = 0
    ecg_packet_index: int = 0
    ecg_sample_index: int = 0
    acc_packet_index: int = 0
    acc_sample_index: int = 0
    clock_offsets_ns: dict[str, int] = field(default_factory=dict)
    last_sensor_timestamp_ns: dict[str, int] = field(default_factory=dict)
    pending_gap: bool = True
    live_rr: deque[tuple[float, bool]] = field(default_factory=lambda: deque(maxlen=1024))


class PolarCaptureManager:
    """Own one connected H10 and one active capture slot."""

    DEVICE_TOKEN_TTL_SECONDS = 60
    QUEUE_PACKETS = 512

    def __init__(self, *, engine: Any, artifact_root: Path, transport: PolarTransport) -> None:
        self.engine = engine
        self.artifact_root = artifact_root.expanduser().resolve()
        self.transport = transport
        self._lock = asyncio.Lock()
        self._device_tokens: dict[str, tuple[float, DeviceCandidate]] = {}
        self._device: DeviceCandidate | None = None
        self._capabilities: PolarDeviceCapabilitiesV1 | None = None
        self._capture: _CaptureContext | None = None
        self._events: dict[str, list[PolarCaptureEventV1]] = {}
        self._conditions: dict[str, asyncio.Condition] = {}
        self._sequence: dict[str, int] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._intentional_disconnect = False
        self._connection_lost = False

    async def startup(self) -> None:
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        with Session(self.engine) as db:
            interrupted = db.exec(select(PolarCaptureRecord).where(
                PolarCaptureRecord.lifecycle.in_(("starting", "capturing", "stopping"))
            )).all()
            for row in interrupted:
                reasons = set(json.loads(row.incomplete_reasons_json))
                reasons.add("backend_restart_during_capture")
                row.lifecycle = "failed"
                row.artifact_state = "incomplete"
                row.incomplete_reasons_json = json.dumps(sorted(reasons))
                row.ended_at = _utcnow()
                from app.study_admission import sync_runtime_attempt
                sync_runtime_attempt(db, row, state='interrupted')
                db.add(row)
            db.commit()

    async def shutdown(self) -> None:
        if self._capture is not None:
            await self._stop_active("backend_shutdown")
        await self.disconnect(force=True)

    async def scan(self, timeout_s: float) -> list[tuple[str, DeviceCandidate]]:
        async with self._lock:
            if self._capture is not None:
                raise PolarRuntimeError("capture_active")
            if self._device is not None and self._connection_lost:
                # Release a dead client before looking for the next strap.
                await self.transport.disconnect()
                self._device = None
                self._capabilities = None
            if self._device is not None:
                raise PolarRuntimeError("scan_unavailable_while_connected")
            try:
                candidates = await self.transport.scan(timeout_s)
            except Exception as exc:
                code = (
                    "bluetooth_unavailable"
                    if type(exc).__name__ == "BleakBluetoothNotAvailableError"
                    else "polar_scan_failed"
                )
                raise PolarRuntimeError(code, context={"error_type": type(exc).__name__}) from exc
            now = time.monotonic()
            self._device_tokens.clear()
            result: list[tuple[str, DeviceCandidate]] = []
            for candidate in candidates:
                token = secrets.token_urlsafe(32)
                self._device_tokens[token] = (now + self.DEVICE_TOKEN_TTL_SECONDS, candidate)
                result.append((token, candidate))
            return result

    async def connect(self, token: str) -> PolarDeviceCapabilitiesV1:
        async with self._lock:
            if self._capture is not None:
                raise PolarRuntimeError("capture_active")
            if self._device is not None:
                raise PolarRuntimeError("polar_device_already_connected")
            entry = self._device_tokens.pop(token, None)
            if entry is None or entry[0] < time.monotonic():
                raise PolarRuntimeError("invalid_or_expired_device_token")
            candidate = entry[1]
            if candidate.connectable is False:
                raise PolarRuntimeError("device_not_connectable")
            self._connection_lost = False
            try:
                async with asyncio.timeout(30):
                    await self.transport.connect(candidate, self._on_disconnect)
                    raw = await self.transport.capabilities()
                if self._connection_lost:
                    raise ConnectionError("disconnected_during_connection")
            except Exception as exc:
                await self.transport.disconnect()
                raise PolarRuntimeError(
                    "polar_connection_timeout" if isinstance(exc, TimeoutError) else "polar_connection_failed",
                    context={"error_type": type(exc).__name__}
                ) from exc
            self._device = candidate
            self._capabilities = self._capability_contract(candidate, raw)
            self._device_tokens.clear()
            return self._capabilities

    @staticmethod
    def _capability_contract(
        device: DeviceCandidate, capabilities: TransportCapabilities
    ) -> PolarDeviceCapabilitiesV1:
        streams: list[str] = []
        if capabilities.hr_rr:
            streams.append("hr_rr")
        if capabilities.ecg_rates_hz:
            streams.append("ecg")
        if capabilities.acc_rates_hz:
            streams.append("acc")
        return PolarDeviceCapabilitiesV1(
            device_alias=device.alias,
            firmware=capabilities.firmware,
            battery_percent=capabilities.battery_percent,
            streams=tuple(streams),
            ecg_sample_rates_hz=capabilities.ecg_rates_hz,
            ecg_resolutions_bits=capabilities.ecg_resolutions_bits,
            acc_sample_rates_hz=capabilities.acc_rates_hz,
            acc_resolutions_bits=capabilities.acc_resolutions_bits,
            acc_ranges_g=capabilities.acc_ranges_g,
            internal_recording_qualified=False,
        )

    def connection(self) -> tuple[str | None, PolarDeviceCapabilitiesV1 | None]:
        if self._connection_lost:
            return None, None
        return (self._device.alias if self._device else None, self._capabilities)

    async def disconnect(self, *, force: bool = False) -> None:
        async with self._lock:
            if self._capture is not None and not force:
                raise PolarRuntimeError("capture_active")
            self._intentional_disconnect = True
            try:
                await self.transport.disconnect()
            finally:
                self._intentional_disconnect = False
                self._device = None
                self._capabilities = None
                self._connection_lost = False

    def create_capture(
        self,
        *,
        participant_id: str,
        session_kind: str,
        session_id: str | None,
        settings: dict[str, int],
        execution_purpose: str = "study",
        attempt_id: str | None = None,
    ) -> tuple[PolarCaptureV1, str]:
        if self._device is None or self._capabilities is None or self._connection_lost:
            raise PolarRuntimeError("polar_device_not_connected")
        if self._capture is not None:
            raise PolarRuntimeError("polar_capture_already_active")
        capture_id = str(uuid4())
        lease = secrets.token_urlsafe(32)
        with Session(self.engine) as db:
            if db.get(Participant, participant_id) is None:
                raise PolarRuntimeError("participant_not_found")
            if execution_purpose not in {"practice", "study"}:
                raise PolarRuntimeError("invalid_execution_purpose")
            from app.study_admission import resolve_assignment
            context = resolve_assignment(db, attempt_id=attempt_id, instrument='physiology', participant_id=participant_id,
                purpose=execution_purpose, require_started=False,
                config=dict(binding_id='polar-h10-pmd-v1', input_mapping='rr-ecg-acc', settings=settings, scoring='raw-streams'))
            if context:
                if session_kind == "generic" and session_id is None:
                    session_id = context["occasion_id"]
                self._validate_settings(settings)
                if context['accompanying_key']:
                    from app.assessment_adapters import source_attempt
                    from app.study_registry_models import StudyAssignment
                    assigned = db.get(StudyAssignment, context['assignment_id'])
                    table = {'openmatb': 'openmatb_suite_session', 'liftoff': 'liftoff_session', 'suas': 'simulation_session'}.get(session_kind)
                    if not table: raise PolarRuntimeError('polar_assigned_accompaniment_required')
                    linked_attempt = source_attempt(db, table, session_id)
                    resolve_assignment(db, attempt_id=linked_attempt.id, instrument=session_kind, participant_id=participant_id, visit_id=context['visit_id'], purpose='study', require_started=False)
                    if linked_attempt.occasion_id != json.loads(assigned.occasions_json)[context['accompanying_key']]:
                        raise PolarRuntimeError('polar_assigned_accompaniment_mismatch')
                elif session_kind != 'generic' or session_id != context['occasion_id']:
                    raise PolarRuntimeError('polar_assigned_baseline_context_required')
            if session_kind == "generic" and session_id is None:
                session_id = capture_id
            if session_kind != "generic":
                if not session_id:
                    raise PolarRuntimeError("polar_associated_session_required")
                from sqlalchemy import text
                # Fixed allowlist, never interpolate a caller-controlled table name.
                table = {"openmatb": "openmatb_suite_session", "liftoff": "liftoff_session", "suas": "simulation_session"}.get(session_kind)
                if table is None:
                    raise PolarRuntimeError("invalid_session_kind")
                purpose_column = "'study'" if session_kind == "suas" else "execution_purpose"
                linked = db.connection().execute(text(f"SELECT participant_id, {purpose_column} FROM {table} WHERE id = :id"), {"id": session_id}).first()
                if linked is None or linked[0] != participant_id or linked[1] != execution_purpose:
                    raise PolarRuntimeError("polar_session_identity_or_purpose_mismatch")
            row = PolarCaptureRecord(
                id=capture_id,
                participant_id=participant_id,
                matb_session_kind=session_kind,
                matb_session_id=session_id,
                device_alias=self._device.alias,
                lifecycle="created",
                execution_purpose=execution_purpose,
                requested_settings_json=json.dumps(settings, sort_keys=True),
                controller_lease_hash=_token_hash(lease),
            )
            declare_acquisition(db, row, purpose=execution_purpose, attempt_id=attempt_id)
            db.commit()
            db.refresh(row)
            return self._view(row), lease

    def _require_lease(self, row: PolarCaptureRecord, lease: str) -> None:
        if not lease or not hmac.compare_digest(row.controller_lease_hash, _token_hash(lease)):
            raise PolarRuntimeError("polar_invalid_controller_lease")

    def _row(self, capture_id: str, *, lease: str | None = None) -> PolarCaptureRecord:
        with Session(self.engine) as db:
            row = db.get(PolarCaptureRecord, capture_id)
            if row is None:
                raise PolarRuntimeError("polar_capture_not_found")
            if lease is not None:
                self._require_lease(row, lease)
            db.expunge(row)
            return row

    def active_capture(self) -> PolarCaptureV1 | None:
        return self.capture_view(self._capture.capture_id) if self._capture else None

    def capture_view(self, capture_id: str) -> PolarCaptureV1:
        return self._view(self._row(capture_id))

    def validate_lease(self, capture_id: str, lease: str) -> None:
        self._row(capture_id, lease=lease)

    @staticmethod
    def _view(row: PolarCaptureRecord) -> PolarCaptureV1:
        return PolarCaptureV1(
            purpose_provenance_id=row.purpose_provenance_id,
            execution_purpose=row.execution_purpose,
            capture_id=row.id,
            participant_pseudonym=row.participant_id,
            matb_session_kind=row.matb_session_kind,
            matb_session_id=row.matb_session_id,
            device_alias=row.device_alias,
            lifecycle=row.lifecycle,
            requested_settings=json.loads(row.requested_settings_json),
            resolved_settings=json.loads(row.resolved_settings_json) if row.resolved_settings_json else None,
            stream_counters=json.loads(row.stream_counters_json),
            gap_count=row.gap_count,
            connection_epoch=row.connection_epoch,
            artifact_state=row.artifact_state,
            incomplete_reasons=tuple(json.loads(row.incomplete_reasons_json)),
            started_at_utc=row.started_at,
            ended_at_utc=row.ended_at,
        )

    def _validate_settings(self, requested: dict[str, int]) -> None:
        caps = self._capabilities
        if caps is None:
            raise PolarRuntimeError("polar_device_not_connected")
        missing = [stream for stream in ("hr_rr", "ecg", "acc") if stream not in caps.streams]
        if missing:
            raise PolarRuntimeError("mandatory_stream_unavailable", context={"streams": missing})
        checks = (
            ("ecg_sample_rate_hz", caps.ecg_sample_rates_hz),
            ("ecg_resolution_bits", caps.ecg_resolutions_bits),
            ("acc_sample_rate_hz", caps.acc_sample_rates_hz),
            ("acc_resolution_bits", caps.acc_resolutions_bits),
            ("acc_range_g", caps.acc_ranges_g),
        )
        unsupported = {key: requested[key] for key, supported in checks if requested[key] not in supported}
        if unsupported:
            raise PolarRuntimeError("exact_stream_settings_unavailable", context={"unsupported": unsupported})

    async def start_capture(self, capture_id: str, lease: str) -> PolarCaptureV1:
        async with self._lock:
            if self._capture is not None:
                raise PolarRuntimeError("polar_capture_already_active")
            if self._device is None or self._connection_lost:
                raise PolarRuntimeError("polar_device_not_connected")
            row = self._row(capture_id, lease=lease)
            with Session(self.engine) as db:
                from app.study_admission import guard_source
                guard_source(db, row)
            if row.lifecycle != "created":
                raise PolarRuntimeError("polar_capture_not_startable")
            if row.matb_session_kind == "openmatb":
                from app.openmatb_models import OpenMatbSuiteSession
                with Session(self.engine) as db:
                    linked = db.get(OpenMatbSuiteSession, row.matb_session_id)
                    if linked is None:
                        raise PolarRuntimeError("openmatb_session_not_found")
                    if linked.lifecycle not in {"READY", "PREFLIGHT_HELD", "STARTING", "RUNNING", "PAUSED"}:
                        raise PolarRuntimeError("physiology_requires_openmatb_ready")
            requested = json.loads(row.requested_settings_json)
            self._validate_settings(requested)
            with Session(self.engine) as db:
                from app.station_resources import admit_source
                admit_source(db, row);db.commit()
            self._loop = asyncio.get_running_loop()
            try:
                writer = ParquetCaptureWriter(self.artifact_root, capture_id)
            except FileExistsError as exc:
                raise PolarRuntimeError("capture_artifact_directory_exists") from exc
            context = _CaptureContext(
                capture_id=capture_id,
                writer=writer,
                settings=requested,
                queues={name: asyncio.Queue(maxsize=self.QUEUE_PACKETS) for name in ("rr", "ecg", "acc")},
            )
            self._capture = context
            context.tasks = [
                asyncio.create_task(self._consume(name, context), name=f"polar-{name}-{capture_id}")
                for name in ("rr", "ecg", "acc")
            ]
            self._update_row(capture_id, lifecycle="starting", artifact_state="partial",
                             artifact_root=str(writer.capture_root), started_at=_utcnow(),
                             resolved_settings_json=json.dumps(requested, sort_keys=True))
            await self._emit(capture_id, "status", {"lifecycle": "starting"})
            try:
                await self.transport.start_hr(lambda packet: self._enqueue("rr", packet))
                await self.transport.start_ecg(
                    requested["ecg_sample_rate_hz"], requested["ecg_resolution_bits"],
                    lambda packet: self._enqueue("ecg", packet),
                )
                await self.transport.start_acc(
                    requested["acc_sample_rate_hz"], requested["acc_resolution_bits"],
                    requested["acc_range_g"], lambda packet: self._enqueue("acc", packet),
                )
            except Exception as exc:
                context.incomplete_reasons.add(f"mandatory_stream_start_failed:{type(exc).__name__}")
                await self._stop_active("mandatory_stream_start_failed")
                raise PolarRuntimeError(
                    "mandatory_stream_start_failed", context={"error_type": type(exc).__name__}
                ) from exc
            self._update_row(capture_id, lifecycle="capturing")
            await self._emit(capture_id, "status", {"lifecycle": "capturing", "resolved_settings": requested})
            return self.capture_view(capture_id)

    def _enqueue(self, stream: str, packet: Any) -> None:
        context = self._capture
        loop = self._loop
        if context is None or loop is None:
            return
        def put() -> None:
            active = self._capture
            if active is not context:
                return
            try:
                context.queues[stream].put_nowait(packet)
            except asyncio.QueueFull:
                context.counters["queue_overflow_packets"] += 1
                context.gap_count += 1
                context.pending_gap = True
                context.incomplete_reasons.add(f"{stream}_queue_overflow")
                asyncio.create_task(self._emit(context.capture_id, "gap", {
                    "stream": stream, "reason": "bounded_queue_overflow"
                }))
        loop.call_soon_threadsafe(put)

    async def _consume(self, stream: str, context: _CaptureContext) -> None:
        queue = context.queues[stream]
        while True:
            packet = await queue.get()
            try:
                if packet is None:
                    return
                rows = self._rows_for_packet(stream, packet, context)
                await asyncio.to_thread(context.writer.write_rows, stream, rows)
            except Exception as exc:
                context.incomplete_reasons.add(f"{stream}_writer_error:{type(exc).__name__}")
                context.gap_count += 1
                context.pending_gap = True
                await self._emit(context.capture_id, "error", {
                    "stream": stream, "reason": "writer_error", "error_type": type(exc).__name__
                })
            finally:
                queue.task_done()

    def _sensor_rows(
        self, stream: str, packet: EcgPacket | AccPacket, context: _CaptureContext,
        sample_rate_hz: int,
    ) -> list[tuple[int, int, int]]:
        samples = packet.samples_uv if isinstance(packet, EcgPacket) else packet.samples_mg
        period_ns = round(1_000_000_000 / sample_rate_hz)
        mapping = f"{stream}_epoch_{context.connection_epoch}"
        utc_key = f"{mapping}_to_utc"
        monotonic_key = f"{mapping}_to_monotonic"
        if utc_key not in context.clock_offsets_ns:
            context.clock_offsets_ns[utc_key] = packet.received_utc_ns - packet.sensor_timestamp_ns
            context.clock_offsets_ns[monotonic_key] = (
                packet.received_monotonic_ns - packet.sensor_timestamp_ns
            )
        previous = context.last_sensor_timestamp_ns.get(mapping)
        if previous is not None:
            expected = previous + len(samples) * period_ns
            if abs(packet.sensor_timestamp_ns - expected) > period_ns:
                context.gap_count += 1
                context.pending_gap = True
                context.incomplete_reasons.add(f"{stream}_sensor_timestamp_discontinuity")
                asyncio.create_task(self._emit(context.capture_id, "gap", {
                    "stream": stream,
                    "reason": "sensor_timestamp_discontinuity",
                    "connection_epoch": context.connection_epoch,
                    "expected_sensor_timestamp_ns": expected,
                    "observed_sensor_timestamp_ns": packet.sensor_timestamp_ns,
                }))
        context.last_sensor_timestamp_ns[mapping] = packet.sensor_timestamp_ns
        utc_offset = context.clock_offsets_ns[utc_key]
        monotonic_offset = context.clock_offsets_ns[monotonic_key]
        return [
            (packet.sensor_timestamp_ns - (len(samples) - 1 - index) * period_ns,
             packet.sensor_timestamp_ns - (len(samples) - 1 - index) * period_ns
             + monotonic_offset,
             packet.sensor_timestamp_ns - (len(samples) - 1 - index) * period_ns
             + utc_offset)
            for index in range(len(samples))
        ]

    def _rows_for_packet(self, stream: str, packet: Any, context: _CaptureContext) -> list[dict[str, Any]]:
        if stream == "rr":
            assert isinstance(packet, HrPacket)
            context.notification_index += 1
            context.counters["hr_notifications"] += 1
            measurement = packet.measurement
            rows: list[dict[str, Any]] = []
            suffix_ticks = 0
            beat_times: list[int] = []
            for ticks in reversed(measurement.rr_ticks_1024):
                beat_times.append(packet.received_monotonic_ns - round(suffix_ticks * 1_000_000_000 / 1024))
                suffix_ticks += ticks
            beat_times.reverse()
            for index, (ticks, rr_ms) in enumerate(zip(measurement.rr_ticks_1024, measurement.rr_ms)):
                context.beat_index += 1
                gap = context.pending_gap
                context.pending_gap = False
                rows.append({
                    "notification_index": context.notification_index,
                    "beat_index": context.beat_index,
                    "received_monotonic_ns": packet.received_monotonic_ns,
                    "received_utc_ns": packet.received_utc_ns,
                    "beat_monotonic_ns": beat_times[index],
                    "rr_ticks_1024": ticks,
                    "rr_ms": rr_ms,
                    "heart_rate_bpm": measurement.heart_rate_bpm,
                    "contact_supported": measurement.sensor_contact_supported,
                    "contact_detected": measurement.sensor_contact_detected,
                    "gap_before": gap,
                    "connection_epoch": context.connection_epoch,
                })
                if ticks > 0:
                    context.live_rr.append((rr_ms, not gap))
            context.counters["rr_intervals"] += len(rows)
            asyncio.create_task(self._emit(context.capture_id, "hr", {
                "heart_rate_bpm": measurement.heart_rate_bpm,
                "rr_ms": list(measurement.rr_ms),
                "contact_supported": measurement.sensor_contact_supported,
                "contact_detected": measurement.sensor_contact_detected,
                "timestamp_basis": "host_reconstructed_unknown_ble_latency",
            }))
            self._maybe_emit_live_quality(context)
            return rows
        if stream == "ecg":
            assert isinstance(packet, EcgPacket)
            context.ecg_packet_index += 1
            context.counters["ecg_packets"] += 1
            times = self._sensor_rows("ecg", packet, context, context.settings["ecg_sample_rate_hz"])
            rows = []
            for value, (sensor_ns, monotonic_ns, utc_ns) in zip(packet.samples_uv, times):
                context.ecg_sample_index += 1
                rows.append({
                    "packet_index": context.ecg_packet_index, "sample_index": context.ecg_sample_index,
                    "sensor_timestamp_ns": sensor_ns,
                    "reconstructed_monotonic_ns": monotonic_ns,
                    "reconstructed_utc_ns": utc_ns,
                    "received_monotonic_ns": packet.received_monotonic_ns,
                    "received_utc_ns": packet.received_utc_ns, "ecg_uv": value,
                    "connection_epoch": context.connection_epoch,
                })
            context.counters["ecg_samples"] += len(rows)
            if packet.samples_uv:
                asyncio.create_task(self._emit(context.capture_id, "preview", {
                    "stream": "ecg", "sample_count": len(packet.samples_uv),
                    "minimum_uv": min(packet.samples_uv), "maximum_uv": max(packet.samples_uv),
                    "sensor_timestamp_ns": packet.sensor_timestamp_ns,
                }))
            return rows
        assert isinstance(packet, AccPacket)
        context.acc_packet_index += 1
        context.counters["acc_packets"] += 1
        times = self._sensor_rows("acc", packet, context, context.settings["acc_sample_rate_hz"])
        rows = []
        magnitudes: list[float] = []
        for (x, y, z), (sensor_ns, monotonic_ns, utc_ns) in zip(packet.samples_mg, times):
            context.acc_sample_index += 1
            rows.append({
                "packet_index": context.acc_packet_index, "sample_index": context.acc_sample_index,
                "sensor_timestamp_ns": sensor_ns,
                "reconstructed_monotonic_ns": monotonic_ns,
                "reconstructed_utc_ns": utc_ns,
                "received_monotonic_ns": packet.received_monotonic_ns,
                "received_utc_ns": packet.received_utc_ns,
                "x_mg": x, "y_mg": y, "z_mg": z,
                "sample_rate_hz": context.settings["acc_sample_rate_hz"],
                "range_g": context.settings["acc_range_g"],
                "connection_epoch": context.connection_epoch,
            })
            magnitudes.append(math.sqrt(x * x + y * y + z * z))
        context.counters["acc_samples"] += len(rows)
        if magnitudes:
            asyncio.create_task(self._emit(context.capture_id, "preview", {
                "stream": "acc", "sample_count": len(magnitudes),
                "mean_vector_magnitude_mg": sum(magnitudes) / len(magnitudes),
                "sensor_timestamp_ns": packet.sensor_timestamp_ns,
            }))
        return rows

    def _maybe_emit_live_quality(self, context: _CaptureContext) -> None:
        values = list(context.live_rr)
        total = 0.0
        start = len(values)
        for index in range(len(values) - 1, -1, -1):
            total += values[index][0]
            start = index
            if total >= 60_000.0:
                break
        window = values[start:]
        if total < 60_000.0 or len(window) < 30:
            return
        rr = [entry[0] for entry in window]
        continuity = [window[index + 1][1] for index in range(len(window) - 1)]
        metrics = analyze_rr_window(rr, continuity=continuity, minimum_duration_s=60.0)
        metrics["window_label"] = "60_second_descriptive_sdnn_ultra_short_exploratory"
        asyncio.create_task(self._emit(context.capture_id, "quality", metrics))

    async def add_marker(self, capture_id: str, lease: str, label: str, payload: dict[str, Any]) -> PolarCaptureV1:
        row = self._row(capture_id, lease=lease)
        if row.lifecycle != "capturing" or self._capture is None or self._capture.capture_id != capture_id:
            raise PolarRuntimeError("polar_capture_not_running")
        sequence = self._sequence.get(capture_id, 0) + 1
        marker = PolarCaptureMarkerRecord(
            capture_id=capture_id,
            sequence=sequence,
            label=label,
            payload_json=json.dumps(payload, sort_keys=True),
            host_monotonic_ns=time.monotonic_ns(),
        )
        with Session(self.engine) as db:
            db.add(marker)
            db.commit()
        await self._emit(capture_id, "marker", {
            "label": label, "payload": payload,
            "timestamp_basis": "host_monotonic_not_physical_stimulus_onset",
        })
        return self.capture_view(capture_id)

    async def system_marker_for_session(
        self, session_kind: str, session_id: str, label: str, payload: dict[str, Any] | None = None
    ) -> bool:
        """Insert a trusted lifecycle marker for the currently linked MATB session."""

        context = self._capture
        if context is None:
            return False
        row = self._row(context.capture_id)
        if (
            row.lifecycle != "capturing"
            or row.matb_session_kind != session_kind
            or row.matb_session_id != session_id
        ):
            return False
        marker = PolarCaptureMarkerRecord(
            capture_id=context.capture_id,
            sequence=self._sequence.get(context.capture_id, 0) + 1,
            label=label,
            payload_json=json.dumps(payload or {}, sort_keys=True),
            host_monotonic_ns=time.monotonic_ns(),
        )
        with Session(self.engine) as db:
            db.add(marker)
            db.commit()
        await self._emit(context.capture_id, "marker", {
            "label": label,
            "payload": payload or {},
            "source": "matb_session_lifecycle",
            "timestamp_basis": "host_monotonic_not_physical_stimulus_onset",
        })
        return True

    async def stop_capture(self, capture_id: str, lease: str) -> PolarCaptureV1:
        row = self._row(capture_id, lease=lease)
        if self._capture is None or self._capture.capture_id != capture_id:
            if row.lifecycle in {"complete", "failed"}:
                return self._view(row)
            raise PolarRuntimeError("polar_capture_not_running")
        async with self._lock:
            await self._stop_active(None)
        return self.capture_view(capture_id)

    async def _stop_active(self, reason: str | None) -> None:
        context = self._capture
        if context is None:
            return
        capture_id = context.capture_id
        self._update_row(capture_id, lifecycle="stopping")
        await self._emit(capture_id, "status", {"lifecycle": "stopping"})
        if reason:
            context.incomplete_reasons.add(reason)
        try:
            await self.transport.stop_all()
        except Exception as exc:
            context.incomplete_reasons.add(f"stream_stop_failed:{type(exc).__name__}")
        for queue in context.queues.values():
            await queue.put(None)
        results = await asyncio.gather(*context.tasks, return_exceptions=True)
        if any(isinstance(result, BaseException) for result in results):
            context.incomplete_reasons.add("writer_task_failed")
        ended = _utcnow()
        row = self._row(capture_id)
        started = row.started_at or ended
        manifest_seed = PolarArtifactManifestV1(
            execution_purpose=row.execution_purpose,
            capture_id=capture_id,
            participant_pseudonym=row.participant_id,
            matb_session_kind=row.matb_session_kind,
            matb_session_id=row.matb_session_id,
            started_at_utc=started,
            ended_at_utc=ended,
            requested_settings=json.loads(row.requested_settings_json),
            resolved_settings=json.loads(row.resolved_settings_json or row.requested_settings_json),
            clock_model={
                "pmd_sensor_timestamp_preserved": True,
                "pmd_epoch_offsets_ns": context.clock_offsets_ns,
                "hrs_beat_time_basis": "host_reconstructed_unknown_ble_latency",
                "marker_time_basis": "host_monotonic_not_physical_stimulus_onset",
            },
            stream_counters=context.counters,
            algorithm_versions=HRV_ALGORITHM_VERSIONS,
            incomplete_reasons=tuple(sorted(context.incomplete_reasons)),
            artifacts=(),
        )
        try:
            manifest = await asyncio.to_thread(context.writer.finalize, manifest_seed)
            manifest_json = json.dumps(manifest.model_dump(mode="json"), sort_keys=True)
            manifest_hash = _file_sha256(context.writer.capture_root / "manifest.json")
            state = "incomplete" if context.incomplete_reasons else "finalized"
            lifecycle = "failed" if reason else "complete"
            self._update_row(
                capture_id, lifecycle=lifecycle, artifact_state=state, ended_at=ended,
                stream_counters_json=json.dumps(context.counters, sort_keys=True),
                gap_count=context.gap_count, connection_epoch=context.connection_epoch,
                incomplete_reasons_json=json.dumps(sorted(context.incomplete_reasons)),
                manifest_json=manifest_json, manifest_sha256=manifest_hash,
            )
        except Exception as exc:
            context.writer.abort()
            context.incomplete_reasons.add(f"artifact_finalization_failed:{type(exc).__name__}")
            self._update_row(
                capture_id, lifecycle="failed", artifact_state="incomplete", ended_at=ended,
                stream_counters_json=json.dumps(context.counters, sort_keys=True),
                gap_count=context.gap_count,
                incomplete_reasons_json=json.dumps(sorted(context.incomplete_reasons)),
            )
        self._capture = None
        finalized = self._row(capture_id)
        if finalized.manifest_json:
            try:
                await asyncio.to_thread(self._rr_exports, finalized)
            except Exception as exc:
                # A derived-format failure must not relabel successfully saved raw data.
                import logging
                logging.getLogger(__name__).warning("RR export unavailable: %s", type(exc).__name__)
        await self._emit(capture_id, "status", {
            "lifecycle": self.capture_view(capture_id).lifecycle,
            "artifact_state": self.capture_view(capture_id).artifact_state,
        })

    def _update_row(self, capture_id: str, **values: Any) -> None:
        with Session(self.engine) as db:
            row = db.get(PolarCaptureRecord, capture_id)
            if row is None:
                raise PolarRuntimeError("polar_capture_not_found")
            for key, value in values.items():
                setattr(row, key, value)
            from app.study_admission import sync_runtime_attempt
            lifecycle = values.get('lifecycle')
            if lifecycle in {'starting', 'capturing'}: sync_runtime_attempt(db, row, state='started')
            elif lifecycle == 'complete': sync_runtime_attempt(db, row, state='finished')
            elif lifecycle in {'interrupted', 'failed'}: sync_runtime_attempt(db, row, state='interrupted')
            db.add(row)
            db.commit()

    def _on_disconnect(self) -> None:
        if not self._intentional_disconnect:
            self._connection_lost = True
        if self._intentional_disconnect or self._capture is None or self._loop is None:
            return
        context = self._capture
        def mark() -> None:
            if self._capture is not context:
                return
            context.connection_epoch += 1
            context.gap_count += 1
            context.pending_gap = True
            context.incomplete_reasons.add("unexpected_disconnect")
            asyncio.create_task(self._emit(context.capture_id, "gap", {
                "reason": "unexpected_disconnect", "connection_epoch": context.connection_epoch,
            }))
        self._loop.call_soon_threadsafe(mark)

    async def _emit(self, capture_id: str, event_type: str, payload: dict[str, Any]) -> None:
        sequence = self._sequence.get(capture_id, 0) + 1
        self._sequence[capture_id] = sequence
        event = PolarCaptureEventV1(
            capture_id=capture_id,
            sequence=sequence,
            event_type=event_type,
            occurred_at_utc=_utcnow(),
            payload=payload,
        )
        events = self._events.setdefault(capture_id, [])
        events.append(event)
        if len(events) > 5000:
            del events[:-5000]
        condition = self._conditions.setdefault(capture_id, asyncio.Condition())
        async with condition:
            condition.notify_all()

    async def events_after(self, capture_id: str, after_sequence: int, timeout_s: float = 30.0) -> list[PolarCaptureEventV1]:
        self._row(capture_id)
        current = [event for event in self._events.get(capture_id, ()) if event.sequence > after_sequence]
        if current:
            return current
        condition = self._conditions.setdefault(capture_id, asyncio.Condition())
        try:
            async with condition:
                await asyncio.wait_for(condition.wait(), timeout=timeout_s)
        except TimeoutError:
            return []
        return [event for event in self._events.get(capture_id, ()) if event.sequence > after_sequence]

    def inventory(self, capture_id: str, lease: str) -> tuple[PolarCaptureRecord, PolarArtifactManifestV1 | None, list[str]]:
        row = self._row(capture_id, lease=lease)
        manifest = PolarArtifactManifestV1.model_validate_json(row.manifest_json) if row.manifest_json else None
        partials: list[str] = []
        if row.artifact_root:
            root = resolve_artifact(row.artifact_root).resolve()
            if root.parent == self.artifact_root and root.exists():
                partials = [path.name for path in sorted(root.glob("*.partial"))]
        return row, manifest, partials

    def bundle(self, capture_id: str, lease: str) -> Path:
        row, manifest, partials = self.inventory(capture_id, lease)
        if manifest is None or partials or row.artifact_state not in {"finalized", "incomplete"}:
            raise PolarRuntimeError("polar_artifacts_not_finalized")
        root = resolve_artifact(row.artifact_root or "").resolve()
        if root.parent != self.artifact_root:
            raise PolarRuntimeError("polar_artifact_path_invalid")
        target = root / f"{capture_id}.zip"
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for entry in manifest.artifacts:
                path = (root / entry.relative_path).resolve()
                if path.parent != root or _file_sha256(path) != entry.sha256:
                    raise PolarRuntimeError("polar_artifact_checksum_failed")
                archive.write(path, arcname=entry.relative_path)
            archive.write(root / "manifest.json", arcname="manifest.json")
            exports = self._rr_exports(row)
            for item in exports["files"]:
                archive.write(root / "rr-export" / item["filename"], arcname="rr-export/" + item["filename"])
            archive.write(root / "rr-export" / "rr_export_manifest.json", arcname="rr-export/rr_export_manifest.json")
            archive.write(self.rr_export_file(capture_id, lease, "capture_context.json"), arcname="rr-export/capture_context.json")
        return target

    def _rr_exports(self, row: PolarCaptureRecord) -> dict[str, Any]:
        if not row.manifest_json or row.artifact_state not in {"finalized", "incomplete"}:
            raise PolarRuntimeError("polar_artifacts_not_finalized")
        root = resolve_artifact(row.artifact_root or "").resolve()
        if root.parent != self.artifact_root:
            raise PolarRuntimeError("polar_artifact_path_invalid")
        manifest = PolarArtifactManifestV1.model_validate_json(row.manifest_json)
        try:
            return export_rr_capture(root, manifest)
        except RRExportError as exc:
            raise PolarRuntimeError(str(exc)) from exc

    def rr_export(self, capture_id: str, lease: str) -> dict[str, Any]:
        from app.physiology_schemas import RRExportView
        result = self._rr_exports(self._row(capture_id, lease=lease))
        return {key: result[key] for key in RRExportView.model_fields}

    def rr_export_file(self, capture_id: str, lease: str, filename: str) -> Path:
        row = self._row(capture_id, lease=lease)
        result = self._rr_exports(row)
        allowed = {item["filename"] for item in result["files"]} | {"rr_export_manifest.json", "capture_context.json"}
        if filename not in allowed:
            raise PolarRuntimeError("polar_rr_export_file_not_found")
        root = (resolve_artifact(row.artifact_root) / "rr-export").resolve()
        path = (root / filename).resolve()
        if path.parent != root:
            raise PolarRuntimeError("polar_artifact_path_invalid")
        if filename == "capture_context.json":
            with Session(self.engine) as db:
                markers = db.exec(select(PolarCaptureMarkerRecord).where(
                    PolarCaptureMarkerRecord.capture_id == capture_id).order_by(PolarCaptureMarkerRecord.sequence)).all()
            context = dict(schema_id="matb.polar.capture-context.v1", capture_id=capture_id,
                participant_pseudonym=row.participant_id, execution_purpose=row.execution_purpose,
                matb_session_kind=row.matb_session_kind, matb_session_id=row.matb_session_id,
                device_alias=row.device_alias, alias_is_persistent_device_id=False,
                source_manifest_sha256=row.manifest_sha256,
                markers=[dict(sequence=marker.sequence, label=marker.label, payload=json.loads(marker.payload_json),
                    host_monotonic_ns=marker.host_monotonic_ns, occurred_at_utc=marker.occurred_at_utc.isoformat()) for marker in markers])
            # Derived from durable metadata, not a change to the raw capture.
            # Serialize into the same-directory temporary file before publication.
            import os
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, suffix=".partial", delete=False) as handle:
                json.dump(context, handle, indent=2, allow_nan=False)
                temporary = handle.name
            os.replace(temporary, path)
        return path

    def review_capture(self, capture_id: str, lease: str) -> dict[str, Any]:
        from matb_integration.physiology.review import review_capture
        row, manifest, partials = self.inventory(capture_id, lease)
        if manifest is None or partials or row.artifact_state not in {"finalized", "incomplete"}:
            raise PolarRuntimeError("polar_artifacts_not_finalized")
        root = resolve_artifact(row.artifact_root or "").resolve()
        if root.parent != self.artifact_root:
            raise PolarRuntimeError("polar_artifact_path_invalid")
        try:
            return review_capture(root, manifest)
        except RRExportError as exc:
            raise PolarRuntimeError(str(exc)) from exc

    def analyze_capture(self, capture_id: str, lease: str) -> dict[str, Any]:
        """Compute standardized five-minute phase descriptors from finalized raw data."""

        row, manifest, partials = self.inventory(capture_id, lease)
        if manifest is None or partials:
            raise PolarRuntimeError("polar_artifacts_not_finalized")
        root = resolve_artifact(row.artifact_root or "").resolve()
        if root.parent != self.artifact_root:
            raise PolarRuntimeError("polar_artifact_path_invalid")
        import pyarrow.parquet as pq

        rr_table = pq.read_table(root / "rr.parquet", columns=[
            "beat_monotonic_ns", "rr_ms", "contact_supported", "contact_detected",
            "gap_before", "connection_epoch",
        ]).to_pydict()
        acc_table = pq.read_table(root / "acc.parquet", columns=[
            "received_monotonic_ns", "x_mg", "y_mg", "z_mg",
        ]).to_pydict()
        with Session(self.engine) as db:
            markers = db.exec(
                select(PolarCaptureMarkerRecord)
                .where(PolarCaptureMarkerRecord.capture_id == capture_id)
                .order_by(PolarCaptureMarkerRecord.host_monotonic_ns)
            ).all()
        if not markers:
            return {
                "capture_id": capture_id, "valid": False, "reason": "no_phase_markers",
                "phase_window_seconds": 300, "phases": [], "workload_responses": [],
                "interpretation": "descriptive_only_no_workload_classification",
            }
        phase_results: list[dict[str, Any]] = []
        beat_times = rr_table["beat_monotonic_ns"]
        for marker_index, marker in enumerate(markers):
            end = marker.host_monotonic_ns + 300_000_000_000
            if marker_index + 1 < len(markers):
                end = min(end, markers[marker_index + 1].host_monotonic_ns)
            indices = [
                index for index, timestamp in enumerate(beat_times)
                if marker.host_monotonic_ns <= timestamp < end
            ]
            rr = [float(rr_table["rr_ms"][index]) for index in indices]
            supported = [bool(rr_table["contact_supported"][index]) for index in indices]
            detected = [rr_table["contact_detected"][index] for index in indices]
            external_valid = [not support or contact is True for support, contact in zip(supported, detected)]
            continuity: list[bool] = []
            for left, right in zip(indices, indices[1:]):
                adjacent = right == left + 1
                same_epoch = rr_table["connection_epoch"][left] == rr_table["connection_epoch"][right]
                no_gap = not bool(rr_table["gap_before"][right])
                continuity.append(adjacent and same_epoch and no_gap)
            metrics = analyze_rr_window(
                rr, continuity=continuity, external_valid=external_valid,
                minimum_duration_s=300.0, minimum_sqi=0.8,
            ) if rr else {
                "valid": False, "reason": "no_rr_intervals", "n_intervals": 0,
                "duration_s": 0.0, "mean_instantaneous_hr_bpm": None,
                "sdnn_ms": None, "rmssd_ms": None, "ln_rmssd": None,
                "pnn50_percent": None, "lf_power_ms2": None, "hf_power_ms2": None,
                "lf_hf_ratio": None,
            }
            magnitudes = [
                math.sqrt(x * x + y * y + z * z)
                for timestamp, x, y, z in zip(
                    acc_table["received_monotonic_ns"], acc_table["x_mg"],
                    acc_table["y_mg"], acc_table["z_mg"],
                )
                if marker.host_monotonic_ns <= timestamp < end
            ]
            phase_results.append({
                "label": marker.label,
                "marker_sequence": marker.sequence,
                "window_start_monotonic_ns": marker.host_monotonic_ns,
                "window_end_monotonic_ns": end,
                "metrics": metrics,
                "movement_context": {
                    "mean_vector_magnitude_mg": (
                        sum(magnitudes) / len(magnitudes) if magnitudes else None
                    ),
                    "n_acc_samples": len(magnitudes),
                },
            })
        baseline = next((phase for phase in phase_results if phase["label"] in {"BASELINE", "TASK_PRE"}), None)
        responses: list[dict[str, Any]] = []
        for phase in phase_results:
            if phase["label"] not in {"PRACTICE", "LOW", "MEDIUM", "HIGH"}:
                continue
            response = workload_response(
                baseline["metrics"] if baseline else {"valid": False}, phase["metrics"]
            )
            responses.append({
                "phase": phase["label"], **response,
                "artifact_burden_percent": phase["metrics"].get("artifact_burden_percent"),
                "usable_coverage_percent": (
                    min(100.0, 100.0 * phase["metrics"].get("usable_duration_s", 0.0) / 300.0)
                    if phase["metrics"].get("usable_duration_s") is not None else 0.0
                ),
                "movement_context": phase["movement_context"],
            })
        valid = bool(baseline and baseline["metrics"].get("valid") and responses)
        return {
            "capture_id": capture_id,
            "valid": valid,
            "reason": None if valid else "baseline_or_task_phase_unavailable",
            "phase_window_seconds": 300,
            "phases": phase_results,
            "workload_responses": responses,
            "interpretation": "descriptive_only_no_workload_classification",
        }
