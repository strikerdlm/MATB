"""Strict preliminary decoder for Liftoff's all-fields UDP profile."""

from __future__ import annotations

from dataclasses import dataclass
import math
import struct

LIFTOFF_ALL_V1 = "liftoff-telemetry-all-v1"
_PACKET = struct.Struct("<20fB4f")
PACKET_SIZE = _PACKET.size


class PacketDecodeError(ValueError):
    """Raised when a datagram does not match the characterized profile."""


@dataclass(frozen=True, slots=True)
class LiftoffPacket:
    simulator_time: float
    position_native: tuple[float, float, float]
    attitude_native: tuple[float, float, float, float]
    velocity_native: tuple[float, float, float]
    angular_rate_native: tuple[float, float, float]
    processed_input: tuple[float, float, float, float]
    battery_voltage: float
    charge_percent: float
    motor_count: int
    motor_rpm: tuple[float, float, float, float]


def decode_packet(payload: bytes) -> LiftoffPacket:
    """Decode one exact-size packet without guessing units or layout."""

    if len(payload) != PACKET_SIZE:
        raise PacketDecodeError("packet_size")
    values = _PACKET.unpack(payload)
    floats = values[:20]
    motor_count = values[20]
    rpms = values[21:]
    if motor_count != 4:
        raise PacketDecodeError("motor_count")
    if not all(math.isfinite(value) for value in (*floats, *rpms)):
        raise PacketDecodeError("packet_values")
    return LiftoffPacket(
        simulator_time=floats[0],
        position_native=(floats[1], floats[2], floats[3]),
        attitude_native=(floats[4], floats[5], floats[6], floats[7]),
        velocity_native=(floats[8], floats[9], floats[10]),
        angular_rate_native=(floats[11], floats[12], floats[13]),
        processed_input=(floats[14], floats[15], floats[16], floats[17]),
        battery_voltage=floats[18],
        charge_percent=floats[19],
        motor_count=motor_count,
        motor_rpm=(rpms[0], rpms[1], rpms[2], rpms[3]),
    )


__all__ = [
    "LIFTOFF_ALL_V1",
    "PACKET_SIZE",
    "LiftoffPacket",
    "PacketDecodeError",
    "decode_packet",
]
