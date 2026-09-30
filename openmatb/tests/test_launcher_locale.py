"""The native launcher must install the requested catalog, including Spanish."""

import builtins
import os
import runpy
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.parametrize("language,title", [
    ("es_CO", "Comunicaciones"),
    ("en_EN", "Communications"),
])
def test_native_launcher_uses_requested_catalog(language, title, monkeypatch):
    from matb_integration import scenario_builder

    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)
    monkeypatch.setattr(sys, "argv", [str(root / "main.py"), "--language", language])
    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.setattr(builtins, "_", builtins._)
    monkeypatch.setattr(
        scenario_builder, "detect_generator_source_provenance",
        lambda _root: ("a" * 40, False),
    )
    runpy.run_path(str(root / "main.py"), run_name="launcher_locale_test")
    assert builtins._("Communications") == title


@pytest.mark.parametrize("failed", [False, True])
def test_launcher_releases_native_audio_before_interpreter_shutdown(failed, monkeypatch):
    from matb_integration import scenario_builder

    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)
    monkeypatch.setattr(sys, "argv", [str(root / "main.py"), "--scenario", "smoke.txt"])
    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.setattr(builtins, "_", builtins._)
    monkeypatch.setattr(scenario_builder, "detect_generator_source_provenance", lambda _root: ("a" * 40, False))
    namespace = runpy.run_path(str(root / "main.py"), run_name="launcher_cleanup_test")
    launcher = namespace["OpenMATB"]
    scheduler = MagicMock(side_effect=RuntimeError("native test failure") if failed else None)
    release = MagicMock()
    with patch.dict(launcher.__init__.__globals__, {
        "Window": MagicMock(), "Scheduler": scheduler,
        "REPLAY_MODE": False, "_release_audio_driver": release,
    }):
        if failed:
            with pytest.raises(RuntimeError, match="native test failure"):
                launcher()
        else:
            launcher()
    release.assert_called_once_with()
