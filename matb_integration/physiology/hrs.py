"""Bluetooth Heart Rate Service decoder.

Unlike several convenience wrappers, this parser handles 8/16-bit heart rate,
energy-expended fields, contact flags, and every transmitted RR interval.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HeartRateMeasurement:
    heart_rate_bpm: int
    rr_ticks_1024: tuple[int, ...]
    rr_ms: tuple[float, ...]
    sensor_contact_supported: bool
    sensor_contact_detected: bool | None
    energy_expended_kj: int | None


def parse_heart_rate_measurement(data: bytes | bytearray | memoryview) -> HeartRateMeasurement:
    """Decode Bluetooth SIG Heart Rate Measurement characteristic bytes."""

    payload = bytes(data)
    if len(payload) < 2:
        raise ValueError("truncated Heart Rate Measurement")
    flags = payload[0]
    index = 1
    if flags & 0x01:
        if len(payload) < index + 2:
            raise ValueError("truncated 16-bit heart rate")
        heart_rate = int.from_bytes(payload[index:index + 2], "little")
        index += 2
    else:
        heart_rate = payload[index]
        index += 1

    contact_supported = bool(flags & 0x04)
    contact_detected = bool(flags & 0x02) if contact_supported else None
    energy = None
    if flags & 0x08:
        if len(payload) < index + 2:
            raise ValueError("truncated energy-expended field")
        energy = int.from_bytes(payload[index:index + 2], "little")
        index += 2

    ticks: list[int] = []
    if flags & 0x10:
        if (len(payload) - index) % 2:
            raise ValueError("truncated RR interval")
        while index < len(payload):
            ticks.append(int.from_bytes(payload[index:index + 2], "little"))
            index += 2
    elif index != len(payload):
        raise ValueError("unexpected trailing Heart Rate Measurement bytes")

    return HeartRateMeasurement(
        heart_rate_bpm=heart_rate,
        rr_ticks_1024=tuple(ticks),
        rr_ms=tuple(tick * 1000.0 / 1024.0 for tick in ticks),
        sensor_contact_supported=contact_supported,
        sensor_contact_detected=contact_detected,
        energy_expended_kj=energy,
    )
