"""Behavioral tests for bounded asynchronous scientific sinks."""

from __future__ import annotations

from threading import Event
from time import monotonic

import pytest


def test_sink_preserves_fifo_order_and_drains_before_close():
    from core.recordsink import BoundedAsyncSink

    observed: list[int] = []
    sink = BoundedAsyncSink(name="raw-events", writer=observed.append, capacity=4)

    for value in range(4):
        assert sink.submit(value) is True
    sink.close()

    assert observed == [0, 1, 2, 3]
    evidence = sink.evidence()
    assert evidence.accepted == 4
    assert evidence.processed == 4
    assert evidence.dropped == 0
    assert evidence.failed == 0
    assert evidence.closed is True


def test_drop_newest_policy_records_explicit_overflow_evidence():
    from core.recordsink import BoundedAsyncSink

    observed: list[str] = []
    sink = BoundedAsyncSink(
        name="optional-stream",
        writer=observed.append,
        capacity=1,
        overflow_policy="drop_newest",
        autostart=False,
    )

    assert sink.submit("preserved") is True
    assert sink.submit("dropped") is False
    before_start = sink.evidence()
    assert before_start.accepted == 1
    assert before_start.dropped == 1
    assert before_start.high_watermark == 1

    sink.start()
    sink.close()
    assert observed == ["preserved"]


def test_block_policy_exposes_backpressure_without_dropping_records():
    from core.recordsink import BoundedAsyncSink

    release_writer = Event()
    writer_started = Event()
    observed: list[str] = []

    def slow_writer(value: str) -> None:
        writer_started.set()
        release_writer.wait(timeout=2)
        observed.append(value)

    sink = BoundedAsyncSink(name="authoritative", writer=slow_writer, capacity=1)
    assert sink.submit("in-flight") is True
    assert writer_started.wait(timeout=1)
    assert sink.submit("queued") is True

    submitted = Event()

    def submit_blocked_record() -> None:
        sink.submit("backpressured")
        submitted.set()

    from threading import Thread

    producer = Thread(target=submit_blocked_record, daemon=True)
    producer.start()
    assert submitted.wait(timeout=0.05) is False
    release_writer.set()
    assert submitted.wait(timeout=1)
    producer.join(timeout=1)
    sink.close()

    assert observed == ["in-flight", "queued", "backpressured"]
    evidence = sink.evidence()
    assert evidence.dropped == 0
    assert evidence.backpressure_events >= 1
    assert evidence.backpressure_ns > 0


def test_worker_failure_is_retained_and_raised_at_close():
    from core.recordsink import BoundedAsyncSink, SinkWorkerError

    def broken_writer(_value: str) -> None:
        raise OSError("disk unavailable")

    sink = BoundedAsyncSink(name="raw-events", writer=broken_writer, capacity=2)
    sink.submit("event")

    with pytest.raises(SinkWorkerError, match="disk unavailable"):
        sink.close()

    evidence = sink.evidence()
    assert evidence.failed == 1
    assert evidence.last_error == "OSError: disk unavailable"


def test_close_timeout_covers_a_full_queue_before_the_stop_marker_can_be_enqueued():
    """A hung optional integration must not bypass the configured close deadline."""
    from core.recordsink import BoundedAsyncSink, SinkCloseTimeout

    writer_started = Event()
    release_writer = Event()

    def hung_writer(_value: str) -> None:
        writer_started.set()
        release_writer.wait(timeout=2)

    sink = BoundedAsyncSink(name="hung-stream", writer=hung_writer, capacity=1)
    sink.submit("in-flight")
    assert writer_started.wait(timeout=1)
    sink.submit("queue-is-full")

    started = monotonic()
    with pytest.raises(SinkCloseTimeout, match="did not drain"):
        sink.close(timeout_s=0.05)
    assert monotonic() - started < 0.5

    release_writer.set()
    sink.close(timeout_s=1.0)


def test_close_timeout_includes_waiting_for_a_blocked_producer():
    """Close remains bounded even when a backpressured submit owns the submit lock."""
    from threading import Thread

    from core.recordsink import BoundedAsyncSink, SinkCloseTimeout

    writer_started = Event()
    release_writer = Event()

    def hung_writer(_value: str) -> None:
        writer_started.set()
        release_writer.wait(timeout=2)

    sink = BoundedAsyncSink(name="blocked-producer", writer=hung_writer, capacity=1)
    sink.submit("in-flight")
    assert writer_started.wait(timeout=1)
    sink.submit("queued")

    producer_done = Event()
    producer = Thread(
        target=lambda: (sink.submit("blocked"), producer_done.set()),
        daemon=True,
    )
    producer.start()
    assert producer_done.wait(timeout=0.05) is False

    started = monotonic()
    with pytest.raises(SinkCloseTimeout, match="did not begin closing"):
        sink.close(timeout_s=0.05)
    assert monotonic() - started < 0.5

    release_writer.set()
    assert producer_done.wait(timeout=1)
    producer.join(timeout=1)
    sink.close(timeout_s=1.0)
