from __future__ import annotations

import asyncio
from dataclasses import replace
import socket

import pytest

from matb_integration.liftoff.protocol import decode_packet
from matb_integration.liftoff.receiver import (
    LiftoffUdpReceiver,
    ReceiverHealth,
    _LiftoffDatagramProtocol,
)
from tests.liftoff.test_protocol import valid_payload


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def unused_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def send_packets(port: int, payloads: list[bytes]) -> None:
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        asyncio.DatagramProtocol,
        remote_addr=("127.0.0.1", port),
    )
    try:
        for payload in payloads:
            transport.sendto(payload)
        await asyncio.sleep(0.05)
    finally:
        transport.close()


@pytest.mark.anyio
async def test_receiver_requires_loopback():
    with pytest.raises(ValueError, match="loopback_required"):
        LiftoffUdpReceiver(host="0.0.0.0", port=9001)


@pytest.mark.anyio
async def test_readiness_after_twenty_valid_packets(unused_udp_port):
    receiver = LiftoffUdpReceiver(host="127.0.0.1", port=unused_udp_port)
    await receiver.start()
    try:
        payloads = []
        base = decode_packet(valid_payload())
        for index in range(20):
            packet = replace(base, simulator_time=index / 100.0)
            payloads.append(
                __import__("struct").pack(
                    "<20fB4f",
                    packet.simulator_time,
                    *packet.position_native,
                    *packet.attitude_native,
                    *packet.velocity_native,
                    *packet.angular_rate_native,
                    *packet.processed_input,
                    packet.battery_voltage,
                    packet.charge_percent,
                    packet.motor_count,
                    *packet.motor_rpm,
                )
            )
        await send_packets(unused_udp_port, payloads)

        assert await receiver.wait_ready(min_valid=20, timeout_seconds=2.0)
        assert receiver.health().valid_packets == 20
    finally:
        await receiver.stop()


@pytest.mark.anyio
async def test_receiver_accounts_for_invalid_ordering_overflow_and_raw_callback(unused_udp_port):
    captured: list[bytes] = []
    receiver = LiftoffUdpReceiver(
        host="127.0.0.1",
        port=unused_udp_port,
        queue_size=20,
        callback=lambda payload, _monotonic_ns, _utc: captured.append(payload),
    )
    await receiver.start()
    try:
        payloads = [valid_payload(replacement=(0, index / 100.0)) for index in range(22)]
        payloads.extend([
            valid_payload(replacement=(0, 0.21)),
            valid_payload(replacement=(0, 0.20)),
            b"bad",
        ])
        await send_packets(unused_udp_port, payloads)
        health = receiver.health()

        assert health.valid_packets == 22
        assert health.overflow_count == 2
        assert health.duplicate_time_count == 1
        assert health.out_of_order_count == 1
        assert health.invalid_size_count == 1
        assert len(captured) == len(payloads)
    finally:
        await receiver.stop()


@pytest.mark.slow
def test_synthetic_thirty_second_packet_volume_stays_bounded():
    queue: asyncio.Queue = asyncio.Queue(maxsize=4096)
    health = ReceiverHealth()
    protocol = _LiftoffDatagramProtocol(queue, health, asyncio.Event(), None)

    for index in range(3_000):
        protocol.datagram_received(
            valid_payload(replacement=(0, index / 100.0)),
            ("127.0.0.1", 9001),
        )

    assert health.valid_packets == 3_000
    assert health.overflow_count == 0
    assert queue.qsize() == 3_000
