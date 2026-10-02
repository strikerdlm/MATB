from __future__ import annotations

import pytest

from copy import deepcopy
import json
from pathlib import Path

from core.theme import THEMES, VISUAL_THEME_NAMES, get_theme, get_theme_from_file, normalize_visual_theme
from matb_integration.openmatb_visual_profiles import (
    VisualProfileValidationError,
    load_visual_profile,
    profile_sha256,
    validate_visual_profile,
)


def test_visual_theme_contract_is_closed_and_daylight_is_default():
    assert VISUAL_THEME_NAMES == ("classic", "cockpit", "fac_modern", "daylight_avionics")
    assert normalize_visual_theme(None) == "daylight_avionics"
    assert normalize_visual_theme(" Cockpit ") == "cockpit"
    assert set(THEMES) == set(VISUAL_THEME_NAMES)


def test_invalid_visual_theme_fails_closed():
    with pytest.raises(ValueError, match="classic, cockpit, fac_modern"):
        normalize_visual_theme("fighter")


def test_cockpit_palette_has_distinct_redundant_state_colors():
    cockpit = get_theme("cockpit")
    assert cockpit.shows_corner_marks
    assert cockpit.module_flag("tracking", "show_grid")
    assert cockpit.colors["BACKGROUND"] != cockpit.colors["INSTRUMENT"]
    assert len({cockpit.colors["GREEN"], cockpit.colors["CAUTION"], cockpit.colors["RED"]}) == 3
    assert all(len(color) == 4 and all(0 <= channel <= 255 for channel in color) for color in cockpit.colors.values())


def test_classic_palette_retains_historical_core_colors():
    classic = get_theme("classic")
    assert not classic.shows_corner_marks
    assert not classic.module_flag("tracking", "show_grid")
    assert classic.colors["BACKGROUND"] == (240, 240, 240, 255)
    assert classic.colors["BLACK"] == (50, 50, 50, 255)
    assert classic.colors["GREEN"] == (142, 219, 176, 255)
    assert classic.colors["ACCENT"] == classic.colors["BLACK"]
    assert classic.colors["WHITE_TRANSLUCENT"] == (255, 255, 255, 235)
    assert classic.colors["LIGHTGREY"] == (220, 220, 220, 255)
    assert classic.colors["BLUE"] == (153, 204, 255, 255)
    assert classic.colors["BEZEL"] == (50, 50, 50, 255)


def test_cockpit_palette_retains_historical_compatibility_aliases():
    cockpit = get_theme("cockpit")
    assert cockpit.colors["WHITE_TRANSLUCENT"] == (21, 31, 39, 242)
    assert cockpit.colors["BLACK"] == (196, 218, 225, 255)
    assert cockpit.colors["LIGHTGREY"] == (21, 31, 39, 255)
    assert cockpit.colors["BLUE"] == (91, 209, 229, 255)


def test_fac_modern_has_light_fac_semantics_with_presentation_only_geometry():
    modern = get_theme("fac_modern")
    assert modern.profile_id == "matb-fac-modern"
    assert modern.panel_radius == 12
    assert modern.line_width == 2
    assert modern.module_option("system_monitoring", "lamp_shape") == "circle"
    assert modern.module_color("tracking", "axis") == (40, 110, 243, 255)
    assert modern.module_flag("resource_management", "show_pump_ring")
    assert modern.schema_version == "openmatb-visual-profile-v1"


def test_daylight_preserves_tracking_state_colors_and_actual_label_contrast():
    from matb_integration.openmatb_visual_profiles import assess_visual_profile, contrast_ratio

    root = Path(__file__).resolve().parents[1] / "themes"
    original = load_visual_profile(root / "fac_modern.json")
    daylight = load_visual_profile(root / "daylight_avionics.json")
    assert daylight["profile_id"] == "matb-daylight-avionics"
    assert daylight["version"] == "1.0.0"
    assert daylight["geometry_policy"] == original["geometry_policy"]
    assert daylight["modules"]["tracking"] == original["modules"]["tracking"]
    assert daylight["palette"]["text"] == original["palette"]["text"]
    pairs = {
        "system_monitoring": ("lamp_1", "lamp_2", "lamp_3", "lamp_4", "lamp_off", "pointer", "feedback_positive", "feedback_negative"),
        "communications": ("active", "inactive", "positive", "negative"),
        "resource_management": ("fluid", "pipe_on", "pipe_off", "pump_on", "pump_off", "pump_failure", "tolerance", "meter"),
    }
    for module, keys in pairs.items():
        for key in keys:
            assert daylight["modules"][module][key] == original["modules"][module][key]
    for module, keys in {
        "system_monitoring": ("lamp_1", "lamp_2", "lamp_off"),
        "resource_management": ("pump_on", "pump_off", "pump_failure"),
    }.items():
        for key in keys:
            assert contrast_ratio(daylight["palette"]["text"], daylight["modules"][module][key]) == contrast_ratio(original["palette"]["text"], original["modules"][module][key])
    assert not assess_visual_profile(daylight)["errors"]
    assert assess_visual_profile(daylight)["warnings"] == assess_visual_profile(original)["warnings"]
    assert get_theme("daylight_avionics").sha256 == profile_sha256(daylight)


def test_visual_profile_hash_is_stable_across_json_formatting(tmp_path: Path):
    source = Path(__file__).resolve().parents[1] / "themes" / "fac_modern.json"
    profile = load_visual_profile(source)
    reformatted = tmp_path / "profile.json"
    reformatted.write_text(json.dumps(profile, indent=7, sort_keys=False), encoding="utf-8")
    loaded = get_theme_from_file(reformatted)
    assert loaded.sha256 == profile_sha256(profile)


def test_visual_profile_rejects_unknown_or_behavioral_fields():
    source = Path(__file__).resolve().parents[1] / "themes" / "fac_modern.json"
    profile = deepcopy(load_visual_profile(source))
    profile["automation"] = {"enabled": True}
    with pytest.raises(VisualProfileValidationError, match="unknown fields: automation"):
        validate_visual_profile(profile)


def test_visual_profile_rejects_css_and_non_hex_colors():
    source = Path(__file__).resolve().parents[1] / "themes" / "fac_modern.json"
    profile = deepcopy(load_visual_profile(source))
    profile["palette"]["accent"] = "var(--fac-blue)"
    with pytest.raises(VisualProfileValidationError, match="#RRGGBB"):
        validate_visual_profile(profile)
