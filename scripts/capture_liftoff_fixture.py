#!/usr/bin/env python3
"""Capture and characterize Liftoff UDP packets without process access."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import ipaddress
import math
import os
from pathlib import Path
import socket
import struct
import time

from matb_integration.liftoff.protocol import PacketDecodeError, decode_packet
from matb_integration.recording.artifacts import write_json_artifact

_FRAME = struct.Struct("<4sQH")


@dataclass(frozen=True, slots=True)
class CapturedPacket:
    payload: bytes
    received_monotonic_ns: int


def capture_packets(
    *,
    host: str,
    port: int,
    count: int,
    timeout: float,
) -> list[CapturedPacket]:
    if not ipaddress.ip_address(host).is_loopback:
        raise ValueError("loopback_required")
    if not 1 <= port <= 65535 or count <= 0 or timeout <= 0:
        raise ValueError("invalid_capture_configuration")
    packets: list[CapturedPacket] = []
    deadline = time.monotonic() + timeout
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.bind((host, port))
        udp.settimeout(min(1.0, timeout))
        while len(packets) < count and time.monotonic() < deadline:
            try:
                payload, _address = udp.recvfrom(65_535)
            except TimeoutError:
                continue
            packets.append(CapturedPacket(bytes(payload), time.monotonic_ns()))
    if len(packets) < count:
        raise TimeoutError(f"captured {len(packets)} of {count} requested packets")
    return packets


def characterize_packets(packets: list[CapturedPacket]) -> dict[str, object]:
    sizes = Counter(len(packet.payload) for packet in packets)
    decoded = []
    schema_errors = 0
    for packet in packets:
        try:
            decoded.append(decode_packet(packet.payload))
        except PacketDecodeError:
            schema_errors += 1
    simulator_times = [packet.simulator_time for packet in decoded]
    receive_times = [packet.received_monotonic_ns for packet in packets]
    receive_duration_s = (
        (receive_times[-1] - receive_times[0]) / 1_000_000_000
        if len(receive_times) >= 2
        else 0.0
    )
    positions = [packet.position_native for packet in decoded]
    axis_ranges = {
        axis: (
            max(values) - min(values) if values else None
        )
        for axis, values in {
            "position_0": [value[0] for value in positions],
            "position_1": [value[1] for value in positions],
            "position_2": [value[2] for value in positions],
        }.items()
    }
    return {
        "report_version": "liftoff-characterization-v1",
        "packet_count": len(packets),
        "packet_sizes": {str(key): value for key, value in sorted(sizes.items())},
        "single_packet_size": len(sizes) == 1,
        "schema_errors": schema_errors,
        "finite_values": schema_errors == 0 and all(
            math.isfinite(value)
            for packet in decoded
            for value in (
                packet.simulator_time,
                *packet.position_native,
                *packet.attitude_native,
                *packet.velocity_native,
                *packet.angular_rate_native,
                *packet.processed_input,
                packet.battery_voltage,
                packet.charge_percent,
                *packet.motor_rpm,
            )
        ),
        "simulator_time_monotonic": all(
            right > left for left, right in zip(simulator_times, simulator_times[1:])
        ),
        "observed_rate_hz": (len(packets) / receive_duration_s if receive_duration_s > 0 else None),
        "motor_counts": {
            str(key): value
            for key, value in sorted(Counter(packet.motor_count for packet in decoded).items())
        },
        "position_axis_ranges_native": axis_ranges,
        "raw_sha256": [hashlib.sha256(packet.payload).hexdigest() for packet in packets],
        "unresolved": {
            "coordinate_units": True,
            "axis_orientation": True,
            "quaternion_order": True,
            "native_time_units": True,
        },
    }


def write_framed_fixture(path: Path, packets: list[CapturedPacket]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        with temporary.open("xb") as stream:
            for packet in packets:
                stream.write(_FRAME.pack(b"LFC1", packet.received_monotonic_ns, len(packet.payload)))
                stream.write(packet.payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=9001)
    parser.add_argument("--count", type=int, default=1200)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    packets = capture_packets(
        host="127.0.0.1",
        port=args.port,
        count=args.count,
        timeout=args.timeout,
    )
    diagnostics = characterize_packets(packets)
    write_framed_fixture(args.output, packets)
    write_json_artifact(args.report, diagnostics)
    return 0 if diagnostics["single_packet_size"] and diagnostics["finite_values"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
