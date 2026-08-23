"""Cross-platform Bleak adapter for the Polar H10 standard HRS stream."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
import inspect
import secrets
import struct
import sys
import time
from typing import Any, Protocol


HEART_RATE_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HEART_RATE_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

NotificationCallback = Callable[[bytes], None | Awaitable[None]]
DisconnectCallback = Callable[[], None | Awaitable[None]]


class PolarBackendError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class DeviceCandidate:
    device_token: str
    display_name: str
    rssi: int | None
    is_polar_h10: bool
    heart_rate_service_advertised: bool
    token_expires_at_utc_ns: int


class PolarBackend(Protocol):
    backend_name: str

    async def scan(self, timeout_seconds: float) -> tuple[DeviceCandidate, ...]: ...
    async def connect(self, device_token: str) -> None: ...
    async def reconnect_selected(self) -> None: ...
    async def start_notifications(self, callback: NotificationCallback) -> None: ...
    async def stop_notifications(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def read_battery_level(self) -> int | None: ...
    async def shutdown(self) -> None: ...
    def set_disconnect_handler(self, callback: DisconnectCallback | None) -> None: ...

    @property
    def connected_device_name(self) -> str | None: ...

    @property
    def connected_raw_identifier(self) -> str | None: ...


@dataclass(slots=True)
class _ScannedEntry:
    device: Any
    candidate: DeviceCandidate
    raw_identifier: str
    expires_monotonic: float
    connectable: bool | None


_WINDOWS_STA_REMEDIATED = False


def _prepare_windows_bleak_thread() -> None:
    global _WINDOWS_STA_REMEDIATED
    if sys.platform != "win32" or _WINDOWS_STA_REMEDIATED:
        return
    try:
        from bleak.backends.winrt.util import uninitialize_sta

        uninitialize_sta()
    except (ImportError, RuntimeError):
        return
    _WINDOWS_STA_REMEDIATED = True


def _scan_error_code(exc: Exception) -> str:
    reason_name = getattr(getattr(exc, "reason", None), "name", "")
    reason_codes = {
        "NO_BLUETOOTH": "bluetooth_adapter_unavailable",
        "NO_BLE_CENTRAL_ROLE": "bluetooth_adapter_unsupported",
        "POWERED_OFF": "bluetooth_powered_off",
        "DENIED_BY_USER": "bluetooth_access_denied",
        "DENIED_BY_SYSTEM": "bluetooth_access_denied",
        "DENIED_BY_UNKNOWN": "bluetooth_access_denied",
        "UNKNOWN": "bluetooth_unavailable",
    }
    if reason_name in reason_codes:
        return reason_codes[reason_name]
    dbus_error = str(getattr(exc, "dbus_error", ""))
    if dbus_error in {
        "org.freedesktop.DBus.Error.AccessDenied",
        "org.freedesktop.DBus.Error.AuthFailed",
    }:
        return "bluetooth_access_denied"
    if dbus_error in {
        "org.freedesktop.DBus.Error.Disconnected",
        "org.freedesktop.DBus.Error.ServiceUnknown",
        "org.freedesktop.DBus.Error.NoServer",
    }:
        return "bluetooth_service_unavailable"
    if dbus_error == "org.bluez.Error.NotReady":
        return "bluetooth_powered_off"
    if dbus_error == "org.bluez.Error.NotSupported":
        return "bluetooth_adapter_unsupported"
    if isinstance(exc, PermissionError):
        return "bluetooth_access_denied"
    message = str(exc).casefold()
    if "thread is configured for windows gui" in message:
        return "bluetooth_windows_threading_invalid"
    return "bluetooth_scan_failed"


async def _default_scanner(timeout_seconds: float) -> Sequence[tuple[Any, Any]]:
    _prepare_windows_bleak_thread()
    try:
        from bleak import BleakScanner
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise PolarBackendError("bleak_unavailable") from exc
    kwargs: dict[str, Any] = {"timeout": timeout_seconds, "return_adv": True}
    if sys.platform != "win32":
        kwargs["service_uuids"] = [HEART_RATE_SERVICE_UUID]
    try:
        discovered = await BleakScanner.discover(**kwargs)
    except Exception as exc:  # pragma: no cover - backend-specific
        raise PolarBackendError(_scan_error_code(exc)) from exc
    if isinstance(discovered, dict):
        return list(discovered.values())
    return [(device, None) for device in discovered]


def _default_client_factory(device: Any, disconnected_callback=None):
    _prepare_windows_bleak_thread()
    try:
        from bleak import BleakClient
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise PolarBackendError("bleak_unavailable") from exc
    return BleakClient(device, disconnected_callback=disconnected_callback)


def _display_name(device: Any, advertisement: Any) -> str:
    return str(
        getattr(advertisement, "local_name", None)
        or getattr(device, "name", None)
        or "Unnamed BLE device"
    )


def _service_uuids(advertisement: Any) -> set[str]:
    return {
        str(value).lower()
        for value in (getattr(advertisement, "service_uuids", None) or ())
    }


def _connectable(advertisement: Any) -> bool | None:
    platform_data = getattr(advertisement, "platform_data", None)
    if not platform_data or len(platform_data) < 2:
        return None
    raw = platform_data[1]
    event = getattr(raw, "adv", None) or getattr(raw, "scan", None)
    value = getattr(event, "is_connectable", None)
    return bool(value) if value is not None else None


async def _disconnect_client_quietly(client: Any) -> bool:
    """Best-effort cleanup, returning whether the native client remains live."""

    try:
        await client.disconnect()
    except BaseException:
        # Preserve the transition error that triggered cleanup.  Callers retain
        # a still-connected client so a later disconnect can retry the release.
        pass
    return bool(getattr(client, "is_connected", False))


async def _stop_notify_quietly(client: Any) -> None:
    """Finish best-effort unsubscribe even while the caller is cancelling."""

    cleanup = asyncio.create_task(
        client.stop_notify(HEART_RATE_MEASUREMENT_UUID)
    )
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            # The original cancellation is re-raised by the caller after the
            # independent cleanup task has completed.
            continue
        except BaseException:
            break
    with suppress(BaseException):
        cleanup.result()


def _verify_heart_rate_measurement(client: Any) -> None:
    services = getattr(client, "services", None)
    get_characteristic = getattr(services, "get_characteristic", None)
    if (
        not callable(get_characteristic)
        or get_characteristic(HEART_RATE_MEASUREMENT_UUID) is None
    ):
        raise PolarBackendError("heart_rate_measurement_unavailable")


class BleakPolarBackend:
    """Exact-device Bleak client restricted to Polar H10 HRS notifications."""

    backend_name = "bleak"

    def __init__(
        self,
        *,
        scanner: Callable[[float], Awaitable[Sequence[tuple[Any, Any]]]] = _default_scanner,
        client_factory: Callable[..., Any] = _default_client_factory,
        token_ttl_seconds: float = 90.0,
    ) -> None:
        self._scanner = scanner
        self._client_factory = client_factory
        self._token_ttl_seconds = max(1.0, float(token_ttl_seconds))
        self._entries: dict[str, _ScannedEntry] = {}
        self._selected: _ScannedEntry | None = None
        self._client: Any = None
        self._notifying = False
        self._disconnect_handler: DisconnectCallback | None = None

    @property
    def connected_device_name(self) -> str | None:
        return self._selected.candidate.display_name if self._selected else None

    @property
    def connected_raw_identifier(self) -> str | None:
        return self._selected.raw_identifier if self._selected else None

    def set_disconnect_handler(self, callback: DisconnectCallback | None) -> None:
        self._disconnect_handler = callback

    async def scan(self, timeout_seconds: float) -> tuple[DeviceCandidate, ...]:
        if self._client is not None and bool(getattr(self._client, "is_connected", False)):
            raise PolarBackendError("scan_not_allowed_while_connected")
        timeout = min(30.0, max(0.1, float(timeout_seconds)))
        discovered = await self._scanner(timeout)
        expires_monotonic = time.monotonic() + self._token_ttl_seconds
        expires_utc_ns = time.time_ns() + round(self._token_ttl_seconds * 1_000_000_000)
        entries: list[_ScannedEntry] = []
        for device, advertisement in discovered:
            name = _display_name(device, advertisement)
            if "polar h10" not in name.casefold():
                continue
            token = secrets.token_urlsafe(24)
            candidate = DeviceCandidate(
                device_token=token,
                display_name=name,
                rssi=getattr(advertisement, "rssi", None),
                is_polar_h10=True,
                heart_rate_service_advertised=HEART_RATE_SERVICE_UUID
                in _service_uuids(advertisement),
                token_expires_at_utc_ns=expires_utc_ns,
            )
            entries.append(
                _ScannedEntry(
                    device=device,
                    candidate=candidate,
                    raw_identifier=str(getattr(device, "address", "unknown")),
                    expires_monotonic=expires_monotonic,
                    connectable=_connectable(advertisement),
                )
            )
        entries.sort(key=lambda entry: (-(entry.candidate.rssi or -1000), entry.candidate.display_name))
        self._entries = {entry.candidate.device_token: entry for entry in entries}
        return tuple(entry.candidate for entry in entries)

    async def connect(self, device_token: str) -> None:
        if self._client is not None and bool(getattr(self._client, "is_connected", False)):
            raise PolarBackendError("device_already_connected")
        entry = self._entries.get(device_token)
        if entry is None or time.monotonic() > entry.expires_monotonic:
            raise PolarBackendError("device_token_invalid")
        if entry.connectable is False:
            raise PolarBackendError("device_not_connectable")
        client = self._client_factory(entry.device, disconnected_callback=self._on_disconnected)
        try:
            await client.connect()
            if not bool(getattr(client, "is_connected", False)):
                raise PolarBackendError("device_connection_failed")
            _verify_heart_rate_measurement(client)
        except BaseException as exc:
            still_connected = await _disconnect_client_quietly(client)
            if still_connected:
                self._client = client
                self._selected = entry
                self._notifying = False
                self._entries = {device_token: entry}
            if isinstance(exc, (PolarBackendError, asyncio.CancelledError)):
                raise
            raise PolarBackendError("device_connection_failed") from exc
        self._client = client
        self._selected = entry
        self._entries = {device_token: entry}

    async def start_notifications(self, callback: NotificationCallback) -> None:
        client = self._require_connected()
        if self._notifying:
            return

        async def handler(_sender: Any, data: bytearray) -> None:
            result = callback(bytes(data))
            if inspect.isawaitable(result):
                await result

        try:
            await client.start_notify(HEART_RATE_MEASUREMENT_UUID, handler)
        except BaseException as exc:
            await _stop_notify_quietly(client)
            self._notifying = False
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise PolarBackendError("notification_start_failed") from exc
        self._notifying = True

    async def stop_notifications(self) -> None:
        if self._client is None or not self._notifying:
            return
        try:
            await self._client.stop_notify(HEART_RATE_MEASUREMENT_UUID)
        except asyncio.CancelledError:
            await _stop_notify_quietly(self._client)
            raise
        except Exception as exc:
            raise PolarBackendError("notification_stop_failed") from exc
        finally:
            self._notifying = False

    async def read_battery_level(self) -> int | None:
        client = self._require_connected()
        try:
            payload = await client.read_gatt_char(BATTERY_LEVEL_UUID)
        except Exception:
            return None
        return int(payload[0]) if payload else None

    async def disconnect(self) -> None:
        client = self._client
        if client is None:
            self._selected = None
            self._notifying = False
            return
        try:
            await client.disconnect()
        except asyncio.CancelledError:
            await _disconnect_client_quietly(client)
            if bool(getattr(client, "is_connected", False)):
                self._client = client
            else:
                self._client = None
                self._selected = None
                self._notifying = False
            raise
        except Exception as exc:
            if bool(getattr(client, "is_connected", False)):
                self._client = client
            else:
                self._client = None
                self._selected = None
                self._notifying = False
            raise PolarBackendError("device_disconnect_failed") from exc
        self._client = None
        self._selected = None
        self._notifying = False

    async def reconnect_selected(self) -> None:
        entry = self._selected
        if entry is None:
            raise PolarBackendError("selected_device_missing")
        previous_client = self._client
        if previous_client is not None:
            try:
                await previous_client.disconnect()
            except asyncio.CancelledError:
                await _disconnect_client_quietly(previous_client)
                if bool(getattr(previous_client, "is_connected", False)):
                    self._client = previous_client
                else:
                    self._client = None
                    self._notifying = False
                raise
            except Exception as exc:
                if bool(getattr(previous_client, "is_connected", False)):
                    self._client = previous_client
                else:
                    self._client = None
                    self._notifying = False
                raise PolarBackendError("device_reconnect_failed") from exc
            self._client = None
            self._notifying = False
        client = self._client_factory(entry.device, disconnected_callback=self._on_disconnected)
        try:
            await client.connect()
            if not bool(getattr(client, "is_connected", False)):
                raise PolarBackendError("device_reconnect_failed")
            _verify_heart_rate_measurement(client)
        except BaseException as exc:
            still_connected = await _disconnect_client_quietly(client)
            if still_connected:
                self._client = client
                self._notifying = False
            if isinstance(exc, asyncio.CancelledError):
                raise
            if isinstance(exc, PolarBackendError):
                raise
            raise PolarBackendError("device_reconnect_failed") from exc
        self._client = client
        self._notifying = False

    async def shutdown(self) -> None:
        try:
            await self.stop_notifications()
        except PolarBackendError:
            pass
        for _attempt in range(2):
            try:
                await self.disconnect()
            except PolarBackendError:
                continue
            break

    def _require_connected(self):
        if self._client is None or not bool(getattr(self._client, "is_connected", False)):
            raise PolarBackendError("device_not_connected")
        return self._client

    def _on_disconnected(self, client: Any) -> None:
        if client is not self._client:
            return
        self._client = None
        self._notifying = False
        callback = self._disconnect_handler
        if callback is None:
            return
        result = callback()
        if inspect.isawaitable(result):
            asyncio.get_running_loop().create_task(result)


class SimulatedPolarBackend:
    """Hardware-free backend that emits actual HRS binary frames."""

    backend_name = "simulated"

    def __init__(self) -> None:
        self._token = "simulated-polar-h10"
        self._connected = False
        self._callback: NotificationCallback | None = None
        self._disconnect_handler: DisconnectCallback | None = None

    @property
    def connected_device_name(self) -> str | None:
        return "Polar H10 Simulator" if self._connected else None

    @property
    def connected_raw_identifier(self) -> str | None:
        return "simulated://polar-h10" if self._connected else None

    def set_disconnect_handler(self, callback: DisconnectCallback | None) -> None:
        self._disconnect_handler = callback

    async def scan(self, timeout_seconds: float) -> tuple[DeviceCandidate, ...]:
        await asyncio.sleep(min(max(timeout_seconds, 0.0), 0.01))
        return (
            DeviceCandidate(
                device_token=self._token,
                display_name="Polar H10 Simulator",
                rssi=-30,
                is_polar_h10=True,
                heart_rate_service_advertised=True,
                token_expires_at_utc_ns=time.time_ns() + 90_000_000_000,
            ),
        )

    async def connect(self, device_token: str) -> None:
        if device_token != self._token:
            raise PolarBackendError("device_token_invalid")
        self._connected = True

    async def reconnect_selected(self) -> None:
        self._connected = True

    async def start_notifications(self, callback: NotificationCallback) -> None:
        if not self._connected:
            raise PolarBackendError("device_not_connected")
        self._callback = callback

    async def stop_notifications(self) -> None:
        self._callback = None

    async def disconnect(self) -> None:
        await self.stop_notifications()
        self._connected = False

    async def read_battery_level(self) -> int | None:
        return 95 if self._connected else None

    async def shutdown(self) -> None:
        await self.disconnect()

    async def emit_rr_ticks(
        self,
        ticks: tuple[int, ...],
        *,
        heart_rate_bpm: int = 60,
    ) -> None:
        if not self._connected or self._callback is None:
            raise PolarBackendError("notifications_not_started")
        payload = bytes([0x10, heart_rate_bpm]) + b"".join(
            struct.pack("<H", value) for value in ticks
        )
        result = self._callback(payload)
        if inspect.isawaitable(result):
            await result


__all__ = [
    "BATTERY_LEVEL_UUID",
    "HEART_RATE_MEASUREMENT_UUID",
    "HEART_RATE_SERVICE_UUID",
    "BleakPolarBackend",
    "DeviceCandidate",
    "PolarBackend",
    "PolarBackendError",
    "SimulatedPolarBackend",
]
