from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.briefing import ParticipantBriefing


def make_briefing():
    briefing = object.__new__(ParticipantBriefing)
    briefing.player = None
    briefing.html_label = SimpleNamespace(text="instructions")
    briefing._instructions_html = "instructions"
    briefing.continue_key = "SPACE"
    return briefing


def test_cannot_start_timed_task_while_instructions_are_playing():
    briefing = make_briefing()
    briefing.player = MagicMock(playing=True)
    with (
        patch("core.briefing.winkey.symbol_string", return_value="SPACE"),
        patch("core.modaldialog.ModalDialog.on_key_release") as release,
    ):
        briefing.on_key_release(32, 0)
    release.assert_not_called()


def test_end_of_audio_allows_participant_to_continue():
    briefing = make_briefing()
    briefing.player = MagicMock(source=None)
    with (
        patch("core.briefing.winkey.symbol_string", return_value="SPACE"),
        patch("core.modaldialog.ModalDialog.on_key_release") as release,
    ):
        briefing.on_key_release(32, 0)
    release.assert_called_once_with(32, 0)


def test_unavailable_output_stays_outside_the_timed_test_and_can_retry():
    briefing = make_briefing()
    with patch("core.briefing.get_audio_driver", return_value=None), patch("core.briefing.get_logger"):
        briefing.play_instructions()
    assert briefing.continue_key is None
    assert "No se pudo reproducir" in briefing.html_label.text
    with (
        patch("core.briefing.get_audio_driver", return_value=object()),
        patch("core.briefing.load"),
        patch("core.briefing.Player") as player,
        patch("core.briefing.get_logger"),
        patch("pathlib.Path.read_bytes", return_value=b"wave"),
    ):
        briefing.play_instructions()
    player.return_value.play.assert_called_once()
    assert briefing.continue_key == "SPACE"
    assert briefing.html_label.text == "instructions"


def test_closing_briefing_releases_audio_before_task_starts():
    briefing = make_briefing()
    player = briefing.player = MagicMock()
    with patch("core.modaldialog.ModalDialog.on_delete"):
        briefing.on_delete()
    player.pause.assert_called_once()
    player.delete.assert_called_once()
    assert briefing.player is None
