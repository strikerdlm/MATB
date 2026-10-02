"""Native shutdown must return through the media/window event loop."""

from unittest.mock import MagicMock, patch

from core.scheduler import Scheduler


def test_exit_returns_to_event_loop_and_finalizes_once():
    scheduler = object.__new__(Scheduler)
    scheduler.event_loop = MagicMock()
    scheduler.control_bridge = None
    logger = MagicMock()
    window = MagicMock()
    with patch("core.scheduler.get_logger", return_value=logger), patch(
        "core.scheduler.Window.MainWindow", window
    ):
        scheduler.exit()
        scheduler.exit(completion="window_closed")
    logger.log_manual_entry.assert_called_once_with("end")
    logger.finalize_evidence.assert_called_once_with("completed")
    scheduler.event_loop.exit.assert_called_once_with()
    window.close.assert_called_once_with()


def test_exiting_scheduler_never_advances_another_frame():
    scheduler = object.__new__(Scheduler)
    scheduler._exiting = True
    scheduler.update_timers = MagicMock()
    scheduler.update(0.1)
    scheduler.update_timers.assert_not_called()


def test_cancelling_briefing_never_starts_due_tasks():
    scheduler = object.__new__(Scheduler)
    scheduler.check_if_must_exit = MagicMock()
    scheduler.update_timers = MagicMock()
    scheduler.execute_events = MagicMock()
    with patch("core.scheduler.Window.MainWindow", MagicMock(alive=False)):
        scheduler.update(0.1)
    scheduler.check_if_must_exit.assert_called_once()
    scheduler.update_timers.assert_not_called()
    scheduler.execute_events.assert_not_called()


def test_completed_scenario_does_not_also_finalize_as_window_closed():
    scheduler = object.__new__(Scheduler)
    scheduler.events = []
    scheduler.events_queue = []
    scheduler.plugins = {}
    scheduler.exit = MagicMock()
    with patch("core.scheduler.Window.MainWindow", MagicMock(alive=False)):
        scheduler.check_if_must_exit()
    scheduler.exit.assert_called_once_with()
