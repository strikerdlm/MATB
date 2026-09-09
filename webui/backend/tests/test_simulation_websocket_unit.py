from __future__ import annotations

import pytest

from app.websocket.simulation import StreamEnvelope, StreamKind


def test_stream_envelope_is_strict_and_json_safe() -> None:
    envelope = StreamEnvelope(
        session_id="sim-20260801-00000000",
        sequence=1,
        simulation_time_ms=0,
        wall_time_utc="2026-08-01T12:00:00Z",
        state_version=0,
        kind=StreamKind.SNAPSHOT,
        payload={"resynchronizes_after_sequence": 0},
    )
    assert envelope.as_json()["kind"] == "snapshot"
    with pytest.raises(ValueError):
        StreamEnvelope(
            session_id="sim-1",
            sequence=0,
            simulation_time_ms=0,
            wall_time_utc="2026-08-01T12:00:00Z",
            state_version=0,
            kind=StreamKind.SNAPSHOT,
            payload={},
            unexpected=True,
        )

@pytest.mark.anyio
async def test_disconnect_takes_precedence_over_a_queued_frame():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.routers.simulation import simulation_stream
    envelope=SimpleNamespace(as_json=lambda:{'kind':'snapshot'})
    queue=asyncio.Queue();queue.put_nowait(envelope)
    subscription=SimpleNamespace(queue=queue,_closed=asyncio.Event())
    hub=SimpleNamespace(subscribe=AsyncMock(return_value=subscription),unsubscribe=AsyncMock())
    manager=SimpleNamespace(hub=hub,view=AsyncMock(),snapshot_envelope=AsyncMock(return_value=envelope),observer_disconnected=AsyncMock())
    class Socket:
        headers={'origin':'http://localhost:3100'}
        query_params={}
        app=SimpleNamespace(state=SimpleNamespace(frontend_origins={'http://localhost:3100'},simulation_manager=manager))
        closed=False
        sent=[]
        async def accept(self):pass
        async def receive(self):
            self.closed=True
            return {'type':'websocket.disconnect'}
        async def send_json(self,value):
            assert not self.closed,'attempted send after disconnect'
            self.sent.append(value)
    socket=Socket()
    await simulation_stream(socket,'test-session')
    assert socket.sent==[{'kind':'snapshot'}]
    hub.unsubscribe.assert_awaited_once_with(subscription)
    manager.observer_disconnected.assert_awaited_once_with('test-session')
