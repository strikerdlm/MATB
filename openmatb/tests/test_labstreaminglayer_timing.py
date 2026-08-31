from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest

from core.recordsink import SinkCloseTimeout
from plugins.labstreaminglayer import Labstreaminglayer
from core.event import Event

_module = importlib.import_module("plugins.labstreaminglayer")


def test_push_uses_explicit_lsl_clock_and_returns_clock_metadata():
    plugin = object.__new__(Labstreaminglayer)
    plugin.stream_outlet = MagicMock()
    fake_pylsl = MagicMock()
    fake_pylsl.local_clock.return_value = 123.456
    with patch.object(_module, "pylsl", fake_pylsl), patch.object(
        _module, "perf_counter_ns", side_effect=[10, 20]
    ):
        result = plugin.push("marker")
    plugin.stream_outlet.push_sample.assert_called_once_with(["marker"], 123.456)
    assert result == {
        "lsl_time_s": 123.456,
        "push_started_monotonic_ns": 10,
        "push_finished_monotonic_ns": 20,
    }


def test_lsl_source_identity_is_unique_per_scientific_session():
    fake_pylsl = MagicMock()
    source_ids: list[str] = []
    fake_pylsl.StreamInfo.side_effect = lambda *args, **kwargs: source_ids.append(
        kwargs["source_id"]
    ) or object()

    for session_id in (
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
    ):
        plugin = object.__new__(Labstreaminglayer)
        plugin.logger = MagicMock(scientific_session_id=session_id)
        plugin.parameters = {"pauseatstart": False}
        with patch.object(_module, "pylsl", fake_pylsl), patch.object(
            _module.Instructions, "start"
        ):
            plugin.start()

    assert source_ids == [
        "openmatb-11111111-1111-4111-8111-111111111111",
        "openmatb-22222222-2222-4222-8222-222222222222",
    ]
    assert len(set(source_ids)) == 2


def test_explicit_marker_is_submitted_to_the_bounded_async_logger_sink():
    plugin = object.__new__(Labstreaminglayer)
    plugin.parameters = {"streamsession": False, "marker": "probe-onset"}
    plugin.logger = MagicMock()
    plugin.logger.lsl = None
    plugin.stream_outlet = object()

    with patch.object(_module.Instructions, "update"):
        plugin.update(0.1)

    plugin.logger.submit_lsl_marker.assert_called_once_with(plugin, "probe-onset")
    assert plugin.parameters["marker"] == ""


def test_scheduler_preserves_every_same_tick_explicit_marker_until_plugin_update():
    from core.scheduler import Scheduler

    plugin = object.__new__(Labstreaminglayer)
    plugin.parameters = {"streamsession": False, "marker": ""}
    plugin._marker_queue = []
    plugin.logger = MagicMock()
    plugin.logger.lsl = None
    plugin.stream_outlet = object()
    scheduler = object.__new__(Scheduler)
    scheduler.plugins = {"labstreaminglayer": plugin}
    event_logger = MagicMock()

    with patch("core.scheduler.get_logger", return_value=event_logger):
        scheduler.execute_one_event(
            Event(1, 5, "labstreaminglayer", ["marker", "first"])
        )
        scheduler.execute_one_event(
            Event(2, 5, "labstreaminglayer", ["marker", "second"])
        )
    with patch.object(_module.Instructions, "update"):
        plugin.update(5.0)

    assert [call.args[1] for call in plugin.logger.submit_lsl_marker.call_args_list] == [
        "first",
        "second",
    ]
    assert plugin._marker_queue == []


def test_stop_drains_logger_sink_before_releasing_the_outlet():
    plugin = object.__new__(Labstreaminglayer)
    plugin.logger = MagicMock()
    plugin.logger.lsl = plugin
    plugin.stream_info = object()
    plugin.stream_outlet = object()
    plugin.parameters = {"marker": ""}
    plugin._marker_queue = []

    def drained() -> bool:
        assert plugin.stream_outlet is not None
        return True

    plugin.logger.close_async_sinks.side_effect = drained
    with patch.object(_module.Instructions, "stop") as parent_stop:
        plugin.stop()

    parent_stop.assert_called_once()
    assert plugin.logger.lsl is None
    assert plugin.stream_info is None
    assert plugin.stream_outlet is None


def test_stop_preserves_outlet_when_async_markers_have_not_drained():
    plugin = object.__new__(Labstreaminglayer)
    plugin.logger = MagicMock()
    plugin.logger.lsl = plugin
    stream_info = object()
    stream_outlet = object()
    plugin.stream_info = stream_info
    plugin.stream_outlet = stream_outlet
    plugin.parameters = {"marker": ""}
    plugin._marker_queue = []
    plugin.logger.close_async_sinks.return_value = False

    with patch.object(_module.Instructions, "stop") as parent_stop, pytest.raises(
        SinkCloseTimeout, match="before the LSL outlet could be released"
    ):
        plugin.stop()

    parent_stop.assert_not_called()
    assert plugin.logger.lsl is plugin
    assert plugin.stream_info is stream_info
    assert plugin.stream_outlet is stream_outlet


def test_same_tick_marker_is_flushed_before_stop_closes_the_sink():
    plugin = object.__new__(Labstreaminglayer)
    plugin.parameters = {"marker": ""}
    plugin._marker_queue = ["trial-boundary"]
    plugin.logger = MagicMock()
    plugin.logger.lsl = plugin
    plugin.logger.close_async_sinks.return_value = True
    plugin.stream_info = object()
    plugin.stream_outlet = object()
    calls: list[str] = []
    plugin.logger.submit_lsl_marker.side_effect = lambda *_args: calls.append("submit") or True
    plugin.logger.close_async_sinks.side_effect = lambda: calls.append("close") or True

    with patch.object(_module.Instructions, "stop"):
        plugin.stop()

    assert calls == ["submit", "close"]
    plugin.logger.submit_lsl_marker.assert_called_once_with(plugin, "trial-boundary")
    assert plugin._marker_queue == []
