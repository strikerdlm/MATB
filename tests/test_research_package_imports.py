"""Import-boundary tests for the research package."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_protocol_import_does_not_require_rich() -> None:
    """Scientific protocol consumers should not load the terminal UI stack."""
    repo_root = Path(__file__).resolve().parents[1]
    script = f"""
import builtins
import sys

sys.path.insert(0, {str(repo_root)!r})
real_import = builtins.__import__

def import_without_rich(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "rich" or name.startswith("rich."):
        raise ModuleNotFoundError("blocked optional Rich dependency")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = import_without_rich
from aircraft_monitor.research.protocol import WorkloadLevel

assert WorkloadLevel.LOW.value == "low"
assert "aircraft_monitor.research.runner" not in sys.modules
"""

    subprocess.run(
        [sys.executable, "-I", "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )
