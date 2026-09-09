"""Analysis execution identity, independent of the native acquisition manifest.

No acquisition environment variables are trusted as analysis source identity.
Unavailable source metadata stays unavailable in installed distributions.
"""
from __future__ import annotations

from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import platform
import subprocess
import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .contracts import canonical_bytes

ANALYSIS_CONFIG = {"continuous_sample_max_gap_intervals": 3, "missing_sample_interpolation": False}
ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILES = (
    "matb_integration/contracts/__init__.py", "matb_integration/contracts/_immutability.py",
    "matb_integration/contracts/events.py", "matb_integration/contracts/components.py",
    "matb_integration/contracts/experiments.py", "matb_integration/log_converter.py",
    "matb_integration/metrics_spec.json", "matb_integration/metrics_schema.py", "matb_integration/evidence/contracts.py",
    "matb_integration/evidence/reconcile.py", "matb_integration/evidence/provenance.py",
)


class AnalysisExecutionV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["1.0"] = "1.0"
    source_commit: str | None = Field(pattern=r"^[a-f0-9]{40,64}$")
    source_dirty: bool | None
    implementation_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_files: dict[str, str]
    dependency_lock_sha256: str | None
    dependencies: dict[str, str | None]
    dependency_lock_matches: bool
    environment: dict[str, str]
    analysis_configuration: dict


def collect_analysis_execution() -> dict:
    """Capture once per derivation; excludes paths, usernames and wall-clock time."""
    hashes = {name: sha256((ROOT / name).read_text(encoding="utf-8").encode()).hexdigest()
              for name in SOURCE_FILES}
    commit, dirty = None, None
    try:
        result = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=5, check=True)
        commit = result.stdout.strip()
        result = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
                                capture_output=True, text=True, timeout=5, check=True)
        dirty = bool(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        commit, dirty = None, None
    lock = ROOT / "requirements-evidence.lock"
    content = lock.read_text(encoding="utf-8") if lock.is_file() else ""
    expected = dict(line.split("==", 1) for line in content.splitlines() if line and not line.startswith("#"))
    dependencies = {}
    for name in expected:
        try:
            dependencies[name] = version(name)
        except PackageNotFoundError:
            dependencies[name] = None
    return AnalysisExecutionV1(
        source_commit=commit, source_dirty=dirty, source_files=hashes,
        implementation_sha256=sha256(canonical_bytes(hashes)).hexdigest(),
        dependency_lock_sha256=sha256(content.encode()).hexdigest() if content else None,
        dependencies=dependencies, dependency_lock_matches=bool(expected) and dependencies == expected,
        environment={"python": platform.python_version(), "implementation": sys.implementation.name,
                     "os": platform.system(), "os_release": platform.release(), "machine": platform.machine()},
        analysis_configuration=dict(ANALYSIS_CONFIG),
    ).model_dump()


def validate_execution(value: dict) -> dict:
    execution = AnalysisExecutionV1.model_validate(value).model_dump()
    if execution["analysis_configuration"] != ANALYSIS_CONFIG:
        raise ValueError("unsupported analysis configuration")
    if execution["implementation_sha256"] != sha256(canonical_bytes(execution["source_files"])).hexdigest():
        raise ValueError("analysis implementation digest mismatch")
    return execution
