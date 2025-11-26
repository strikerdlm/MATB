# Copyright 2023, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)
import os
import subprocess
from pathlib import Path
from typing import Optional
from pyglet import font
from core.constants import PATHS as P, CONFIG
import sys

def clamp(x, val_min, val_max):
    if x < val_min:
        return val_min
    elif x > val_max:
        return val_max
    return x


def get_session_numbers():
    session_numbers = list()
    try:
        for csv_file in P['SESSIONS'].glob('**/*.csv'):
            number = _extract_session_number(csv_file)
            if number is not None:
                session_numbers.append(number)
    except FileNotFoundError:
        pass

    if len(session_numbers) == 0:
        return [0]
    return session_numbers


def _extract_session_number(path: Path) -> Optional[int]:
    stem = path.stem
    if '_' in stem and stem.split('_')[0].isdigit():
        return int(stem.split('_')[0])
    parent_name = path.parent.name
    if '_' in parent_name and parent_name.split('_')[0].isdigit():
        return int(parent_name.split('_')[0])
    return None


def find_the_first_available_session_number():
    session_numbers = get_session_numbers()
    first_avail = None

    # Take max session number + 1, and find the minimum available number into [1, max+1]
    # If no session has been manually removed, it will be max+1
    if len(session_numbers) == 0:
        first_avail = 1
    else:
        for n in range(1, max(session_numbers)+1):
            if n not in session_numbers and first_avail is None:
                first_avail = n

    if first_avail is None:
        first_avail = max(session_numbers) + 1

    return first_avail


def find_the_last_session_number():
    session_numbers = get_session_numbers()
    return max(session_numbers)

def has_conf_value(section, key):
    return key in CONFIG

def get_conf_value(section, key, val_type=None):
    value = CONFIG[section][key]

    # Boolean boolean values
    if key in ['fullscreen', 'highlight_aoi', 'hide_on_pause', 'display_session_number']:
        if value.strip().lower() == 'true':
            return True
        elif value.strip().lower() == 'false':
            return False
        else:
            raise TypeError(_(f"In config.ini, [%s] parameter must be a boolean (true or false, not %s). Defaulting to False") % (key, value))


    # Integer values
    elif key in ['screen_index']:
        try:
            value = int(value)
        except:
            raise TypeError(_(f"In config.ini, [%s] parameter must be an integer (not %s)") % (key, value))
        else:
            return value

    # Float values
    elif key in ['clock_speed']:
        try:
            value = float(value)
        except:
            raise TypeError(_(f"In config.ini, [%s] parameter must be a float (not %s)") % (key, value))
        else:
            return value

    # List values
    elif key in ['top_bounds', 'bottom_bounds']:
        try:
            value = eval(value)
        except:
            raise TypeError(_(f"In config.ini, [%s] parameter must be a list of floats (not %s)") % (key, value))
        else:
            return value

    # String value
    else:
        # Font definition & check
        if key == 'font_name':
            if len(value) == 0:
                return
            elif not font.have_font(value):
                raise TypeError(_(f"In config.ini, the specified font is not available. A default font will be used."))
            else:
                return value

        return value


def get_replay_session_id()->int:
    if len(sys.argv) > 2:
        return int(sys.argv[2])
    elif has_conf_value('Replay', 'replay_session_id'):
        return int(get_conf_value('Replay', 'replay_session_id'))
    else:
        return int(find_the_last_session_number())


def open_path(target: Optional[Path]) -> bool:
    """Open a file or directory with the host OS. Returns True on success."""
    if target is None:
        return False
    resolved = Path(target)
    if not resolved.exists():
        return False
    try:
        if sys.platform.startswith('win'):
            os.startfile(str(resolved))  # type: ignore[attr-defined]
        elif sys.platform == 'darwin':
            subprocess.run(['open', str(resolved)], check=True)
        else:
            subprocess.run(['xdg-open', str(resolved)], check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False