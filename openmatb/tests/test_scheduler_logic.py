"""Tests for core.scheduler - Logic only (no event loop)."""

from collections import deque
import json
from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from core.event import Event


def test_set_scenario_configures_provenance_before_bootstrap_records():
    from core.scheduler import Scheduler

    scheduler = object.__new__(Scheduler)
    scheduler.runtime_version = "1.4.5"
    scheduler.scenario_path = Path("scenario.txt")
    scheduler.joystick = MagicMock()
    source = MagicMock(
        scenario_sha256="a" * 64,
        scenario_path=Path("scenario.txt"),
    )
    scenario = MagicMock(
        scenario_sha256=source.scenario_sha256,
        scenario_path=source.scenario_path,
        events=[],
        plugins={},
    )
    logger = MagicMock()

    bound_manifest = MagicMock(evidence={"status": "verified"})
    with patch("core.scheduler.Scenario", return_value=scenario) as scenario_class, patch(
        "core.scheduler.ExperimentClock"
    ), patch(
        "core.scheduler.load_adjacent_scenario_manifest", return_value=bound_manifest
    ), patch("core.scheduler.get_logger", return_value=logger), patch(
        "core.scheduler.Window.MainWindow", MagicMock()
    ):
        scenario_class.resolve_source.return_value = source
        scheduler.set_scenario()

    assert [call[0] for call in logger.method_calls[:4]] == [
        "configure_scientific_context",
        "archive_scenario_manifest",
        "log_manual_entry",
        "log_manual_entry",
    ]
    assert logger.method_calls[2].kwargs == {"key": "version"}
    assert logger.method_calls[3].kwargs == {"key": "scenario_path"}
    scenario_class.assert_called_once_with(source=source)


def test_communications_bootstrap_jsonl_never_precedes_provenance_binding(
    tmp_path,
    monkeypatch,
    mock_errors,
    mock_window,
):
    """COMM random seeds emitted in __init__ must carry the bound scenario context."""
    from core.constants import PATHS
    from core.logger import Logger, set_logger
    from core.scenarioprovenance import BoundScenarioManifest
    from core.scheduler import Scheduler

    sessions_dir = tmp_path / "sessions"
    scenario_path = tmp_path / "communications.txt"
    scenario_path.write_text(
        "0:00:00;communications;start\n"
        "0:00:01;communications;stop\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(PATHS, "SESSIONS", sessions_dir)
    monkeypatch.setitem(PATHS, "SCENARIO_ERRORS", tmp_path / "scenario-errors.txt")
    monkeypatch.setenv("MATB_SOURCE_COMMIT", "c" * 40)
    monkeypatch.setenv("MATB_SOURCE_DIRTY", "false")
    bound = BoundScenarioManifest(
        evidence={
            "schema_version": "1.0",
            "status": "verified",
            "scenario_sha256": "unused-by-configure",
            "adjacent_manifest_filename": "communications.txt.manifest.json",
            "scenario_manifest_sha256": "d" * 64,
            "manifest_identity": {
                "experiment_spec_sha256": "e" * 64,
                "experiment_seed": 7,
                "scenario_compiler_id": "matb-research",
                "scenario_compiler_version": "1.0.0",
            },
        },
        content=None,
    )
    logger = Logger()
    set_logger(logger)
    scheduler = object.__new__(Scheduler)
    scheduler.runtime_version = "1.4.5"
    scheduler.scenario_path = scenario_path
    scheduler.joystick = MagicMock()
    callsigns = iter(
        ("ABC123", "DEF456", "GHI789", "JKL012", "MNO345", "PQR678")
    )
    try:
        with patch(
            "core.scheduler.load_adjacent_scenario_manifest",
            return_value=bound,
        ), patch(
            "core.pseudorandom.rstrxeger",
            side_effect=lambda _pattern: next(callsigns),
        ):
            scheduler.set_scenario()
        logger.events_file.flush()
        rows = [
            json.loads(line)
            for line in logger.events_path.read_text(encoding="utf-8").splitlines()
        ]
    finally:
        logger.close()
        set_logger(None)

    assert rows
    assert any(row["record_type"] == "seed_value" for row in rows)
    assert all(row["scenario_sha256"] == scheduler.scenario.scenario_sha256 for row in rows)
    assert all(row["scenario_manifest_status"] == "verified" for row in rows)
    assert all(row["runtime_contract_status"] == "complete" for row in rows)


class TestGetPluginsByStates:
    def _make_scheduler_methods(self):
        """Extract the filtering method without running __init__."""
        from core.scheduler import Scheduler

        # Just test the static method logic using a mock
        sched = object.__new__(Scheduler)
        return sched

    def test_filter_alive(self):
        """Filters plugins where alive=True."""
        sched = self._make_scheduler_methods()

        p1 = MagicMock(alive=True, paused=False)
        p2 = MagicMock(alive=False, paused=False)
        sched.plugins = {"p1": p1, "p2": p2}

        result = sched.get_plugins_by_states([("alive", True)])
        assert p1 in result
        assert p2 not in result

    def test_filter_multiple_states(self):
        """Combines multiple state conditions with AND."""
        sched = self._make_scheduler_methods()

        p1 = MagicMock(alive=True, blocking=True, paused=False)
        p2 = MagicMock(alive=True, blocking=False, paused=False)
        sched.plugins = {"p1": p1, "p2": p2}

        result = sched.get_plugins_by_states([("blocking", True), ("paused", False)])
        assert p1 in result
        assert p2 not in result

    def test_empty_plugins(self):
        """Empty plugin dict returns empty list."""
        sched = self._make_scheduler_methods()
        sched.plugins = {}
        result = sched.get_plugins_by_states([("alive", True)])
        assert result == []


class TestScenarioTimePause:
    def _make_scheduler(self):
        sched = object.__new__(__import__("core.scheduler", fromlist=["Scheduler"]).Scheduler)
        sched.pause_scenario_time = False
        return sched

    def test_initial_not_paused(self):
        """Scenario starts unpaused."""
        sched = self._make_scheduler()
        assert sched.is_scenario_time_paused() is False

    def test_pause(self):
        """pause_scenario sets paused to True."""
        sched = self._make_scheduler()
        sched.pause_scenario()
        assert sched.is_scenario_time_paused() is True

    def test_resume(self):
        """resume_scenario clears pause flag."""
        sched = self._make_scheduler()
        sched.pause_scenario()
        sched.resume_scenario()
        assert sched.is_scenario_time_paused() is False

    def test_toggle(self):
        """toggle_scenario flips the pause state."""
        sched = self._make_scheduler()
        sched.toggle_scenario()
        assert sched.is_scenario_time_paused() is True
        sched.toggle_scenario()
        assert sched.is_scenario_time_paused() is False


class TestExitReadiness:
    def _make_scheduler(self, events):
        from core.scheduler import Scheduler

        scheduler = object.__new__(Scheduler)
        scheduler.plugins = {"sysmon": MagicMock(alive=False)}
        scheduler.events = events
        scheduler.events_queue = []
        scheduler.exit = MagicMock()
        return scheduler

    def test_delayed_first_start_does_not_exit_before_it_is_due(self):
        scheduler = self._make_scheduler([Event(1, 10, "sysmon", "start")])

        with patch("core.scheduler.Window.MainWindow", MagicMock(alive=True)):
            scheduler.check_if_must_exit()

        scheduler.exit.assert_not_called()

    def test_idle_gap_between_balanced_task_blocks_does_not_exit(self):
        completed_stop = Event(2, 5, "sysmon", "stop")
        completed_stop.done = 1
        scheduler = self._make_scheduler(
            [completed_stop, Event(3, 20, "sysmon", "start")]
        )

        with patch("core.scheduler.Window.MainWindow", MagicMock(alive=True)):
            scheduler.check_if_must_exit()

        scheduler.exit.assert_not_called()

    def test_exits_only_after_every_scenario_event_is_finished(self):
        completed_stop = Event(2, 5, "sysmon", "stop")
        completed_stop.done = 1
        scheduler = self._make_scheduler([completed_stop])

        with patch("core.scheduler.Window.MainWindow", MagicMock(alive=True)):
            scheduler.check_if_must_exit()

        scheduler.exit.assert_called_once_with()


class TestUnqueueEvent:
    def _make_scheduler(self):
        sched = object.__new__(__import__("core.scheduler", fromlist=["Scheduler"]).Scheduler)
        return sched

    def test_empty_queue(self):
        """Empty queue returns None."""
        sched = self._make_scheduler()
        sched.events_queue = []
        assert sched.unqueue_event() is None

    def test_dequeue_order(self):
        """Events are dequeued in FIFO order."""
        sched = self._make_scheduler()
        e1 = MagicMock(name="e1")
        e2 = MagicMock(name="e2")
        sched.events_queue = [e1, e2]

        result = sched.unqueue_event()
        assert result == e1
        assert len(sched.events_queue) == 1
        assert sched.events_queue[0] == e2


class TestActivePluginHelpers:
    def _make_scheduler(self):
        sched = object.__new__(__import__("core.scheduler", fromlist=["Scheduler"]).Scheduler)
        return sched

    def test_get_active_plugins(self):
        """Returns only alive plugins."""
        sched = self._make_scheduler()
        p1 = MagicMock(alive=True)
        p2 = MagicMock(alive=False)
        sched.plugins = {"p1": p1, "p2": p2}
        result = sched.get_active_plugins()
        assert len(result) == 1
        assert p1 in result

    def test_get_active_blocking_plugin(self):
        """Returns the blocking, unpaused plugin."""
        sched = self._make_scheduler()
        p1 = MagicMock(alive=True, blocking=True, paused=False)
        p2 = MagicMock(alive=True, blocking=False, paused=False)
        sched.plugins = {"p1": p1, "p2": p2}
        result = sched.get_active_blocking_plugin()
        assert result == p1

    def test_get_active_blocking_plugin_none(self):
        """Returns None when no blocking plugin."""
        sched = self._make_scheduler()
        p1 = MagicMock(alive=False, blocking=False, paused=False)
        sched.plugins = {"p1": p1}
        result = sched.get_active_blocking_plugin()
        assert result is None

    def test_get_active_non_blocking(self):
        """Returns unpaused non-blocking plugins."""
        sched = self._make_scheduler()
        p1 = MagicMock(alive=True, blocking=True, paused=False)
        p2 = MagicMock(alive=True, blocking=False, paused=False)
        sched.plugins = {"p1": p1, "p2": p2}
        result = sched.get_active_non_blocking_plugins()
        assert p2 in result
        assert p1 not in result


class TestBatchEventDispatch:
    def test_one_update_dispatches_every_due_event_in_scenario_line_order(self):
        """Catch frame-rate-dependent delays between simultaneous scenario events."""
        from core.scheduler import Scheduler

        scheduler = object.__new__(Scheduler)
        late = Event(30, 5, "track", "start")
        first = Event(10, 5, "sysmon", "start")
        second = Event(20, 5, "communications", "start")
        scheduler.events = [late, second, first]
        scheduler.events_queue = []
        scheduler.scenario_time = 5.25
        scheduler.pause_scenario_time = False
        scheduler.paused_plugins = []
        scheduler.get_active_blocking_plugin = MagicMock(return_value=None)
        scheduler.execute_one_event = MagicMock(
            side_effect=lambda event: setattr(event, "done", 1)
        )

        scheduler.execute_events()

        assert [call.args[0] for call in scheduler.execute_one_event.call_args_list] == [
            first,
            second,
            late,
        ]

    def test_overdue_events_dispatch_by_scheduled_time_before_scenario_section_line(self):
        """A frame stall must not dispatch a later task-section event first."""
        from core.scheduler import Scheduler

        scheduler = object.__new__(Scheduler)
        earlier_high_line = Event(90, 5, "communications", "start")
        later_low_line = Event(10, 8, "sysmon", "start")
        scheduler.events = [later_low_line, earlier_high_line]
        scheduler.events_queue = []

        first = scheduler.get_event_at_scenario_time(10.0)
        second = scheduler.unqueue_event()

        assert (first, second) == (earlier_high_line, later_low_line)

    def test_contract_maximum_overdue_batch_drains_once_in_order(self):
        """The 10,000-event contract maximum must use an O(1) FIFO drain."""
        from core.scheduler import Scheduler

        class CountingEvents(list):
            iterations = 0

            def __iter__(self):
                self.iterations += 1
                return super().__iter__()

        scheduler = object.__new__(Scheduler)
        scheduler.events = CountingEvents(
            Event(index, index % 10, "sysmon", "start") for index in range(10_000)
        )
        scheduler.events_queue = []
        scheduler.scenario_time = 20.0
        scheduler.pause_scenario_time = False
        scheduler.paused_plugins = []
        scheduler.get_active_blocking_plugin = MagicMock(return_value=None)
        scheduler.execute_one_event = MagicMock(
            side_effect=lambda event: setattr(event, "done", 1)
        )

        scheduler.execute_events()

        assert scheduler.execute_one_event.call_count == 10_000
        assert scheduler.events.iterations <= 2
        assert isinstance(scheduler.events_queue, deque)

    def test_batch_stops_when_one_due_event_starts_a_blocking_plugin(self):
        """Later due events remain queued until the modal/blocking task ends."""
        from core.scheduler import Scheduler

        scheduler = object.__new__(Scheduler)
        blocker = MagicMock(alive=False, blocking=True, paused=False)
        other = MagicMock(alive=False, blocking=False, paused=False)
        first = Event(10, 5, "blocker", "start")
        second = Event(20, 5, "other", "start")
        scheduler.events = [first, second]
        scheduler.events_queue = []
        scheduler.plugins = {"blocker": blocker, "other": other}
        scheduler.scenario_time = 5.0
        scheduler.pause_scenario_time = False
        scheduler.paused_plugins = []

        def execute(event):
            event.done = 1
            if event is first:
                blocker.alive = True

        scheduler.execute_one_event = MagicMock(side_effect=execute)
        scheduler.execute_events()

        scheduler.execute_one_event.assert_called_once_with(first)
        assert list(scheduler.events_queue) == [second]

    def test_blocking_start_freezes_time_and_peers_in_the_same_dispatch(self):
        """No extra scenario frame may elapse after a blocking start returns."""
        from core.scheduler import Scheduler

        scheduler = object.__new__(Scheduler)
        blocker = MagicMock(alive=False, blocking=True, paused=False)
        active_peer = MagicMock(alive=True, blocking=False, paused=False)
        later = MagicMock(alive=False, blocking=False, paused=False)
        first = Event(10, 5, "blocker", "start")
        second = Event(20, 5, "later", "start")
        scheduler.events = [first, second]
        scheduler.events_queue = []
        scheduler.plugins = {
            "blocker": blocker,
            "active_peer": active_peer,
            "later": later,
        }
        scheduler.scenario_time = 5.0
        scheduler.pause_scenario_time = False
        scheduler.paused_plugins = []

        def execute(event):
            event.done = 1
            blocker.alive = True

        scheduler.execute_one_event = MagicMock(side_effect=execute)
        scheduler.execute_events()

        assert scheduler.pause_scenario_time is True
        assert scheduler.paused_plugins == [active_peer]
        active_peer.pause.assert_called_once_with()
        active_peer.hide.assert_called_once_with()
        later.pause.assert_not_called()
        assert list(scheduler.events_queue) == [second]

    def test_negative_frame_delta_terminalizes_scenario_clock_before_mutation(self):
        from core.experimentclock import ExperimentClock
        from core.scheduler import Scheduler

        scheduler = object.__new__(Scheduler)
        scheduler.scenario_time = 10.0
        scheduler.pause_scenario_time = False
        scheduler.events_queue = [Event(8, 11, "track", "start")]
        scheduler.experiment_clock = ExperimentClock(monotonic_ns=lambda: 1_000)
        logger = MagicMock()

        with patch("core.scheduler.get_logger", return_value=logger), pytest.raises(
            ValueError, match="non-negative"
        ):
            scheduler.update_timers(-0.1)

        assert scheduler.scenario_time == 10.0
        assert scheduler.pause_scenario_time is True
        assert scheduler.events_queue == []
        assert scheduler._dispatch_failed is True
        assert scheduler._dispatch_failure["failure_phase"] == "scenario_clock_update"
        logger.set_scenario_time.assert_not_called()
        logger.log_manual_entry.assert_called_once()

    def test_event_dispatch_records_start_and_end_boundaries(self):
        """Catch event records that collapse dispatch execution into one timestamp."""
        from core.experimentclock import ExperimentClock
        from core.scheduler import Scheduler

        scheduler = object.__new__(Scheduler)
        plugin = MagicMock()
        scheduler.plugins = {"sysmon": plugin}
        event = Event(7, 10, "sysmon", "start")
        logger = MagicMock()
        readings = iter([1_000, 1_275])
        scheduler.experiment_clock = ExperimentClock(monotonic_ns=lambda: next(readings))

        with patch("core.scheduler.get_logger", return_value=logger):
            scheduler.execute_one_event(event)

        logger.record_event.assert_called_once_with(
            event,
            dispatch_start_monotonic_ns=1_000,
            dispatch_end_monotonic_ns=1_275,
        )
        assert scheduler.experiment_clock._last_experiment_time_ns == 10_000_000_000
        assert scheduler.experiment_clock._last_host_monotonic_ns == 1_275
        assert event.done == 1

    def test_host_clock_regression_terminalizes_and_records_dispatch_failure(self):
        from core.experimentclock import ExperimentClock
        from core.scheduler import Scheduler

        scheduler = object.__new__(Scheduler)
        plugin = MagicMock()
        scheduler.plugins = {"sysmon": plugin}
        scheduler.events_queue = [Event(8, 10, "track", "start")]
        scheduler.pause_scenario_time = False
        event = Event(7, 10, "sysmon", "start")
        logger = MagicMock()
        scheduler.experiment_clock = ExperimentClock(
            monotonic_ns=iter([1_000, 900]).__next__
        )

        with (
            patch("core.scheduler.get_logger", return_value=logger),
            patch("core.scheduler.perf_counter_ns", return_value=1_275),
            pytest.raises(RuntimeError, match="host monotonic clock regressed"),
        ):
            scheduler.execute_one_event(event)

        plugin.start.assert_called_once_with()
        logger.record_event.assert_not_called()
        logger.record_event_failure.assert_called_once_with(
            event,
            dispatch_start_monotonic_ns=1_000,
            dispatch_end_monotonic_ns=1_275,
            error_type="RuntimeError",
            error_message="host monotonic clock regressed",
            failure_phase="clock_acquisition",
        )
        assert event.done == 1
        assert scheduler.pause_scenario_time is True
        assert scheduler.events_queue == []
        assert scheduler._dispatch_failure["failure_phase"] == "clock_acquisition"

    def test_raising_plugin_creates_terminal_failure_evidence_without_retry(self):
        from core.experimentclock import ExperimentClock
        from core.scheduler import Scheduler

        scheduler = object.__new__(Scheduler)
        plugin = MagicMock()
        plugin.start.side_effect = RuntimeError("simulated dispatch failure")
        scheduler.plugins = {"sysmon": plugin}
        scheduler.events_queue = [Event(8, 10, "track", "start")]
        scheduler.pause_scenario_time = False
        event = Event(7, 10, "sysmon", "start")
        logger = MagicMock()
        readings = iter([1_000, 1_275])
        scheduler.experiment_clock = ExperimentClock(monotonic_ns=lambda: next(readings))

        with patch("core.scheduler.get_logger", return_value=logger), pytest.raises(
            RuntimeError, match="simulated dispatch failure"
        ):
            scheduler.execute_one_event(event)

        logger.record_event.assert_not_called()
        logger.record_event_failure.assert_called_once_with(
            event,
            dispatch_start_monotonic_ns=1_000,
            dispatch_end_monotonic_ns=1_275,
            error_type="RuntimeError",
            error_message="simulated dispatch failure",
            failure_phase="command_dispatch",
        )
        assert event.done == 1
        assert scheduler.pause_scenario_time is True
        assert scheduler.events_queue == []
        assert scheduler._dispatch_failed is True
        assert "_scenario_dispatch_context" not in plugin.__dict__

        # Even if a host catches the original exception, the event can never
        # be dispatched a second time in this invalid session.
        scheduler.update = Scheduler.update.__get__(scheduler, Scheduler)
        scheduler.update(0.1)
        plugin.start.assert_called_once_with()

    def test_secondary_failure_record_error_never_replaces_primary_dispatch_exception(self):
        from core.experimentclock import ExperimentClock
        from core.scheduler import Scheduler

        scheduler = object.__new__(Scheduler)
        plugin = MagicMock()
        plugin.start.side_effect = RuntimeError("primary plugin failure")
        scheduler.plugins = {"sysmon": plugin}
        scheduler.events_queue = deque()
        scheduler.pause_scenario_time = False
        event = Event(7, 10, "sysmon", "start")
        logger = MagicMock()
        logger.record_event_failure.side_effect = OSError("secondary logger failure")
        scheduler.experiment_clock = ExperimentClock(
            monotonic_ns=iter([1_000, 1_275]).__next__
        )

        with patch("core.scheduler.get_logger", return_value=logger), pytest.raises(
            RuntimeError, match="primary plugin failure"
        ):
            scheduler.execute_one_event(event)

        assert scheduler._dispatch_failure["failure_phase"] == "command_dispatch"
        assert scheduler._dispatch_failure["failure_evidence_status"] == "write_failed"

    def test_plugin_update_failure_terminalizes_the_entire_session(self):
        from core.scheduler import Scheduler

        scheduler = object.__new__(Scheduler)
        plugin = MagicMock(alive=True)
        plugin.update.side_effect = RuntimeError("plugin update failed")
        scheduler.plugins = {"sysmon": plugin}
        scheduler.events_queue = deque([Event(8, 10, "sysmon", "stop")])
        scheduler.scenario_time = 0.0
        scheduler.pause_scenario_time = False
        scheduler._dialog_paused = False
        scheduler._dispatch_failed = False
        scheduler.update_timers = MagicMock()
        scheduler.update_joystick = MagicMock()
        scheduler.execute_events = MagicMock()
        scheduler.check_if_must_exit = MagicMock()
        logger = MagicMock()
        errors = MagicMock()
        errors.is_empty.return_value = True

        with patch("core.scheduler.get_logger", return_value=logger), patch(
            "core.scheduler.get_errors", return_value=errors
        ), patch("core.scheduler.Window.MainWindow", MagicMock(modal_dialog=None)), pytest.raises(
            RuntimeError, match="plugin update failed"
        ):
            Scheduler.update(scheduler, 0.1)

        assert scheduler._dispatch_failed is True
        assert scheduler.pause_scenario_time is True
        assert scheduler.events_queue == deque()
        assert scheduler._dispatch_failure["failure_phase"] == "plugin_update"
        logger.log_manual_entry.assert_called_once()

    def test_authoritative_event_log_failure_freezes_session_before_host_can_continue(self):
        from core.experimentclock import ExperimentClock
        from core.logger import AuthoritativeLogFailure
        from core.scheduler import Scheduler

        scheduler = object.__new__(Scheduler)
        plugin = MagicMock()
        scheduler.plugins = {"sysmon": plugin}
        scheduler.events_queue = [Event(8, 10, "sysmon", "stop")]
        scheduler.pause_scenario_time = False
        event = Event(7, 10, "sysmon", "start")
        logger = MagicMock()
        logger.record_event.side_effect = AuthoritativeLogFailure("disk failed")
        readings = iter([1_000, 1_275])
        scheduler.experiment_clock = ExperimentClock(monotonic_ns=lambda: next(readings))

        with patch("core.scheduler.get_logger", return_value=logger), pytest.raises(
            AuthoritativeLogFailure, match="disk failed"
        ):
            scheduler.execute_one_event(event)

        assert event.done == 1
        assert scheduler.pause_scenario_time is True
        assert scheduler.events_queue == []
        assert scheduler._dispatch_failed is True
        assert scheduler._dispatch_failure["failure_phase"] == "authoritative_event_logging"

        # A GUI host may catch the sink exception. No later event/plugin update
        # is permitted in a session whose executed command was not recorded.
        scheduler.update = Scheduler.update.__get__(scheduler, Scheduler)
        scheduler.update(0.1)
        plugin.start.assert_called_once_with()
        plugin.stop.assert_not_called()
