"""Bridge the vendored OpenMATB runtime to the repository scientific recorder."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from matb_integration.scientific_data.recorder import ResearchRecorder  # noqa: E402


def _scenario_source(scenario_path: Path | None) -> dict[str, Any]:
    if scenario_path is None:
        return {}
    source: dict[str, Any] = {
        "scenario": {
            "filename": scenario_path.name,
            "sha256": hashlib.sha256(scenario_path.read_bytes()).hexdigest(),
        }
    }
    manifest_path = scenario_path.with_suffix(scenario_path.suffix + ".manifest.json")
    if manifest_path.is_file():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            source["scenario_manifest_error"] = f"{type(exc).__name__}: {exc}"
        else:
            if isinstance(payload, dict):
                source["scenario_manifest"] = payload
                source["scenario_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            else:
                source["scenario_manifest_error"] = "manifest root is not an object"
    return source


def create_research_recorder(
    *,
    logger: Any,
    scenario_path: Path | None,
    enabled: bool,
    sample_hz: float,
    start_monotonic_ns: int,
    start_utc_ns: int,
    flush_interval_sec: float = 1.0,
    fsync_interval_sec: float = 5.0,
) -> ResearchRecorder | None:
    if not enabled:
        return None
    legacy_path = Path(logger.path)
    source = _scenario_source(scenario_path)
    scenario_manifest = source.get("scenario_manifest", {})
    score_config: dict[str, Any] = {}
    if isinstance(scenario_manifest, dict):
        parameters = scenario_manifest.get("parameters", {})
        if isinstance(parameters, dict) and isinstance(parameters.get("scientific_scoring"), dict):
            score_config = dict(parameters["scientific_scoring"])
    return ResearchRecorder(
        session_id=str(logger.session_id),
        run_dir=legacy_path.with_suffix(".research"),
        sample_hz=sample_hz,
        start_monotonic_ns=start_monotonic_ns,
        start_utc_ns=start_utc_ns,
        manifest=source,
        score_config=score_config,
        flush_interval_sec=flush_interval_sec,
        fsync_interval_sec=fsync_interval_sec,
    )


__all__ = ["create_research_recorder"]
