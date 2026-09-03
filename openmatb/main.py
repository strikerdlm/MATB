#! .venv/bin/python3

"""OpenMATB entry point, including the supervised MATB-FAC launch contract."""

from __future__ import annotations

import argparse
import gettext
import os
import sys
from pathlib import Path


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("-r", "--replay", action="store_true")
    parser.add_argument("--scenario", type=Path)
    parser.add_argument("--session-dir", type=Path)
    parser.add_argument("--language", default=None)
    parser.add_argument("--display-index", type=int, default=None)
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--control-stdio", action="store_true")
    args, _unknown = parser.parse_known_args()
    if args.display_index is not None and args.display_index < 0:
        parser.error("--display-index must be non-negative")
    if args.control_stdio and args.scenario is None:
        parser.error("--control-stdio requires --scenario")
    return args


ARGS = _arguments()
OPENMATB_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = OPENMATB_ROOT.parent
# Bound scenario provenance imports the canonical generator and research
# protocol. Direct launches set sys.path to openmatb/, so add the repository
# root explicitly on Windows and Linux instead of relying on the caller's cwd.
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
os.chdir(OPENMATB_ROOT)
if ARGS.session_dir is not None:
    os.environ["MATB_OPENMATB_SESSION_DIR"] = str(ARGS.session_dir.resolve())
if ARGS.display_index is not None:
    os.environ["MATB_OPENMATB_SCREEN_INDEX"] = str(ARGS.display_index)
if ARGS.windowed:
    os.environ["MATB_OPENMATB_FULLSCREEN"] = "False"
if ARGS.control_stdio:
    os.environ["MATB_OPENMATB_DISPLAY_SESSION_NUMBER"] = "False"

LOCALE_PATH = OPENMATB_ROOT / "locales"
configured_language = ARGS.language
if configured_language is None:
    with (OPENMATB_ROOT / "config.ini").open("r", encoding="utf-8") as handle:
        configured_language = [line for line in handle if "language=" in line][0].split("=")[-1].strip()
catalog_language = "en_EN" if configured_language.lower().startswith("es") else configured_language
gettext.translation("openmatb", LOCALE_PATH, [catalog_language], fallback=True).install()

from core import ReplayScheduler, Scheduler
from core.constants import PATHS, REPLAY_MODE
from core.controlbridge import StdioControlBridge
from core.selector import FileSelector
from core.utils import get_conf_value
from core.window import Window


class OpenMATB:
    def __init__(self) -> None:
        Window(style=Window.WINDOW_STYLE_DIALOG, resizable=True)
        if REPLAY_MODE or ARGS.replay:
            selected = FileSelector(Window.MainWindow, "replay").run()
            if selected is None:
                sys.exit(0)
            ReplayScheduler(session_path=selected)
            return

        if ARGS.scenario is not None:
            selected = ARGS.scenario.resolve()
        else:
            ini_scenario = get_conf_value("Openmatb", "scenario_path").strip()
            selected = PATHS["SCENARIOS"].joinpath(ini_scenario) if ini_scenario else FileSelector(
                Window.MainWindow, "scenario"
            ).run()
            if selected is None:
                sys.exit(0)
        Scheduler(
            scenario_path=selected,
            control_bridge=StdioControlBridge() if ARGS.control_stdio else None,
        )


if __name__ == "__main__":
    OpenMATB()
