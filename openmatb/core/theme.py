# Copyright 2023-2026, by Julien Cegarra & Benoit Valery. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

"""Immutable, data-driven visual themes for the OpenMATB presentation layer.

Themes contain rendering data only. Task state, geometry, input areas, timing,
and scoring remain owned by the existing plugins and widgets.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

# ``main.py`` performs this setup for participant launches. Theme validation is
# also used by standalone utilities and focused tests, so keep imports stable
# when those entry points start inside ``openmatb/``.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.append(str(_REPOSITORY_ROOT))

from matb_integration.openmatb_visual_profiles import (  # noqa: E402
    hex_to_rgba,
    load_visual_profile,
    profile_sha256,
    validate_visual_profile,
)

Color = tuple[int, int, int, int]
VISUAL_THEME_NAMES = ("classic", "cockpit", "fac_modern", "daylight_avionics")
_THEME_ROOT = Path(__file__).resolve().parents[1] / "themes"

# These public names predate visual profiles and remain available to scenario
# colors, the replay UI, and selectors. Preserve their exact bundled values
# while configurable widgets consume semantic palette/module tokens below.
_BUNDLED_LEGACY_ALIAS_OVERRIDES: Mapping[str, Mapping[str, Color]] = MappingProxyType(
    {
        "classic": MappingProxyType(
            {
                "WHITE_TRANSLUCENT": (255, 255, 255, 235),
                "LIGHTGREY": (220, 220, 220, 255),
                "BEZEL": (50, 50, 50, 255),
            }
        ),
        "cockpit": MappingProxyType(
            {
                "WHITE_TRANSLUCENT": (21, 31, 39, 242),
                "BLACK": (196, 218, 225, 255),
                "LIGHTGREY": (21, 31, 39, 255),
            }
        ),
    }
)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    return value


@dataclass(frozen=True, slots=True)
class ThemeSpec:
    """Validated visual profile exposed as semantic rendering properties."""

    name: str
    profile_id: str
    version: str
    label: str
    schema_version: str
    sha256: str
    palette: Mapping[str, Color]
    metrics: Mapping[str, float]
    modules: Mapping[str, Mapping[str, Color | str | bool]]
    colors: Mapping[str, Color]

    @property
    def line_width(self) -> float:
        return self.metrics["line_width"]

    @property
    def panel_radius(self) -> float:
        return self.metrics["panel_radius"]

    @property
    def corner_mark_ratio(self) -> float:
        return self.metrics["corner_mark_ratio"]

    @property
    def shows_corner_marks(self) -> bool:
        return self.corner_mark_ratio > 0

    def module_color(self, module: str, key: str) -> Color:
        value = self.modules[module][key]
        if not isinstance(value, tuple):
            raise KeyError(f"{module}.{key} is not a color")
        return value

    def module_flag(self, module: str, key: str) -> bool:
        value = self.modules[module][key]
        if not isinstance(value, bool):
            raise KeyError(f"{module}.{key} is not a flag")
        return value

    def module_option(self, module: str, key: str) -> str:
        value = self.modules[module][key]
        if not isinstance(value, str):
            raise KeyError(f"{module}.{key} is not an option")
        return value


def _theme_from_profile(profile: dict[str, Any], *, name: str | None = None) -> ThemeSpec:
    normalized = validate_visual_profile(profile)
    palette = {key: hex_to_rgba(value) for key, value in normalized["palette"].items()}
    modules: dict[str, dict[str, Color | str | bool]] = {}
    for module_name, module in normalized["modules"].items():
        modules[module_name] = {
            key: hex_to_rgba(value) if isinstance(value, str) and value.startswith("#") else value
            for key, value in module.items()
        }

    # Compatibility aliases keep scenario color parameters stable while all
    # renderer-specific decisions use semantic palette/module properties.
    colors: dict[str, Color] = {
        "WHITE": (255, 255, 255, 255),
        "WHITE_TRANSLUCENT": palette["panel_background"],
        "BLACK": palette["text"],
        "GREEN": palette["safe"],
        "RED": palette["critical"],
        "BACKGROUND": palette["app_background"],
        "LIGHTGREY": palette["panel_background"],
        "DARKGREY": palette["panel_header"],
        "GREY": palette["muted_text"],
        "BLUE": modules["workload"]["marker"],
        "PANEL": palette["panel_background"],
        "INSTRUMENT": palette["instrument_background"],
        "LINE": palette["border"],
        "TEXT": palette["text"],
        "MUTED": palette["muted_text"],
        "ACCENT": palette["accent"],
        "CAUTION": palette["warning"],
        "BEZEL": palette["grid"],
        "CONTROL_OFF": palette["disabled"],
    }
    colors.update(_BUNDLED_LEGACY_ALIAS_OVERRIDES.get(name or "", {}))
    return ThemeSpec(
        name=name or normalized["profile_id"],
        profile_id=normalized["profile_id"],
        version=normalized["version"],
        label=normalized["label"],
        schema_version=normalized["schema_version"],
        sha256=profile_sha256(normalized),
        palette=_freeze(palette),
        metrics=_freeze(normalized["metrics"]),
        modules=_freeze(modules),
        colors=_freeze(colors),
    )


def _load_bundled_theme(name: str) -> ThemeSpec:
    return _theme_from_profile(load_visual_profile(_THEME_ROOT / f"{name}.json"), name=name)


THEMES: Mapping[str, ThemeSpec] = MappingProxyType(
    {name: _load_bundled_theme(name) for name in VISUAL_THEME_NAMES}
)


def normalize_visual_theme(value: str | None) -> str:
    normalized = (value or "daylight_avionics").strip().lower()
    if normalized not in THEMES:
        allowed = ", ".join(VISUAL_THEME_NAMES)
        raise ValueError(f"visual_theme must be one of: {allowed}")
    return normalized


def get_theme(value: str | None) -> ThemeSpec:
    return THEMES[normalize_visual_theme(value)]


def get_theme_from_file(path: str | Path) -> ThemeSpec:
    candidate = Path(path).expanduser().resolve(strict=True)
    if not candidate.is_file():
        raise ValueError("theme file must be a regular file")
    return _theme_from_profile(load_visual_profile(candidate))


def resolve_theme(*, theme_file: str | Path | None, visual_theme: str | None) -> ThemeSpec:
    if theme_file is not None and visual_theme is not None:
        raise ValueError("theme_file and visual_theme are mutually exclusive")
    if theme_file is not None:
        return get_theme_from_file(theme_file)
    return get_theme(visual_theme)
