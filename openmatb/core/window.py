# Copyright 2023-2026, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from sys import platform
from typing import Any

from pyglet import image
from pyglet.display import get_display
from pyglet.gl import GL_TRIANGLES, glClearColor
from pyglet.graphics import Batch
from pyglet.window import Window
from pyglet.window import key as winkey

from core.constants import COLORS as C
from core.constants import PATHS as P
from core.constants import PLUGIN_TITLE_HEIGHT_PROPORTION, REPLAY_MODE, REPLAY_STRIP_PROPORTION
from core.container import Container
from core.logger import get_logger
from core.modaldialog import ModalDialog
from core.rendering import get_group, get_program, polygon_indices
from core.utils import get_conf_value


def _windows_work_area(screen: Any) -> tuple[int, int, int, int] | None:
    """Read the selected monitor's usable rectangle; retain bounds if unavailable."""
    handle = getattr(screen, "_handle", None)
    if handle is None:
        return None
    from ctypes import byref, sizeof

    from pyglet.libs.win32 import _user32
    from pyglet.libs.win32.types import MONITORINFOEX

    info = MONITORINFOEX()
    info.cbSize = sizeof(info)
    if not _user32.GetMonitorInfoW(handle, byref(info)):
        return None
    left = max(int(screen.x), info.rcWork.left)
    top = max(int(screen.y), info.rcWork.top)
    right = min(int(screen.x + screen.width), info.rcWork.right)
    bottom = min(int(screen.y + screen.height), info.rcWork.bottom)
    if right <= left or bottom <= top:
        return None
    return left, top, right - left, bottom - top


class Window(Window):
    # Static variable
    MainWindow: Window | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        Window.MainWindow = self  # correct way to set it as a static

        screen: Any = self.get_screen()

        self._width: int = max(1, int(screen.width))
        self._height: int = max(1, int(screen.height))
        self._fullscreen: bool = get_conf_value("Openmatb", "fullscreen")
        self._presentation_position = (int(screen.x), int(screen.y))

        # A whole-display window can enter the same unstable presentation path
        # as exclusive fullscreen on Windows. Leave one row for composition;
        # plugin geometry and input coordinates use the resulting client size.
        if platform == "win32" and self._fullscreen:
            self._fullscreen = False
            work_area = _windows_work_area(screen)
            if work_area is not None:
                x, y, self._width, self._height = work_area
                self._presentation_position = (x, y)
            self._height = max(1, self._height - 1)
            kwargs["style"] = self.WINDOW_STYLE_BORDERLESS
            kwargs["resizable"] = False

        super().__init__(
            fullscreen=self._fullscreen,
            screen=screen,
            width=self._width,
            height=self._height,
            vsync=True,
            *args,
            **kwargs,
        )

        img_path: Any = P["IMG"]
        logo16: Any = image.load(img_path.joinpath("logo16.png"))
        logo32: Any = image.load(img_path.joinpath("logo32.png"))
        self.set_icon(logo16, logo32)

        self.set_size_and_location(screen)  # Postpone multiple monitor support
        self.set_mouse_visible(REPLAY_MODE)

        self.batch: Batch = Batch()
        self.keyboard: dict[str, bool] = dict()  # Reproduce a simple KeyStateHandler

        self.create_MATB_background()
        self.alive: bool = True
        self.modal_dialog: ModalDialog | None = None
        self.slider_visible: bool = False

        self.on_key_press_replay: Any | None = None  # used by the replay

    def display_session_id(self) -> None:
        # Display the session ID if needed at window instanciation
        if not REPLAY_MODE and get_conf_value("Openmatb", "display_session_number"):
            msg: str = _("Session ID: %s") % get_logger().session_id
            title: str = "OpenMATB"

            self.modal_dialog = ModalDialog(self, msg, title)

    def get_screen(self) -> Any:
        # Screen definition
        try:
            screen_index: int = get_conf_value("Openmatb", "screen_index")
        except (KeyError, TypeError):
            screen_index = 0

        screens: list[Any] = get_display().get_screens()
        if screen_index + 1 > len(screens):
            screen: Any = screens[-1]
            from core.error import get_errors

            get_errors().add_error(
                _(
                    "In config.ini, the specified screen index exceeds the number of"
                    " available screens (%s). Last screen selected."
                )
                % len(get_display().get_screens())
            )
        else:
            screen = screens[screen_index]

        return screen

    def set_size_and_location(self, screen: Any) -> None:
        self.switch_to()  # The Window must be active before setting the location
        target_x, target_y = getattr(self, "_presentation_position", (screen.x, screen.y))
        self.set_location(int(target_x), int(target_y))

    def create_MATB_background(self) -> None:
        MATB_container: Container = self.get_container("fullscreen")
        l, b, w, h = MATB_container.get_lbwh()
        container_title_h: float = PLUGIN_TITLE_HEIGHT_PROPORTION / 2
        program = get_program()
        indices = polygon_indices(4)

        # Main background
        program.vertex_list_indexed(
            4,
            GL_TRIANGLES,
            indices,
            batch=self.batch,
            group=get_group(order=-1),
            position=("f", (l, b + h, l + w, b + h, l + w, b, l, b)),
            colors=("Bn", C["BACKGROUND"] * 4),
        )

        # Upper band
        program.vertex_list_indexed(
            4,
            GL_TRIANGLES,
            indices,
            batch=self.batch,
            group=get_group(order=-1),
            position=(
                "f",
                (l, b + h, l + w, b + h, l + w, b + h * (1 - container_title_h), l, b + h * (1 - container_title_h)),
            ),
            colors=("Bn", C["DARKGREY"] * 4),
        )

        # Middle band
        program.vertex_list_indexed(
            4,
            GL_TRIANGLES,
            indices,
            batch=self.batch,
            group=get_group(order=0),
            position=(
                "f",
                (
                    l,
                    b + h / 2,
                    l + w,
                    b + h / 2,
                    l + w,
                    b + h * (0.5 - container_title_h),
                    0,
                    b + h * (0.5 - container_title_h),
                ),
            ),
            colors=("Bn", C["DARKGREY"] * 4),
        )

    def on_draw(self) -> None:
        self.set_mouse_visible(self.is_mouse_necessary())
        glClearColor(0, 0, 0, 1)
        self.clear()
        self.batch.draw()

    def is_mouse_necessary(self) -> bool:
        return self.slider_visible or REPLAY_MODE

    # Log any keyboard input, either plugins accept it or not
    # is subclassed in replay mode
    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if REPLAY_MODE:
            return

        if self.modal_dialog is None:
            keystr: str = winkey.symbol_string(symbol)
            self.keyboard[keystr] = True  # KeyStateHandler

            if keystr == "ESCAPE":
                self.exit_prompt()
            elif keystr == "P":
                self.pause_prompt()

            get_logger().record_input("keyboard", keystr, "press")

    def on_key_release(self, symbol: int, modifiers: int) -> None:
        if not REPLAY_MODE:
            keystr: str = winkey.symbol_string(symbol)
            self.keyboard[keystr] = False
        if self.modal_dialog is not None:
            self.modal_dialog.on_key_release(symbol, modifiers)
            return

        if REPLAY_MODE:
            return

        get_logger().record_input("keyboard", keystr, "release")

    def clear_held_keys(self, reason: str = "focus_lost") -> None:
        # A release may be delivered to another window or swallowed by a modal.
        keyboard = getattr(self, "keyboard", {})
        can_log = not REPLAY_MODE and getattr(self, "alive", False)
        held = [keystr for keystr, pressed in keyboard.items() if pressed]
        if held and can_log:
            get_logger().log_manual_entry(
                f"Software key-state reset ({reason}): {', '.join(held)}", key="keyboard_state_reset"
            )
        for keystr, pressed in list(keyboard.items()):
            if pressed:
                keyboard[keystr] = False
                if can_log:
                    get_logger().record_input("keyboard", keystr, "release")

    def on_deactivate(self) -> None:
        self.clear_held_keys("focus_lost")

    def exit_prompt(self) -> None:
        self.clear_held_keys("exit_dialog")
        self.modal_dialog = ModalDialog(self, _("You hit the Escape key"), title=_("Exit OpenMATB?"), exit_key="q")

    def pause_prompt(self) -> None:
        self.clear_held_keys("pause_dialog")
        self.modal_dialog = ModalDialog(self, _("Pause"))

    def exit(self) -> None:
        self.alive = False

    def get_container_list(self) -> list[Container]:
        mar: float = REPLAY_STRIP_PROPORTION if REPLAY_MODE else 0
        w: float = (1 - mar) * self.width
        h: float = (1 - mar) * self.height
        b: float = self.height * mar

        # Vertical bounds
        x1, x2 = (int(w * bound) for bound in get_conf_value("Openmatb", "top_bounds"))  # Top row
        x3, x4 = (int(w * bound) for bound in get_conf_value("Openmatb", "bottom_bounds"))  # Bottom row

        # Horizontal bound
        y1: float = b + h / 2

        return [
            Container("invisible", 0, 0, 0, 0),
            Container("fullscreen", 0, b, w, h),
            Container("topleft", 0, y1, x1, h / 2),
            Container("topmid", x1, y1, x2 - x1, h / 2),
            Container("topright", x2, y1, w - x2, h / 2),
            Container("bottomleft", 0, b, x3, h / 2),
            Container("bottommid", x3, b, x4 - x3, h / 2),
            Container("bottomright", x4, b, w - x4, h / 2),
            Container("mediastrip", 0, 0, self._width * (1 + mar), b),
            Container("inputstrip", w, b, self._width * mar, h),
        ]

    def get_container(self, placement_name: str) -> Container | None:
        container: list[Container] = [c for c in self.get_container_list() if c.name == placement_name]
        if len(container) > 0:
            return container[0]
        else:
            print(_("Error. No placement found for the [%s] alias") % placement_name)

    def open_modal_window(self, pass_list: list[str], title: str, continue_key: str | None, exit_key: str) -> None:
        # TODO: would be better to use callbacks than to detect the alive variable
        # for example to close
        self.modal_dialog = ModalDialog(self, pass_list, title=title, continue_key=continue_key, exit_key="Q")
