# Copyright 2023-2024, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

import sys
from pyglet.graphics import OrderedGroup as Group
from pathlib import Path
import configparser

REPLAY_MODE = len(sys.argv) > 1 and sys.argv[1] == '-r'
REPLAY_STRIP_PROPORTION = 0.08

C = COLORS = dict(WHITE=(255, 255, 255, 255),
                  WHITE_TRANSLUCENT=(255, 255, 255, 235),
                  BLACK=(50, 50, 50, 255),
                  GREEN=(142, 219, 176, 255),
                  RED=(241, 100, 100, 255),
                  ORANGE=(255, 165, 0, 255),
                  YELLOW=(255, 255, 0, 255),
                  CYAN=(0, 255, 255, 255),
                  BACKGROUND=(240, 240, 240, 255),
                  LIGHTGREY=(220, 220, 220, 255),
                  DARKGREY=(50, 50, 50, 255),
                  GREY=(200, 200, 200, 255),
                  BLUE=(153, 204, 255, 255))

# Proportion of the plugin title into its container
PLUGIN_TITLE_HEIGHT_PROPORTION = 0.1

# Limit between the background and the foreground in relation with draw order
BFLIM = 15

# Ignore these plugins arguments
DEPRECATED = ['pumpstatus', 'end', 'cutofffrequency', 'equalproportions']

PATHS = {k.upper(): Path('.', k) for k in ['plugins', 'sessions']}
PATHS.update({k.upper(): Path('.', 'includes', k)
              for k in ['img', 'instructions', 'scenarios', 'sounds', 'questionnaires']})

[path.mkdir(parents=False, exist_ok=True) for p, path in PATHS.items() if path.exists() is False]
PATHS['SCENARIO_ERRORS'] = Path('.', 'last_scenario_errors.log')

# Read the configuration file
CONFIG = configparser.ConfigParser()
CONFIG.read(PATHS['PLUGINS'].parent.joinpath('config.ini'))

def _get_float_conf(section: str, key: str, default: float) -> float:
    """Return a float configuration value, falling back to a default on error."""
    try:
        raw = CONFIG[section].get(key, str(default))  # type: ignore[index]
    except Exception:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _get_bool_conf(section: str, key: str, default: bool) -> bool:
    """Return a boolean configuration value, falling back to a default on error."""
    try:
        raw = CONFIG[section].get(key, str(default))  # type: ignore[index]
    except Exception:
        return default
    return str(raw).strip().lower() == 'true'


UI_SCALE = _get_float_conf('Openmatb', 'ui_scale', 1.0)
COLORBLIND_MODE = _get_bool_conf('Openmatb', 'colorblind_mode', False)

F = FONT_SIZES = dict(TINY=int(9 * UI_SCALE),
                      SMALL=int(12 * UI_SCALE),
                      MEDIUM=int(16 * UI_SCALE),
                      LARGE=int(20 * UI_SCALE),
                      XLARGE=int(30 * UI_SCALE))

# Aeronautical/military-inspired status levels for consistent symbology
STATUS_LEVELS = ('NORMAL', 'ADVISORY', 'CAUTION', 'WARNING', 'INOPERATIVE')
STATUS_COLORS = dict(NORMAL=C['GREEN'],           # Normal/within limits
                     ADVISORY=C['BLUE'],          # Advisory/info only
                     CAUTION=C['ORANGE'],         # Caution/amber-level
                     WARNING=C['RED'],            # Warning/critical
                     INOPERATIVE=C['DARKGREY'])   # Inoperative/failed/off
