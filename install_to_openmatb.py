#!/usr/bin/env python3
"""
Copy military aviation assets (questionnaires + scenarios) into an OpenMATB tree.

Usage:
    python3 install_to_openmatb.py /custom/path
    OPENMATB_DIR=/custom/path python3 install_to_openmatb.py
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

MATB_ROOT = Path(__file__).resolve().parent
QUESTIONNAIRES_SRC = MATB_ROOT / "matb_integration" / "questionnaires"
SCENARIOS_SRC = MATB_ROOT / "scenarios" / "military_aviation"


def _default_openmatb() -> Path | None:
    raw = os.environ.get("OPENMATB_DIR")
    return Path(raw).expanduser() if raw else None


def install(openmatb_path: Path) -> None:
    includes = openmatb_path / "includes"
    if not includes.is_dir():
        sys.exit(
            f"Error: {includes} not found.\n"
            f"Is {openmatb_path} an OpenMATB installation?\n"
            f"Pass a local OpenMATB checkout/install root containing includes/."
        )

    # Questionnaires
    q_dest = includes / "questionnaires"
    q_dest.mkdir(parents=True, exist_ok=True)
    for src in sorted(QUESTIONNAIRES_SRC.glob("*.txt")):
        dst = q_dest / src.name
        shutil.copy2(src, dst)
        print(f"  questionnaire: {src.name} → {dst}")

    # Scenarios
    s_dest = includes / "scenarios" / "military_aviation"
    s_dest.mkdir(parents=True, exist_ok=True)
    for src in sorted(SCENARIOS_SRC.glob("*.txt")):
        dst = s_dest / src.name
        shutil.copy2(src, dst)
        print(f"  scenario:      {src.name} → {dst}")

    print(f"\nDone. To run a scenario:")
    print(f"  cd {openmatb_path}")
    print(f"  DISPLAY=:100 python main.py   # Linux/headless")
    print(f"  python main.py                 # Windows / macOS")
    print(f"  # then select: scenarios/military_aviation/low_workload.txt")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Install military aviation assets into OpenMATB.")
    parser.add_argument(
        "openmatb_path",
        type=Path,
        nargs="?",
        default=_default_openmatb(),
        help="Path to an external OpenMATB directory, or set OPENMATB_DIR",
    )
    args = parser.parse_args()
    if args.openmatb_path is None:
        parser.error(
            "openmatb_path is required because the vendored openmatb submodule "
            "has been removed. Pass /path/to/openmatb or set OPENMATB_DIR."
        )
    install(args.openmatb_path)
