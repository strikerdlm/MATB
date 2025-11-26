"""Unit tests for the operator capacity helper model."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_module() -> ModuleType:
    module_path = PROJECT_ROOT / 'plugins' / 'operatorcapacity_model.py'
    spec = importlib.util.spec_from_file_location('operatorcapacity_module', module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError('Unable to load operatorcapacity module')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_module = _load_module()
CapacityModel = _module.CapacityModel


def test_capacity_model_detects_supervisory_violation() -> None:
    model = CapacityModel(
        active_limit=3,
        supervisory_limit=6,
        overlap_low_threshold=0.3,
        overlap_high_threshold=0.6,
        overlap_window=4,
    )
    active_report = model.update_assignments('active', ['uav1', 'uav2'], None)
    assert active_report.count == 2
    assert active_report.limit == 3
    assert active_report.exceeded is False

    supervisory_report = model.update_assignments('supervisory', None, 5)
    assert supervisory_report.limit == 6
    assert supervisory_report.exceeded is False

    model.record_overlap(0.1)
    model.record_overlap(0.2)
    supervisory_report = model.update_assignments('supervisory', None, 5)
    assert supervisory_report.limit == 4
    assert supervisory_report.exceeded is True


def test_capacity_model_updates_config_and_overlap_window() -> None:
    model = CapacityModel(
        active_limit=2,
        supervisory_limit=4,
        overlap_low_threshold=0.2,
        overlap_high_threshold=0.7,
        overlap_window=2,
    )
    model.record_overlap(0.5)
    model.update_config(active_limit=4, supervisory_limit=8, overlap_window=6)
    assert model.active_limit == 4
    assert model.supervisory_limit == 8
    assert model.overlap_samples.maxlen == 6

