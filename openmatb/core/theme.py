# Copyright 2023-2026, by Julien Cegarra & Benoit Valery. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

"""Visual-theme definitions for the OpenMATB presentation layer.

Themes intentionally contain rendering data only.  Task state, geometry, input
areas, timing, and scoring remain owned by the existing plugins and widgets.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

Color = tuple[int, int, int, int]
VISUAL_THEME_NAMES = ("classic", "cockpit")


@dataclass(frozen=True, slots=True)
class ThemeSpec:
    name: str
    colors: Mapping[str, Color]
    line_width: float
    corner_mark_ratio: float

    @property
    def is_cockpit(self) -> bool:
        return self.name == "cockpit"


_CLASSIC_COLORS: dict[str, Color] = {
    "WHITE": (255, 255, 255, 255),
    "WHITE_TRANSLUCENT": (255, 255, 255, 235),
    "BLACK": (50, 50, 50, 255),
    "GREEN": (142, 219, 176, 255),
    "RED": (241, 100, 100, 255),
    "BACKGROUND": (240, 240, 240, 255),
    "LIGHTGREY": (220, 220, 220, 255),
    "DARKGREY": (50, 50, 50, 255),
    "GREY": (200, 200, 200, 255),
    "BLUE": (153, 204, 255, 255),
    "PANEL": (240, 240, 240, 255),
    "INSTRUMENT": (255, 255, 255, 255),
    "LINE": (50, 50, 50, 255),
    "TEXT": (50, 50, 50, 255),
    "MUTED": (200, 200, 200, 255),
    # Preserve the historical black instrument pointers in classic mode.
    # BLUE remains available to controls that previously used it explicitly.
    "ACCENT": (50, 50, 50, 255),
    "CAUTION": (226, 159, 56, 255),
    "BEZEL": (50, 50, 50, 255),
    "CONTROL_OFF": (255, 255, 255, 255),
}

_COCKPIT_COLORS: dict[str, Color] = {
    # Named WHITE is a public scenario/configuration color and remains literal.
    "WHITE": (255, 255, 255, 255),
    "WHITE_TRANSLUCENT": (21, 31, 39, 242),
    "BLACK": (196, 218, 225, 255),
    "GREEN": (83, 214, 151, 255),
    "RED": (255, 91, 91, 255),
    "BACKGROUND": (10, 16, 21, 255),
    "LIGHTGREY": (21, 31, 39, 255),
    "DARKGREY": (6, 10, 14, 255),
    "GREY": (93, 116, 126, 255),
    "BLUE": (91, 209, 229, 255),
    "PANEL": (15, 24, 31, 255),
    "INSTRUMENT": (7, 13, 18, 255),
    "LINE": (111, 142, 153, 255),
    "TEXT": (220, 235, 239, 255),
    "MUTED": (93, 116, 126, 255),
    "ACCENT": (91, 209, 229, 255),
    "CAUTION": (255, 181, 71, 255),
    "BEZEL": (31, 46, 56, 255),
    "CONTROL_OFF": (31, 46, 56, 255),
}

THEMES: Mapping[str, ThemeSpec] = MappingProxyType({
    "classic": ThemeSpec("classic", MappingProxyType(_CLASSIC_COLORS), 2.0, 0.0),
    "cockpit": ThemeSpec("cockpit", MappingProxyType(_COCKPIT_COLORS), 2.0, 0.08),
})


def normalize_visual_theme(value: str | None) -> str:
    normalized = (value or "classic").strip().lower()
    if normalized not in THEMES:
        allowed = ", ".join(VISUAL_THEME_NAMES)
        raise ValueError(f"visual_theme must be one of: {allowed}")
    return normalized


def get_theme(value: str | None) -> ThemeSpec:
    return THEMES[normalize_visual_theme(value)]
