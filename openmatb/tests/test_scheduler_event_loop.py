"""Native window callbacks must use the loop that owns the scheduler."""

from types import SimpleNamespace

from pyglet import app

from core import scheduler as scheduler_module


def test_windows_blocking_callback_reaches_running_scheduler_loop(monkeypatch, mock_window):
    reached = []
    inactive_loop = SimpleNamespace(enter_blocking=lambda: reached.append("inactive"))
    running_loop = SimpleNamespace(enter_blocking=lambda: reached.append("running"))
    # This is the lookup used by pyglet's Windows size/move callbacks.
    running_loop.run = lambda: app.event_loop.enter_blocking()
    monkeypatch.setattr(app, "event_loop", inactive_loop)
    monkeypatch.setattr(scheduler_module, "EventLoop", lambda: running_loop)
    monkeypatch.setattr(scheduler_module, "Clock", lambda name: SimpleNamespace(schedule=lambda callback: None))
    monkeypatch.setattr(scheduler_module.Scheduler, "set_scenario", lambda self: None)

    scheduler_module.Scheduler()

    assert reached == ["running"]
