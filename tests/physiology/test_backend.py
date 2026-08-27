from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from matb_integration.physiology.backend import (
    HEART_RATE_MEASUREMENT_UUID,
    BleakPolarBackend,
    PolarBackendError,
    SimulatedPolarBackend,
)


@dataclass
class FakeDevice:
    name: str
    address: str


@dataclass
class FakeAdvertisement:
    service_uuids: list[str]
    rssi: int
    local_name: str | None = None


class FakeServices:
    def get_characteristic(self, uuid: str):
        return object() if uuid == HEART_RATE_MEASUREMENT_UUID else None


class FakeClient:
    def __init__(self, device: FakeDevice, disconnected_callback=None) -> None:
        self.device = device
        self.disconnected_callback = disconnected_callback
        self.is_connected = False
        self.services = FakeServices()
        self.started: list[str] = []
        self.writes: list[object] = []

    async def connect(self) -> None:
        self.is_connected = True

    async def disconnect(self) -> None:
        self.is_connected = False
        if self.disconnected_callback:
            self.disconnected_callback(self)

    async def start_notify(self, uuid: str, callback) -> None:
        self.started.append(uuid)
        self.callback = callback

    async def stop_notify(self, _uuid: str) -> None:
        return None

    async def read_gatt_char(self, _uuid: str) -> bytes:
        return bytes([87])


def test_backend_connects_with_exact_scanned_device_and_only_subscribes_to_hrs() -> None:
    h10 = FakeDevice("Polar H10 12345678", "AA:BB:CC:DD:EE:01")
    generic = FakeDevice("Other HR", "AA:BB:CC:DD:EE:02")
    clients: list[FakeClient] = []

    async def scanner(_timeout: float):
        return [
            (h10, FakeAdvertisement([], -45)),
            (generic, FakeAdvertisement(["0000180d-0000-1000-8000-00805f9b34fb"], -30)),
        ]

    def client_factory(device, disconnected_callback=None):
        client = FakeClient(device, disconnected_callback)
        clients.append(client)
        return client

    async def scenario() -> None:
        backend = BleakPolarBackend(scanner=scanner, client_factory=client_factory)
        candidates = await backend.scan(0.01)
        assert [candidate.display_name for candidate in candidates] == ["Polar H10 12345678"]
        await backend.connect(candidates[0].device_token)
        await backend.start_notifications(lambda _payload: None)
        assert await backend.read_battery_level() == 87

    asyncio.run(scenario())

    assert clients[0].device is h10
    assert clients[0].started == [HEART_RATE_MEASUREMENT_UUID]
    assert clients[0].writes == []


def test_backend_rejects_a_connection_without_the_hrs_measurement_characteristic() -> None:
    h10 = FakeDevice("Polar H10 12345678", "AA:BB:CC:DD:EE:01")
    clients: list[FakeClient] = []

    async def scanner(_timeout: float):
        return [(h10, FakeAdvertisement([], -45))]

    def client_factory(device, disconnected_callback=None):
        client = FakeClient(device, disconnected_callback)
        client.services = None
        clients.append(client)
        return client

    async def scenario() -> None:
        backend = BleakPolarBackend(scanner=scanner, client_factory=client_factory)
        candidate = (await backend.scan(0.01))[0]
        with pytest.raises(
            PolarBackendError,
            match="heart_rate_measurement_unavailable",
        ):
            await backend.connect(candidate.device_token)

    asyncio.run(scenario())

    assert clients[0].is_connected is False


def test_initial_connect_failure_retains_client_when_cleanup_disconnect_fails() -> None:
    h10 = FakeDevice("Polar H10 12345678", "AA:BB:CC:DD:EE:01")
    clients: list[FakeClient] = []

    async def scanner(_timeout: float):
        return [(h10, FakeAdvertisement([], -45))]

    class PartiallyConnectedClient(FakeClient):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.disconnect_count = 0

        async def connect(self) -> None:
            self.is_connected = True
            raise RuntimeError("injected_connect_failure")

        async def disconnect(self) -> None:
            self.disconnect_count += 1
            if self.disconnect_count == 1:
                raise RuntimeError("injected_disconnect_failure")
            await super().disconnect()

    def client_factory(device, disconnected_callback=None):
        client = PartiallyConnectedClient(device, disconnected_callback)
        clients.append(client)
        return client

    async def scenario() -> BleakPolarBackend:
        backend = BleakPolarBackend(scanner=scanner, client_factory=client_factory)
        candidate = (await backend.scan(0.01))[0]
        with pytest.raises(PolarBackendError, match="device_connection_failed"):
            await backend.connect(candidate.device_token)
        assert backend._client is clients[0]
        assert backend._selected is not None
        await backend.shutdown()
        return backend

    backend = asyncio.run(scenario())

    assert clients[0].disconnect_count == 2
    assert clients[0].is_connected is False
    assert backend._client is None
    assert backend._selected is None


def test_simulated_backend_emits_real_multi_rr_hrs_payload() -> None:
    received: list[bytes] = []

    async def scenario() -> None:
        backend = SimulatedPolarBackend()
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        await backend.start_notifications(received.append)
        await backend.emit_rr_ticks((1024, 512), heart_rate_bpm=80)

    asyncio.run(scenario())

    assert received == [bytes([0x10, 80, 0x00, 0x04, 0x00, 0x02])]


def test_failed_reconnect_disconnects_the_partially_connected_client() -> None:
    h10 = FakeDevice("Polar H10 12345678", "AA:BB:CC:DD:EE:01")
    clients: list[FakeClient] = []

    async def scanner(_timeout: float):
        return [(h10, FakeAdvertisement([], -45))]

    class FailingReconnectClient(FakeClient):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.disconnect_count = 0

        async def connect(self) -> None:
            self.is_connected = True
            raise RuntimeError("injected_reconnect_failure")

        async def disconnect(self) -> None:
            self.disconnect_count += 1
            await super().disconnect()

    def client_factory(device, disconnected_callback=None):
        client: FakeClient
        if clients:
            client = FailingReconnectClient(device, disconnected_callback)
        else:
            client = FakeClient(device, disconnected_callback)
        clients.append(client)
        return client

    async def scenario() -> None:
        backend = BleakPolarBackend(scanner=scanner, client_factory=client_factory)
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        backend._on_disconnected(clients[0])

        with pytest.raises(PolarBackendError, match="device_reconnect_failed"):
            await backend.reconnect_selected()

    asyncio.run(scenario())

    assert isinstance(clients[1], FailingReconnectClient)
    assert clients[1].disconnect_count == 1
    assert clients[1].is_connected is False


def test_failed_reconnect_retains_new_client_when_cleanup_disconnect_fails() -> None:
    h10 = FakeDevice("Polar H10 12345678", "AA:BB:CC:DD:EE:01")
    clients: list[FakeClient] = []

    async def scanner(_timeout: float):
        return [(h10, FakeAdvertisement([], -45))]

    class PartiallyReconnectedClient(FakeClient):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.disconnect_count = 0

        async def connect(self) -> None:
            self.is_connected = True
            raise RuntimeError("injected_reconnect_failure")

        async def disconnect(self) -> None:
            self.disconnect_count += 1
            if self.disconnect_count == 1:
                raise RuntimeError("injected_disconnect_failure")
            await super().disconnect()

    def client_factory(device, disconnected_callback=None):
        if clients:
            client = PartiallyReconnectedClient(device, disconnected_callback)
        else:
            client = FakeClient(device, disconnected_callback)
        clients.append(client)
        return client

    async def scenario() -> BleakPolarBackend:
        backend = BleakPolarBackend(scanner=scanner, client_factory=client_factory)
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        clients[0].is_connected = False
        backend._on_disconnected(clients[0])

        with pytest.raises(PolarBackendError, match="device_reconnect_failed"):
            await backend.reconnect_selected()
        assert backend._client is clients[1]
        await backend.shutdown()
        return backend

    backend = asyncio.run(scenario())

    assert isinstance(clients[1], PartiallyReconnectedClient)
    assert clients[1].disconnect_count == 2
    assert clients[1].is_connected is False
    assert backend._client is None
    assert backend._selected is None


def test_reconnect_replaces_a_client_whose_notification_restart_failed() -> None:
    h10 = FakeDevice("Polar H10 12345678", "AA:BB:CC:DD:EE:01")
    clients: list[FakeClient] = []

    async def scanner(_timeout: float):
        return [(h10, FakeAdvertisement([], -45))]

    class NotifyFailureClient(FakeClient):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.disconnect_count = 0

        async def start_notify(self, _uuid: str, _callback) -> None:
            raise RuntimeError("injected_notification_failure")

        async def disconnect(self) -> None:
            self.disconnect_count += 1
            if self.disconnect_count == 1:
                raise RuntimeError("injected_disconnect_failure")
            await super().disconnect()

    def client_factory(device, disconnected_callback=None):
        if len(clients) == 1:
            client = NotifyFailureClient(device, disconnected_callback)
        else:
            client = FakeClient(device, disconnected_callback)
        clients.append(client)
        return client

    async def scenario() -> None:
        backend = BleakPolarBackend(scanner=scanner, client_factory=client_factory)
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        backend._on_disconnected(clients[0])
        await backend.reconnect_selected()
        with pytest.raises(PolarBackendError, match="notification_start_failed"):
            await backend.start_notifications(lambda _payload: None)
        with pytest.raises(PolarBackendError, match="device_reconnect_failed"):
            await backend.reconnect_selected()
        assert backend._client is clients[1]
        await backend.reconnect_selected()

    asyncio.run(scenario())

    assert isinstance(clients[1], NotifyFailureClient)
    assert clients[1].disconnect_count == 2
    assert clients[1].is_connected is False
    assert clients[2].is_connected is True


def test_shutdown_retries_a_failed_disconnect_without_losing_the_client() -> None:
    h10 = FakeDevice("Polar H10 12345678", "AA:BB:CC:DD:EE:01")
    clients: list[FakeClient] = []

    async def scanner(_timeout: float):
        return [(h10, FakeAdvertisement([], -45))]

    class FailOnceDisconnectClient(FakeClient):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.disconnect_count = 0

        async def disconnect(self) -> None:
            self.disconnect_count += 1
            if self.disconnect_count == 1:
                raise RuntimeError("injected_disconnect_failure")
            await super().disconnect()

    def client_factory(device, disconnected_callback=None):
        client = FailOnceDisconnectClient(device, disconnected_callback)
        clients.append(client)
        return client

    async def scenario() -> BleakPolarBackend:
        backend = BleakPolarBackend(scanner=scanner, client_factory=client_factory)
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        await backend.shutdown()
        return backend

    backend = asyncio.run(scenario())

    assert clients[0].disconnect_count == 2
    assert clients[0].is_connected is False
    assert backend._client is None
    assert backend._selected is None


def test_cancelled_notification_start_best_effort_unsubscribes() -> None:
    h10 = FakeDevice("Polar H10 12345678", "AA:BB:CC:DD:EE:01")
    clients: list[FakeClient] = []

    async def scanner(_timeout: float):
        return [(h10, FakeAdvertisement([], -45))]

    class BlockingNotifyClient(FakeClient):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.start_entered = asyncio.Event()
            self.release_start = asyncio.Event()
            self.stop_count = 0

        async def start_notify(self, uuid: str, callback) -> None:
            self.started.append(uuid)
            self.callback = callback
            self.start_entered.set()
            await self.release_start.wait()

        async def stop_notify(self, _uuid: str) -> None:
            self.stop_count += 1

    def client_factory(device, disconnected_callback=None):
        client = BlockingNotifyClient(device, disconnected_callback)
        clients.append(client)
        return client

    async def scenario() -> BleakPolarBackend:
        backend = BleakPolarBackend(scanner=scanner, client_factory=client_factory)
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        start_task = asyncio.create_task(backend.start_notifications(lambda _payload: None))
        await clients[0].start_entered.wait()
        start_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await start_task
        return backend

    backend = asyncio.run(scenario())

    assert clients[0].stop_count == 1
    assert backend._notifying is False


def test_cancelled_notification_stop_finishes_best_effort_unsubscribe() -> None:
    h10 = FakeDevice("Polar H10 12345678", "AA:BB:CC:DD:EE:01")
    clients: list[FakeClient] = []

    async def scanner(_timeout: float):
        return [(h10, FakeAdvertisement([], -45))]

    class BlockingStopClient(FakeClient):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.stop_entered = asyncio.Event()
            self.stop_count = 0

        async def stop_notify(self, _uuid: str) -> None:
            self.stop_count += 1
            if self.stop_count == 1:
                self.stop_entered.set()
                await asyncio.Event().wait()

    def client_factory(device, disconnected_callback=None):
        client = BlockingStopClient(device, disconnected_callback)
        clients.append(client)
        return client

    async def scenario() -> BleakPolarBackend:
        backend = BleakPolarBackend(scanner=scanner, client_factory=client_factory)
        candidate = (await backend.scan(0.01))[0]
        await backend.connect(candidate.device_token)
        await backend.start_notifications(lambda _payload: None)
        stop_task = asyncio.create_task(backend.stop_notifications())
        await clients[0].stop_entered.wait()
        stop_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await stop_task
        return backend

    backend = asyncio.run(scenario())

    assert clients[0].stop_count == 2
    assert backend._notifying is False
