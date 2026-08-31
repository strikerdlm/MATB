"""Tests for core.logger - Logger slot formatting, queue management, and record methods."""

import importlib
import io
import json
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier, Event as ThreadEvent
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from core.event import Event
from core.logger import AuthoritativeLogFailure, TIMING_SAMPLE_CAPACITY, Logger
from core.scenarioprovenance import BoundScenarioManifest

# core.__init__ re-exports the Logger instance as `core.logger`, shadowing
# the module.  Use importlib to get the actual module for patching.
_logger_module = importlib.import_module("core.logger")


def _make_logger(**overrides):
    """Create a Logger instance bypassing __init__ to avoid file I/O."""
    lg = object.__new__(Logger)
    lg.fields_list = ["logtime", "scenario_time", "type", "module", "address", "value"]
    lg.slot = namedtuple("Row", lg.fields_list)
    lg.maxfloats = 6
    lg.scenario_time = 0
    lg.session_id = 1
    lg.lsl = None
    lg.queue = []
    lg.file = None
    lg.writer = MagicMock()
    lg.__dict__.update(overrides)
    return lg


# ── round_row ────────────────────────────────────


class TestRoundRow:
    def test_rounds_floats(self):
        """Float values are rounded to maxfloats decimals."""
        lg = _make_logger()
        row = [1.123456789, 0, "event", "sysmon", "self", "start"]
        result = lg.round_row(row)
        assert result.logtime == round(1.123456789, 6)

    def test_rounds_ints(self):
        """Integer values are passed through round() but stay unchanged."""
        lg = _make_logger()
        row = [1, 0, "event", "sysmon", "self", "start"]
        result = lg.round_row(row)
        assert result.logtime == 1

    def test_preserves_strings(self):
        """String values are not rounded."""
        lg = _make_logger()
        row = [1.0, 0, "event", "sysmon", "self", "start"]
        result = lg.round_row(row)
        assert result.type == "event"
        assert result.module == "sysmon"
        assert result.address == "self"
        assert result.value == "start"

    def test_returns_namedtuple(self):
        """Result is a Row namedtuple with correct fields."""
        lg = _make_logger()
        row = [1.0, 0, "event", "sysmon", "self", "start"]
        result = lg.round_row(row)
        assert hasattr(result, "logtime")
        assert hasattr(result, "scenario_time")
        assert hasattr(result, "type")


# ── Queue management ─────────────────────────────


class TestQueueManagement:
    def test_add_row_to_queue(self):
        """add_row_to_queue appends to the queue."""
        lg = _make_logger()
        lg.add_row_to_queue("row1")
        lg.add_row_to_queue("row2")
        assert lg.queue == ["row1", "row2"]

    def test_empty_queue(self):
        """empty_queue clears all items."""
        lg = _make_logger()
        lg.queue = ["a", "b", "c"]
        lg.empty_queue()
        assert lg.queue == []

    def test_empty_queue_on_fresh(self):
        """Emptying an already-empty queue is a no-op."""
        lg = _make_logger()
        lg.empty_queue()
        assert lg.queue == []


# ── Setters ──────────────────────────────────────


class TestSetters:
    def test_set_scenario_time(self):
        """set_scenario_time updates scenario_time attribute."""
        lg = _make_logger()
        lg.set_scenario_time(42.5)
        assert lg.scenario_time == 42.5

    def test_set_totaltime(self):
        """set_totaltime stores totaltime attribute."""
        lg = _make_logger()
        lg.set_totaltime(300)
        assert lg.totaltime == 300


# ── record_event ─────────────────────────────────


class TestRecordEvent:
    @patch.object(_logger_module, "perf_counter", return_value=1.0)
    def test_single_command_uses_self_address(self, _mock_pc):
        """Single-command event uses address='self'."""
        lg = _make_logger(scenario_time=10)
        lg.write_single_slot = MagicMock()
        event = Event(1, 60, "sysmon", "start")
        lg.record_event(event)
        args = lg.write_single_slot.call_args[0][0]
        assert args[2] == "event"
        assert args[3] == "sysmon"
        assert args[4] == "self"
        assert args[5] == "start"

    @patch.object(_logger_module, "perf_counter", return_value=1.0)
    def test_two_command_uses_address_value(self, _mock_pc):
        """Two-command event uses command[0] as address, command[1] as value."""
        lg = _make_logger(scenario_time=10)
        lg.write_single_slot = MagicMock()
        event = Event(1, 60, "resman", ["pump-1-state", "on"])
        lg.record_event(event)
        args = lg.write_single_slot.call_args[0][0]
        assert args[4] == "pump-1-state"
        assert args[5] == "on"

    @patch.object(_logger_module, "perf_counter", return_value=1.0)
    def test_uses_current_scenario_time(self, _mock_pc):
        """Slot uses the logger's current scenario_time."""
        lg = _make_logger(scenario_time=99.5)
        lg.write_single_slot = MagicMock()
        event = Event(1, 60, "track", "start")
        lg.record_event(event)
        args = lg.write_single_slot.call_args[0][0]
        assert args[1] == 99.5

    @patch.object(_logger_module, "perf_counter", return_value=1.0)
    def test_dispatch_failure_is_a_terminal_structured_runtime_record(self, _mock_pc):
        lg = _make_logger(scenario_time=10)
        lg.write_single_slot = MagicMock()
        event = Event(7, 10, "sysmon", "start")

        lg.record_event_failure(
            event,
            dispatch_start_monotonic_ns=1_000,
            dispatch_end_monotonic_ns=1_275,
            error_type="RuntimeError",
            error_message="simulated dispatch failure",
            failure_phase="command_dispatch",
        )

        slot = lg.write_single_slot.call_args.args[0]
        metadata = lg.write_single_slot.call_args.kwargs["metadata"]
        assert slot == [
            1.0,
            10,
            "event_dispatch_failure",
            "sysmon",
            "start",
            "RuntimeError",
        ]
        assert metadata == {
            "scheduled_scenario_time_s": 10,
            "scenario_line": 7,
            "dispatch_start_monotonic_ns": 1_000,
            "dispatch_end_monotonic_ns": 1_275,
            "dispatch_status": "failed_terminal",
            "session_status": "invalid_dispatch_failure",
            "failed_command": ["start"],
            "error_type": "RuntimeError",
            "error_message": "simulated dispatch failure",
            "failure_phase": "command_dispatch",
        }


# ── record_input ─────────────────────────────────


class TestRecordInput:
    @patch.object(_logger_module, "perf_counter", return_value=2.0)
    def test_formats_input_slot(self, _mock_pc):
        """Builds slot with type='input', module, key, state."""
        lg = _make_logger(scenario_time=5)
        lg.write_single_slot = MagicMock()
        lg.record_input("keyboard", "F1", "press")
        args = lg.write_single_slot.call_args[0][0]
        assert args == [2.0, 5, "input", "keyboard", "F1", "press"]


# ── record_aoi ───────────────────────────────────


class TestRecordAoi:
    @patch.object(_logger_module, "perf_counter", return_value=3.0)
    def test_parses_plugin_and_widget(self, _mock_pc):
        """Splits 'plugin_widget' name into plugin and widget parts."""
        lg = _make_logger(scenario_time=0)
        lg.write_single_slot = MagicMock()
        container = MagicMock()
        container.get_x1y1x2y2.return_value = (10, 70, 110, 20)
        lg.record_aoi(container, "sysmon_scale1")
        args = lg.write_single_slot.call_args[0][0]
        assert args[2] == "aoi"
        assert args[3] == "sysmon"
        assert args[4] == "scale1"
        assert args[5] == (10, 70, 110, 20)

    @patch.object(_logger_module, "perf_counter", return_value=3.0)
    def test_multi_underscore_widget_name(self, _mock_pc):
        """Widget name with multiple underscores keeps all parts after first."""
        lg = _make_logger(scenario_time=0)
        lg.write_single_slot = MagicMock()
        container = MagicMock()
        container.get_x1y1x2y2.return_value = (0, 0, 0, 0)
        lg.record_aoi(container, "track_cursor_inner")
        args = lg.write_single_slot.call_args[0][0]
        assert args[3] == "track"
        assert args[4] == "cursor_inner"


# ── record_state ─────────────────────────────────


class TestRecordState:
    @patch.object(_logger_module, "perf_counter", return_value=4.0)
    def test_parses_graph_name(self, _mock_pc):
        """Splits graph_name into module and widget, builds address."""
        lg = _make_logger(scenario_time=0)
        lg.write_single_slot = MagicMock()
        lg.record_state("sysmon_light1", "color", "(255,0,0)")
        args = lg.write_single_slot.call_args[0][0]
        assert args[2] == "state"
        assert args[3] == "sysmon"
        assert args[4] == "light1, color"
        assert args[5] == "(255,0,0)"

    @patch.object(_logger_module, "perf_counter", return_value=4.0)
    def test_multi_underscore_graph_name(self, _mock_pc):
        """Graph name with multiple underscores preserves widget parts."""
        lg = _make_logger(scenario_time=0)
        lg.write_single_slot = MagicMock()
        lg.record_state("resman_tank_a", "level", 2500)
        args = lg.write_single_slot.call_args[0][0]
        assert args[3] == "resman"
        assert args[4] == "tank_a, level"


# ── record_parameter ─────────────────────────────


class TestRecordParameter:
    @patch.object(_logger_module, "perf_counter", return_value=5.0)
    def test_formats_parameter_slot(self, _mock_pc):
        """Builds slot with type='parameter'."""
        lg = _make_logger(scenario_time=10)
        lg.write_single_slot = MagicMock()
        lg.record_parameter("sysmon", "alerttimeout", 10000)
        args = lg.write_single_slot.call_args[0][0]
        assert args == [5.0, 10, "parameter", "sysmon", "alerttimeout", 10000]


# ── log_performance ──────────────────────────────


class TestLogPerformance:
    @patch.object(_logger_module, "perf_counter", return_value=6.0)
    def test_formats_performance_slot(self, _mock_pc):
        """Builds slot with type='performance'."""
        lg = _make_logger(scenario_time=20)
        lg.write_single_slot = MagicMock()
        lg.log_performance("track", "deviation", 0.05)
        args = lg.write_single_slot.call_args[0][0]
        assert args == [6.0, 20, "performance", "track", "deviation", 0.05]


# ── record_a_pseudorandom_value ──────────────────


class TestRecordPseudorandomValue:
    @patch.object(_logger_module, "perf_counter", return_value=7.0)
    def test_writes_two_slots(self, _mock_pc):
        """Writes both seed_value and seed_output slots."""
        lg = _make_logger(scenario_time=0)
        lg.write_single_slot = MagicMock()
        lg.record_a_pseudorandom_value("communications", 42, "result")
        assert lg.write_single_slot.call_count == 2

    @patch.object(_logger_module, "perf_counter", return_value=7.0)
    def test_seed_value_slot(self, _mock_pc):
        """First slot has type='seed_value' with the seed."""
        lg = _make_logger(scenario_time=0)
        lg.write_single_slot = MagicMock()
        lg.record_a_pseudorandom_value("communications", 42, "result")
        first_args = lg.write_single_slot.call_args_list[0][0][0]
        assert first_args[2] == "seed_value"
        assert first_args[5] == 42

    @patch.object(_logger_module, "perf_counter", return_value=7.0)
    def test_seed_output_slot(self, _mock_pc):
        """Second slot has type='seed_output' with the output."""
        lg = _make_logger(scenario_time=0)
        lg.write_single_slot = MagicMock()
        lg.record_a_pseudorandom_value("communications", 42, "result")
        second_args = lg.write_single_slot.call_args_list[1][0][0]
        assert second_args[2] == "seed_output"
        assert second_args[5] == "result"


# ── log_manual_entry ─────────────────────────────


class TestLogManualEntry:
    @patch.object(_logger_module, "perf_counter", return_value=8.0)
    def test_default_key(self, _mock_pc):
        """Default type is 'manual'."""
        lg = _make_logger(scenario_time=0)
        lg.write_single_slot = MagicMock()
        lg.log_manual_entry("user note")
        args = lg.write_single_slot.call_args[0][0]
        assert args[2] == "manual"
        assert args[5] == "user note"

    @patch.object(_logger_module, "perf_counter", return_value=8.0)
    def test_custom_key(self, _mock_pc):
        """Custom key replaces 'manual' type."""
        lg = _make_logger(scenario_time=0)
        lg.write_single_slot = MagicMock()
        lg.log_manual_entry("note", key="custom")
        args = lg.write_single_slot.call_args[0][0]
        assert args[2] == "custom"

    @patch.object(_logger_module, "perf_counter", return_value=8.0)
    def test_end_marker_writes_timing_qc(self, _mock_pc):
        """Normal scheduler completion materializes the timing-QC sidecar."""
        lg = _make_logger()
        lg.write_single_slot = MagicMock()
        lg.write_timing_qc = MagicMock()
        lg.log_manual_entry("end", key="control")
        lg.write_timing_qc.assert_called_once_with()

    @patch.object(_logger_module, "perf_counter", return_value=8.0)
    def test_end_marker_refuses_successful_termination_while_sink_is_live(self, _mock_pc):
        """A daemon sink timeout must be visible instead of losing accepted markers."""
        from core.recordsink import SinkCloseTimeout

        lg = _make_logger()
        lg.write_single_slot = MagicMock()
        lg.write_timing_qc = MagicMock()
        lg.close_async_sinks = MagicMock(return_value=False)

        with pytest.raises(SinkCloseTimeout, match="terminal marker"):
            lg.log_manual_entry("end")
        lg.write_timing_qc.assert_called_once_with()

    @patch.object(_logger_module, "perf_counter", return_value=8.0)
    def test_end_marker_retry_drains_without_writing_duplicate_terminal_event(self, _mock_pc):
        from core.recordsink import SinkCloseTimeout

        lg = _make_logger()
        lg.write_single_slot = MagicMock()
        lg.write_timing_qc = MagicMock()
        lg.close_async_sinks = MagicMock(side_effect=[False, True])

        with pytest.raises(SinkCloseTimeout, match="terminal marker"):
            lg.log_manual_entry("end")
        lg.log_manual_entry("end")

        lg.write_single_slot.assert_called_once()
        assert lg._terminal_marker_persisted is True
        assert lg._terminal_shutdown_complete is True


# ── write_single_slot ────────────────────────────


class TestWriteSingleSlot:
    @patch.object(_logger_module, "REPLAY_MODE", False)
    def test_adds_to_queue_and_writes(self):
        """Slot is queued then written via write_row_queue."""
        lg = _make_logger()
        values = [1.0, 0, "event", "sysmon", "self", "start"]
        lg.write_single_slot(values)
        # After write_row_queue, queue should be emptied
        assert lg.queue == []
        lg.writer.writerow.assert_called_once()

    @patch.object(_logger_module, "REPLAY_MODE", False)
    def test_written_row_has_correct_fields(self):
        """Written dict has all 6 expected fields."""
        lg = _make_logger()
        values = [1.0, 0, "event", "sysmon", "self", "start"]
        lg.write_single_slot(values)
        written = lg.writer.writerow.call_args[0][0]
        assert set(written.keys()) == set(lg.fields_list)
        assert written["type"] == "event"
        assert written["module"] == "sysmon"


# ── write_row_queue ──────────────────────────────


class TestWriteRowQueue:
    @patch.object(_logger_module, "REPLAY_MODE", False)
    def test_writes_all_queued_rows(self):
        """All queued rows are written and queue is emptied."""
        lg = _make_logger()
        lg.queue = [
            lg.slot(1.0, 0, "event", "sysmon", "self", "start"),
            lg.slot(2.0, 1, "event", "track", "self", "start"),
        ]
        lg.write_row_queue()
        assert lg.writer.writerow.call_count == 2
        assert lg.queue == []

    @patch.object(_logger_module, "REPLAY_MODE", False)
    def test_change_dict_overrides_fields(self):
        """change_dict overrides specific fields in each row."""
        lg = _make_logger()
        lg.queue = [lg.slot(1.0, 0, "event", "sysmon", "self", "start")]
        lg.write_row_queue(change_dict={"module": "OVERRIDE"})
        written = lg.writer.writerow.call_args[0][0]
        assert written["module"] == "OVERRIDE"

    @patch.object(_logger_module, "REPLAY_MODE", False)
    def test_empty_queue_prints_warning(self, capsys=None):
        """Empty queue prints a warning instead of writing."""
        lg = _make_logger()
        lg.write_row_queue()  # queue is empty
        lg.writer.writerow.assert_not_called()

    @patch.object(_logger_module, "REPLAY_MODE", True)
    def test_replay_mode_skips_writing(self):
        """In replay mode, nothing is written."""
        lg = _make_logger()
        lg.queue = [lg.slot(1.0, 0, "event", "sysmon", "self", "start")]
        lg.write_row_queue()
        lg.writer.writerow.assert_not_called()

    @patch.object(_logger_module, "REPLAY_MODE", False)
    def test_lsl_push_when_enabled(self):
        """When lsl is set, each row is also pushed to LSL."""
        mock_lsl = MagicMock()
        lg = _make_logger(lsl=mock_lsl)
        lg.queue = [lg.slot(1.0, 0, "event", "sysmon", "self", "start")]
        lg.write_row_queue()
        lg.close_async_sinks()
        mock_lsl.push.assert_called_once()

    @patch.object(_logger_module, "REPLAY_MODE", False)
    def test_jsonl_failure_never_writes_or_replays_legacy_csv(self):
        class FailingEvents:
            def write(self, _value):
                raise OSError("disk full")

        lg = _make_logger(events_file=FailingEvents(), event_sequence=0)
        values = [1.0, 0, "event", "sysmon", "self", "start"]

        with pytest.raises(AuthoritativeLogFailure, match="authoritative JSONL"):
            lg.write_single_slot(values)

        assert lg.writer.writerow.call_count == 0
        assert lg.queue == []
        with pytest.raises(AuthoritativeLogFailure, match="fail-stop"):
            lg.write_single_slot(values)
        assert lg.writer.writerow.call_count == 0

    @patch.object(_logger_module, "REPLAY_MODE", False)
    def test_csv_failure_is_not_retried_and_jsonl_remains_authoritative(self):
        events = io.StringIO()
        lg = _make_logger(events_file=events, event_sequence=0)
        lg.writer.writerow.side_effect = OSError("legacy sink unavailable")

        lg.write_single_slot([1.0, 0, "event", "sysmon", "self", "start"])
        lg.write_single_slot([2.0, 1, "event", "track", "self", "start"])

        assert len(events.getvalue().splitlines()) == 2
        assert lg.writer.writerow.call_count == 1
        assert lg.queue == []
        evidence = lg.timing_qc_summary()["sinks"]["legacy_csv"]
        assert evidence["status"] == "failed_disabled"
        assert evidence["failure_count"] == 1

    @patch.object(_logger_module, "REPLAY_MODE", False)
    def test_lsl_publish_runs_off_the_authoritative_logger_call_path(self):
        """A stalled network marker outlet must not stall local event persistence."""
        push_started = ThreadEvent()
        release_push = ThreadEvent()

        def slow_push(_message):
            push_started.set()
            release_push.wait(timeout=2)
            return {"lsl_time_s": 123.5}

        mock_lsl = MagicMock()
        mock_lsl.push.side_effect = slow_push
        lg = _make_logger(lsl=mock_lsl, lsl_observations_file=io.StringIO())

        lg.write_single_slot([1.0, 0, "event", "sysmon", "self", "start"])
        assert lg.writer.writerow.call_count == 1
        assert push_started.wait(timeout=1)

        release_push.set()
        lg.close_async_sinks()
        evidence = lg.timing_qc_summary()["sinks"]["lsl"]
        assert evidence["accepted"] == 1
        assert evidence["processed"] == 1
        assert evidence["dropped"] == 0

    @patch.object(_logger_module, "REPLAY_MODE", False)
    def test_lsl_observation_is_reconciled_to_source_sequence(self):
        """Async LSL timestamps remain linkable without mutating the raw event."""
        mock_lsl = MagicMock()
        mock_lsl.push.return_value = {
            "lsl_time_s": 123.5,
            "push_started_monotonic_ns": 5_000,
            "push_finished_monotonic_ns": 5_100,
        }
        observations = io.StringIO()
        lg = _make_logger(
            lsl=mock_lsl,
            events_file=io.StringIO(),
            lsl_observations_file=observations,
            event_sequence=0,
        )

        lg.write_single_slot([1.0, 0, "event", "sysmon", "self", "start"])
        lg.close_async_sinks()

        observation = json.loads(observations.getvalue())
        assert observation["schema_version"] == "1.0"
        assert observation["source_sequence"] == 1
        assert observation["lsl_time_s"] == 123.5
        assert observation["push_started_monotonic_ns"] == 5_000
        assert observation["push_finished_monotonic_ns"] == 5_100

    def test_lsl_queue_drop_names_the_exact_source_event_in_observation_evidence(self):
        sink = MagicMock()
        sink.submit.return_value = False
        observations = io.StringIO()
        lg = _make_logger(lsl_observations_file=observations)
        lg._ensure_lsl_sink = MagicMock(return_value=sink)

        accepted = lg.submit_lsl_marker(
            object(),
            "marker",
            source_sequence=7,
            source_event_id="event-7",
        )

        assert accepted is False
        evidence = json.loads(observations.getvalue())
        assert evidence["delivery_status"] == "dropped"
        assert evidence["drop_reason"] == "queue_full_drop_newest"
        assert evidence["source_sequence"] == 7
        assert evidence["source_event_id"] == "event-7"

    @patch.object(_logger_module, "REPLAY_MODE", False)
    def test_explicit_lsl_markers_reconcile_to_their_exact_same_tick_commands(self):
        events = io.StringIO()
        lg = _make_logger(events_file=events, event_sequence=0)
        lg.record_event(Event(1, 10, "labstreaminglayer", ["marker", "first"]))
        lg.record_event(Event(2, 10, "labstreaminglayer", ["marker", "second"]))
        runtime_events = [json.loads(line) for line in events.getvalue().splitlines()]
        sink = MagicMock()
        sink.submit.return_value = True
        lg._ensure_lsl_sink = MagicMock(return_value=sink)

        assert lg.submit_lsl_marker(object(), "first") is True
        assert lg.submit_lsl_marker(object(), "second") is True

        submitted = [call.args[0] for call in sink.submit.call_args_list]
        assert [record["source_sequence"] for record in submitted] == [1, 2]
        assert [record["source_event_id"] for record in submitted] == [
            runtime_events[0]["event_id"],
            runtime_events[1]["event_id"],
        ]

    @pytest.mark.parametrize(
        ("push_result", "push_error", "failure_reason"),
        [
            (None, None, "missing_or_invalid_lsl_timestamp"),
            (None, OSError("outlet unavailable"), "push_exception"),
        ],
    )
    def test_lsl_delivery_failure_is_source_linked_and_counted(
        self, push_result, push_error, failure_reason
    ):
        target = MagicMock()
        if push_error is not None:
            target.push.side_effect = push_error
        else:
            target.push.return_value = push_result
        observations = io.StringIO()
        lg = _make_logger(lsl_observations_file=observations)

        assert lg.submit_lsl_marker(
            target,
            "marker",
            source_sequence=12,
            source_event_id="event-12",
        ) is True
        assert lg.close_async_sinks() is True

        observation = json.loads(observations.getvalue())
        assert observation["delivery_status"] == "failed"
        assert observation["failure_reason"] == failure_reason
        assert observation["source_sequence"] == 12
        assert observation["source_event_id"] == "event-12"
        assert lg._last_lsl_sink_evidence["failed"] == 1
        assert lg._last_lsl_sink_evidence["processed"] == 0

    def test_lsl_close_timeout_preserves_the_live_sink_for_a_safe_retry(self):
        from core.recordsink import SinkCloseTimeout

        sink = MagicMock()
        sink.close.side_effect = SinkCloseTimeout("still draining")
        sink.evidence.return_value.to_dict.return_value = {"closed": False}
        target = object()
        observations = io.StringIO()
        lg = _make_logger(
            _lsl_sink=sink,
            _lsl_sink_target=target,
            lsl_observations_file=observations,
        )

        assert lg.close_async_sinks(timeout_s=0.01) is False
        assert lg._lsl_sink is sink
        assert lg._lsl_sink_target is target
        assert observations.closed is False

    def test_lsl_marker_after_stop_timeout_is_failure_isolated_and_source_linked(self):
        from core.recordsink import SinkCloseTimeout

        sink = MagicMock()
        sink.close.side_effect = SinkCloseTimeout("still draining")
        sink.evidence.return_value.to_dict.return_value = {"closed": False}
        sink.submit.side_effect = RuntimeError("sink 'lsl' is closing")
        target = object()
        observations = io.StringIO()
        lg = _make_logger(
            lsl=target,
            _lsl_sink=sink,
            _lsl_sink_target=target,
            lsl_observations_file=observations,
        )

        assert lg.close_async_sinks(timeout_s=0.01) is False
        assert lg.submit_lsl_marker(
            target,
            "failed-stop-marker",
            source_sequence=42,
            source_event_id="event-42",
            marker_kind="runtime_record",
        ) is False

        observation = json.loads(observations.getvalue())
        assert observation["delivery_status"] == "failed"
        assert observation["failure_reason"] == "sink_state_unavailable"
        assert observation["source_sequence"] == 42
        assert observation["source_event_id"] == "event-42"

    def test_logger_close_never_closes_an_observation_file_used_by_a_live_sink(self):
        from core.recordsink import SinkCloseTimeout

        sink = MagicMock()
        sink.close.side_effect = SinkCloseTimeout("still draining")
        sink.evidence.return_value.to_dict.return_value = {"closed": False}
        observations = io.StringIO()
        lg = _make_logger(
            _lsl_sink=sink,
            _lsl_sink_target=object(),
            lsl_observations_file=observations,
        )

        with pytest.raises(SinkCloseTimeout, match="observation file remains open"):
            lg.close()
        assert observations.closed is False
        assert lg._lsl_sink is sink

    def test_optional_lsl_observation_sidecar_failure_never_fails_authoritative_session(self):
        class FailingObservations:
            closed = False

            def write(self, _value):
                raise OSError("observation disk unavailable")

            def flush(self):
                return None

        lg = _make_logger(lsl_observations_file=FailingObservations())

        assert lg._write_lsl_observation({"delivery_status": "delivered"}) is False
        evidence = lg.timing_qc_summary()["sinks"]["lsl_observations_jsonl"]
        assert evidence["status"] == "failed_disabled"
        assert evidence["failure_count"] == 1


def test_concurrent_logger_construction_atomically_claims_distinct_session_ids(
    tmp_path,
    monkeypatch,
):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 8, 31, 12, 0, 0)
            return value if tz is None else value.replace(tzinfo=tz)

    sessions = tmp_path / "sessions"
    gate = Barrier(2)

    def same_initial_candidate():
        gate.wait(timeout=2)
        return 1

    monkeypatch.setitem(_logger_module.PATHS, "SESSIONS", sessions)
    monkeypatch.setattr(_logger_module, "REPLAY_MODE", False)
    monkeypatch.setattr(_logger_module, "datetime", FixedDateTime)
    monkeypatch.setattr(
        _logger_module,
        "find_the_first_available_session_number",
        same_initial_candidate,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        loggers = list(executor.map(lambda _index: Logger(), range(2)))
    try:
        assert {logger.session_id for logger in loggers} == {1, 2}
        assert len({logger.path for logger in loggers}) == 2
    finally:
        for logger in loggers:
            logger.close()


class TestVersionedEventAndTimingQc:
    @patch.object(_logger_module, "REPLAY_MODE", False)
    def test_session_manifest_identity_is_uniform_and_archived(self, tmp_path):
        events = io.StringIO()
        manifest_content = b'{"manifest_version":3}\n'
        manifest_digest = __import__("hashlib").sha256(manifest_content).hexdigest()
        evidence = {
            "schema_version": "1.0",
            "status": "verified",
            "scenario_sha256": "a" * 64,
            "adjacent_manifest_filename": "scenario.txt.manifest.json",
            "scenario_manifest_sha256": manifest_digest,
            "manifest_identity": {
                "manifest_schema_version": "3",
                "metrics_schema_version": "2.0",
                "experiment_spec_sha256": "c" * 64,
                "experiment_seed": 42,
                "scenario_compiler_id": "matb_integration.scenario_builder",
                "scenario_compiler_version": "3.0.0",
            },
        }
        provenance_path = tmp_path / "session.scenario_provenance.json"
        archive_path = tmp_path / "session.scenario.manifest.json"
        lg = _make_logger(
            events_file=events,
            event_sequence=0,
            scenario_provenance_path=provenance_path,
            scenario_manifest_archive_path=archive_path,
        )
        lg.configure_scientific_context(
            scenario_sha256="a" * 64,
            profile_id="MATB-EXTENDED-2.0",
            source_commit="b" * 40,
            source_dirty=False,
            component_version="1.4.5",
            scenario_manifest_evidence=evidence,
        )
        lg.archive_scenario_manifest(
            BoundScenarioManifest(evidence=evidence, content=manifest_content)
        )
        lg.log_manual_entry("1.4.5", key="version")

        payloads = [json.loads(line) for line in events.getvalue().splitlines()]
        assert len(payloads) == 3
        assert {item["runtime_contract_status"] for item in payloads} == {"complete"}
        assert {item["scenario_manifest_sha256"] for item in payloads} == {
            manifest_digest
        }
        assert {item["experiment_spec_sha256"] for item in payloads} == {"c" * 64}
        assert {item["experiment_seed"] for item in payloads} == {42}
        assert archive_path.read_bytes() == manifest_content
        assert json.loads(provenance_path.read_text())["status"] == "verified"

    @patch.object(_logger_module, "REPLAY_MODE", False)
    def test_jsonl_event_is_additive_and_versioned(self):
        events = io.StringIO()
        lg = _make_logger(events_file=events, event_sequence=0)
        lg.write_single_slot(
            [1.0, 10.25, "event", "sysmon", "self", "start"],
            metadata={"scheduled_scenario_time_s": 10.0, "scenario_line": 7},
        )
        payload = json.loads(events.getvalue())
        assert payload["event_schema_version"] == "1.0"
        assert payload["sequence"] == 1
        assert payload["scenario_line"] == 7
        assert payload["dispatch_lateness_ms"] == 250.0
        assert lg.writer.writerow.call_count == 1  # legacy CSV remains present

    @patch.object(_logger_module, "REPLAY_MODE", False)
    def test_jsonl_event_has_deterministic_identity_and_truthful_provenance_status(self):
        """Every runtime record is stably addressable without inventing missing evidence."""
        events = io.StringIO()
        session_uuid = UUID("12345678-1234-5678-1234-567812345678")
        lg = _make_logger(
            events_file=events,
            event_sequence=0,
            _scientific_session_uuid=session_uuid,
            _scientific_context={
                "scenario_sha256": "a" * 64,
                "profile_id": "openmatb-1.4.5-derived",
                "source_commit": "48e9dbaa946349021d2ce2186d599c1f82182ab4",
                "source_dirty": False,
                "component_version": "1.4.5",
                "scenario_manifest_status": "verified",
            },
        )

        lg.write_single_slot([1.0, 10.0, "event", "sysmon", "self", "start"])

        payload = json.loads(events.getvalue())
        expected = Logger.expected_event_id(
            session_id=session_uuid,
            sequence=1,
            event_type="event",
        )
        assert payload["event_id"] == str(expected)
        assert payload["scientific_session_id"] == str(session_uuid)
        assert payload["scenario_time_ns"] == 10_000_000_000
        assert payload["runtime_contract_status"] == "complete"
        assert payload["scientific_contract_status"] == "not_scientific_event_v3"
        assert payload["scenario_sha256"] == "a" * 64
        assert "scientific_event_schema_version" not in payload

    @pytest.mark.parametrize(
        ("source_dirty", "expected_status"),
        [
            (True, "provisional_dirty_source_tree"),
            (None, "provisional_unverified_source_tree"),
        ],
    )
    def test_jsonl_full_commit_requires_clean_tree_attestation(
        self,
        source_dirty,
        expected_status,
    ):
        events = io.StringIO()
        lg = _make_logger(
            events_file=events,
            event_sequence=0,
            _scientific_context={
                "scenario_sha256": "a" * 64,
                "profile_id": "openmatb-1.4.5-derived",
                "source_commit": "48e9dbaa946349021d2ce2186d599c1f82182ab4",
                "source_dirty": source_dirty,
                "component_version": "1.4.5",
            },
        )

        with patch.object(_logger_module, "REPLAY_MODE", False):
            lg.write_single_slot([1.0, 0.0, "event", "sysmon", "self", "start"])

        assert json.loads(events.getvalue())["runtime_contract_status"] == expected_status

    def test_authoritative_event_envelope_rejects_forged_metadata_before_csv_write(self):
        events = io.StringIO()
        lg = _make_logger(events_file=events, event_sequence=0)

        with pytest.raises(ValueError, match="reserved event metadata"):
            lg.write_single_slot(
                [1.0, 0.0, "event", "sysmon", "self", "start"],
                metadata={"event_id": "forged"},
            )

        lg.writer.writerow.assert_not_called()
        assert events.getvalue() == ""
        assert not hasattr(lg, "_last_runtime_event_id")

    @patch.object(_logger_module, "REPLAY_MODE", False)
    def test_jsonl_marks_missing_scenario_provenance_instead_of_fabricating_it(self):
        events = io.StringIO()
        lg = _make_logger(events_file=events, event_sequence=0)

        lg.write_single_slot([1.0, 0.0, "event", "sysmon", "self", "start"])

        payload = json.loads(events.getvalue())
        assert payload["runtime_contract_status"] == "provisional_missing_provenance"
        assert payload["scientific_contract_status"] == "not_scientific_event_v3"
        assert payload["scenario_sha256"] is None

    @pytest.mark.parametrize("source_commit", ["foo", "n/a", "48e9dbaa", "A" * 40])
    def test_jsonl_never_upgrades_noncanonical_source_commit(
        self,
        source_commit,
    ):
        events = io.StringIO()
        lg = _make_logger(
            events_file=events,
            event_sequence=0,
            _scientific_context={
                "scenario_sha256": "a" * 64,
                "profile_id": "openmatb-1.4.5-derived",
                "source_commit": source_commit,
                "component_version": "1.4.5",
            },
        )

        with patch.object(_logger_module, "REPLAY_MODE", False):
            lg.write_single_slot([1.0, 0.0, "event", "sysmon", "self", "start"])

        payload = json.loads(events.getvalue())
        assert payload["runtime_contract_status"] == "provisional_invalid_source_commit"

    @pytest.mark.parametrize("source_commit", ["UNKNOWN", " unavailable "])
    def test_jsonl_treats_case_and_padding_variants_as_missing_commit_sentinels(
        self,
        source_commit,
    ):
        events = io.StringIO()
        lg = _make_logger(
            events_file=events,
            event_sequence=0,
            _scientific_context={
                "scenario_sha256": "a" * 64,
                "profile_id": "openmatb-1.4.5-derived",
                "source_commit": source_commit,
                "component_version": "1.4.5",
            },
        )

        with patch.object(_logger_module, "REPLAY_MODE", False):
            lg.write_single_slot([1.0, 0.0, "event", "sysmon", "self", "start"])

        payload = json.loads(events.getvalue())
        assert payload["runtime_contract_status"] == "provisional_missing_provenance"
        assert payload["source_commit_status"] == "provisional_missing_provenance"

    @patch.object(_logger_module, "REPLAY_MODE", False)
    def test_jsonl_treats_unavailable_source_commit_as_missing_provenance(self):
        events = io.StringIO()
        lg = _make_logger(
            events_file=events,
            event_sequence=0,
            _scientific_context={
                "scenario_sha256": "a" * 64,
                "profile_id": "openmatb-1.4.5-derived",
                "source_commit": "unavailable",
                "component_version": "1.4.5",
            },
        )

        lg.write_single_slot([1.0, 0.0, "event", "sysmon", "self", "start"])

        payload = json.loads(events.getvalue())
        assert payload["runtime_contract_status"] == "provisional_missing_provenance"

    @patch.object(_logger_module, "REPLAY_MODE", False)
    def test_jsonl_normalizes_legacy_nonfinite_values_to_standard_json_null(self):
        events = io.StringIO()
        lg = _make_logger(events_file=events, event_sequence=0)

        lg.write_single_slot([1.0, 0.0, "performance", "sysmon", "response_time", float("nan")])

        raw = events.getvalue()
        assert "NaN" not in raw
        payload = json.loads(raw, parse_constant=lambda value: pytest.fail(value))
        assert payload["value"] is None
        assert payload["nonfinite_fields_normalized"] == ["value"]

    @patch.object(_logger_module, "REPLAY_MODE", False)
    @patch.object(_logger_module, "perf_counter_ns", side_effect=[123_456_789, 123_500_000])
    def test_jsonl_uses_direct_monotonic_capture_and_dispatch_boundaries(self, _mock_ns):
        """Catch float-derived timestamps and collapsed dispatch intervals."""
        events = io.StringIO()
        lg = _make_logger(events_file=events, event_sequence=0)
        lg.write_single_slot(
            [1.0, 10.0, "event", "sysmon", "self", "start"],
            metadata={
                "scheduled_scenario_time_s": 10.0,
                "dispatch_start_monotonic_ns": 123_000_000,
                "dispatch_end_monotonic_ns": 123_250_000,
            },
        )

        payload = json.loads(events.getvalue())
        assert payload["recorded_monotonic_ns"] == 123_456_789
        assert payload["logger_write_monotonic_ns"] == 123_500_000
        assert payload["dispatch_start_monotonic_ns"] == 123_000_000
        assert payload["dispatch_end_monotonic_ns"] == 123_250_000

    @patch.object(_logger_module, "perf_counter_ns", side_effect=[1_000_000_000, 1_050_000_000])
    def test_set_scenario_time_collects_update_intervals(self, _mock_ns):
        lg = _make_logger()
        lg.set_scenario_time(1.0)
        lg.set_scenario_time(1.05)
        summary = lg.timing_qc_summary()
        assert summary["update_interval"]["n"] == 1
        assert summary["update_interval"]["median_ms"] == 50.0
        assert summary["scenario_delta"]["median_ms"] == 50.0
        assert summary["physical_onset"]["available"] is False

    def test_timing_qc_retention_is_bounded_for_long_sessions(self):
        lg = _make_logger()
        accumulator = lg._timing_accumulator("update_interval")

        for index in range(TIMING_SAMPLE_CAPACITY * 3):
            accumulator.add(float(index % 250))

        summary = lg.timing_qc_summary()["update_interval"]
        assert summary["n"] == TIMING_SAMPLE_CAPACITY * 3
        assert summary["retained_n"] == TIMING_SAMPLE_CAPACITY
        assert summary["retention_capacity"] == TIMING_SAMPLE_CAPACITY
        assert summary["quantiles_approximate"] is True
        assert len(accumulator._sample) == TIMING_SAMPLE_CAPACITY
        assert summary["max_ms"] == 249.0

    def test_timing_qc_uses_standard_nearest_rank_quantiles(self):
        accumulator = _logger_module._BoundedTimingAccumulator(
            capacity=4,
            seed=1,
        )
        for value in (1.0, 2.0, 3.0, 4.0):
            accumulator.add(value)

        summary = accumulator.summary()

        assert summary["quantile_method"].endswith("nearest_rank")
        assert summary["median_ms"] == 2.0
        assert summary["p95_ms"] == 4.0

    def test_timing_qc_binds_exact_scientific_session_context_and_sidecars(self, tmp_path):
        events_path = tmp_path / "session.events.jsonl"
        csv_path = tmp_path / "session.csv"
        lsl_path = tmp_path / "session.lsl_observations.jsonl"
        events_path.write_text('{"event":1}\n', encoding="utf-8")
        csv_path.write_text("header\n", encoding="utf-8")
        lsl_path.write_text('{"marker":1}\n', encoding="utf-8")
        session_uuid = UUID("12345678-1234-5678-1234-567812345678")
        lg = _make_logger(
            _scientific_session_uuid=session_uuid,
            _scientific_context={
                "scenario_sha256": "a" * 64,
                "profile_id": "MATB-EXTENDED-2.0",
                "source_commit": "b" * 40,
                "source_dirty": False,
                "component_version": "1.4.5",
                "scenario_manifest_status": "verified",
            },
            path=csv_path,
            events_path=events_path,
            lsl_observations_path=lsl_path,
        )

        summary = lg.timing_qc_summary()

        assert summary["timing_qc_schema_version"] == "2.0"
        assert summary["scientific_session_id"] == str(session_uuid)
        assert summary["scenario_sha256"] == "a" * 64
        assert summary["profile_id"] == "MATB-EXTENDED-2.0"
        assert summary["source_commit"] == "b" * 40
        assert summary["source_dirty"] is False
        assert summary["runtime_contract_status"] == "complete"
        assert set(summary["artifacts"]) == {"csv", "events_jsonl", "lsl_observations_jsonl"}
        assert all(item["sha256"] and item["size_bytes"] > 0 for item in summary["artifacts"].values())

    def test_update_stall_count_remains_exact_after_reservoir_sampling(self):
        lg = _make_logger()
        accumulator = lg._timing_accumulator("update_interval")
        for index in range(TIMING_SAMPLE_CAPACITY + 100):
            accumulator.add(101.0 if index % 10 == 0 else 20.0)

        assert lg.timing_qc_summary()["long_update_stalls_over_100ms"] == (
            TIMING_SAMPLE_CAPACITY + 109
        ) // 10
