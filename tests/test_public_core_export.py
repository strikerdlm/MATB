from __future__ import annotations

from pathlib import Path

import pytest

from scripts.export_public_core import ROOT, export_candidate, load_manifest, selected_files


def test_public_core_selection_excludes_sensitive_product_trees() -> None:
    manifest = load_manifest()
    files = selected_files(ROOT, manifest)
    names = {path.as_posix() for path in files}
    assert "matb_integration/qualification/contracts.py" in names
    assert "openmatb/LICENSE" in names
    assert not any(name.startswith("SMS/") for name in names)
    assert not any(name.startswith("matb_integration/suas/") for name in names)
    assert not any(name.startswith("matb_integration/liftoff/") for name in names)


def test_publish_export_fails_while_evidence_gates_are_blocked(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="public release is blocked"):
        export_candidate(tmp_path / "public")


def test_candidate_export_has_hashed_inventory(tmp_path: Path) -> None:
    report = export_candidate(tmp_path / "candidate", candidate=True)
    assert report["candidate"] is True
    assert report["publishable"] is False
    assert report["files"]
    assert all(len(item["sha256"]) == 64 for item in report["files"])
    assert (tmp_path / "candidate" / "PUBLIC_CORE_INVENTORY.json").is_file()
