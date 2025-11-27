"""Unit tests for the VTOL manager helper model."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[1] / 'plugins' / 'vtolmanager_model.py'
    spec = importlib.util.spec_from_file_location('vtolmanager_model', module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError('Unable to load vtolmanager_model module')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_module = _load_module()
VtolModel = _module.VtolModel


def _build_model() -> VtolModel:
    return VtolModel(
        battery_seconds=1800,
        phase_power={
            'vertical_takeoff': 1.4,
            'transition': 1.2,
            'cruise': 0.8,
            'transition_return': 1.1,
            'vertical_landing': 1.5,
        },
        confirm_phases=('transition', 'transition_return'),
        warning_ratio=0.3,
        critical_ratio=0.15,
    )


def test_phase_change_sets_pending_flag() -> None:
    model = _build_model()
    info = model.set_phase('VTOL1', 'transition', now=10.0)
    assert info['pending_confirmation'] is True
    assert model.pending('VTOL1') is True
    assert model.confirm('VTOL1') is True
    assert model.pending('VTOL1') is False


def test_energy_consumption_triggers_warnings() -> None:
    model = _build_model()
    model.set_phase('VTOL2', 'cruise', now=0.0)
    remaining, level = model.update_energy('VTOL2', now=1000.0)
    assert remaining < 1800
    assert level in (None, 'warning', 'critical')
    model.set_battery('VTOL2', 600, now=1000.0)
    assert model.update_energy('VTOL2', now=1600.0)[0] <= 600

