"""Avoid whole-display presentation on Windows without changing task logic."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import window as window_module


@pytest.mark.parametrize(
    "platform,requested_fullscreen,exclusive,height,expected_height",
    [
        ("win32", True, False, 1080, 1079),
        ("win32", False, False, 1080, 1080),
        ("linux", True, True, 1080, 1080),
        ("win32", True, False, 1, 1),
    ],
)
def test_fullscreen_presentation_keeps_selected_screen(
    monkeypatch, platform, requested_fullscreen, exclusive, height, expected_height
):
    screen = SimpleNamespace(x=1920, y=0, width=1920, height=height)
    calls = []
    positions = []
    base = window_module.Window.__bases__[0]
    monkeypatch.setattr(window_module, "platform", platform, raising=False)
    monkeypatch.setattr(window_module, "_windows_work_area", lambda screen: None, raising=False)
    monkeypatch.setattr(base, "WINDOW_STYLE_BORDERLESS", "borderless", raising=False)
    monkeypatch.setattr(base, "__init__", lambda self, *args, **kwargs: calls.append(kwargs))
    monkeypatch.setattr(base, "set_location", lambda self, x, y: positions.append((x, y)))
    monkeypatch.setattr(window_module.Window, "get_screen", lambda self: screen)
    monkeypatch.setattr(window_module.Window, "create_MATB_background", lambda self: None)
    monkeypatch.setattr(window_module, "get_conf_value", lambda section, key: requested_fullscreen)

    window_module.Window(style="dialog", resizable=True)

    assert calls[0]["fullscreen"] is exclusive
    assert calls[0]["screen"] is screen
    assert (calls[0]["width"], calls[0]["height"]) == (1920, expected_height)
    assert positions == [(1920, 0)]
    assert calls[0]["style"] == (
        "borderless" if platform == "win32" and requested_fullscreen else "dialog"
    )
    assert calls[0]["resizable"] is not (platform == "win32" and requested_fullscreen)


def test_windows_tasks_fit_work_area_on_selected_monitor(monkeypatch):
    screen = SimpleNamespace(x=-1920, y=0, width=1920, height=1080)
    calls = []
    positions = []
    base = window_module.Window.__bases__[0]
    monkeypatch.setattr(window_module, "platform", "win32")
    monkeypatch.setattr(window_module, "_windows_work_area", lambda screen: (-1920, 25, 1920, 995), raising=False)
    monkeypatch.setattr(base, "WINDOW_STYLE_BORDERLESS", "borderless", raising=False)
    def initialize(self, *args, **kwargs):
        calls.append(kwargs)
        self.width, self.height = kwargs["width"], kwargs["height"]
    monkeypatch.setattr(base, "__init__", initialize)
    monkeypatch.setattr(base, "set_location", lambda self, x, y: positions.append((x, y)))
    monkeypatch.setattr(window_module.Window, "get_screen", lambda self: screen)
    monkeypatch.setattr(window_module.Window, "create_MATB_background", lambda self: None)
    def config(section, key):
        return {"fullscreen": True, "top_bounds": [0.35, 0.85], "bottom_bounds": [0.3, 0.85]}[key]
    monkeypatch.setattr(window_module, "get_conf_value", config)
    monkeypatch.setattr(window_module, "REPLAY_MODE", False)

    window = window_module.Window()

    assert (calls[0]["width"], calls[0]["height"]) == (1920, 994)
    assert positions == [(-1920, 25)]
    for container in window.get_container_list():
        assert container.b >= 0
        assert container.b + container.h <= 994


@pytest.mark.parametrize(
    "platform,modern_windows,exclusive,vsync,visible,should_sync",
    [
        ("win32", True, False, True, True, True),
        ("win32", True, False, True, False, False),
        ("win32", True, False, False, True, False),
        ("win32", True, True, True, True, False),
        ("win32", False, False, True, True, False),
        ("linux", True, False, True, True, False),
    ],
)
def test_windows_compositor_sync_precedes_the_single_buffer_swap(
    monkeypatch, platform, modern_windows, exclusive, vsync, visible, should_sync
):
    calls = []
    base = window_module.Window.__bases__[0]
    monkeypatch.setattr(base, "flip", lambda self: calls.append("swap"), raising=False)
    monkeypatch.setattr(window_module, "platform", platform)
    monkeypatch.setattr(window_module, "_sync_windows_compositor", lambda: calls.append("sync") or True)
    window = object.__new__(window_module.Window)
    window._always_dwm = modern_windows
    window.fullscreen, window.vsync, window.visible = exclusive, vsync, visible
    window.flip()
    assert calls == (["sync", "swap"] if should_sync else ["swap"])


def test_failed_composition_falls_back_to_driver_sync_once(monkeypatch):
    base = window_module.Window.__bases__[0]
    monkeypatch.setattr(base, "flip", lambda self: None, raising=False)
    monkeypatch.setattr(window_module, "platform", "win32")
    sync = Mock(return_value=False)
    monkeypatch.setattr(window_module, "_sync_windows_compositor", sync)
    window = object.__new__(window_module.Window)
    window._always_dwm = True
    window.fullscreen, window.vsync, window.visible = False, True, True
    window.context = SimpleNamespace(set_vsync=Mock())
    window.flip()
    window.flip()
    sync.assert_called_once()
    window.context.set_vsync.assert_called_once_with(True)
