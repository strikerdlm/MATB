from __future__ import annotations

from pathlib import Path

import pytest

import install_to_openmatb as installer


def _qualified_stub(root: Path) -> None:
    (root / "includes").mkdir(parents=True)
    for relative, marker in installer.REQUIRED_RUNTIME_CAPABILITIES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# test capability\n{marker}\n", encoding="utf-8")


def test_tracked_runtime_satisfies_the_install_capability_contract():
    result = installer.verify_openmatb_runtime(installer.MATB_ROOT / "openmatb")

    assert result["runtime_root"] == str((installer.MATB_ROOT / "openmatb").resolve())
    assert result["communications_profile"]["profile_id"]


def test_asset_install_rejects_an_unqualified_includes_only_directory(tmp_path):
    (tmp_path / "includes").mkdir()

    with pytest.raises(installer.IncompatibleOpenMATBError, match="capability"):
        installer.install(tmp_path)


def test_verifier_qualifies_audio_from_selected_runtime_not_repository(
    tmp_path, monkeypatch
):
    _qualified_stub(tmp_path)
    observed: list[Path] = []
    monkeypatch.setattr(
        installer,
        "verify_communications_audio_profile",
        lambda *, runtime_root: observed.append(runtime_root) or {"profile_id": "test"},
    )

    installer.verify_openmatb_runtime(tmp_path)

    assert observed == [tmp_path.resolve()]
