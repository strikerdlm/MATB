"""Tests for core.scheduler - Logic only (no event loop)."""

import os
from unittest.mock import MagicMock, patch


class TestParentProcessWatchdog:
    @patch.dict(os.environ, {"OPENMATB_PARENT_PID": "4321"}, clear=False)
    @patch("core.scheduler.sys.platform", "win32")
    @patch("core.scheduler.os.kill")
    @patch("core.scheduler._windows_process_alive", return_value=True)
    def test_windows_uses_a_non_terminating_process_probe(
        self,
        windows_alive,
        os_kill,
    ):
        from core.scheduler import _parent_process_alive

        assert _parent_process_alive() is True
        windows_alive.assert_called_once_with(4321)
        os_kill.assert_not_called()

    @patch.dict(os.environ, {"OPENMATB_PARENT_PID": "4321"}, clear=False)
    @patch("core.scheduler.sys.platform", "linux")
    @patch("core.scheduler.os.kill")
    def test_unix_retains_signal_zero_probe(self, os_kill):
        from core.scheduler import _parent_process_alive

        assert _parent_process_alive() is True
        os_kill.assert_called_once_with(4321, 0)


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
        p1 = MagicMock(blocking=True, paused=False)
        p2 = MagicMock(blocking=False, paused=False)
        sched.plugins = {"p1": p1, "p2": p2}
        result = sched.get_active_blocking_plugin()
        assert result == p1

    def test_get_active_blocking_plugin_none(self):
        """Returns None when no blocking plugin."""
        sched = self._make_scheduler()
        p1 = MagicMock(blocking=False, paused=False)
        sched.plugins = {"p1": p1}
        result = sched.get_active_blocking_plugin()
        assert result is None

    def test_get_active_non_blocking(self):
        """Returns unpaused non-blocking plugins."""
        sched = self._make_scheduler()
        p1 = MagicMock(blocking=True, paused=False)
        p2 = MagicMock(blocking=False, paused=False)
        sched.plugins = {"p1": p1, "p2": p2}
        result = sched.get_active_non_blocking_plugins()
        assert p2 in result
        assert p1 not in result


class TestCheckIfMustExit:
    def _make_scheduler(self):
        scheduler_type = __import__("core.scheduler", fromlist=["Scheduler"]).Scheduler
        scheduler = object.__new__(scheduler_type)
        scheduler.plugins = {}
        scheduler.events_queue = []
        scheduler.exit = MagicMock()
        return scheduler

    @patch("core.scheduler.Window")
    def test_future_events_do_not_count_as_natural_completion(self, window):
        scheduler = self._make_scheduler()
        scheduler.events = [MagicMock(done=0)]
        window.MainWindow.alive = True

        scheduler.check_if_must_exit()

        scheduler.exit.assert_not_called()

    @patch("core.scheduler.Window")
    def test_all_events_done_exits_as_completed(self, window):
        scheduler = self._make_scheduler()
        scheduler.events = [MagicMock(done=1)]
        window.MainWindow.alive = True

        scheduler.check_if_must_exit()

        scheduler.exit.assert_called_once_with(completed=True)

    @patch("core.scheduler.Window")
    def test_closed_window_exits_without_completion(self, window):
        scheduler = self._make_scheduler()
        scheduler.events = [MagicMock(done=0)]
        window.MainWindow.alive = False

        scheduler.check_if_must_exit()

        scheduler.exit.assert_called_once_with(completed=False)


class TestParentWatchdog:
    @patch("core.scheduler._parent_process_alive", return_value=False)
    def test_synchronized_child_exits_if_backend_parent_is_gone(self, _alive):
        scheduler_type = __import__("core.scheduler", fromlist=["Scheduler"]).Scheduler
        scheduler = object.__new__(scheduler_type)
        scheduler.exit = MagicMock()

        scheduler.update(0.1)

        scheduler.exit.assert_called_once_with(completed=False)

    @patch("core.scheduler._parent_process_alive", return_value=True)
    @patch("core.scheduler.monotonic", side_effect=(10.0, 10.25, 11.1))
    def test_parent_watchdog_is_throttled_to_once_per_second(self, _clock, alive):
        scheduler_type = __import__("core.scheduler", fromlist=["Scheduler"]).Scheduler
        scheduler = object.__new__(scheduler_type)

        assert scheduler._parent_alive_throttled() is True
        assert scheduler._parent_alive_throttled() is True
        assert scheduler._parent_alive_throttled() is True
        assert alive.call_count == 2
