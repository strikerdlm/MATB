# Copyright 2023-2026, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

"""Bounded asynchronous sinks with auditable loss and backpressure evidence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from queue import Full, Queue
from threading import Lock, Thread
from time import monotonic, perf_counter_ns
from typing import Generic, Literal, TypeVar, cast


RecordT = TypeVar("RecordT")
OverflowPolicy = Literal["block", "drop_newest"]


class SinkWorkerError(RuntimeError):
    """A sink writer failed while processing a submitted record."""


class SinkCloseTimeout(RuntimeError):
    """A sink could not drain and stop within its close deadline."""


@dataclass(frozen=True, slots=True)
class SinkEvidence:
    """Point-in-time evidence for a bounded asynchronous sink."""

    name: str
    capacity: int
    overflow_policy: OverflowPolicy
    accepted: int
    processed: int
    dropped: int
    failed: int
    backpressure_events: int
    backpressure_ns: int
    high_watermark: int
    started: bool
    closed: bool
    last_error: str | None

    def to_dict(self) -> dict[str, str | int | bool | None]:
        return asdict(self)


class BoundedAsyncSink(Generic[RecordT]):
    """Process records on one worker thread through a bounded FIFO queue.

    ``block`` is intended for authoritative records: the producer experiences
    backpressure and no record is silently discarded. ``drop_newest`` is intended
    only for optional live integrations such as network marker streams; every drop
    remains visible in :class:`SinkEvidence`.
    """

    _STOP = object()

    def __init__(
        self,
        *,
        name: str,
        writer: Callable[[RecordT], object],
        capacity: int = 4096,
        overflow_policy: OverflowPolicy = "block",
        autostart: bool = True,
    ) -> None:
        if not name or not name.strip():
            raise ValueError("sink name must not be empty")
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
            raise ValueError("sink capacity must be a positive integer")
        if overflow_policy not in {"block", "drop_newest"}:
            raise ValueError("unsupported sink overflow policy")

        self.name = name
        self.capacity = capacity
        self.overflow_policy = overflow_policy
        self._writer = writer
        self._queue: Queue[RecordT | object] = Queue(maxsize=capacity)
        self._lock = Lock()
        self._submit_lock = Lock()
        self._worker: Thread | None = None
        self._started = False
        self._closing = False
        self._closed = False
        self._stop_enqueued = False
        self._accepted = 0
        self._processed = 0
        self._dropped = 0
        self._failed = 0
        self._backpressure_events = 0
        self._backpressure_ns = 0
        self._high_watermark = 0
        self._last_exception: Exception | None = None

        if autostart:
            self.start()

    def start(self) -> None:
        with self._lock:
            if self._closed or self._closing:
                raise RuntimeError(f"sink {self.name!r} is closing or closed")
            if self._started:
                return
            self._started = True
            self._worker = Thread(
                target=self._run,
                name=f"matb-sink-{self.name}",
                daemon=True,
            )
            self._worker.start()

    def submit(self, record: RecordT) -> bool:
        # Serialize submissions against close so no producer can enqueue behind the
        # terminal sentinel and leave an unprocessed record in the queue.
        with self._submit_lock:
            with self._lock:
                if self._closed or self._closing:
                    raise RuntimeError(f"sink {self.name!r} is closing or closed")
                if self._last_exception is not None:
                    raise SinkWorkerError(self._failure_message()) from self._last_exception

            if self.overflow_policy == "drop_newest":
                try:
                    self._queue.put_nowait(record)
                except Full:
                    with self._lock:
                        self._dropped += 1
                    return False
                self._mark_accepted()
                return True

            was_full = self._queue.full()
            started_ns = perf_counter_ns()
            self._queue.put(record)
            elapsed_ns = perf_counter_ns() - started_ns
            with self._lock:
                if was_full:
                    self._backpressure_events += 1
                    self._backpressure_ns += max(0, elapsed_ns)
                self._accepted += 1
                self._high_watermark = max(self._high_watermark, self._queue.qsize())
            return True

    def close(self, timeout_s: float = 5.0) -> None:
        if timeout_s <= 0:
            raise ValueError("sink close timeout must be positive")

        deadline = monotonic() + timeout_s
        acquired_submit_lock = self._submit_lock.acquire(
            timeout=max(0.0, deadline - monotonic())
        )
        if not acquired_submit_lock:
            raise SinkCloseTimeout(
                f"sink {self.name!r} did not begin closing within {timeout_s} seconds"
            )
        try:
            with self._lock:
                if self._closed:
                    if self._last_exception is not None:
                        raise SinkWorkerError(self._failure_message()) from self._last_exception
                    return
                if not self._started:
                    self._started = True
                    self._worker = Thread(
                        target=self._run,
                        name=f"matb-sink-{self.name}",
                        daemon=True,
                    )
                    self._worker.start()
                self._closing = True
                worker = self._worker

            if not self._stop_enqueued:
                try:
                    self._queue.put(
                        self._STOP,
                        timeout=max(0.0, deadline - monotonic()),
                    )
                except Full as exc:
                    raise SinkCloseTimeout(
                        f"sink {self.name!r} did not drain within {timeout_s} seconds"
                    ) from exc
                self._stop_enqueued = True
            assert worker is not None
            worker.join(timeout=max(0.0, deadline - monotonic()))
            if worker.is_alive():
                raise SinkCloseTimeout(f"sink {self.name!r} did not drain within {timeout_s} seconds")
        finally:
            self._submit_lock.release()

        with self._lock:
            self._closed = True
            error = self._last_exception
        if error is not None:
            raise SinkWorkerError(self._failure_message()) from error

    def evidence(self) -> SinkEvidence:
        with self._lock:
            last_error = None
            if self._last_exception is not None:
                last_error = f"{type(self._last_exception).__name__}: {self._last_exception}"
            return SinkEvidence(
                name=self.name,
                capacity=self.capacity,
                overflow_policy=self.overflow_policy,
                accepted=self._accepted,
                processed=self._processed,
                dropped=self._dropped,
                failed=self._failed,
                backpressure_events=self._backpressure_events,
                backpressure_ns=self._backpressure_ns,
                high_watermark=self._high_watermark,
                started=self._started,
                closed=self._closed,
                last_error=last_error,
            )

    def _mark_accepted(self) -> None:
        with self._lock:
            self._accepted += 1
            self._high_watermark = max(self._high_watermark, self._queue.qsize())

    def _run(self) -> None:
        while True:
            queued = self._queue.get()
            try:
                if queued is self._STOP:
                    return
                try:
                    self._writer(cast(RecordT, queued))
                except Exception as exc:  # retain evidence and surface on submit/close
                    with self._lock:
                        self._failed += 1
                        self._last_exception = exc
                else:
                    with self._lock:
                        self._processed += 1
            finally:
                self._queue.task_done()

    def _failure_message(self) -> str:
        error = self._last_exception
        if error is None:
            return f"sink {self.name!r} failed"
        return f"sink {self.name!r} worker failed: {type(error).__name__}: {error}"
