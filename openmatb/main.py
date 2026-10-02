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
    theme = parser.add_mutually_exclusive_group()
    theme.add_argument("--visual-theme", choices=("classic", "cockpit", "fac_modern", "daylight_avionics"), default=None)
    theme.add_argument("--theme-file", type=Path, default=None)
    parser.add_argument("--display-index", type=int, default=None)
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--control-stdio", action="store_true")
    parser.add_argument(
        "--skip-briefing", action="store_true", help="Skip the standalone Spanish briefing for synthetic diagnostics"
    )
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
from matb_integration.scenario_builder import detect_generator_source_provenance
_runtime_commit, _runtime_dirty = detect_generator_source_provenance(REPOSITORY_ROOT)
os.environ["MATB_SOURCE_COMMIT"] = _runtime_commit
if _runtime_dirty is None:
    os.environ.pop("MATB_SOURCE_DIRTY", None)
else:
    os.environ["MATB_SOURCE_DIRTY"] = "true" if _runtime_dirty else "false"
os.chdir(OPENMATB_ROOT)
if ARGS.session_dir is not None:
    os.environ["MATB_OPENMATB_SESSION_DIR"] = str(ARGS.session_dir.resolve())
if ARGS.display_index is not None:
    os.environ["MATB_OPENMATB_SCREEN_INDEX"] = str(ARGS.display_index)
if ARGS.windowed:
    os.environ["MATB_OPENMATB_FULLSCREEN"] = "False"
if ARGS.visual_theme is not None:
    os.environ.pop("MATB_OPENMATB_THEME_FILE", None)
    os.environ["MATB_OPENMATB_VISUAL_THEME"] = ARGS.visual_theme
if ARGS.theme_file is not None:
    theme_file = ARGS.theme_file.expanduser().resolve(strict=True)
    if not theme_file.is_file():
        raise ValueError("--theme-file must point to a regular file")
    os.environ.pop("MATB_OPENMATB_VISUAL_THEME", None)
    os.environ["MATB_OPENMATB_THEME_FILE"] = str(theme_file)
if ARGS.control_stdio:
    os.environ["MATB_OPENMATB_DISPLAY_SESSION_NUMBER"] = "False"

LOCALE_PATH = OPENMATB_ROOT / "locales"
configured_language = ARGS.language
if configured_language is None:
    with (OPENMATB_ROOT / "config.ini").open("r", encoding="utf-8") as handle:
        configured_language = [line for line in handle if "language=" in line][0].split("=")[-1].strip()
gettext.translation("openmatb", LOCALE_PATH, [configured_language], fallback=True).install()

from core import ReplayScheduler, Scheduler
from core.constants import PATHS, REPLAY_MODE
from core.controlbridge import StdioControlBridge
from core.selector import FileSelector
from core.utils import get_conf_value
from core.window import Window


def _release_audio_driver() -> None:
    """Stop native audio workers before interpreter/COM garbage collection."""
    from pyglet.media import get_audio_driver

    driver = get_audio_driver()
    if driver is not None:
        driver.delete()


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
        try:
            Scheduler(
                scenario_path=selected,
                control_bridge=StdioControlBridge() if ARGS.control_stdio else None,
                participant_briefing=(
                    not ARGS.control_stdio and not ARGS.skip_briefing and configured_language.startswith("es")
                ),
            )
        finally:
            _release_audio_driver()


if __name__ == "__main__":
    OpenMATB()
