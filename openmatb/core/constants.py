# Copyright 2023-2026, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

import configparser
import os
import sys
from pathlib import Path

from pyglet.graphics import Group  # noqa: F401

from core.theme import get_theme

REPLAY_MODE: bool = len(sys.argv) > 1 and sys.argv[1] == "-r"
REPLAY_STRIP_PROPORTION: float = 0.08

FONT_SIZES: dict[str, int] = dict(SMALL=12, MEDIUM=16, LARGE=20, XLARGE=30)
F = FONT_SIZES

# Proportion of the plugin title into its container
PLUGIN_TITLE_HEIGHT_PROPORTION: float = 0.1

# Limit between the background and the foreground in relation with draw order
BFLIM: int = 15

# Ignore these plugins arguments
DEPRECATED: list[str] = ["pumpstatus", "end", "cutofffrequency", "equalproportions"]

SYSTEM_PSEUDO_PLUGIN: str = "system"
SYSTEM_COMMANDS: list[str] = ["pause", "boundary"]

PATHS: dict[str, Path] = {k.upper(): Path(".", k) for k in ["plugins", "sessions"]}
if configured_sessions := os.environ.get("MATB_OPENMATB_SESSION_DIR"):
    PATHS["SESSIONS"] = Path(configured_sessions).expanduser().resolve()
PATHS.update(
    {k.upper(): Path(".", "includes", k) for k in ["img", "instructions", "scenarios", "sounds", "questionnaires"]}
)

[path.mkdir(parents=False, exist_ok=True) for p, path in PATHS.items() if path.exists() is False]
PATHS["SCENARIO_ERRORS"] = Path(".", "last_scenario_errors.log")

# Read the configuration file
CONFIG: configparser.ConfigParser = configparser.ConfigParser()
CONFIG.read(PATHS["PLUGINS"].parent.joinpath("config.ini"))

VISUAL_THEME = get_theme(
    os.environ.get(
        "MATB_OPENMATB_VISUAL_THEME",
        CONFIG.get("Openmatb", "visual_theme", fallback="classic"),
    )
)
COLORS: dict[str, tuple[int, int, int, int]] = dict(VISUAL_THEME.colors)
C = COLORS
