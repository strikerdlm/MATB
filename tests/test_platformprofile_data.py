"""Unit tests for platform profile helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[1] / 'plugins' / 'platformprofile_data.py'
    spec = importlib.util.spec_from_file_location('platformprofile_data', module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError('Unable to load platformprofile_data module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_module = _load_module()
build_profile = _module.build_profile
canonical_platform_id = _module.canonical_platform_id
parse_override_block = _module.parse_override_block


def test_build_profile_defaults_scaneagle() -> None:
    profile = build_profile('ScanEagle')
    assert profile['id'] == 'scaneagle'
    assert profile['name'] == 'ScanEagle'
    assert profile['endurance_sec'] == 24 * 3600
    assert profile['sensors'] == ('EO Zoom', 'IR', 'Multi-Imager')
    assert profile['warning_buffer_sec'] >= 600


def test_build_profile_with_overrides_and_units() -> None:
    overrides = parse_override_block('endurance=12h|payload=4.5|datalink=55|sensors=EO/IR|launch=VTOL')
    profile = build_profile('custom', overrides)
    assert profile['endurance_sec'] == 43200
    assert profile['payload_capacity_kg'] == 4.5
    assert profile['datalink_mbps'] == 55.0
    assert profile['sensors'] == ('EO', 'IR')
    assert profile['launch_method'] == 'VTOL'


def test_canonical_platform_id_strips_whitespace() -> None:
    assert canonical_platform_id('  ScanEagle  ') == 'scaneagle'

