from __future__ import annotations

import pytest

from app.websocket.simulation import HubConflict, SimulationHub, StreamEnvelope, StreamKind


def envelope(sequence: int, kind: StreamKind = StreamKind.SNAPSHOT) -> StreamEnvelope:
    return StreamEnvelope(
        session_id="sim-1",
        sequence=sequence,
        simulation_time_ms=sequence * 100,
        wall_time_utc="2026-08-01T12:00:00Z",
        state_version=sequence,
        kind=kind,
        payload={"sequence": sequence},
    )


@pytest.mark.anyio
async def test_hub_preserves_order_and_initial_snapshot() -> None:
    hub = SimulationHub(queue_size=8)
    subscription = await hub.subscribe("sim-1", role="observer", initial=envelope(10))
    await hub.publish("sim-1", envelope(11, StreamKind.DOMAIN_EVENT))
    assert (await subscription.queue.get()).sequence == 10
    assert (await subscription.queue.get()).sequence == 11


@pytest.mark.anyio
async def test_slow_observer_is_dropped_without_blocking_controller() -> None:
    hub = SimulationHub(queue_size=1)
    observer = await hub.subscribe("sim-1", role="observer")
    controller = await hub.subscribe("sim-1", role="controller")
    await hub.publish("sim-1", envelope(1))
    await hub.publish("sim-1", envelope(2))
    assert observer.closed_code == 4408
    assert (await controller.queue.get()).sequence == 1


@pytest.mark.anyio
async def test_only_one_controller_is_allowed() -> None:
    hub = SimulationHub()
    await hub.subscribe("sim-1", role="controller")
    with pytest.raises(HubConflict):
        await hub.subscribe("sim-1", role="controller")


@pytest.mark.anyio
async def test_controller_overflow_requests_pause_before_close() -> None:
    paused: list[str] = []

    async def pause(session_id: str) -> None:
        paused.append(session_id)

    hub = SimulationHub(queue_size=1, on_controller_overflow=pause)
    controller = await hub.subscribe("sim-1", role="controller")
    await hub.publish("sim-1", envelope(1))
    await hub.publish("sim-1", envelope(2))
    assert paused == ["sim-1"]
    assert controller.closed_code == 4408
