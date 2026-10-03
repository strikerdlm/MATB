from __future__ import annotations

import asyncio
from datetime import date

import pyarrow.parquet as pq
import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from tests.study_fixtures import h10_arguments
from app.models import Participant
from app.physiology_models import PolarCaptureRecord  # noqa: F401
from app.physiology_runtime import PolarCaptureManager, PolarRuntimeError
from matb_integration.physiology.artifacts import ParquetCaptureWriter
from matb_integration.physiology.transport import SimulatedPolarTransport


def _engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Participant(id="P01", enrollment_date=date(2026, 9, 3)))
        db.commit()
    return engine


def test_all_h10_acc_rate_and_range_combinations_are_exact() -> None:
    async def exercise() -> None:
        transport = SimulatedPolarTransport()
        await transport.connect(transport.device, lambda: None)
        for rate in (25, 50, 100, 200):
            for range_g in (2, 4, 8):
                await transport.start_acc(rate, 16, range_g, lambda packet: None)
        await transport.disconnect()

    asyncio.run(exercise())


def test_simulated_simultaneous_capture_finalizes_loss_visible_artifacts(tmp_path) -> None:
    async def exercise() -> None:
        transport = SimulatedPolarTransport()
        manager = PolarCaptureManager(engine=_engine(), artifact_root=tmp_path, transport=transport)
        await manager.startup()
        token, _candidate = (await manager.scan(0.25))[0]
        capabilities = await manager.connect(token)
        assert capabilities.acc_sample_rates_hz == (25, 50, 100, 200)
        capture, lease = manager.create_capture(**h10_arguments(manager.engine,
            participant_id="P01", session_kind="generic", session_id="test-session",
            settings={"ecg_sample_rate_hz": 130, "ecg_resolution_bits": 14,
                      "acc_sample_rate_hz": 50, "acc_resolution_bits": 16, "acc_range_g": 2},
        ))
        await manager.start_capture(capture.capture_id, lease)
        transport.emit_hr(bytes.fromhex("16 3c 00 04"))
        transport.emit_ecg(10_000_000_000, (-100, 0, 100))
        transport.emit_acc(10_000_000_000, ((0, 0, 1000), (10, -10, 999)))
        await asyncio.sleep(0.05)
        await manager.add_marker(capture.capture_id, lease, "LOW", {"block": 1})
        final = await manager.stop_capture(capture.capture_id, lease)
        assert final.lifecycle == "complete"
        assert final.artifact_state == "finalized"
        row, manifest, partials = manager.inventory(capture.capture_id, lease)
        assert not partials and manifest is not None
        assert manifest.stream_counters["rr_intervals"] == 1
        assert "ecg_epoch_0_to_monotonic" in manifest.clock_model["pmd_epoch_offsets_ns"]
        assert "ecg_epoch_0_to_utc" in manifest.clock_model["pmd_epoch_offsets_ns"]
        assert pq.read_table(tmp_path / capture.capture_id / "rr.parquet").num_rows == 1
        assert pq.read_table(tmp_path / capture.capture_id / "ecg.parquet").num_rows == 3
        assert pq.read_table(tmp_path / capture.capture_id / "acc.parquet").num_rows == 2
        bundle = manager.bundle(capture.capture_id, lease)
        assert bundle.is_file() and row.manifest_sha256
        await manager.shutdown()

    asyncio.run(exercise())


def test_nonconnectable_advertisement_is_rejected_before_gatt(tmp_path) -> None:
    async def exercise() -> None:
        manager = PolarCaptureManager(
            engine=_engine(), artifact_root=tmp_path,
            transport=SimulatedPolarTransport(connectable=False),
        )
        await manager.startup()
        token, _candidate = (await manager.scan(0.25))[0]
        try:
            await manager.connect(token)
        except Exception as exc:
            assert getattr(exc, "code", None) == "device_not_connectable"
        else:
            raise AssertionError("non-connectable device was accepted")

    asyncio.run(exercise())


def test_idle_disconnected_strap_can_be_replaced_without_restarting_backend(tmp_path):
    async def exercise():
        transport = SimulatedPolarTransport()
        manager = PolarCaptureManager(engine=_engine(), artifact_root=tmp_path, transport=transport)
        token, _ = (await manager.scan(0.25))[0]
        await manager.connect(token)
        transport.trigger_disconnect()
        assert manager.connection() == (None, None)
        token, _ = (await manager.scan(0.25))[0]
        await manager.connect(token)
        assert manager.connection()[0] == "Simulated Polar H10"
        await manager.shutdown()
    asyncio.run(exercise())


def test_connection_timeout_releases_transport_for_a_fresh_scan(tmp_path):
    class TimeoutOnce(SimulatedPolarTransport):
        fail = True

        async def capabilities(self):
            if self.fail:
                self.fail = False
                raise TimeoutError()
            return await super().capabilities()

    async def exercise():
        transport = TimeoutOnce()
        manager = PolarCaptureManager(engine=_engine(), artifact_root=tmp_path, transport=transport)
        token, _ = (await manager.scan(0.25))[0]
        with pytest.raises(PolarRuntimeError, match="polar_connection_timeout"):
            await manager.connect(token)
        assert not transport.connected
        token, _ = (await manager.scan(0.25))[0]
        await manager.connect(token)
        assert manager.connection()[0] is not None
        await manager.shutdown()
    asyncio.run(exercise())


def test_queue_pressure_and_disconnect_are_never_silent(tmp_path) -> None:
    async def exercise() -> None:
        transport = SimulatedPolarTransport()
        manager = PolarCaptureManager(engine=_engine(), artifact_root=tmp_path, transport=transport)
        manager.QUEUE_PACKETS = 1
        await manager.startup()
        token, _candidate = (await manager.scan(0.25))[0]
        await manager.connect(token)
        capture, lease = manager.create_capture(**h10_arguments(manager.engine,
            participant_id="P01", session_kind="generic", session_id="pressure",
            settings={"ecg_sample_rate_hz": 130, "ecg_resolution_bits": 14,
                      "acc_sample_rate_hz": 50, "acc_resolution_bits": 16, "acc_range_g": 2},
        ))
        await manager.start_capture(capture.capture_id, lease)
        for index in range(40):
            transport.emit_ecg(10_000_000_000 + index * 10_000_000, (index,))
        transport.trigger_disconnect()
        await asyncio.sleep(0.05)
        assert manager.connection() == (None, None)
        with pytest.raises(PolarRuntimeError, match="capture_active"):
            await manager.scan(0.25)
        with pytest.raises(PolarRuntimeError, match="capture_active"):
            await manager.connect("another-strap-token")
        final = await manager.stop_capture(capture.capture_id, lease)
        assert final.artifact_state == "incomplete"
        assert final.connection_epoch == 1
        assert final.gap_count > 0
        assert "unexpected_disconnect" in final.incomplete_reasons
        assert "ecg_queue_overflow" in final.incomplete_reasons
        await manager.shutdown()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "delay_consumer", [False, True], ids=["normal", "delayed-pump"]
)
def test_sensor_timestamp_discontinuity_emits_gap_event(
    tmp_path, monkeypatch, delay_consumer
) -> None:
    async def exercise() -> None:
        transport = SimulatedPolarTransport()
        manager = PolarCaptureManager(
            engine=_engine(), artifact_root=tmp_path, transport=transport
        )
        release_consumer = asyncio.Event()
        original_consume = manager._consume

        async def gated_consume(stream, context):
            if stream == "ecg":
                await release_consumer.wait()
            await original_consume(stream, context)

        if delay_consumer:
            monkeypatch.setattr(manager, "_consume", gated_consume)
        await manager.startup()
        try:
            token, _candidate = (await manager.scan(0.25))[0]
            await manager.connect(token)
            capture, lease = manager.create_capture(
                **h10_arguments(
                    manager.engine,
                    participant_id="P01",
                    session_kind="generic",
                    session_id="timestamp-gap",
                    settings={
                        "ecg_sample_rate_hz": 130,
                        "ecg_resolution_bits": 14,
                        "acc_sample_rate_hz": 50,
                        "acc_resolution_bits": 16,
                        "acc_range_g": 2,
                    },
                )
            )
            await manager.start_capture(capture.capture_id, lease)
            transport.emit_ecg(10_000_000_000, (1, 2))
            transport.emit_ecg(11_000_000_000, (3, 4))
            # Existing status events are returned immediately, even while the
            # consumer is still waiting to write the first ECG packet.
            events = await manager.events_after(capture.capture_id, 0, timeout_s=0.01)
            if delay_consumer:
                assert events and all(event.event_type == "status" for event in events)
                assert not release_consumer.is_set()
            release_consumer.set()

            async def wait_for_gap():
                batch = events
                cursor = 0
                while True:
                    for event in batch:
                        cursor = max(cursor, event.sequence)
                        if (
                            event.event_type == "gap"
                            and event.payload.get("reason")
                            == "sensor_timestamp_discontinuity"
                        ):
                            return event
                    batch = await manager.events_after(
                        capture.capture_id, cursor, timeout_s=1
                    )

            gap = await asyncio.wait_for(wait_for_gap(), timeout=5)
            assert gap.payload["stream"] == "ecg"
            assert gap.payload["observed_sensor_timestamp_ns"] == 11_000_000_000
            final = await manager.stop_capture(capture.capture_id, lease)
            assert "ecg_sensor_timestamp_discontinuity" in final.incomplete_reasons
            assert final.artifact_state == "incomplete"
            assert (
                pq.read_table(tmp_path / capture.capture_id / "ecg.parquet").num_rows
                == 4
            )
        finally:
            release_consumer.set()
            await manager.shutdown()

    asyncio.run(exercise())


def test_startup_marks_partial_capture_as_interrupted(tmp_path) -> None:
    async def exercise() -> None:
        engine = _engine()
        capture_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        writer = ParquetCaptureWriter(tmp_path, capture_id)
        writer.abort()
        import hashlib
        with Session(engine) as db:
            db.add(PolarCaptureRecord(
                id=capture_id, participant_id="P01", matb_session_kind="generic",
                matb_session_id="restart", device_alias="Polar H10 1",
                lifecycle="capturing", requested_settings_json="{}",
                controller_lease_hash=hashlib.sha256(b"lease").hexdigest(),
                artifact_state="partial", artifact_root=str(writer.capture_root),
            ))
            db.commit()
        manager = PolarCaptureManager(
            engine=engine, artifact_root=tmp_path, transport=SimulatedPolarTransport()
        )
        await manager.startup()
        recovered = manager.capture_view(capture_id)
        assert recovered.lifecycle == "failed"
        assert recovered.artifact_state == "incomplete"
        assert "backend_restart_during_capture" in recovered.incomplete_reasons
        assert len(list(writer.capture_root.glob("*.partial"))) == 3

    asyncio.run(exercise())
