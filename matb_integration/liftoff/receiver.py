"""Loopback-only bounded UDP acquisition for Liftoff telemetry."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import ipaddress
import time
from typing import cast

from .protocol import LiftoffPacket, PacketDecodeError, decode_packet

PacketCallback = Callable[[bytes, int, datetime], None]
_CLOCK_STEP_THRESHOLD_NS = 100_000_000


@dataclass(frozen=True, slots=True)
class ReceivedPacket:
    payload: bytes
    received_monotonic_ns: int
    received_utc: datetime
    packet: LiftoffPacket


@dataclass(slots=True)
class ReceiverHealth:
    received_packets: int = 0
    valid_packets: int = 0
    invalid_size_count: int = 0
    invalid_value_count: int = 0
    overflow_count: int = 0
    duplicate_time_count: int = 0
    out_of_order_count: int = 0
    clock_step_detected: bool = False

    @property
    def invalid_packet_count(self) -> int:
        return self.invalid_size_count + self.invalid_value_count


class _LiftoffDatagramProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        queue: asyncio.Queue[ReceivedPacket],
        health: ReceiverHealth,
        ready: asyncio.Event,
        callback: PacketCallback | None,
    ) -> None:
        self._queue = queue
        self._health = health
        self._ready = ready
        self._callback = callback
        self._last_simulator_time: float | None = None
        self._last_monotonic_ns: int | None = None
        self._last_utc_ns: int | None = None

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        del addr
        payload = bytes(data)
        received_monotonic_ns = time.monotonic_ns()
        received_utc = datetime.now(timezone.utc)
        received_utc_ns = int(received_utc.timestamp() * 1_000_000_000)
        self._health.received_packets += 1
        if self._callback is not None:
            self._callback(payload, received_monotonic_ns, received_utc)
        if self._last_monotonic_ns is not None and self._last_utc_ns is not None:
            monotonic_delta = received_monotonic_ns - self._last_monotonic_ns
            utc_delta = received_utc_ns - self._last_utc_ns
            if abs(utc_delta - monotonic_delta) > _CLOCK_STEP_THRESHOLD_NS:
                self._health.clock_step_detected = True
        self._last_monotonic_ns = received_monotonic_ns
        self._last_utc_ns = received_utc_ns

        try:
            packet = decode_packet(payload)
        except PacketDecodeError as exc:
            if str(exc) == "packet_size":
                self._health.invalid_size_count += 1
            else:
                self._health.invalid_value_count += 1
            return

        if self._last_simulator_time is not None:
            if packet.simulator_time == self._last_simulator_time:
                self._health.duplicate_time_count += 1
                return
            if packet.simulator_time < self._last_simulator_time:
                self._health.out_of_order_count += 1
                return
        self._last_simulator_time = packet.simulator_time
        self._health.valid_packets += 1
        received = ReceivedPacket(
            payload=payload,
            received_monotonic_ns=received_monotonic_ns,
            received_utc=received_utc,
            packet=packet,
        )
        try:
            self._queue.put_nowait(received)
        except asyncio.QueueFull:
            self._health.overflow_count += 1
        if self._health.valid_packets >= 20:
            self._ready.set()


class LiftoffUdpReceiver:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        queue_size: int = 4096,
        callback: PacketCallback | None = None,
    ) -> None:
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError("loopback_required") from exc
        if not address.is_loopback:
            raise ValueError("loopback_required")
        if (
            isinstance(port, bool)
            or not isinstance(port, int)
            or not 1 <= port <= 65535
            or isinstance(queue_size, bool)
            or not isinstance(queue_size, int)
            or queue_size < 20
        ):
            raise ValueError("invalid_receiver_configuration")
        self.host = host
        self.port = port
        self._queue: asyncio.Queue[ReceivedPacket] = asyncio.Queue(maxsize=queue_size)
        self._transport: asyncio.DatagramTransport | None = None
        self._health = ReceiverHealth()
        self._ready = asyncio.Event()
        self._callback = callback

    async def start(self) -> None:
        if self._transport is not None:
            raise RuntimeError("receiver_already_started")
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _LiftoffDatagramProtocol(
                self._queue,
                self._health,
                self._ready,
                self._callback,
            ),
            local_addr=(self.host, self.port),
        )
        self._transport = cast(asyncio.DatagramTransport, transport)

    async def stop(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None
            await asyncio.sleep(0)

    async def wait_ready(self, *, min_valid: int = 20, timeout_seconds: float = 2.0) -> bool:
        if min_valid != 20:
            raise ValueError("readiness_requires_twenty_packets")
        if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise ValueError("invalid_readiness_timeout")
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=float(timeout_seconds))
        except TimeoutError:
            return False
        return self._health.valid_packets >= min_valid

    async def next_packet(self) -> ReceivedPacket:
        return await self._queue.get()

    def health(self) -> ReceiverHealth:
        return replace(self._health)


__all__ = ["LiftoffUdpReceiver", "ReceivedPacket", "ReceiverHealth"]
