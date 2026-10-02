"""Keyboard state must remain usable after focus changes and participant pauses."""

from unittest.mock import MagicMock, patch

import pytest

from core.window import Window
from plugins.communications import Communications


def make_window():
    window = object.__new__(Window)
    window.keyboard = {"RIGHT": True, "LEFT": False}
    window.alive = True
    window.modal_dialog = None
    return window


def make_comm():
    comm = object.__new__(Communications)
    comm.parameters = {"keys": {"validateresponse": "ENTER", "selectradioup": "UP", "selectradiodown": "DOWN"}}
    comm.keys = {"ENTER", "UP", "DOWN", "LEFT", "RIGHT"}
    return comm


def test_lost_focus_releases_held_frequency_key():
    window = make_window()
    with patch("core.window.get_logger") as logger:
        window.on_deactivate()
        window.on_deactivate()
    assert not any(window.keyboard.values())
    logger.return_value.record_input.assert_called_once_with("keyboard", "RIGHT", "release")


def test_key_release_is_not_swallowed_by_pause_dialog():
    window = make_window()
    window.modal_dialog = MagicMock()
    with patch("core.window.winkey.symbol_string", return_value="RIGHT"):
        window.on_key_release(123, 0)
    assert window.keyboard["RIGHT"] is False
    window.modal_dialog.on_key_release.assert_called_once_with(123, 0)


@pytest.mark.parametrize("prompt", ["pause_prompt", "exit_prompt"])
def test_dialog_clears_held_keys_before_resuming(prompt):
    window = make_window()
    with patch("core.window.ModalDialog"), patch("core.window.get_logger"):
        getattr(window, prompt)()
    assert not any(window.keyboard.values())


@pytest.mark.parametrize("key", ["ENTER", "NUM_ENTER"])
def test_both_enter_keys_confirm_default_comm_response(key):
    comm = make_comm()
    comm.can_receive_keys = comm.can_execute_keys = True
    comm.confirm_response = MagicMock()
    with patch("plugins.abstractplugin.Window.MainWindow", MagicMock(modal_dialog=None)):
        comm.do_on_key(key, "press", False)
    comm.confirm_response.assert_called_once_with(response_actor="participant")


def test_keypad_enter_does_not_override_custom_response_mapping():
    comm = make_comm()
    comm.parameters["keys"]["validateresponse"] = "SPACE"
    comm.can_receive_keys = comm.can_execute_keys = True
    comm.confirm_response = MagicMock()
    with patch("plugins.abstractplugin.Window.MainWindow", MagicMock(modal_dialog=None)):
        comm.do_on_key("NUM_ENTER", "press", False)
    comm.confirm_response.assert_not_called()


@pytest.mark.parametrize("modal,enabled", [(None, False), (MagicMock(), True)])
def test_paused_or_modal_communications_never_accepts_response(modal, enabled):
    comm = make_comm()
    comm.can_receive_keys = comm.can_execute_keys = enabled
    comm.confirm_response = MagicMock()
    with patch("plugins.abstractplugin.Window.MainWindow", MagicMock(modal_dialog=modal)):
        comm.do_on_key("NUM_ENTER", "press", False)
    comm.confirm_response.assert_not_called()
