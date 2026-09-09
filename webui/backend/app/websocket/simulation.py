"""Ordered, bounded WebSocket fan-out for one simulation session.

The hub owns transport ordering only.  It never advances the simulation and
never makes a command decision.  A slow observer is disposable; a slow
controller is a safety condition and is closed after the manager is asked to
pause the session.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StreamKind(StrEnum):
    TRAFFIC = "traffic"
    SNAPSHOT = "snapshot"
    DOMAIN_EVENT = "domain_event"
    ALERT = "alert"
    COMMAND_RESULT = "command_result"
    PROBE = "probe"
    LIFECYCLE = "lifecycle"
    CHECKPOINT = "checkpoint"
    ERROR = "error"


class StreamEnvelope(BaseModel):
    """Stable transport envelope shared with the browser client."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    simulation_time_ms: int = Field(ge=0)
    wall_time_utc: str
    state_version: int = Field(ge=0)
    kind: StreamKind
    payload: dict[str, Any] = Field(default_factory=dict)

    def as_json(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class HubConflict(RuntimeError):
    """A session already has a controller subscriber."""


CloseCallback = Callable[["HubSubscription", int], Awaitable[None] | None]
PauseCallback = Callable[[str], Awaitable[None] | None]


@dataclass(slots=True)
class HubSubscription:
    session_id: str
    role: str
    queue: asyncio.Queue[StreamEnvelope]
    identity: str | None = None
    close_callback: CloseCallback | None = None
    closed_code: int | None = None
    _closed: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def closed(self) -> bool:
        return self.closed_code is not None

    async def close(self, code: int = 1000) -> None:
        if self.closed_code is not None:
            return
        self.closed_code = code
        self._closed.set()
        if self.close_callback is not None:
            result = self.close_callback(self, code)
            if asyncio.iscoroutine(result):
                await result


class SimulationHub:
    """Per-process bounded fan-out with one controller per session."""

    def __init__(
        self,
        *,
        queue_size: int = 64,
        on_controller_overflow: PauseCallback | None = None,
    ) -> None:
        if isinstance(queue_size, bool) or not isinstance(queue_size, int) or queue_size < 1:
            raise ValueError("queue_size must be a positive integer")
        self.queue_size = queue_size
        self._subscribers: dict[str, list[HubSubscription]] = {}
        self._lock = asyncio.Lock()
        self._on_controller_overflow = on_controller_overflow

    async def subscribe(
        self,
        session_id: str,
        *,
        role: str,
        initial: StreamEnvelope | None = None,
        close_callback: CloseCallback | None = None,
        identity: str | None = None,
    ) -> HubSubscription:
        if role not in {"controller", "observer"}:
            raise ValueError("role must be controller or observer")
        subscription = HubSubscription(
            session_id=session_id,
            role=role,
            queue=asyncio.Queue(maxsize=self.queue_size),
            identity=identity,
            close_callback=close_callback,
        )
        async with self._lock:
            current = self._subscribers.setdefault(session_id, [])
            if role == "controller":
                active_controllers = [item for item in current if item.role == "controller" and not item.closed]
                if active_controllers:
                    same_identity = identity is not None and all(item.identity == identity for item in active_controllers)
                    if not same_identity:
                        raise HubConflict("a controller is already connected")
                    # A reconnect with the same lease is a handoff, not a
                    # second operator. Close old subscriptions before the
                    # replacement is published so their finally blocks can
                    # never pause the still-authoritative replacement stream.
                    for item in active_controllers:
                        item.closed_code = 4001
                        item._closed.set()
            current.append(subscription)
            if initial is not None:
                try:
                    subscription.queue.put_nowait(initial)
                except asyncio.QueueFull:
                    # A freshly allocated queue cannot be full, but keep the
                    # failure mode explicit if a custom queue is ever used.
                    await subscription.close(4408)
        return subscription

    async def unsubscribe(self, subscription: HubSubscription) -> None:
        async with self._lock:
            current = self._subscribers.get(subscription.session_id, [])
            if subscription in current:
                current.remove(subscription)
            if not current:
                self._subscribers.pop(subscription.session_id, None)
        await subscription.close(1000)

    async def publish(self, session_id: str, envelope: StreamEnvelope) -> None:
        if envelope.session_id != session_id:
            raise ValueError("envelope session_id does not match publish session")
        async with self._lock:
            current = tuple(self._subscribers.get(session_id, ()))
        # Queue operations are non-blocking.  Do not hold the hub lock while a
        # controller overflow callback pauses the manager.
        for subscription in current:
            if subscription.closed:
                continue
            try:
                subscription.queue.put_nowait(envelope)
            except asyncio.QueueFull:
                if subscription.role == "controller" and self._on_controller_overflow is not None:
                    result = self._on_controller_overflow(session_id)
                    if asyncio.iscoroutine(result):
                        await result
                error = StreamEnvelope(
                    session_id=session_id,
                    sequence=envelope.sequence,
                    simulation_time_ms=envelope.simulation_time_ms,
                    wall_time_utc=envelope.wall_time_utc,
                    state_version=envelope.state_version,
                    kind=StreamKind.ERROR,
                    payload={"code": "stream_backpressure", "fatal": True},
                )
                # There may be no room for the fatal error.  The close code is
                # authoritative and the receiver will resynchronize via REST.
                try:
                    subscription.queue.put_nowait(error)
                except asyncio.QueueFull:
                    pass
                await subscription.close(4408)

    async def subscribers(self, session_id: str) -> tuple[HubSubscription, ...]:
        async with self._lock:
            return tuple(self._subscribers.get(session_id, ()))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


__all__ = [
    "HubConflict",
    "HubSubscription",
    "SimulationHub",
    "StreamEnvelope",
    "StreamKind",
    "utc_now_iso",
]
