from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

from plugins.labstreaminglayer import Labstreaminglayer

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
