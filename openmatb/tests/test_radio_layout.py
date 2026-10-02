"""Regression checks for distinct radio identifiers and frequency-only tuning."""
from types import SimpleNamespace

import pytest

from core.container import Container
from core.widgets.radio import Radio


@pytest.fixture
def radio(monkeypatch, mock_logger, mock_window):
    def label(text, **attributes):
        return SimpleNamespace(text=text, **attributes)

    monkeypatch.setattr("core.widgets.radio.Label", label)
    monkeypatch.setattr(Radio, "show", lambda self: None)
    return Radio("radio_NAV_1", Container("row", 0, 0, 640, 50), "NAV_1", 111.9, False)


def test_identifier_and_frequency_occupy_distinct_aligned_columns(radio):
    identifier = radio.vertex["radio_identifier"]
    frequency = radio.vertex["radio_frequency"]
    assert identifier.text == "NAV 1"
    assert frequency.text == "111.9"
    assert identifier.anchor_x == "right"
    assert frequency.anchor_x == "left"
    assert frequency.x - identifier.x == 24
    assert frequency.y == identifier.y


def test_tuning_preserves_identifier_and_logs_numeric_frequency(radio, mock_logger):
    radio.set_frequency_text(112.03)
    assert radio.vertex["radio_identifier"].text == "NAV 1"
    assert radio.vertex["radio_frequency"].text == "112.0"
    mock_logger.record_state.assert_called_once_with("radio_NAV_1", "radio_frequency", 112.03)
    mock_logger.record_state.reset_mock()
    radio.set_frequency_text(112.04)
    mock_logger.record_state.assert_not_called()
