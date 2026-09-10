"""Fixed console chrome provenance, independent of optional scene presentation.

Hash covers the exact bytes of the versioned profile artifact. Never bind this
on read/recovery: a missing profile denotes the historical console.
"""
from hashlib import sha256
from pathlib import Path
import json

_PROFILE_PATH = Path(__file__).resolve().parents[3] / "matb_integration/suas/presentation/console-profile.v1.json"


def current_console_profile() -> dict[str, str | int]:
    raw = _PROFILE_PATH.read_bytes()
    definition = json.loads(raw)
    return {"id": definition["id"], "version": definition["version"], "sha256": sha256(raw).hexdigest()}
