"""Regression: the `app` package must make `matb_integration` importable.

The running server (uvicorn launched from webui/backend) has neither the repo
root on PYTHONPATH nor the conftest sys.path hack. app/__init__.py bootstraps
it. This caught a real 500 (ModuleNotFoundError) that the TestClient tests
masked because conftest injects the repo root.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]  # webui/backend


def test_app_package_makes_matb_integration_importable():
    # Fresh interpreter, cwd = webui/backend, clean env (no PYTHONPATH leak).
    result = subprocess.run(
        [sys.executable, "-c", "import app; import matb_integration; print('ok')"],
        cwd=_BACKEND_DIR,
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "")},
    )
    assert result.returncode == 0, f"stderr:\n{result.stderr}"
    assert "ok" in result.stdout
