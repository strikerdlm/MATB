"""Listen-only Polar manufacturer HR advertisement decoding.

This narrow protocol implementation follows Polar SDK advertisement behavior;
the repository carries the corresponding Polar SDK license and path mapping.
Broadcast HR is preflight information only and is never an HRV input.
"""

from __future__ import annotations

from dataclasses import dataclass


POLAR_COMPANY_ID = 0x006B


@dataclass(frozen=True, slots=True)
class PolarHrBroadcast:
    heart_rate_bpm: int
    fast_average_hr_bpm: int
    frame_counter: int
    sensor_contact: bool
    battery_ok: bool
    broadcast_enabled: bool
    status_flag: bool
    khz_code: int


def parse_polar_hr_manufacturer_data(payload: bytes | bytearray | memoryview) -> PolarHrBroadcast | None:
    """Parse Bleak's Polar manufacturer value (company identifier excluded)."""

    content = bytes(payload)
    offset = 0
    while offset < len(content):
        if content[offset] & 0x40 == 0:
            remaining = len(content) - offset
            if remaining < 3:
                raise ValueError("truncated Polar HR advertisement")
            frame_size = 4 if remaining == 4 else 3
            frame = content[offset:offset + frame_size]
            flags = frame[0]
            return PolarHrBroadcast(
                heart_rate_bpm=frame[3] if frame_size == 4 else frame[2],
                fast_average_hr_bpm=frame[2],
                frame_counter=(flags & 0x1C) >> 2,
                sensor_contact=bool(flags & 0x02),
                battery_ok=not bool(flags & 0x01),
                broadcast_enabled=bool(flags & 0x20),
                status_flag=bool(flags & 0x80),
                khz_code=frame[1],
            )
        # General-purpose block: type byte, length byte, then length bytes.
        offset += 1
        if offset >= len(content):
            raise ValueError("truncated Polar general-purpose advertisement")
        block_length = content[offset]
        offset += block_length + 1
    return None
