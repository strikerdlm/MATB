from __future__ import annotations

import pytest

from core.theme import THEMES, VISUAL_THEME_NAMES, get_theme, normalize_visual_theme


def test_visual_theme_contract_is_closed_and_classic_is_default():
    assert VISUAL_THEME_NAMES == ("classic", "cockpit")
    assert normalize_visual_theme(None) == "classic"
    assert normalize_visual_theme(" Cockpit ") == "cockpit"
    assert set(THEMES) == set(VISUAL_THEME_NAMES)


def test_invalid_visual_theme_fails_closed():
    with pytest.raises(ValueError, match="classic, cockpit"):
        normalize_visual_theme("fighter")


def test_cockpit_palette_has_distinct_redundant_state_colors():
    cockpit = get_theme("cockpit")
    assert cockpit.is_cockpit
    assert cockpit.colors["BACKGROUND"] != cockpit.colors["INSTRUMENT"]
    assert len({cockpit.colors["GREEN"], cockpit.colors["CAUTION"], cockpit.colors["RED"]}) == 3
    assert all(len(color) == 4 and all(0 <= channel <= 255 for channel in color) for color in cockpit.colors.values())


def test_classic_palette_retains_historical_core_colors():
    classic = get_theme("classic")
    assert not classic.is_cockpit
    assert classic.colors["BACKGROUND"] == (240, 240, 240, 255)
    assert classic.colors["BLACK"] == (50, 50, 50, 255)
    assert classic.colors["GREEN"] == (142, 219, 176, 255)
    assert classic.colors["ACCENT"] == classic.colors["BLACK"]
