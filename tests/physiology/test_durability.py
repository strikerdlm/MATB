from __future__ import annotations

from pathlib import Path

from matb_integration.physiology import durability


def test_new_private_directory_fsyncs_its_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    synchronized: list[Path] = []
    monkeypatch.setattr(durability, "fsync_directory", synchronized.append)
    destination = tmp_path / "attempt"

    durability.make_private_directory(destination)

    assert synchronized == [tmp_path]


def test_existing_private_directory_does_not_repeat_parent_sync(
    tmp_path: Path,
    monkeypatch,
) -> None:
    destination = tmp_path / "attempt"
    destination.mkdir()
    synchronized: list[Path] = []
    monkeypatch.setattr(durability, "fsync_directory", synchronized.append)

    durability.make_private_directory(destination)

    assert synchronized == []
