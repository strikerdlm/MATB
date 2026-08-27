"""Bluetooth SIG Heart Rate Measurement (0x2A37) decoder."""

from __future__ import annotations

from dataclasses import dataclass
import struct


@dataclass(frozen=True, slots=True)
class RRValue:
    ticks_1024: int
    milliseconds: float


@dataclass(frozen=True, slots=True)
class HeartRatePacket:
    flags: int
    heart_rate_bpm: int
    rr_values: tuple[RRValue, ...]
    sensor_contact_supported: bool
    sensor_contact_detected: bool | None
    energy_expended_kj: int | None


class HeartRatePacketError(ValueError):
    """Bounded decoder failure for one Heart Rate Measurement payload."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def parse_heart_rate_measurement(data: bytes | bytearray) -> HeartRatePacket:
    payload = bytes(data)
    if not payload:
        raise HeartRatePacketError("empty_heart_rate_packet")

    flags = payload[0]
    offset = 1
    hr_16bit = bool(flags & 0x01)
    contact_supported = bool(flags & 0x04)
    contact_detected = bool(flags & 0x02) if contact_supported else None
    energy_present = bool(flags & 0x08)
    rr_present = bool(flags & 0x10)

    heart_rate_length = 2 if hr_16bit else 1
    if len(payload) < offset + heart_rate_length:
        raise HeartRatePacketError("truncated_heart_rate")
    if hr_16bit:
        heart_rate = struct.unpack_from("<H", payload, offset)[0]
    else:
        heart_rate = payload[offset]
    offset += heart_rate_length

    energy: int | None = None
    if energy_present:
        if len(payload) < offset + 2:
            raise HeartRatePacketError("truncated_energy_expended")
        energy = struct.unpack_from("<H", payload, offset)[0]
        offset += 2

    rr_values: list[RRValue] = []
    if rr_present:
        if (len(payload) - offset) % 2:
            raise HeartRatePacketError("truncated_rr_value")
        while offset < len(payload):
            ticks = struct.unpack_from("<H", payload, offset)[0]
            rr_values.append(RRValue(ticks, ticks * 1000.0 / 1024.0))
            offset += 2

    return HeartRatePacket(
        flags=flags,
        heart_rate_bpm=heart_rate,
        rr_values=tuple(rr_values),
        sensor_contact_supported=contact_supported,
        sensor_contact_detected=contact_detected,
        energy_expended_kj=energy,
    )
