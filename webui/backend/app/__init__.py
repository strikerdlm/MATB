"""MATB Research Console backend package.

Ensures the MATB repo root is importable so the reused `matb_integration`
library (log_converter + suhir) resolves regardless of the process CWD —
e.g. when uvicorn is launched from webui/backend. Tests add this via conftest;
this bootstrap covers the production server path.
"""

from __future__ import annotations

import sys
from pathlib import Path

# webui/backend/app/__init__.py -> parents[3] == repo root (/.../MATB)
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
