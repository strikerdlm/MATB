"""MATB-owned Polar transport boundary with a Bleak desktop adapter."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
import time
from typing import Any, Callable, Protocol

from .broadcast import POLAR_COMPANY_ID, PolarHrBroadcast, parse_polar_hr_manufacturer_data
from .hrs import HeartRateMeasurement, parse_heart_rate_measurement


@dataclass(frozen=True, slots=True)
class DeviceCandidate:
    alias: str
    name: str
    connectable: bool | None
    rssi: int | None
    broadcast: PolarHrBroadcast | None
    native_device: Any = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class HrPacket:
    measurement: HeartRateMeasurement
    received_monotonic_ns: int
    received_utc_ns: int


@dataclass(frozen=True, slots=True)
class EcgPacket:
    sensor_timestamp_ns: int
    samples_uv: tuple[int, ...]
    received_monotonic_ns: int
    received_utc_ns: int


@dataclass(frozen=True, slots=True)
class AccPacket:
    sensor_timestamp_ns: int
    samples_mg: tuple[tuple[int, int, int], ...]
    received_monotonic_ns: int
    received_utc_ns: int


@dataclass(frozen=True, slots=True)
class TransportCapabilities:
    firmware: str | None
    battery_percent: int | None
    hr_rr: bool
    ecg_rates_hz: tuple[int, ...]
    ecg_resolutions_bits: tuple[int, ...]
    acc_rates_hz: tuple[int, ...]
    acc_resolutions_bits: tuple[int, ...]
    acc_ranges_g: tuple[int, ...]


HrCallback = Callable[[HrPacket], None]
EcgCallback = Callable[[EcgPacket], None]
AccCallback = Callable[[AccPacket], None]
DisconnectCallback = Callable[[], None]


class PolarTransport(Protocol):
    async def scan(self, timeout_s: float) -> list[DeviceCandidate]: ...
    async def connect(self, device: DeviceCandidate, on_disconnect: DisconnectCallback) -> None: ...
    async def capabilities(self) -> TransportCapabilities: ...
    async def start_hr(self, callback: HrCallback) -> None: ...
    async def start_ecg(self, sample_rate_hz: int, resolution_bits: int, callback: EcgCallback) -> None: ...
    async def start_acc(
        self, sample_rate_hz: int, resolution_bits: int, range_g: int, callback: AccCallback
    ) -> None: ...
    async def stop_all(self) -> None: ...
    async def disconnect(self) -> None: ...


def _connectability(native_device: Any, advertisement: Any) -> bool | None:
    direct = getattr(advertisement, "connectable", None)
    if isinstance(direct, bool):
        return direct
    platform_data = getattr(advertisement, "platform_data", None)
    if isinstance(platform_data, (tuple, list)) and len(platform_data) >= 2:
        raw = platform_data[1]
        for event in (getattr(raw, "adv", None), getattr(raw, "scan", None)):
            value = getattr(event, "is_connectable", None)
            if isinstance(value, bool):
                return value
    for source in (advertisement, getattr(native_device, "details", None)):
        value = getattr(source, "is_connectable", None)
        if isinstance(value, bool):
            return value
        if isinstance(source, dict):
            value = source.get("is_connectable")
            if isinstance(value, bool):
                return value
            nested = source.get("adv")
            value = getattr(nested, "is_connectable", None)
            if isinstance(value, bool):
                return value
    return None


def _prepare_windows_bleak_thread() -> None:
    """Match the HRV native backend's WinRT apartment preparation."""
    if sys.platform == "win32":
        try:
            from bleak.backends.winrt.util import uninitialize_sta
            uninitialize_sta()
        except (ImportError, RuntimeError):
            pass


def _setting_values(settings: Any, setting_type: Any) -> tuple[int, ...]:
    values: set[int] = set()
    for setting in settings.settings:
        if setting.type == setting_type:
            values.update(int(value) for value in setting.values)
    return tuple(sorted(values))


def validate_pmd_frame(data: bytes | bytearray | memoryview) -> None:
    """Reject truncated/unsupported raw PMD frames before third-party parsing."""

    payload = bytes(data)
    if len(payload) < 10:
        raise ValueError("truncated PMD frame header")
    measurement_type = payload[0]
    frame_type = payload[9]
    compressed = bool(frame_type & 0x80)
    base_type = frame_type & 0x7F
    content_length = len(payload) - 10
    if measurement_type not in {0, 2}:
        raise ValueError(f"unsupported PMD measurement type: {measurement_type}")
    if compressed:
        return
    if measurement_type == 0:
        if base_type != 0:
            raise ValueError(f"unsupported ECG PMD frame type: {base_type}")
        if content_length == 0 or content_length % 3:
            raise ValueError("truncated ECG PMD sample")
    elif base_type == 0:
        if content_length == 0 or content_length % 3:
            raise ValueError("truncated 8-bit ACC PMD sample")
    elif base_type == 1:
        if content_length == 0 or content_length % 6:
            raise ValueError("truncated 16-bit ACC PMD sample")
    else:
        raise ValueError(f"unsupported ACC PMD frame type: {base_type}")


class PolarBleakTransport:
    """One-connection Bleak adapter using polar-python's public PMD parser.

    Bluetooth imports are lazy so the optional component never becomes a core
    runtime dependency. The exact scanned BLEDevice is passed to BleakClient.
    """

    HEART_RATE_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
    BATTERY_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
    FIRMWARE_UUID = "00002a26-0000-1000-8000-00805f9b34fb"

    def __init__(self) -> None:
        self._client: Any = None
        self._control_queue: asyncio.Queue[bytearray] = asyncio.Queue()
        self._factors: dict[Any, float] = {}
        self._hr_callback: HrCallback | None = None
        self._ecg_callback: EcgCallback | None = None
        self._acc_callback: AccCallback | None = None
        self._active: set[Any] = set()
        self._disconnect_callback: DisconnectCallback | None = None

    async def scan(self, timeout_s: float) -> list[DeviceCandidate]:
        if not 0.25 <= timeout_s <= 30.0:
            raise ValueError("scan timeout must be between 0.25 and 30 seconds")
        from bleak import BleakScanner

        _prepare_windows_bleak_thread()
        discovered = await BleakScanner.discover(timeout=timeout_s, return_adv=True)
        pairs = discovered.values() if isinstance(discovered, dict) else discovered
        candidates: list[DeviceCandidate] = []
        for native_device, advertisement in pairs:
            name = (
                getattr(advertisement, "local_name", None)
                or getattr(native_device, "name", None)
                or ""
            )
            if "polar h10" not in name.casefold():
                continue
            manufacturer = getattr(advertisement, "manufacturer_data", {}) or {}
            broadcast = None
            if POLAR_COMPANY_ID in manufacturer:
                try:
                    broadcast = parse_polar_hr_manufacturer_data(manufacturer[POLAR_COMPANY_ID])
                except ValueError:
                    broadcast = None
            candidates.append(
                DeviceCandidate(
                    alias=f"Polar H10 {len(candidates) + 1}",
                    name=name,
                    connectable=_connectability(native_device, advertisement),
                    rssi=getattr(advertisement, "rssi", None),
                    broadcast=broadcast,
                    native_device=native_device,
                )
            )
        return candidates

    async def connect(self, device: DeviceCandidate, on_disconnect: DisconnectCallback) -> None:
        if self._client is not None:
            raise RuntimeError("a Polar device is already connected")
        if device.connectable is False:
            raise RuntimeError("device_not_connectable")
        from bleak import BleakClient

        _prepare_windows_bleak_thread()
        self._disconnect_callback = on_disconnect
        self._client = BleakClient(device.native_device, disconnected_callback=self._on_disconnect)
        try:
            await self._client.connect()
            services = self._client.services
            required = {
                self.HEART_RATE_UUID.casefold(),
                "fb005c81-02e7-f387-1cad-8acd2d8df0c8",
                "fb005c82-02e7-f387-1cad-8acd2d8df0c8",
            }
            observed = {characteristic.uuid.casefold() for service in services for characteristic in service.characteristics}
            missing = sorted(required - observed)
            if missing:
                raise RuntimeError("required_gatt_characteristics_missing:" + ",".join(missing))
            from polar_python.constants import PolarCharacteristic

            await self._client.start_notify(PolarCharacteristic.PMD_CONTROL_POINT.value, self._on_control)
            await self._client.start_notify(PolarCharacteristic.PMD_DATA.value, self._on_pmd_data)
        except BaseException:
            await self.disconnect()
            raise

    def _on_disconnect(self, _client: Any) -> None:
        if self._disconnect_callback is not None:
            self._disconnect_callback()

    def _on_control(self, _characteristic: Any, data: bytearray) -> None:
        if data and data[0] == 0xF0:
            self._control_queue.put_nowait(bytearray(data))

    def _on_pmd_data(self, _characteristic: Any, data: bytearray) -> None:
        from polar_python import parsers
        from polar_python.models import ACCData, ECGData

        validate_pmd_frame(data)
        received_mono = time.monotonic_ns()
        received_utc = time.time_ns()
        parsed = parsers.parse_polar_data(bytearray(data), self._factors.get)
        if isinstance(parsed, ECGData) and self._ecg_callback is not None:
            self._ecg_callback(EcgPacket(int(parsed.timestamp), tuple(int(x) for x in parsed.data), received_mono, received_utc))
        elif isinstance(parsed, ACCData) and self._acc_callback is not None:
            samples = tuple((int(x), int(y), int(z)) for x, y, z in parsed.data)
            self._acc_callback(AccPacket(int(parsed.timestamp), samples, received_mono, received_utc))

    def _on_hr(self, _characteristic: Any, data: bytearray) -> None:
        if self._hr_callback is not None:
            self._hr_callback(
                HrPacket(parse_heart_rate_measurement(data), time.monotonic_ns(), time.time_ns())
            )

    async def _response(self, measurement_type: Any, operation_code: Any) -> Any:
        from polar_python.models import MeasurementSettings

        while True:
            raw = await asyncio.wait_for(self._control_queue.get(), timeout=10.0)
            if len(raw) < 5 or raw[1] != int(operation_code) or raw[2] != measurement_type.value:
                continue
            response = MeasurementSettings.from_bytes(raw)
            return response

    async def _request_settings(self, measurement_type: Any) -> Any:
        from polar_python.constants import PmdControlOperationCode, PolarCharacteristic

        await self._client.write_gatt_char(
            PolarCharacteristic.PMD_CONTROL_POINT.value,
            bytearray([PmdControlOperationCode.GET, measurement_type.value]),
        )
        response = await self._response(measurement_type, PmdControlOperationCode.GET)
        if response.error_code.value != 0:
            raise RuntimeError(f"pmd_settings_error:{response.error_code.name}")
        while response.more_frames:
            following = await self._response(measurement_type, PmdControlOperationCode.GET)
            if following.error_code.value != 0:
                raise RuntimeError(f"pmd_settings_error:{following.error_code.name}")
            response.settings.extend(following.settings)
            response.more_frames = following.more_frames
        return response

    async def capabilities(self) -> TransportCapabilities:
        if self._client is None:
            raise RuntimeError("no Polar device connected")
        from polar_python.constants import PmdMeasurementType, PmdSettingType, PolarCharacteristic

        feature_data = await self._client.read_gatt_char(PolarCharacteristic.PMD_CONTROL_POINT.value)
        if not feature_data or feature_data[0] != 0x0F:
            raise RuntimeError("unexpected_pmd_feature_response")
        feature_bits = feature_data[1]
        has_ecg = bool(feature_bits & (1 << PmdMeasurementType.ECG.value))
        has_acc = bool(feature_bits & (1 << PmdMeasurementType.ACC.value))
        ecg = await self._request_settings(PmdMeasurementType.ECG) if has_ecg else None
        acc = await self._request_settings(PmdMeasurementType.ACC) if has_acc else None

        async def optional_read(uuid: str) -> bytes | None:
            try:
                return bytes(await self._client.read_gatt_char(uuid))
            except Exception:
                return None

        firmware_raw, battery_raw = await asyncio.gather(
            optional_read(self.FIRMWARE_UUID), optional_read(self.BATTERY_UUID)
        )
        return TransportCapabilities(
            firmware=firmware_raw.decode("utf-8", errors="replace").strip("\x00") if firmware_raw else None,
            battery_percent=int(battery_raw[0]) if battery_raw else None,
            hr_rr=True,
            ecg_rates_hz=_setting_values(ecg, PmdSettingType.SAMPLE_RATE) if ecg else (),
            ecg_resolutions_bits=_setting_values(ecg, PmdSettingType.RESOLUTION) if ecg else (),
            acc_rates_hz=_setting_values(acc, PmdSettingType.SAMPLE_RATE) if acc else (),
            acc_resolutions_bits=_setting_values(acc, PmdSettingType.RESOLUTION) if acc else (),
            acc_ranges_g=_setting_values(acc, PmdSettingType.RANGE) if acc else (),
        )

    async def _start(self, settings: Any) -> None:
        from polar_python.constants import PmdSettingType, PolarCharacteristic

        await self._client.write_gatt_char(PolarCharacteristic.PMD_CONTROL_POINT.value, settings.to_bytes())
        from polar_python.constants import PmdControlOperationCode

        response = await self._response(settings.measurement_type, PmdControlOperationCode.START)
        if response.error_code.value != 0:
            raise RuntimeError(f"pmd_start_error:{response.error_code.name}")
        for setting in response.settings:
            if setting.type == PmdSettingType.FACTOR and setting.values:
                import struct
                self._factors[settings.measurement_type] = struct.unpack(
                    "<f", struct.pack("<I", setting.values[0])
                )[0]
        self._active.add(settings.measurement_type)

    async def start_hr(self, callback: HrCallback) -> None:
        self._hr_callback = callback
        await self._client.start_notify(self.HEART_RATE_UUID, self._on_hr)

    async def start_ecg(self, sample_rate_hz: int, resolution_bits: int, callback: EcgCallback) -> None:
        from polar_python.constants import PmdMeasurementType, PmdSettingType
        from polar_python.models import MeasurementSettings

        self._ecg_callback = callback
        await self._start(MeasurementSettings(PmdMeasurementType.ECG, [
            MeasurementSettings.SettingType(PmdSettingType.SAMPLE_RATE, [sample_rate_hz]),
            MeasurementSettings.SettingType(PmdSettingType.RESOLUTION, [resolution_bits]),
        ]))

    async def start_acc(
        self, sample_rate_hz: int, resolution_bits: int, range_g: int, callback: AccCallback
    ) -> None:
        from polar_python.constants import PmdMeasurementType, PmdSettingType
        from polar_python.models import MeasurementSettings

        self._acc_callback = callback
        await self._start(MeasurementSettings(PmdMeasurementType.ACC, [
            MeasurementSettings.SettingType(PmdSettingType.SAMPLE_RATE, [sample_rate_hz]),
            MeasurementSettings.SettingType(PmdSettingType.RESOLUTION, [resolution_bits]),
            MeasurementSettings.SettingType(PmdSettingType.RANGE, [range_g]),
        ]))

    async def stop_all(self) -> None:
        if self._client is None:
            return
        from polar_python.constants import PmdControlOperationCode, PolarCharacteristic

        errors: list[Exception] = []
        try:
            if self._hr_callback is not None:
                await self._client.stop_notify(self.HEART_RATE_UUID)
        except Exception as exc:
            errors.append(exc)
        finally:
            self._hr_callback = None
        for measurement_type in tuple(self._active):
            try:
                await self._client.write_gatt_char(
                    PolarCharacteristic.PMD_CONTROL_POINT.value,
                    bytearray([PmdControlOperationCode.STOP, measurement_type.value]),
                )
                response = await self._response(measurement_type, PmdControlOperationCode.STOP)
                if response.error_code.value != 0:
                    raise RuntimeError(f"pmd_stop_error:{response.error_code.name}")
            except Exception as exc:
                errors.append(exc)
            finally:
                self._active.discard(measurement_type)
                self._factors.pop(measurement_type, None)
        self._ecg_callback = None
        self._acc_callback = None
        if errors:
            raise RuntimeError("one_or_more_streams_failed_to_stop") from errors[0]

    async def disconnect(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        try:
            if client.is_connected:
                await client.disconnect()
        finally:
            self._active.clear()
            self._factors.clear()
            self._hr_callback = None
            self._ecg_callback = None
            self._acc_callback = None


class SimulatedPolarTransport:
    """Deterministic test transport; no simulated data is labelled as hardware."""

    def __init__(self, *, connectable: bool = True) -> None:
        self.device = DeviceCandidate(
            alias="Simulated Polar H10", name="Polar H10 SIM", connectable=connectable,
            rssi=-45, broadcast=PolarHrBroadcast(60, 60, 1, True, True, True, False, 0),
            native_device=object(),
        )
        self.connected = False
        self.hr_callback: HrCallback | None = None
        self.ecg_callback: EcgCallback | None = None
        self.acc_callback: AccCallback | None = None
        self.on_disconnect: DisconnectCallback | None = None

    async def scan(self, timeout_s: float) -> list[DeviceCandidate]:
        del timeout_s
        return [self.device]

    async def connect(self, device: DeviceCandidate, on_disconnect: DisconnectCallback) -> None:
        if device.connectable is False:
            raise RuntimeError("device_not_connectable")
        self.connected = True
        self.on_disconnect = on_disconnect

    async def capabilities(self) -> TransportCapabilities:
        if not self.connected:
            raise RuntimeError("no Polar device connected")
        return TransportCapabilities(
            firmware="SIM-1", battery_percent=100, hr_rr=True,
            ecg_rates_hz=(130,), ecg_resolutions_bits=(14,),
            acc_rates_hz=(25, 50, 100, 200), acc_resolutions_bits=(16,), acc_ranges_g=(2, 4, 8),
        )

    async def start_hr(self, callback: HrCallback) -> None:
        self.hr_callback = callback

    async def start_ecg(self, sample_rate_hz: int, resolution_bits: int, callback: EcgCallback) -> None:
        if (sample_rate_hz, resolution_bits) != (130, 14):
            raise RuntimeError("unsupported_ecg_settings")
        self.ecg_callback = callback

    async def start_acc(
        self, sample_rate_hz: int, resolution_bits: int, range_g: int, callback: AccCallback
    ) -> None:
        if sample_rate_hz not in (25, 50, 100, 200) or resolution_bits != 16 or range_g not in (2, 4, 8):
            raise RuntimeError("unsupported_acc_settings")
        self.acc_callback = callback

    async def stop_all(self) -> None:
        self.hr_callback = self.ecg_callback = self.acc_callback = None

    async def disconnect(self) -> None:
        self.connected = False

    def emit_hr(self, payload: bytes, *, mono_ns: int | None = None, utc_ns: int | None = None) -> None:
        if self.hr_callback:
            self.hr_callback(HrPacket(
                parse_heart_rate_measurement(payload),
                time.monotonic_ns() if mono_ns is None else mono_ns,
                time.time_ns() if utc_ns is None else utc_ns,
            ))

    def emit_ecg(self, timestamp_ns: int, samples: tuple[int, ...]) -> None:
        if self.ecg_callback:
            self.ecg_callback(EcgPacket(timestamp_ns, samples, time.monotonic_ns(), time.time_ns()))

    def emit_acc(self, timestamp_ns: int, samples: tuple[tuple[int, int, int], ...]) -> None:
        if self.acc_callback:
            self.acc_callback(AccPacket(timestamp_ns, samples, time.monotonic_ns(), time.time_ns()))

    def trigger_disconnect(self) -> None:
        self.connected = False
        if self.on_disconnect:
            self.on_disconnect()
