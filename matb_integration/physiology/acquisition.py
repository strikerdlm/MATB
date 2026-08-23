"""Session-scoped Polar H10 RR capture with explicit phase boundaries."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import asdict, dataclass
import asyncio
import hashlib
import json
import os
from pathlib import Path
import time
from typing import IO, Any
from uuid import uuid4

import numpy as np

from .backend import DeviceCandidate, PolarBackend, PolarBackendError
from .durability import (
    fsync_directory as _fsync_directory,
    make_private_directory,
    open_private_exclusive,
)
from .hrs import HeartRatePacket, HeartRatePacketError, RRValue, parse_heart_rate_measurement
from .hrv import analyze_rr_phase
from .timing import (
    ClockAnchor,
    HostClockMapper,
    NotificationRRBatch,
    estimate_segment_beat_times,
)


PHASE_NAMES = ("baseline", "task", "recovery")
_DEFAULT_PHASE_DURATIONS = {"baseline": 300.0, "task": 900.0, "recovery": 300.0}


async def _finish_cleanup(
    operation: Callable[[], Awaitable[None]],
    *,
    suppress_errors: bool,
) -> None:
    """Finish cleanup despite cancellation, then preserve cancellation semantics."""

    cleanup = asyncio.create_task(operation())
    cancellation_requested = False
    try:
        await cleanup
    except asyncio.CancelledError:
        # Cancellation reaches the first cleanup call so implementations such
        # as Bleak can unwind their in-flight OS operation.  Retry the
        # idempotent cleanup in an independent task before re-raising.
        cancellation_requested = True
        cleanup = asyncio.create_task(operation())
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                continue
            except BaseException:
                break
    except BaseException:
        pass
    cleanup_error: BaseException | None = None
    try:
        cleanup.result()
    except BaseException as exc:
        cleanup_error = exc
    if cancellation_requested:
        raise asyncio.CancelledError
    if cleanup_error is not None and not suppress_errors:
        raise cleanup_error


async def _stop_notifications_quietly(backend: PolarBackend) -> None:
    """Complete unsubscribe without replacing an in-flight primary error."""

    await _finish_cleanup(backend.stop_notifications, suppress_errors=True)


class AcquisitionLifecycleError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PolarSessionResult:
    rr_records: tuple[dict[str, Any], ...]
    phase_results: dict[str, dict[str, Any]]
    clock_anchors: tuple[dict[str, Any], ...]
    malformed_packet_count: int
    disconnect_count: int
    queue_overflow_count: int
    contact_loss_detected: bool


@dataclass(frozen=True, slots=True)
class PolarConnectionStatus:
    state: str
    backend_name: str
    connected_device_name: str | None
    device_identifier_sha256: str | None
    battery_level: int | None
    recording: bool
    reconnect_attempts: int
    last_error_code: str | None
    preflight_ready: bool
    last_rr_at_utc_ns: int | None
    sensor_contact_detected: bool | None


@dataclass(frozen=True, slots=True)
class PolarPreflightResult:
    ready: bool
    heart_rate_bpm: int | None
    rr_count: int
    sensor_contact_detected: bool | None
    battery_level: int | None
    measured_at_utc_ns: int
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class _CapturedNotification:
    phase: str
    segment_id: str
    batch: NotificationRRBatch
    packet: HeartRatePacket


class PolarSessionRecorder:
    """Capture the standard HRS notification stream for one MATB attempt."""

    def __init__(
        self,
        backend: PolarBackend,
        *,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
        wall_ns: Callable[[], int] = time.time_ns,
    ) -> None:
        self.backend = backend
        self._monotonic_ns = monotonic_ns
        self._clock = HostClockMapper(monotonic_ns=monotonic_ns, wall_ns=wall_ns)
        self._session_id: str | None = None
        self._active = False
        self._phase: str | None = None
        self._phase_durations: dict[str, float] = {}
        self._phase_bounds_monotonic_ns: dict[str, list[int | None]] = {}
        self._notifications: list[_CapturedNotification] = []
        self._notification_index = 0
        self._segment_id: str | None = None
        self._malformed_packet_count = 0
        self._disconnect_count = 0
        self._disconnected = False
        self._queue_overflow_count = 0
        self._contact_loss_phases: set[str] = set()
        self._last_sensor_contact_detected: bool | None = None
        self._disconnect_phases: dict[str, int] = defaultdict(int)
        self._journal_file: IO[str] | None = None
        self._journal_path: Path | None = None
        self._journal_sequence = 0
        self._journal_previous_sha256 = "0" * 64

    async def start(self, session_id: str, *, journal_path: Path | None = None) -> None:
        if self._active:
            raise AcquisitionLifecycleError("acquisition_already_started")
        if not session_id:
            raise AcquisitionLifecycleError("session_id_required")
        self._session_id = session_id
        if journal_path is not None:
            path = Path(journal_path)
            parent_existed = path.parent.exists()
            make_private_directory(path.parent)
            if not parent_existed:
                _fsync_directory(path.parent.parent)
            self._journal_file = open_private_exclusive(path, binary=False)
            self._journal_path = path
            _fsync_directory(path.parent)
            self._write_journal("session_started", session_id=session_id)
        self._active = True
        self._start_segment("acquisition_started")
        try:
            await self.backend.start_notifications(self._handle_notification)
        except BaseException:
            self._active = False
            await _stop_notifications_quietly(self.backend)
            with suppress(BaseException):
                self._close_journal()
            raise

    def begin_phase(
        self,
        phase: str,
        *,
        nominal_duration_s: float,
        boundary_monotonic_ns: int | None = None,
    ) -> None:
        self._require_active()
        if phase not in PHASE_NAMES:
            raise AcquisitionLifecycleError("invalid_acquisition_phase")
        if self._phase is not None:
            raise AcquisitionLifecycleError("acquisition_phase_already_active")
        if phase in self._phase_durations:
            raise AcquisitionLifecycleError("acquisition_phase_already_recorded")
        if nominal_duration_s <= 0:
            raise AcquisitionLifecycleError("phase_duration_must_be_positive")
        self._phase = phase
        self._phase_durations[phase] = float(nominal_duration_s)
        anchor = self._capture_anchor(f"{phase}_started")
        start_monotonic_ns = (
            anchor.monotonic_midpoint_ns
            if boundary_monotonic_ns is None
            else int(boundary_monotonic_ns)
        )
        self._phase_bounds_monotonic_ns[phase] = [start_monotonic_ns, None]
        if self._disconnected and self._disconnect_phases[phase] == 0:
            self._disconnect_phases[phase] = 1
        if self._last_sensor_contact_detected is False:
            self._contact_loss_phases.add(phase)
        self._write_journal(
            "phase_started",
            phase=phase,
            nominal_duration_s=float(nominal_duration_s),
            monotonic_ns=start_monotonic_ns,
            disconnected=self._disconnected,
            sensor_contact_detected=self._last_sensor_contact_detected,
        )
        self._write_journal(
            "phase_state_snapshot",
            phase=phase,
            disconnected=self._disconnected,
            sensor_contact_detected=self._last_sensor_contact_detected,
        )

    def end_phase(
        self,
        phase: str,
        *,
        boundary_monotonic_ns: int | None = None,
        use_observed_duration: bool = False,
    ) -> None:
        self._require_active()
        if self._phase != phase:
            raise AcquisitionLifecycleError("acquisition_phase_order")
        anchor = self._capture_anchor(f"{phase}_finished")
        end_monotonic_ns = (
            anchor.monotonic_midpoint_ns
            if boundary_monotonic_ns is None
            else int(boundary_monotonic_ns)
        )
        start_monotonic_ns = int(self._phase_bounds_monotonic_ns[phase][0])
        if end_monotonic_ns < start_monotonic_ns:
            raise AcquisitionLifecycleError("acquisition_phase_boundary_invalid")
        self._phase_bounds_monotonic_ns[phase][1] = end_monotonic_ns
        observed_duration_s = (end_monotonic_ns - start_monotonic_ns) / 1_000_000_000
        if use_observed_duration:
            if observed_duration_s <= 0:
                raise AcquisitionLifecycleError("acquisition_phase_boundary_invalid")
            self._phase_durations[phase] = observed_duration_s
        self._write_journal(
            "phase_finished",
            phase=phase,
            monotonic_ns=end_monotonic_ns,
            observed_duration_s=(observed_duration_s if use_observed_duration else None),
        )
        self._phase = None

    async def stop(self) -> PolarSessionResult:
        self._require_active()
        if self._phase is not None:
            raise AcquisitionLifecycleError("acquisition_phase_still_active")
        self._capture_anchor("acquisition_finished")
        try:
            await self.backend.stop_notifications()
            self._active = False
            result = self._build_result()
            self._write_journal("session_finished", session_id=self._session_id)
            return result
        finally:
            self._active = False
            self._close_journal()

    async def restart_after_reconnect(self) -> None:
        self._require_active()
        await self.backend.start_notifications(self._handle_notification)
        self.note_reconnected()

    def note_disconnect(self) -> None:
        """Record a BLE discontinuity; callers own reconnect attempts."""

        if not self._active:
            return
        self._disconnect_count += 1
        self._disconnected = True
        if self._phase is not None:
            self._disconnect_phases[self._phase] += 1
        self._capture_anchor("bluetooth_disconnected")
        self._write_journal("bluetooth_disconnected", phase=self._phase)

    def note_reconnected(self) -> None:
        self._require_active()
        self._start_segment("bluetooth_reconnected")

    def _start_segment(self, reason: str) -> None:
        self._disconnected = False
        self._segment_id = str(uuid4())
        self._capture_anchor(reason)
        self._write_journal(
            "segment_started",
            segment_id=self._segment_id,
            reason=reason,
        )

    async def _handle_notification(self, payload: bytes) -> None:
        if not self._active or self._segment_id is None:
            return
        captured_phase = self._phase or "unassigned"
        received = int(self._monotonic_ns())
        try:
            packet = parse_heart_rate_measurement(payload)
        except HeartRatePacketError:
            self._malformed_packet_count += 1
            self._write_journal("malformed_packet", phase=self._phase)
            return
        if packet.sensor_contact_supported:
            contact = packet.sensor_contact_detected
            if contact != self._last_sensor_contact_detected:
                self._write_journal(
                    "sensor_contact_status",
                    phase=captured_phase,
                    received_monotonic_ns=received,
                    sensor_contact_detected=contact,
                )
                self._last_sensor_contact_detected = contact
            if contact is False:
                self._contact_loss_phases.add(captured_phase)
        if not packet.rr_values:
            return
        batch = NotificationRRBatch(
            notification_index=self._notification_index,
            received_monotonic_ns=received,
            rr_ticks_1024=tuple(value.ticks_1024 for value in packet.rr_values),
        )
        self._notifications.append(
            _CapturedNotification(
                phase=captured_phase,
                segment_id=self._segment_id,
                batch=batch,
                packet=packet,
            )
        )
        self._write_journal(
            "rr_notification",
            phase=captured_phase,
            segment_id=self._segment_id,
            notification_index=self._notification_index,
            received_monotonic_ns=received,
            flags=packet.flags,
            heart_rate_bpm=packet.heart_rate_bpm,
            rr_ticks_1024=list(batch.rr_ticks_1024),
            sensor_contact_supported=packet.sensor_contact_supported,
            sensor_contact_detected=packet.sensor_contact_detected,
            energy_expended_kj=packet.energy_expended_kj,
        )
        self._notification_index += 1

    def _capture_anchor(self, reason: str) -> ClockAnchor:
        anchor = self._clock.capture_anchor(reason)
        self._write_journal("clock_anchor", **asdict(anchor))
        return anchor

    def _write_journal(self, kind: str, **payload: Any) -> None:
        stream = self._journal_file
        if stream is None:
            return
        self._journal_sequence += 1
        record = {
            "schema_version": "polar-rr-journal-v1",
            "sequence": self._journal_sequence,
            "previous_record_sha256": self._journal_previous_sha256,
            "kind": kind,
            **payload,
        }
        canonical = json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        record_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        record["record_sha256"] = record_hash
        stream.write(
            json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        )
        stream.flush()
        os.fsync(stream.fileno())
        self._journal_previous_sha256 = record_hash

    def _close_journal(self) -> None:
        stream = self._journal_file
        self._journal_file = None
        if stream is not None and not stream.closed:
            try:
                stream.flush()
                os.fsync(stream.fileno())
            finally:
                stream.close()

    def _build_result(self) -> PolarSessionResult:
        estimates: dict[tuple[str, int, int], Any] = {}
        by_segment: dict[str, list[NotificationRRBatch]] = defaultdict(list)
        for captured in self._notifications:
            by_segment[captured.segment_id].append(captured.batch)
        for segment_id, batches in by_segment.items():
            for estimate in estimate_segment_beat_times(segment_id, batches):
                estimates[
                    (
                        segment_id,
                        estimate.notification_index,
                        estimate.rr_index_in_notification,
                    )
                ] = estimate

        phase_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        beat_index = 0
        for captured in self._notifications:
            for rr_index, rr_value in enumerate(captured.packet.rr_values):
                estimate = estimates.get(
                    (captured.segment_id, captured.batch.notification_index, rr_index)
                )
                estimated_monotonic = (
                    estimate.estimated_beat_monotonic_ns
                    if estimate is not None
                    else captured.batch.received_monotonic_ns
                )
                anchor = min(
                    self._clock.anchors,
                    key=lambda item: abs(item.monotonic_midpoint_ns - estimated_monotonic),
                )
                estimated_phase = captured.phase
                for candidate_phase in PHASE_NAMES:
                    bounds = self._phase_bounds_monotonic_ns.get(candidate_phase)
                    if bounds is None or bounds[1] is None:
                        continue
                    if int(bounds[0]) <= estimated_monotonic < int(bounds[1]):
                        estimated_phase = candidate_phase
                        break
                row = {
                    "session_id": self._session_id,
                    "phase": estimated_phase,
                    "segment_id": captured.segment_id,
                    "beat_index": beat_index,
                    "notification_index": captured.batch.notification_index,
                    "rr_index_in_notification": rr_index,
                    "heart_rate_bpm": captured.packet.heart_rate_bpm,
                    "rr_ticks_1024": rr_value.ticks_1024,
                    "rr_ms": rr_value.milliseconds,
                    "corrected_rr_ms": None,
                    "is_artifact": None,
                    "notification_received_monotonic_ns": captured.batch.received_monotonic_ns,
                    "estimated_beat_monotonic_ns": estimated_monotonic,
                    "estimated_beat_utc_ns": estimated_monotonic
                    + anchor.utc_minus_monotonic_offset_ns,
                    "fit_residual_ns": estimate.fit_residual_ns if estimate else None,
                    "fit_uncertainty_ns": estimate.fit_uncertainty_ns if estimate else None,
                    "timestamp_source": (
                        estimate.timestamp_source if estimate else "host_notification_receipt_v1"
                    ),
                    "sensor_contact_supported": captured.packet.sensor_contact_supported,
                    "sensor_contact_detected": captured.packet.sensor_contact_detected,
                    "energy_expended_kj": captured.packet.energy_expended_kj,
                }
                phase_rows[estimated_phase].append(row)
                beat_index += 1

        phase_results: dict[str, dict[str, Any]] = {}
        ordered_records: list[dict[str, Any]] = []
        for phase in PHASE_NAMES:
            if phase not in self._phase_durations:
                analysis = analyze_rr_phase(
                    np.asarray([], dtype=float),
                    nominal_duration_s=_DEFAULT_PHASE_DURATIONS[phase],
                    coverage_fraction=0.0,
                )
                analysis["phase_started"] = False
                analysis["quality"]["reason_codes"] = ["phase_not_started"]
                analysis["time_domain"] = {
                    "status": "not_computable",
                    "reason_code": "phase_not_started",
                    "metrics": None,
                }
                analysis["frequency_domain"] = {
                    "status": "not_computable",
                    "reason_codes": ["phase_not_started"],
                    "metrics": None,
                    "psd": [],
                }
                phase_results[phase] = analysis
                continue
            rows = phase_rows.get(phase, [])
            intervals = np.asarray([row["rr_ms"] for row in rows], dtype=float)
            nominal_duration = self._phase_durations[phase]
            coverage = min(1.0, float(np.sum(intervals)) / (nominal_duration * 1000.0))
            analysis = analyze_rr_phase(
                intervals,
                nominal_duration_s=nominal_duration,
                coverage_fraction=coverage,
                disconnect_count=self._disconnect_phases[phase],
                queue_overflow_count=self._queue_overflow_count,
                contact_loss_detected=phase in self._contact_loss_phases,
            )
            analysis["phase_started"] = True
            for row, corrected, valid in zip(
                rows,
                analysis["corrected_rr_ms"],
                analysis["valid_mask"],
                strict=True,
            ):
                row["corrected_rr_ms"] = corrected
                row["is_artifact"] = not valid
            phase_results[phase] = analysis
            ordered_records.extend(rows)

        # Preserve every RR interval received between named analysis phases
        # (for example while the OpenMATB window initializes).  These rows stay
        # raw and explicitly unassigned; they are never included in HRV phase
        # metrics or coverage calculations.
        for phase, rows in phase_rows.items():
            if phase not in PHASE_NAMES:
                ordered_records.extend(rows)

        ordered_records.sort(key=lambda row: int(row["beat_index"]))
        return PolarSessionResult(
            rr_records=tuple(ordered_records),
            phase_results=phase_results,
            clock_anchors=tuple(asdict(anchor) for anchor in self._clock.anchors),
            malformed_packet_count=self._malformed_packet_count,
            disconnect_count=self._disconnect_count,
            queue_overflow_count=self._queue_overflow_count,
            contact_loss_detected=bool(self._contact_loss_phases),
        )

    def _require_active(self) -> None:
        if not self._active:
            raise AcquisitionLifecycleError("acquisition_not_started")


def recover_polar_session_journal(journal_path: Path) -> PolarSessionResult:
    """Rebuild all fsynced RR evidence after an abrupt backend interruption."""

    path = Path(journal_path)
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AcquisitionLifecycleError("acquisition_journal_unavailable") from exc

    raw_lines = raw_text.splitlines()
    records: list[dict[str, Any]] = []
    for index, line in enumerate(raw_lines):
        if not line.strip():
            raise AcquisitionLifecycleError("acquisition_journal_invalid")
        try:
            record = json.loads(line)
        except (TypeError, ValueError):
            # A power loss can leave only the final append truncated.  Every
            # earlier line was fsynced and remains independently recoverable.
            if index == len(raw_lines) - 1 and not raw_text.endswith("\n"):
                break
            raise AcquisitionLifecycleError("acquisition_journal_invalid")
        if (
            isinstance(record, dict)
            and record.get("schema_version") == "polar-rr-journal-v1"
        ):
            records.append(record)
        else:
            raise AcquisitionLifecycleError("acquisition_journal_invalid")
    if records:
        previous_hash = "0" * 64
        for sequence, record in enumerate(records, start=1):
            stored_hash = record.get("record_sha256")
            candidate = dict(record)
            candidate.pop("record_sha256", None)
            canonical = json.dumps(
                candidate,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            actual_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if (
                record.get("sequence") != sequence
                or record.get("previous_record_sha256") != previous_hash
                or stored_hash != actual_hash
            ):
                raise AcquisitionLifecycleError("acquisition_journal_invalid")
            previous_hash = actual_hash
    started = next(
        (record for record in records if record.get("kind") == "session_started"),
        None,
    )
    if started is None or not started.get("session_id"):
        raise AcquisitionLifecycleError("acquisition_journal_invalid")

    recorder = PolarSessionRecorder(None)  # type: ignore[arg-type]
    recorder._session_id = str(started["session_id"])
    recorder._active = False
    anchors: list[ClockAnchor] = []
    anchor_fields = set(ClockAnchor.__dataclass_fields__)

    try:
        for record in records:
            kind = record.get("kind")
            if kind == "clock_anchor":
                anchors.append(
                    ClockAnchor(**{name: record[name] for name in anchor_fields})
                )
            elif kind == "phase_started":
                phase = str(record["phase"])
                if phase not in PHASE_NAMES:
                    continue
                disconnected = record.get("disconnected", recorder._disconnected)
                contact = record.get(
                    "sensor_contact_detected",
                    recorder._last_sensor_contact_detected,
                )
                if not isinstance(disconnected, bool) or (
                    contact is not None and not isinstance(contact, bool)
                ):
                    raise ValueError("invalid phase state")
                recorder._disconnected = disconnected
                recorder._last_sensor_contact_detected = contact
                if disconnected and recorder._disconnect_phases[phase] == 0:
                    recorder._disconnect_phases[phase] = 1
                if contact is False:
                    recorder._contact_loss_phases.add(phase)
                recorder._phase_durations[phase] = float(record["nominal_duration_s"])
                recorder._phase_bounds_monotonic_ns[phase] = [
                    int(record["monotonic_ns"]),
                    None,
                ]
            elif kind == "phase_state_snapshot":
                phase = str(record["phase"])
                disconnected = record.get("disconnected")
                contact = record.get("sensor_contact_detected")
                if (
                    phase not in PHASE_NAMES
                    or not isinstance(disconnected, bool)
                    or (contact is not None and not isinstance(contact, bool))
                ):
                    raise ValueError("invalid phase state snapshot")
                recorder._disconnected = disconnected
                recorder._last_sensor_contact_detected = contact
                if disconnected and recorder._disconnect_phases[phase] == 0:
                    recorder._disconnect_phases[phase] = 1
                if contact is False:
                    recorder._contact_loss_phases.add(phase)
            elif kind == "phase_finished":
                phase = str(record["phase"])
                bounds = recorder._phase_bounds_monotonic_ns.get(phase)
                if bounds is not None:
                    bounds[1] = int(record["monotonic_ns"])
                    observed_duration = record.get("observed_duration_s")
                    if observed_duration is not None:
                        recorder._phase_durations[phase] = float(observed_duration)
            elif kind == "malformed_packet":
                recorder._malformed_packet_count += 1
            elif kind == "bluetooth_disconnected":
                recorder._disconnect_count += 1
                recorder._disconnected = True
                phase_value = record.get("phase")
                if phase_value in PHASE_NAMES:
                    recorder._disconnect_phases[str(phase_value)] += 1
            elif kind == "sensor_contact_status":
                phase = str(record["phase"])
                contact = record.get("sensor_contact_detected")
                if contact is not None and not isinstance(contact, bool):
                    raise ValueError("invalid sensor contact status")
                recorder._last_sensor_contact_detected = contact
                if contact is False:
                    recorder._contact_loss_phases.add(phase)
            elif kind == "segment_started":
                recorder._disconnected = False
            elif kind == "rr_notification":
                phase = str(record["phase"])
                segment_id = str(record["segment_id"])
                ticks = tuple(int(value) for value in record["rr_ticks_1024"])
                notification_index = int(record["notification_index"])
                batch = NotificationRRBatch(
                    notification_index=notification_index,
                    received_monotonic_ns=int(record["received_monotonic_ns"]),
                    rr_ticks_1024=ticks,
                )
                packet = HeartRatePacket(
                    flags=int(record["flags"]),
                    heart_rate_bpm=int(record["heart_rate_bpm"]),
                    rr_values=tuple(
                        RRValue(value, value * 1000.0 / 1024.0) for value in ticks
                    ),
                    sensor_contact_supported=bool(
                        record["sensor_contact_supported"]
                    ),
                    sensor_contact_detected=record.get("sensor_contact_detected"),
                    energy_expended_kj=record.get("energy_expended_kj"),
                )
                recorder._notifications.append(
                    _CapturedNotification(
                        phase=phase,
                        segment_id=segment_id,
                        batch=batch,
                        packet=packet,
                    )
                )
                recorder._notification_index = max(
                    recorder._notification_index,
                    notification_index + 1,
                )
                if (
                    packet.sensor_contact_supported
                    and packet.sensor_contact_detected is False
                ):
                    recorder._contact_loss_phases.add(phase)
    except (KeyError, TypeError, ValueError) as exc:
        raise AcquisitionLifecycleError("acquisition_journal_invalid") from exc

    if recorder._notifications and not anchors:
        raise AcquisitionLifecycleError("acquisition_journal_invalid")
    recorder._clock._anchors = anchors
    recorder._clock._clock_epoch = max(
        (anchor.clock_epoch for anchor in anchors),
        default=0,
    )
    return recorder._build_result()


class PolarConnectionManager:
    """Own one BLE connection and keep an active recording alive across drops."""

    def __init__(
        self,
        backend: PolarBackend,
        *,
        reconnect_delays: tuple[float, ...] = (1.0, 2.0, 4.0),
        recorder_factory: Callable[..., PolarSessionRecorder] = PolarSessionRecorder,
    ) -> None:
        if not reconnect_delays or any(delay < 0 for delay in reconnect_delays):
            raise ValueError("invalid_reconnect_delays")
        self.backend = backend
        self._reconnect_delays = reconnect_delays
        self._recorder_factory = recorder_factory
        self._state = "disconnected"
        self._battery_level: int | None = None
        self._recorder: PolarSessionRecorder | None = None
        self._reconnect_attempts = 0
        self._last_error_code: str | None = None
        self._intentional_disconnect = False
        self._operation_lock = asyncio.Lock()
        self._reconnect_lock = asyncio.Lock()
        self._reconnect_task: asyncio.Task[None] | None = None
        self._preflight_ready = False
        self._last_rr_at_utc_ns: int | None = None
        self._last_rr_at_monotonic_ns: int | None = None
        self._sensor_contact_detected: bool | None = None
        self.backend.set_disconnect_handler(self._schedule_reconnect)

    @property
    def status(self) -> PolarConnectionStatus:
        raw_identifier = self.backend.connected_raw_identifier
        identifier_hash = (
            hashlib.sha256(raw_identifier.encode("utf-8")).hexdigest()
            if raw_identifier
            else None
        )
        return PolarConnectionStatus(
            state=self._state,
            backend_name=self.backend.backend_name,
            connected_device_name=self.backend.connected_device_name,
            device_identifier_sha256=identifier_hash,
            battery_level=self._battery_level,
            recording=self._recorder is not None,
            reconnect_attempts=self._reconnect_attempts,
            last_error_code=self._last_error_code,
            preflight_ready=self._preflight_ready,
            last_rr_at_utc_ns=self._last_rr_at_utc_ns,
            sensor_contact_detected=self._sensor_contact_detected,
        )

    def preflight_is_fresh(self, *, max_age_ns: int) -> bool:
        measured = self._last_rr_at_monotonic_ns
        if not self._preflight_ready or measured is None or max_age_ns < 0:
            return False
        age = time.monotonic_ns() - measured
        return 0 <= age <= max_age_ns

    async def scan(self, timeout_seconds: float = 5.0) -> tuple[DeviceCandidate, ...]:
        async with self._operation_lock:
            if self._recorder is not None:
                raise PolarBackendError("scan_not_allowed_while_recording")
            if self._state in {"connected", "connecting", "reconnecting"}:
                raise PolarBackendError("scan_not_allowed_while_connected")
            self._state = "scanning"
            self._last_error_code = None
            try:
                candidates = await self.backend.scan(timeout_seconds)
            except PolarBackendError as exc:
                self._state = "error"
                self._last_error_code = exc.code
                raise
            self._state = "disconnected"
            return candidates

    async def connect(self, device_token: str) -> PolarConnectionStatus:
        async with self._operation_lock:
            if self._recorder is not None:
                raise PolarBackendError("connect_not_allowed_while_recording")
            if self._state in {"connected", "connecting", "reconnecting"}:
                raise PolarBackendError("device_already_connected")
            self._state = "connecting"
            self._last_error_code = None
            try:
                await self.backend.connect(device_token)
                self._battery_level = await self.backend.read_battery_level()
            except asyncio.CancelledError:
                self._intentional_disconnect = True
                try:
                    await _finish_cleanup(
                        self.backend.disconnect,
                        suppress_errors=True,
                    )
                finally:
                    self._intentional_disconnect = False
                    self._state = (
                        "connected"
                        if self.backend.connected_raw_identifier is not None
                        else "disconnected"
                    )
                    self._battery_level = None
                    self._preflight_ready = False
                    self._last_rr_at_utc_ns = None
                    self._last_rr_at_monotonic_ns = None
                    self._sensor_contact_detected = None
                raise
            except PolarBackendError as exc:
                self._state = (
                    "connected"
                    if self.backend.connected_raw_identifier is not None
                    else "error"
                )
                self._battery_level = None
                self._preflight_ready = False
                self._last_rr_at_utc_ns = None
                self._last_rr_at_monotonic_ns = None
                self._sensor_contact_detected = None
                self._last_error_code = exc.code
                raise
            self._state = "connected"
            self._reconnect_attempts = 0
            self._preflight_ready = False
            self._last_rr_at_utc_ns = None
            self._last_rr_at_monotonic_ns = None
            self._sensor_contact_detected = None
            return self.status

    async def preflight(self, *, timeout_seconds: float = 8.0) -> PolarPreflightResult:
        async with self._operation_lock:
            if self._state != "connected":
                raise PolarBackendError("device_not_connected")
            if self._recorder is not None:
                raise PolarBackendError("preflight_not_allowed_while_recording")
            timeout = min(30.0, max(0.1, float(timeout_seconds)))
            received = asyncio.Event()
            packet_holder: list[HeartRatePacket] = []

            async def callback(payload: bytes) -> None:
                try:
                    packet = parse_heart_rate_measurement(payload)
                except HeartRatePacketError:
                    return
                packet_holder[:] = [packet]
                received.set()

            completed = False
            try:
                try:
                    await self.backend.start_notifications(callback)
                    await asyncio.wait_for(received.wait(), timeout=timeout)
                    completed = True
                finally:
                    await _finish_cleanup(
                        self.backend.stop_notifications,
                        suppress_errors=not completed,
                    )
            except TimeoutError as exc:
                self._preflight_ready = False
                self._last_error_code = "polar_preflight_timeout"
                raise PolarBackendError("polar_preflight_timeout") from exc

            packet = packet_holder[0]
            measured_at = time.time_ns()
            measured_monotonic = time.monotonic_ns()
            self._sensor_contact_detected = packet.sensor_contact_detected
            reason: str | None = None
            if not packet.rr_values:
                reason = "polar_preflight_no_rr"
            elif packet.sensor_contact_supported and packet.sensor_contact_detected is False:
                reason = "polar_preflight_contact_not_detected"
            ready = reason is None
            self._preflight_ready = ready
            self._last_rr_at_utc_ns = measured_at if packet.rr_values else None
            self._last_rr_at_monotonic_ns = measured_monotonic if packet.rr_values else None
            self._last_error_code = reason
            return PolarPreflightResult(
                ready=ready,
                heart_rate_bpm=packet.heart_rate_bpm,
                rr_count=len(packet.rr_values),
                sensor_contact_detected=packet.sensor_contact_detected,
                battery_level=self._battery_level,
                measured_at_utc_ns=measured_at,
                reason_code=reason,
            )

    async def disconnect(self) -> PolarConnectionStatus:
        await self._cancel_reconnect()
        async with self._operation_lock:
            if self._recorder is not None:
                raise PolarBackendError("disconnect_not_allowed_while_recording")
            self._intentional_disconnect = True
            try:
                await self.backend.disconnect()
            except BaseException as exc:
                self._preflight_ready = False
                self._last_rr_at_utc_ns = None
                self._last_rr_at_monotonic_ns = None
                self._sensor_contact_detected = None
                if isinstance(exc, PolarBackendError):
                    self._last_error_code = exc.code
                if self.backend.connected_raw_identifier is not None:
                    self._state = "connected"
                else:
                    self._state = "disconnected"
                    self._battery_level = None
                raise
            finally:
                self._intentional_disconnect = False
            self._state = "disconnected"
            self._battery_level = None
            self._preflight_ready = False
            self._last_rr_at_utc_ns = None
            self._last_rr_at_monotonic_ns = None
            self._sensor_contact_detected = None
            self._last_error_code = None
            return self.status

    async def start_recording(
        self,
        session_id: str,
        *,
        journal_path: Path | None = None,
    ) -> PolarSessionRecorder:
        async with self._operation_lock:
            if self._state != "connected":
                raise PolarBackendError("device_not_connected")
            if self._recorder is not None:
                raise AcquisitionLifecycleError("acquisition_already_started")
            if not self._preflight_ready:
                raise PolarBackendError("polar_preflight_required")
            recorder = self._recorder_factory(self.backend)
            await recorder.start(session_id, journal_path=journal_path)
            self._recorder = recorder
            return recorder

    async def stop_recording(self) -> PolarSessionResult:
        await self._cancel_reconnect()
        async with self._operation_lock:
            recorder = self._recorder
            if recorder is None:
                raise AcquisitionLifecycleError("acquisition_not_started")
            try:
                return await recorder.stop()
            finally:
                self._recorder = None

    async def shutdown(self) -> None:
        await self._cancel_reconnect()
        async with self._operation_lock:
            if self._recorder is not None:
                try:
                    await self._recorder.stop()
                except (AcquisitionLifecycleError, PolarBackendError):
                    pass
                self._recorder = None
            self._intentional_disconnect = True
            try:
                await self.backend.shutdown()
            finally:
                self._intentional_disconnect = False
                self._state = "disconnected"

    def _schedule_reconnect(self) -> None:
        if self._intentional_disconnect:
            return
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        task = asyncio.get_running_loop().create_task(self._handle_disconnect())
        self._reconnect_task = task

        def completed(done: asyncio.Task[None]) -> None:
            if self._reconnect_task is done:
                self._reconnect_task = None
            if not done.cancelled():
                # Retrieve the exception so a backend callback never leaks an
                # unobserved task failure into the event loop.
                done.exception()

        task.add_done_callback(completed)

    async def _cancel_reconnect(self) -> None:
        task = self._reconnect_task
        if task is None or task is asyncio.current_task():
            return
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._reconnect_task = None
        if self._state == "reconnecting":
            self._state = "lost"

    async def _handle_disconnect(self) -> None:
        if self._intentional_disconnect:
            return
        async with self._reconnect_lock:
            recorder = self._recorder
            self._state = "reconnecting" if recorder is not None else "disconnected"
            if recorder is None:
                return
            recorder.note_disconnect()
            try:
                for attempt, delay in enumerate(self._reconnect_delays, start=1):
                    self._reconnect_attempts = attempt
                    if delay:
                        await asyncio.sleep(delay)
                    if recorder is not self._recorder:
                        self._state = "lost"
                        return
                    try:
                        async with self._operation_lock:
                            if recorder is not self._recorder:
                                self._state = "lost"
                                return
                            await self.backend.reconnect_selected()
                            await recorder.restart_after_reconnect()
                            self._battery_level = await self.backend.read_battery_level()
                    except (PolarBackendError, AcquisitionLifecycleError) as exc:
                        self._last_error_code = exc.code
                        continue
                    self._state = "connected"
                    self._last_error_code = None
                    return
                self._intentional_disconnect = True
                try:
                    await _finish_cleanup(
                        self.backend.disconnect,
                        suppress_errors=True,
                    )
                finally:
                    self._intentional_disconnect = False
                self._state = "lost"
            except asyncio.CancelledError:
                self._state = "lost"
                raise


__all__ = [
    "AcquisitionLifecycleError",
    "PHASE_NAMES",
    "PolarConnectionManager",
    "PolarConnectionStatus",
    "PolarPreflightResult",
    "PolarSessionRecorder",
    "PolarSessionResult",
    "recover_polar_session_journal",
]
