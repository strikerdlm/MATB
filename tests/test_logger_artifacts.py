"""Tests for logger artifact capture utilities."""

from __future__ import annotations

import builtins
import json
from pathlib import Path

import sys
from unittest.mock import MagicMock

_MOCK_MODULES = [
    'pyglet',
    'pyglet.graphics',
    'pyglet.gl',
    'pyglet.window',
    'pyglet.text',
    'pyglet.image',
    'pyglet.sprite',
    'pyglet.shapes',
    'pyglet.media',
    'pyglet.clock',
    'pyglet.app',
    'pyglet.font',
    'pyglet.resource',
    'pyglet.canvas',
    'pyglet.event',
    'pyglet.input',
    'pyglet.math',
]

for module_name in _MOCK_MODULES:
    if module_name not in sys.modules:
        mock_module = MagicMock()
        if module_name == 'pyglet.graphics':
            mock_module.OrderedGroup = MagicMock
        if module_name == 'pyglet.canvas':
            mock_module.get_display = MagicMock(return_value=MagicMock())
        if module_name == 'pyglet.font':
            mock_module.have_font.return_value = True
        sys.modules[module_name] = mock_module

if not hasattr(builtins, '_'):
    builtins._ = lambda msg: msg  # type: ignore

from core.constants import PATHS
from core.logger import Logger


def test_capture_run_artifacts_creates_required_files(tmp_path: Path) -> None:
    original_sessions = PATHS['SESSIONS']
    PATHS['SESSIONS'] = tmp_path
    logger_instance = Logger()
    try:
        scenario_path = tmp_path / 'scenario.txt'
        scenario_path.write_text('TEST-SCENARIO', encoding='utf-8')
        logger_instance.capture_run_artifacts(scenario_path)

        session_dir = logger_instance.session_dir
        assert session_dir is not None

        scenario_snapshot = session_dir / 'scenario_snapshot.txt'
        assert scenario_snapshot.read_text(encoding='utf-8') == 'TEST-SCENARIO'

        assert (session_dir / 'scenario_hash.txt').read_text(encoding='utf-8').strip()
        assert (session_dir / 'config_snapshot.ini').exists()

        versions_path = session_dir / 'plugin_versions.json'
        versions = json.loads(versions_path.read_text(encoding='utf-8'))
        assert isinstance(versions, dict)
        assert 'missiondirector' in versions

        info, version = logger_instance.get_provenance_snapshot()
        assert version > 0
        assert info.get('scenario') == 'scenario.txt'
        assert info.get('scenario_hash')
    finally:
        logger_instance.close()
        PATHS['SESSIONS'] = original_sessions


def test_persist_scenario_contents_handles_inline_sources(tmp_path: Path) -> None:
    original_sessions = PATHS['SESSIONS']
    PATHS['SESSIONS'] = tmp_path
    logger_instance = Logger()
    try:
        inline_path = logger_instance.persist_scenario_contents(['LINE1\n', 'LINE2\n'])
        assert inline_path is not None and inline_path.exists()
        logger_instance.capture_run_artifacts(inline_path)
        info, version = logger_instance.get_provenance_snapshot()
        assert version > 0
        assert info.get('scenario') == inline_path.name
    finally:
        logger_instance.close()
        PATHS['SESSIONS'] = original_sessions

