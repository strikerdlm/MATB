from __future__ import annotations

import asyncio
import json
import os
import stat

import pytest

from matb_integration.physiology.acquisition import (
    PolarConnectionManager,
    PolarSessionRecorder,
    recover_polar_session_journal,
)
from matb_integration.physiology.backend import PolarBackendError, SimulatedPolarBackend


def test_recorder_preserves_every_native_rr_and_analyzes_each_phase_separately() -> None:
    async def scenario():
        counter = 0

        def monotonic_ns() -> int:
            nonlocal counter
            counter += 1_000_000
            return counter

        backend = SimulatedPolarBackend()
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        recorder = PolarSessionRecorder(
            backend,
            monotonic_ns=monotonic_ns,
            wall_ns=lambda: 1_700_000_000_000_000_000 + counter,
        )
        await recorder.start("session-1")
        recorder.begin_phase("baseline", nominal_duration_s=300.0)
        await backend.emit_rr_ticks((1024, 512), heart_rate_bpm=70)
        recorder.end_phase("baseline")
        recorder.begin_phase("task", nominal_duration_s=300.0)
        await backend.emit_rr_ticks((768,), heart_rate_bpm=80)
        recorder.end_phase("task")
        recorder.begin_phase("recovery", nominal_duration_s=300.0)
        await backend.emit_rr_ticks((1024,), heart_rate_bpm=65)
        recorder.end_phase("recovery")

        return await recorder.stop()

    result = asyncio.run(scenario())

    assert [row["rr_ticks_1024"] for row in result.rr_records] == [1024, 512, 768, 1024]
    assert [row["phase"] for row in result.rr_records] == [
        "baseline",
        "baseline",
        "task",
        "recovery",
    ]
    assert result.rr_records[0]["rr_ms"] == 1000.0
    assert result.rr_records[1]["rr_ms"] == 500.0
    assert result.rr_records[0]["timestamp_source"] == "host_rr_robust_offset_v1"
    assert set(result.phase_results) == {"baseline", "task", "recovery"}
    assert result.phase_results["baseline"]["raw_rr_count"] == 2
    assert result.phase_results["task"]["frequency_domain"]["status"] == "not_computable"
    assert len(result.clock_anchors) >= 7


def test_recorder_marks_malformed_packets_without_losing_the_session() -> None:
    async def scenario():
        backend = SimulatedPolarBackend()
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        recorder = PolarSessionRecorder(backend)
        await recorder.start("session-1")
        recorder.begin_phase("baseline", nominal_duration_s=300.0)
        assert backend._callback is not None
        await backend._callback(bytes([0x10]))
        await backend.emit_rr_ticks((1024,))
        recorder.end_phase("baseline")
        return await recorder.stop()

    result = asyncio.run(scenario())

    assert result.malformed_packet_count == 1
    assert len(result.rr_records) == 1


def test_rr_notifications_are_fsynced_to_a_recoverable_journal(tmp_path) -> None:
    async def scenario():
        backend = SimulatedPolarBackend()
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        recorder = PolarSessionRecorder(backend)
        journal = tmp_path / "polar-rr-journal.jsonl"
        await recorder.start("session-journal", journal_path=journal)
        recorder.begin_phase("baseline", nominal_duration_s=300.0)
        await backend.emit_rr_ticks((1024, 512), heart_rate_bpm=72)

        recovered_while_active = recover_polar_session_journal(journal)

        recorder.end_phase("baseline")
        await recorder.stop()
        return journal, recovered_while_active

    journal, recovered = asyncio.run(scenario())

    assert journal.is_file()
    if os.name != "nt":
        assert stat.S_IMODE(journal.stat().st_mode) == 0o600
    assert [row["rr_ticks_1024"] for row in recovered.rr_records] == [1024, 512]
    assert [row["phase"] for row in recovered.rr_records] == ["baseline", "baseline"]
    assert recovered.phase_results["baseline"]["raw_rr_count"] == 2


def test_no_rr_contact_loss_is_fsynced_and_recovered(tmp_path) -> None:
    async def scenario():
        backend = SimulatedPolarBackend()
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        journal = tmp_path / "polar-contact-journal.jsonl"
        recorder = PolarSessionRecorder(backend)
        await recorder.start("session-contact", journal_path=journal)
        recorder.begin_phase("baseline", nominal_duration_s=300.0)
        assert backend._callback is not None
        # HRS flags: sensor contact supported, contact not detected, no RR field.
        await backend._callback(bytes((0x04, 70)))
        recovered = recover_polar_session_journal(journal)
        recorder.end_phase("baseline")
        await recorder.stop()
        return journal, recovered

    journal, recovered = asyncio.run(scenario())

    assert '"kind":"sensor_contact_status"' in journal.read_text(encoding="utf-8")
    assert recovered.contact_loss_detected is True
    frequency = recovered.phase_results["baseline"]["frequency_domain"]
    assert "sensor_contact_loss" in frequency["reason_codes"]


def test_disconnect_and_contact_loss_carry_into_a_phase_started_during_the_gap(
    tmp_path,
) -> None:
    async def scenario():
        backend = SimulatedPolarBackend()
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        journal = tmp_path / "phase-overlap-journal.jsonl"
        recorder = PolarSessionRecorder(backend)
        await recorder.start("session-phase-overlap", journal_path=journal)

        # Both adverse states begin between named phases and remain active when
        # the task window opens.
        assert backend._callback is not None
        await backend._callback(bytes((0x04, 70)))
        recorder.note_disconnect()
        recorder.begin_phase("task", nominal_duration_s=300.0)
        recorder.end_phase("task")
        recorder.note_reconnected()

        live = await recorder.stop()
        recovered = recover_polar_session_journal(journal)
        return journal, live, recovered

    journal, live, recovered = asyncio.run(scenario())

    assert '"kind":"phase_state_snapshot"' in journal.read_text(encoding="utf-8")
    for result in (live, recovered):
        reasons = result.phase_results["task"]["frequency_domain"]["reason_codes"]
        assert "bluetooth_disconnect" in reasons
        assert "sensor_contact_loss" in reasons


def test_new_journal_fsyncs_its_directory_entry(tmp_path, monkeypatch) -> None:
    synced: list[object] = []
    monkeypatch.setattr(
        "matb_integration.physiology.acquisition._fsync_directory",
        lambda path: synced.append(path),
    )

    async def scenario() -> None:
        backend = SimulatedPolarBackend()
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        journal = tmp_path / "capture" / "polar-rr-journal.jsonl"
        recorder = PolarSessionRecorder(backend)
        await recorder.start("session-directory", journal_path=journal)
        await recorder.stop()

    asyncio.run(scenario())

    assert tmp_path in synced
    assert tmp_path / "capture" in synced


def test_cancelled_recorder_start_closes_journal_and_stops_notifications(
    tmp_path,
) -> None:
    class BlockingStartBackend(SimulatedPolarBackend):
        def __init__(self) -> None:
            super().__init__()
            self.start_entered = asyncio.Event()
            self.release_start = asyncio.Event()
            self.stop_count = 0

        async def start_notifications(self, callback) -> None:
            self._callback = callback
            self.start_entered.set()
            await self.release_start.wait()

        async def stop_notifications(self) -> None:
            self.stop_count += 1
            self._callback = None

    async def scenario():
        backend = BlockingStartBackend()
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        recorder = PolarSessionRecorder(backend)
        journal = tmp_path / "cancelled-start.jsonl"
        start_task = asyncio.create_task(
            recorder.start("session-cancelled-start", journal_path=journal)
        )
        await backend.start_entered.wait()
        start_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await start_task
        return backend, recorder, journal

    backend, recorder, journal = asyncio.run(scenario())

    assert backend.stop_count == 1
    assert backend._callback is None
    assert recorder._active is False
    assert recorder._journal_file is None
    assert journal.read_text(encoding="utf-8").endswith("\n")


def test_cancelled_preflight_stops_notifications_and_releases_manager_lock() -> None:
    class BlockingPreflightBackend(SimulatedPolarBackend):
        def __init__(self) -> None:
            super().__init__()
            self.start_entered = asyncio.Event()
            self.release_start = asyncio.Event()
            self.stop_count = 0

        async def start_notifications(self, callback) -> None:
            self._callback = callback
            self.start_entered.set()
            await self.release_start.wait()

        async def stop_notifications(self) -> None:
            self.stop_count += 1
            self._callback = None

    async def scenario():
        backend = BlockingPreflightBackend()
        manager = PolarConnectionManager(backend)
        candidate = (await manager.scan(0.01))[0]
        await manager.connect(candidate.device_token)
        preflight_task = asyncio.create_task(manager.preflight(timeout_seconds=1.0))
        await backend.start_entered.wait()
        preflight_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await preflight_task
        stop_count_after_cancel = backend.stop_count
        status = await asyncio.wait_for(manager.disconnect(), timeout=0.2)
        return backend, status, stop_count_after_cancel

    backend, status, stop_count_after_cancel = asyncio.run(scenario())

    assert stop_count_after_cancel == 1
    assert backend.stop_count == 2
    assert backend._callback is None
    assert status.state == "disconnected"


def test_timed_out_preflight_always_stops_notifications() -> None:
    class CountingBackend(SimulatedPolarBackend):
        def __init__(self) -> None:
            super().__init__()
            self.stop_count = 0

        async def stop_notifications(self) -> None:
            self.stop_count += 1
            await super().stop_notifications()

    async def scenario():
        backend = CountingBackend()
        manager = PolarConnectionManager(backend)
        candidate = (await manager.scan(0.01))[0]
        await manager.connect(candidate.device_token)
        with pytest.raises(PolarBackendError, match="polar_preflight_timeout"):
            await manager.preflight(timeout_seconds=0.1)
        return backend, manager

    backend, manager = asyncio.run(scenario())

    assert backend.stop_count == 1
    assert backend._callback is None
    assert manager.status.preflight_ready is False


def test_cancelling_preflight_during_stop_finishes_unsubscribe() -> None:
    class BlockingStopBackend(SimulatedPolarBackend):
        def __init__(self) -> None:
            super().__init__()
            self.stop_entered = asyncio.Event()
            self.stop_count = 0

        async def stop_notifications(self) -> None:
            self.stop_count += 1
            if self.stop_count == 1:
                self.stop_entered.set()
                await asyncio.Event().wait()
            await super().stop_notifications()

    async def scenario():
        backend = BlockingStopBackend()
        manager = PolarConnectionManager(backend)
        candidate = (await manager.scan(0.01))[0]
        await manager.connect(candidate.device_token)
        preflight_task = asyncio.create_task(manager.preflight(timeout_seconds=1.0))
        await asyncio.sleep(0)
        await backend.emit_rr_ticks((1024,))
        await backend.stop_entered.wait()
        preflight_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await preflight_task
        return backend, manager

    backend, manager = asyncio.run(scenario())

    assert backend.stop_count == 2
    assert backend._callback is None
    assert manager.status.state == "connected"


@pytest.mark.parametrize("cancel_stage", ["connect", "battery"])
def test_cancelled_connect_restores_disconnected_state_and_releases_backend(
    cancel_stage: str,
) -> None:
    class BlockingConnectBackend(SimulatedPolarBackend):
        def __init__(self) -> None:
            super().__init__()
            self.stage_entered = asyncio.Event()
            self.disconnect_count = 0

        async def connect(self, device_token: str) -> None:
            await super().connect(device_token)
            if cancel_stage == "connect":
                self.stage_entered.set()
                await asyncio.Event().wait()

        async def read_battery_level(self) -> int | None:
            if cancel_stage == "battery":
                self.stage_entered.set()
                await asyncio.Event().wait()
            return await super().read_battery_level()

        async def disconnect(self) -> None:
            self.disconnect_count += 1
            await super().disconnect()

    async def scenario():
        backend = BlockingConnectBackend()
        manager = PolarConnectionManager(backend)
        candidate = (await manager.scan(0.01))[0]
        connect_task = asyncio.create_task(manager.connect(candidate.device_token))
        await backend.stage_entered.wait()
        connect_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await connect_task
        return backend, manager

    backend, manager = asyncio.run(scenario())

    assert backend.disconnect_count == 1
    assert backend._connected is False
    assert manager.status.state == "disconnected"


def test_failed_connect_reports_connected_until_retained_backend_is_released() -> None:
    class PartiallyConnectedBackend(SimulatedPolarBackend):
        async def connect(self, device_token: str) -> None:
            await super().connect(device_token)
            raise PolarBackendError("device_connection_failed")

    async def scenario():
        backend = PartiallyConnectedBackend()
        manager = PolarConnectionManager(backend)
        candidate = (await manager.scan(0.01))[0]
        with pytest.raises(PolarBackendError, match="device_connection_failed"):
            await manager.connect(candidate.device_token)
        assert manager.status.state == "connected"
        assert manager.status.device_identifier_sha256 is not None
        await manager.disconnect()
        return backend, manager

    backend, manager = asyncio.run(scenario())

    assert backend._connected is False
    assert manager.status.state == "disconnected"


def test_journal_rejects_corrupt_middle_record_but_tolerates_truncated_final_append(
    tmp_path,
) -> None:
    async def record() -> object:
        backend = SimulatedPolarBackend()
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        journal = tmp_path / "integrity.jsonl"
        recorder = PolarSessionRecorder(backend)
        await recorder.start("session-integrity", journal_path=journal)
        recorder.begin_phase("baseline", nominal_duration_s=300.0)
        await backend.emit_rr_ticks((1024,))
        recorder.end_phase("baseline")
        await recorder.stop()
        return journal

    journal = asyncio.run(record())
    original = journal.read_text(encoding="utf-8")
    journal.write_text(original + '{"truncated":', encoding="utf-8")
    recovered = recover_polar_session_journal(journal)
    assert recovered.phase_results["baseline"]["raw_rr_count"] == 1

    lines = original.splitlines()
    lines[2] = "{malformed}"
    journal.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(Exception, match="acquisition_journal_invalid"):
        recover_polar_session_journal(journal)


def test_journal_rejects_a_fully_hashless_v1_stream(tmp_path) -> None:
    async def record() -> object:
        backend = SimulatedPolarBackend()
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        journal = tmp_path / "hashless.jsonl"
        recorder = PolarSessionRecorder(backend)
        await recorder.start("session-hashless", journal_path=journal)
        await recorder.stop()
        return journal

    journal = asyncio.run(record())
    records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    for record in records:
        record.pop("sequence")
        record.pop("previous_record_sha256")
        record.pop("record_sha256")
    journal.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="acquisition_journal_invalid"):
        recover_polar_session_journal(journal)


def test_phase_started_alone_recovers_cross_phase_disconnect_and_contact_state(
    tmp_path,
) -> None:
    async def record() -> object:
        backend = SimulatedPolarBackend()
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        journal = tmp_path / "phase-start-crash.jsonl"
        recorder = PolarSessionRecorder(backend)
        await recorder.start("session-phase-start-crash", journal_path=journal)
        assert backend._callback is not None
        await backend._callback(bytes((0x04, 70)))
        recorder.note_disconnect()
        recorder.begin_phase("task", nominal_duration_s=300.0)
        return journal

    journal = asyncio.run(record())
    lines = journal.read_text(encoding="utf-8").splitlines()
    phase_started_index = next(
        index
        for index, line in enumerate(lines)
        if json.loads(line).get("kind") == "phase_started"
    )
    journal.write_text(
        "\n".join(lines[: phase_started_index + 1]) + "\n",
        encoding="utf-8",
    )

    recovered = recover_polar_session_journal(journal)
    reasons = recovered.phase_results["task"]["frequency_domain"]["reason_codes"]
    assert "bluetooth_disconnect" in reasons
    assert "sensor_contact_loss" in reasons


def test_interrupted_recording_emits_explicit_never_started_phase_results() -> None:
    async def scenario():
        backend = SimulatedPolarBackend()
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        recorder = PolarSessionRecorder(backend)
        await recorder.start("session-partial")
        recorder.begin_phase("baseline", nominal_duration_s=300.0)
        recorder.end_phase("baseline")
        return await recorder.stop()

    result = asyncio.run(scenario())

    assert set(result.phase_results) == {"baseline", "task", "recovery"}
    assert result.phase_results["baseline"]["phase_started"] is True
    assert result.phase_results["task"]["phase_started"] is False
    assert result.phase_results["task"]["time_domain"]["reason_code"] == "phase_not_started"


def test_preflight_freshness_uses_monotonic_not_adjustable_wall_clock(monkeypatch) -> None:
    manager = PolarConnectionManager(SimulatedPolarBackend())
    manager._preflight_ready = True
    manager._last_rr_at_monotonic_ns = 1_000
    manager._last_rr_at_utc_ns = 9_000_000_000_000
    monkeypatch.setattr(
        "matb_integration.physiology.acquisition.time.monotonic_ns",
        lambda: 1_100,
    )
    monkeypatch.setattr(
        "matb_integration.physiology.acquisition.time.time_ns",
        lambda: -9_000_000_000_000,
    )

    assert manager.preflight_is_fresh(max_age_ns=200) is True
    assert manager.preflight_is_fresh(max_age_ns=50) is False


def test_task_phase_can_use_child_boundary_and_observed_wall_duration(tmp_path) -> None:
    async def scenario():
        now_ns = 10_000_000_000

        def monotonic_ns() -> int:
            return now_ns

        backend = SimulatedPolarBackend()
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        recorder = PolarSessionRecorder(
            backend,
            monotonic_ns=monotonic_ns,
            wall_ns=lambda: 1_700_000_000_000_000_000 + now_ns,
        )
        journal = tmp_path / "task-boundary.jsonl"
        await recorder.start("session-task-boundary", journal_path=journal)
        recorder.begin_phase("task", nominal_duration_s=900.0)
        start_ns = int(recorder._phase_bounds_monotonic_ns["task"][0])
        now_ns = start_ns + 975_000_000_000
        recorder.end_phase(
            "task",
            boundary_monotonic_ns=now_ns,
            use_observed_duration=True,
        )
        result = await recorder.stop()
        recovered = recover_polar_session_journal(journal)
        return result, recovered

    result, recovered = asyncio.run(scenario())

    assert result.phase_results["task"]["nominal_duration_s"] == 975.0
    assert recovered.phase_results["task"]["nominal_duration_s"] == 975.0


def test_multi_rr_notification_is_delimited_by_estimated_beat_time() -> None:
    async def scenario():
        monotonic_values = iter(
            [
                0,
                0,  # acquisition anchor
                0,
                0,  # baseline start
                10_000_000_000,
                10_000_000_000,  # baseline finish
                10_000_000_000,
                10_000_000_000,  # task start
                10_500_000_000,  # notification receipt
                12_000_000_000,
                12_000_000_000,  # task finish
                12_000_000_000,
                12_000_000_000,  # acquisition finish
            ]
        )
        backend = SimulatedPolarBackend()
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        recorder = PolarSessionRecorder(
            backend,
            monotonic_ns=lambda: next(monotonic_values),
            wall_ns=lambda: 1_700_000_000_000_000_000,
        )
        await recorder.start("session-boundary")
        recorder.begin_phase("baseline", nominal_duration_s=10.0)
        recorder.end_phase("baseline")
        recorder.begin_phase("task", nominal_duration_s=2.0)
        await backend.emit_rr_ticks((1024, 1024))
        recorder.end_phase("task")
        return await recorder.stop()

    result = asyncio.run(scenario())

    assert [row["phase"] for row in result.rr_records] == ["baseline", "task"]
    assert result.phase_results["baseline"]["raw_rr_count"] == 1
    assert result.phase_results["task"]["raw_rr_count"] == 1


def test_connection_manager_retries_three_times_and_starts_a_new_segment() -> None:
    class FlakyBackend(SimulatedPolarBackend):
        def __init__(self) -> None:
            super().__init__()
            self.reconnect_attempts = 0

        async def reconnect_selected(self) -> None:
            self.reconnect_attempts += 1
            if self.reconnect_attempts < 3:
                raise PolarBackendError("device_reconnect_failed")
            self._connected = True

        async def drop_connection(self) -> None:
            self._connected = False
            self._callback = None
            callback = self._disconnect_handler
            assert callback is not None
            result = callback()
            if result is not None:
                await result

    async def scenario():
        backend = FlakyBackend()
        manager = PolarConnectionManager(backend, reconnect_delays=(0.0, 0.0, 0.0))
        candidate = (await manager.scan(0.01))[0]
        await manager.connect(candidate.device_token)
        preflight = asyncio.create_task(manager.preflight(timeout_seconds=1.0))
        await asyncio.sleep(0)
        await backend.emit_rr_ticks((1024,))
        await preflight
        recorder = await manager.start_recording("session-1")
        recorder.begin_phase("task", nominal_duration_s=300.0)
        await backend.emit_rr_ticks((1024,))
        await backend.drop_connection()
        await asyncio.sleep(0)
        for _ in range(20):
            if manager.status.state == "connected" and backend.reconnect_attempts == 3:
                break
            await asyncio.sleep(0)
        await backend.emit_rr_ticks((1024,))
        recorder.end_phase("task")
        result = await manager.stop_recording()
        return manager, backend, result

    manager, backend, result = asyncio.run(scenario())

    assert backend.reconnect_attempts == 3
    assert manager.status.state == "connected"
    assert result.disconnect_count == 1
    assert len({row["segment_id"] for row in result.rr_records}) == 2
    assert result.phase_results["task"]["frequency_domain"]["reason_codes"] == [
        "beat_coverage_below_95pct",
        "bluetooth_disconnect",
    ]


def test_failed_notification_restart_keeps_recorder_disconnected() -> None:
    class FailingRestartBackend(SimulatedPolarBackend):
        def __init__(self) -> None:
            super().__init__()
            self.fail_restart = False

        async def start_notifications(self, callback) -> None:
            if self.fail_restart:
                raise PolarBackendError("notification_start_failed")
            await super().start_notifications(callback)

    async def scenario():
        backend = FailingRestartBackend()
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        recorder = PolarSessionRecorder(backend)
        await recorder.start("session-failed-subscription")
        recorder.note_disconnect()
        backend.fail_restart = True
        with pytest.raises(PolarBackendError, match="notification_start_failed"):
            await recorder.restart_after_reconnect()
        recorder.begin_phase("task", nominal_duration_s=300.0)
        recorder.end_phase("task")
        return await recorder.stop()

    result = asyncio.run(scenario())

    reasons = result.phase_results["task"]["frequency_domain"]["reason_codes"]
    assert "bluetooth_disconnect" in reasons


def test_connection_preflight_requires_a_valid_rr_notification() -> None:
    async def scenario():
        backend = SimulatedPolarBackend()
        manager = PolarConnectionManager(backend)
        candidate = (await manager.scan(0.01))[0]
        await manager.connect(candidate.device_token)
        pending = asyncio.create_task(manager.preflight(timeout_seconds=1.0))
        await asyncio.sleep(0)
        await backend.emit_rr_ticks((1024,), heart_rate_bpm=66)
        result = await pending
        return manager, result

    manager, result = asyncio.run(scenario())

    assert result.ready is True
    assert result.heart_rate_bpm == 66
    assert result.rr_count == 1
    assert manager.status.preflight_ready is True
    assert manager.status.last_rr_at_utc_ns is not None


def test_connection_manager_rejects_duplicate_connect() -> None:
    async def scenario():
        backend = SimulatedPolarBackend()
        manager = PolarConnectionManager(backend)
        candidate = (await manager.scan(0.01))[0]
        await manager.connect(candidate.device_token)
        with pytest.raises(PolarBackendError, match="device_already_connected"):
            await manager.connect(candidate.device_token)

    asyncio.run(scenario())


def test_operator_disconnect_failure_keeps_manager_connected_for_retry() -> None:
    class FailOnceDisconnectBackend(SimulatedPolarBackend):
        def __init__(self) -> None:
            super().__init__()
            self.disconnect_count = 0

        async def disconnect(self) -> None:
            self.disconnect_count += 1
            if self.disconnect_count == 1:
                raise PolarBackendError("device_disconnect_failed")
            await super().disconnect()

    async def scenario():
        backend = FailOnceDisconnectBackend()
        manager = PolarConnectionManager(backend)
        candidate = (await manager.scan(0.01))[0]
        await manager.connect(candidate.device_token)
        with pytest.raises(PolarBackendError, match="device_disconnect_failed"):
            await manager.disconnect()
        state_after_failure = manager.status.state
        final = await manager.disconnect()
        return backend, state_after_failure, final

    backend, state_after_failure, final = asyncio.run(scenario())

    assert state_after_failure == "connected"
    assert backend.disconnect_count == 2
    assert final.state == "disconnected"


def test_stop_recording_cancels_an_inflight_reconnect() -> None:
    class BlockingReconnectBackend(SimulatedPolarBackend):
        def __init__(self) -> None:
            super().__init__()
            self.reconnect_started = asyncio.Event()
            self.allow_reconnect = asyncio.Event()

        async def reconnect_selected(self) -> None:
            self.reconnect_started.set()
            await self.allow_reconnect.wait()
            await super().reconnect_selected()

        async def drop_connection(self) -> None:
            self._connected = False
            self._callback = None
            callback = self._disconnect_handler
            assert callback is not None
            pending = callback()
            if pending is not None:
                asyncio.create_task(pending)

    async def scenario():
        backend = BlockingReconnectBackend()
        manager = PolarConnectionManager(backend, reconnect_delays=(0.0,))
        candidate = (await manager.scan(0.01))[0]
        await manager.connect(candidate.device_token)
        preflight = asyncio.create_task(manager.preflight(timeout_seconds=1.0))
        await asyncio.sleep(0)
        await backend.emit_rr_ticks((1024,))
        await preflight
        recorder = await manager.start_recording("session-race")
        recorder.begin_phase("task", nominal_duration_s=300.0)
        await backend.emit_rr_ticks((1024,))
        await backend.drop_connection()
        await backend.reconnect_started.wait()
        recorder.end_phase("task")

        result = await asyncio.wait_for(manager.stop_recording(), timeout=0.2)
        backend.allow_reconnect.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        return manager, backend, result

    manager, backend, result = asyncio.run(scenario())

    assert len(result.rr_records) == 1
    assert manager.status.recording is False
    assert manager.status.state in {"disconnected", "lost"}
    assert backend._callback is None
